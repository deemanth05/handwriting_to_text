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
from backend.app.services.preprocessor import ImageSecurityError, preprocessor
from backend.app.services.reconciler import reconciler

router = APIRouter(tags=["Document Extraction"])


@router.post(
    "/extract",
    response_model=DocumentExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and extract structured data from a messy/handwritten document",
)
async def extract_document(
    file: UploadFile = File(..., description="Document image file (JPEG, PNG, WEBP)"),
    doc_type: DocumentType = Form(
        default=DocumentType.INVOICE, description="Document classification type"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Processes document through the 5-stage consensus engine:
    1. Preprocessing (deskew, CLAHE shadow removal, thresholding)
    2. Concurrent multi-model dispatching (Model A, Model B, Model C)
    3. Consensus reconciliation (Hungarian algorithm + RapidFuzz)
    4. Deterministic math validation
    5. Persistence of raw and reconciled records
    """
    doc_id = str(uuid.uuid4())
    raw_bytes = await file.read()

    # 1. Preprocessing & Security Gate
    try:
        bundle = preprocessor.process(raw_bytes)
    except ImageSecurityError as ise:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ise),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preprocessing failed: {e!s}",
        )

    # Save original image to storage
    safe_filename = Path(file.filename or "upload.jpg").name
    saved_path = settings.UPLOAD_DIR / f"{doc_id}_{safe_filename}"
    saved_path.write_bytes(bundle.original_bytes)

    # 2. Asynchronous Multi-Model Vision Dispatcher
    dispatch_result = await ensemble_dispatcher.dispatch(
        image_bytes=bundle.enhanced_rgb_bytes,
        doc_type=doc_type,
    )

    # 3. Consensus Reconciliation & Math Validation
    consensus_response = reconciler.reconcile(
        document_id=doc_id,
        document_type=doc_type,
        successful_runs=dispatch_result.successful_runs,
        failed_runs=dispatch_result.failed_runs,
        confidence_penalty=dispatch_result.confidence_penalty,
        processing_time_ms=dispatch_result.total_duration_ms,
    )

    # 4. Persistence: Document record, raw model outputs, consensus output
    doc_record = DocumentRecord(
        id=doc_id,
        filename=safe_filename,
        content_type=file.content_type or "image/jpeg",
        document_type=doc_type.value,
        overall_confidence=consensus_response.overall_confidence,
        math_valid=consensus_response.math_validation.is_valid,
        status=consensus_response.status,
    )
    db.add(doc_record)

    # Save all raw model outputs verbatim for leaderboard & evaluation
    all_runs = dispatch_result.successful_runs + dispatch_result.failed_runs
    for run in all_runs:
        model_rec = ModelRunRecord(
            document_id=doc_id,
            model_name=run.model_name,
            model_identifier=run.model_identifier,
            raw_response_text=run.raw_text,
            raw_response_json=json.dumps(run.parsed_json) if run.parsed_json else None,
            latency_ms=run.latency_ms,
            status=run.status,
            error_message=run.error,
        )
        db.add(model_rec)

    # Save consensus record
    consensus_rec = ConsensusRecord(
        document_id=doc_id,
        reconciled_json=consensus_response.model_dump_json(),
        math_validation_json=consensus_response.math_validation.model_dump_json(),
    )
    db.add(consensus_rec)

    await db.commit()
    return consensus_response


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
    summary="Stream original document image",
)
async def get_document_image(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve the stored image file."""
    result = await db.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    expected_file = settings.UPLOAD_DIR / f"{doc.id}_{doc.filename}"
    if not expected_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored image file missing on disk.",
        )

    return FileResponse(expected_file, media_type=doc.content_type)
