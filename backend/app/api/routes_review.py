"""HITL (Human-in-the-Loop) Review & Verification Routes."""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import DocumentRecord, GroundTruthRecord
from backend.app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["HITL Review & Verification"])


class VerificationPayload(BaseModel):
    """Payload submitted by a human reviewer in the Split-Screen Review Studio."""

    verified_fields: dict[str, Any] = Field(..., description="Human-corrected scalar fields")
    verified_line_items: list[dict[str, Any]] = Field(
        default_factory=list, description="Human-corrected line items"
    )
    verified_ledger_items: list[dict[str, Any]] = Field(
        default_factory=list, description="Human-corrected ledger items"
    )
    verified_by: str | None = Field(
        default="human-reviewer", description="Identifier of the reviewer"
    )


@router.post(
    "/{document_id}/verify",
    status_code=status.HTTP_200_OK,
    summary="Save human-verified ground truth for a document",
)
async def verify_document(
    document_id: str,
    payload: VerificationPayload,
    db: AsyncSession = Depends(get_db),
):
    """Saves human edits as golden ground truth in ground_truth_records.
    Transitions document status to 'VERIFIED'.
    """
    doc_res = await db.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))
    doc = doc_res.scalars().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )

    # Save or update GroundTruthRecord
    gt_res = await db.execute(
        select(GroundTruthRecord).where(GroundTruthRecord.document_id == document_id)
    )
    gt_record = gt_res.scalars().first()

    ground_truth_data = {
        "fields": payload.verified_fields,
        "line_items": payload.verified_line_items,
        "ledger_items": payload.verified_ledger_items,
    }
    gt_json = json.dumps(ground_truth_data)
    now = datetime.now(UTC)

    if gt_record:
        gt_record.ground_truth_json = gt_json
        gt_record.verified_by = payload.verified_by
        gt_record.verified_at = now
    else:
        gt_record = GroundTruthRecord(
            document_id=document_id,
            ground_truth_json=gt_json,
            verified_by=payload.verified_by,
            verified_at=now,
        )
        db.add(gt_record)

    doc.status = "VERIFIED"
    await db.commit()

    return {
        "document_id": document_id,
        "status": "VERIFIED",
        "verified_at": now.isoformat(),
        "verified_by": payload.verified_by,
        "message": "Human verification recorded as ground truth.",
    }
