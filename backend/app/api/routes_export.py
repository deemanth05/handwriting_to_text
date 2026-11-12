"""Enterprise Accounting & Compliance Export Routes.

Provides streaming exports for:
1. Tally Prime XML (Purchase / Payment / Receipt Vouchers)
2. Reconciled Financial Excel (.xlsx) with Math Audit & Confidence Highlighting
3. Indian GST E-Invoice JSON (v1.1) for B2B e-invoicing compliance
"""

import json
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ConsensusRecord, DocumentRecord, GroundTruthRecord
from backend.app.db.session import get_db
from backend.app.services.exporters import (
    ExcelReconciliationExporter,
    GSTInvoiceExporter,
    TallyPrimeExporter,
)

router = APIRouter(prefix="/documents", tags=["Accounting & Compliance Exports"])


def _sanitize_filename(name: str) -> str:
    """Sanitize original document filename for safe Content-Disposition headers."""
    base = os.path.splitext(name)[0]
    sanitized = re.sub(r"[^\w\-.]", "_", base).strip("_")
    return sanitized or "document"


async def _resolve_document_data(
    document_id: str, db: AsyncSession
) -> tuple[DocumentRecord, dict[str, Any]]:
    """Fetch document and synthesize the most authoritative data (Ground Truth > Consensus)."""
    # 1. Fetch document record
    doc_res = await db.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))
    doc = doc_res.scalars().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    # 2. Fetch consensus and ground truth records
    cons_res = await db.execute(
        select(ConsensusRecord).where(ConsensusRecord.document_id == document_id)
    )
    consensus_rec = cons_res.scalars().first()

    gt_res = await db.execute(
        select(GroundTruthRecord).where(GroundTruthRecord.document_id == document_id)
    )
    gt_rec = gt_res.scalars().first()

    if not consensus_rec and not gt_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No extraction or consensus data found for document {document_id}.",
        )

    # 3. Base doc_data
    doc_data: dict[str, Any] = {
        "document_id": doc.id,
        "document_type": doc.document_type,
        "overall_confidence": doc.overall_confidence,
        "math_valid": doc.math_valid,
        "status": doc.status,
        "fields": {},
        "line_items": [],
        "ledger_items": [],
        "math_validation": {
            "is_valid": doc.math_valid,
            "discrepancy_amount": 0.0,
            "error_details": [],
        },
        "models_participated": [],
    }

    if consensus_rec:
        try:
            reconciled = json.loads(consensus_rec.reconciled_json)
            doc_data.update(reconciled)
        except Exception:
            pass

        if consensus_rec.math_validation_json:
            try:
                doc_data["math_validation"] = json.loads(consensus_rec.math_validation_json)
            except Exception:
                pass

    # 4. Human-verified ground truth overrides consensus if present
    if gt_rec and gt_rec.ground_truth_json:
        try:
            gt_dict = json.loads(gt_rec.ground_truth_json)
            if "fields" in gt_dict and isinstance(gt_dict["fields"], dict):
                # Normalize verified fields
                for k, v in gt_dict["fields"].items():
                    if isinstance(v, dict):
                        doc_data["fields"][k] = v
                    else:
                        doc_data["fields"][k] = {"value": v, "confidence": 1.0, "sources": ["HUMAN"]}

            if "line_items" in gt_dict and gt_dict["line_items"]:
                doc_data["line_items"] = gt_dict["line_items"]

            if "ledger_items" in gt_dict and gt_dict["ledger_items"]:
                doc_data["ledger_items"] = gt_dict["ledger_items"]

            doc_data["status"] = "VERIFIED"
            doc_data["math_valid"] = True
            if isinstance(doc_data.get("math_validation"), dict):
                doc_data["math_validation"]["is_valid"] = True
                doc_data["math_validation"]["discrepancy_amount"] = 0.0
                doc_data["math_validation"]["error_details"] = []
        except Exception:
            pass

    return doc, doc_data


@router.get(
    "/{document_id}/export/tally",
    summary="Export document extraction to Tally Prime XML",
    response_description="Tally Prime importable XML voucher payload",
)
async def export_tally(
    document_id: str,
    purchase_ledger: str = "Purchase Account",
    cgst_ledger: str = "Input CGST",
    sgst_ledger: str = "Input SGST",
    igst_ledger: str = "Input IGST",
    cash_ledger: str = "Petty Cash",
    db: AsyncSession = Depends(get_db),
):
    """Generates balanced double-entry Tally Prime XML vouchers for automated ERP import."""
    doc, doc_data = await _resolve_document_data(document_id, db)

    exporter = TallyPrimeExporter(
        purchase_ledger=purchase_ledger,
        cgst_ledger=cgst_ledger,
        sgst_ledger=sgst_ledger,
        igst_ledger=igst_ledger,
        cash_ledger=cash_ledger,
    )
    xml_content = exporter.export(doc_data)

    filename = f"{_sanitize_filename(doc.filename)}_tally.xml"
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/{document_id}/export/excel",
    summary="Export document extraction to multi-sheet Reconciled Excel (.xlsx)",
    response_description="Multi-sheet Excel workbook with audit summary and confidence styles",
)
async def export_excel(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generates an executive-ready multi-sheet corporate financial workbook (.xlsx)."""
    doc, doc_data = await _resolve_document_data(document_id, db)

    exporter = ExcelReconciliationExporter()
    xlsx_bytes = exporter.export(doc_data)

    filename = f"{_sanitize_filename(doc.filename)}_reconciled.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/{document_id}/export/gst",
    summary="Export document extraction to Indian GST E-Invoice JSON (v1.1)",
    response_description="NIC / GST Suvidha Provider compliant e-invoice JSON",
)
async def export_gst(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generates standard Indian GST E-Invoice schema version 1.1 JSON."""
    doc, doc_data = await _resolve_document_data(document_id, db)

    exporter = GSTInvoiceExporter()
    gst_json_obj = exporter.export(doc_data)
    json_bytes = json.dumps(gst_json_obj, indent=2).encode("utf-8")

    filename = f"{_sanitize_filename(doc.filename)}_gst_einvoice.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
