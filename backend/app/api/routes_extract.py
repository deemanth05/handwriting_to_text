"""Document Extraction and Retrieval API Endpoints."""

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import ConsensusRecord, DocumentRecord, ModelRunRecord
from backend.app.db.session import get_db
from backend.app.schemas.document import DocumentExtractionResponse, DocumentType
from backend.app.services.ensemble import ensemble_dispatcher
from backend.app.services.multipage import (
    DocumentRasterizer,
    MultiPageStitcher,
    RasterizationError,
)
from backend.app.services.preprocessor import ImageSecurityError, preprocessor
from backend.app.services.reconciler import reconciler

router = APIRouter(tags=["Document Extraction"])


@router.post(
    "/extract",
    response_model=DocumentExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and extract structured data from a messy/handwritten document (Images, Multi-Page PDFs, or Stapled ZIPs)",
)
async def extract_document(
    file: UploadFile = File(..., description="Document file (JPEG, PNG, WEBP, PDF, or ZIP bundle)"),
    doc_type: DocumentType = Form(
        default=DocumentType.INVOICE, description="Document classification type"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Processes document through the multi-page container & consensus pipeline:
    1. Container Ingestion & Rasterization (PDFium rendering or ZIP extraction)
    2. Page-by-page Preprocessing & Security Gate
    3. Multi-Model Consensus Extraction
    4. Cross-page Table Continuation & Ledger Continuity Stitching
    5. Persistence of raw and reconciled records
    """
    doc_id = str(uuid.uuid4())
    raw_bytes = await file.read()
    safe_filename = Path(file.filename or "upload.jpg").name

    # 1. Container Ingestion & Rasterization
    rasterizer = DocumentRasterizer()
    try:
        page_buffers = rasterizer.rasterize(raw_bytes, filename=safe_filename)
    except RasterizationError as re:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(re),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Container rasterization failed: {e!s}",
        )

    # Save original container to storage
    orig_path = settings.UPLOAD_DIR / f"{doc_id}_{safe_filename}"
    orig_path.write_bytes(raw_bytes)

    # Save individual page images for review canvas
    for p in page_buffers:
        page_img_path = settings.UPLOAD_DIR / f"{doc_id}_page_{p.page_number}.jpg"
        page_img_path.write_bytes(p.raw_bytes)

    # 2. Page-by-Page Extraction
    page_responses: list[DocumentExtractionResponse] = []
    all_runs_to_persist = []

    for p in page_buffers:
        try:
            bundle = preprocessor.process(p.raw_bytes)
        except ImageSecurityError as ise:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Page {p.page_number} security error: {ise!s}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Page {p.page_number} preprocessing failed: {e!s}",
            )

        dispatch_result = await ensemble_dispatcher.dispatch(
            image_bytes=bundle.enhanced_rgb_bytes,
            doc_type=doc_type,
        )

        page_doc_id = f"{doc_id}_p{p.page_number}" if len(page_buffers) > 1 else doc_id
        page_consensus = reconciler.reconcile(
            document_id=page_doc_id,
            document_type=doc_type,
            successful_runs=dispatch_result.successful_runs,
            failed_runs=dispatch_result.failed_runs,
            confidence_penalty=dispatch_result.confidence_penalty,
            processing_time_ms=dispatch_result.total_duration_ms,
        )
        page_responses.append(page_consensus)

        all_runs = dispatch_result.successful_runs + dispatch_result.failed_runs
        all_runs_to_persist.extend((doc_id, run) for run in all_runs)

    # 3. Cross-Page Table Continuation & Ledger Stitching
    stitcher = MultiPageStitcher()
    final_response = stitcher.stitch(
        document_id=doc_id,
        document_type=doc_type,
        page_responses=page_responses,
    )

    # 4. Persistence
    detected_mime = rasterizer.detect_container_type(raw_bytes)
    doc_record = DocumentRecord(
        id=doc_id,
        filename=safe_filename,
        content_type=detected_mime,
        document_type=doc_type.value,
        overall_confidence=final_response.overall_confidence,
        math_valid=final_response.math_validation.is_valid,
        page_count=len(page_buffers),
        status=final_response.status,
    )
    db.add(doc_record)

    for d_id, run in all_runs_to_persist:
        model_rec = ModelRunRecord(
            document_id=d_id,
            model_name=run.model_name,
            model_identifier=run.model_identifier,
            raw_response_text=run.raw_text,
            raw_response_json=json.dumps(run.parsed_json) if run.parsed_json else None,
            latency_ms=run.latency_ms,
            status=run.status,
            error_message=run.error,
        )
        db.add(model_rec)

    consensus_rec = ConsensusRecord(
        document_id=doc_id,
        reconciled_json=final_response.model_dump_json(),
        math_validation_json=final_response.math_validation.model_dump_json(),
    )
    db.add(consensus_rec)

    await db.commit()
    return final_response


@router.get(
    "/documents",
    summary="List all processed documents for the review queue",
)
async def list_documents(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve list of documents with processing status and confidence for UI workspace."""
    result = await db.execute(
        select(DocumentRecord)
        .order_by(DocumentRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "document_type": d.document_type,
            "overall_confidence": d.overall_confidence,
            "math_valid": d.math_valid,
            "page_count": d.page_count or 1,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentExtractionResponse,
    summary="Retrieve extracted document by ID",
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve verified or reconciled extraction for a document."""
    result = await db.execute(
        select(ConsensusRecord).where(ConsensusRecord.document_id == document_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    parsed = json.loads(record.reconciled_json)
    return DocumentExtractionResponse(**parsed)


@router.get(
    "/documents/{document_id}/image",
    summary="Stream original or rasterized page image",
)
async def get_document_image(
    document_id: str,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Serve the stored image or specific rasterized page image."""
    result = await db.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invalid page {page}. Page numbers must be >= 1.",
        )

    if doc.page_count and page > doc.page_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page} out of range (document has {doc.page_count} pages).",
        )

    # 1. Try specific rasterized page image
    page_file = settings.UPLOAD_DIR / f"{doc.id}_page_{page}.jpg"
    if page_file.exists():
        return FileResponse(page_file, media_type="image/jpeg")

    # 2. Try original uploaded image file (only if it is a single raster image)
    orig_file = settings.UPLOAD_DIR / f"{doc.id}_{doc.filename}"
    if orig_file.exists() and doc.content_type and doc.content_type.startswith("image/"):
        return FileResponse(orig_file, media_type=doc.content_type)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Stored image file for page {page} missing on disk.",
    )


@router.get(
    "/documents/{document_id}/pages",
    summary="Retrieve multi-page metadata and page count",
)
async def get_document_pages(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve available pages and container metadata for multi-page documents."""
    result = await db.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "page_count": doc.page_count or 1,
        "content_type": doc.content_type,
    }
