"""API Routes for Vendor Template Memory Cache Management."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db
from backend.app.services.templates import vendor_template_store

router = APIRouter(prefix="/templates", tags=["Vendor Template Memory"])


def format_iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


class VendorTemplateSummary(BaseModel):
    id: str
    vendor_key: str
    vendor_name: str
    gstin: str | None = None
    phash: str
    document_type: str
    sample_count: int
    created_at: str | None = None
    updated_at: str | None = None


class VendorTemplateDetail(BaseModel):
    id: str
    vendor_key: str
    vendor_name: str
    gstin: str | None = None
    phash: str
    document_type: str
    sample_count: int
    table_zone: dict[str, Any] = Field(default_factory=dict)
    header_zone: dict[str, Any] | None = None
    summary_zone: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


@router.get(
    "",
    response_model=list[VendorTemplateSummary],
    summary="List all cached vendor spatial templates",
)
async def list_templates(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all cached vendor layout templates ordered by sample count and update time."""
    records = await vendor_template_store.list_templates(
        session=db,
        limit=limit,
        offset=offset,
    )
    return [
        VendorTemplateSummary(
            id=r.id,
            vendor_key=r.vendor_key,
            vendor_name=r.vendor_name,
            gstin=r.gstin,
            phash=r.phash,
            document_type=r.document_type,
            sample_count=r.sample_count,
            created_at=format_iso(r.created_at),
            updated_at=format_iso(r.updated_at),
        )
        for r in records
    ]


@router.get(
    "/{template_id}",
    response_model=VendorTemplateDetail,
    summary="Retrieve details and geometry for a specific vendor template",
)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve complete spatial bounding boxes and column intervals for a vendor template."""
    record = await vendor_template_store.get_template(session=db, template_id=template_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor template with ID '{template_id}' not found.",
        )

    table_data = json.loads(record.table_zone_json) if record.table_zone_json else {}
    header_data = json.loads(record.header_zone_json) if record.header_zone_json else None
    summary_data = json.loads(record.summary_zone_json) if record.summary_zone_json else None

    return VendorTemplateDetail(
        id=record.id,
        vendor_key=record.vendor_key,
        vendor_name=record.vendor_name,
        gstin=record.gstin,
        phash=record.phash,
        document_type=record.document_type,
        sample_count=record.sample_count,
        table_zone=table_data,
        header_zone=header_data,
        summary_zone=summary_data,
        created_at=format_iso(record.created_at),
        updated_at=format_iso(record.updated_at),
    )


@router.delete(
    "/{template_id}",
    summary="Delete a vendor template from memory cache",
)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Purge an obsolete or modified vendor template from persistent memory."""
    deleted = await vendor_template_store.delete_template(session=db, template_id=template_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor template with ID '{template_id}' not found.",
        )

    return {
        "message": "Template deleted successfully",
        "id": template_id,
    }
