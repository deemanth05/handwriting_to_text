"""Tests for VendorTemplateStore (SQLite Persistence & Active Learning)."""

import json
from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import DocumentRecord, VendorTemplateRecord
from backend.app.schemas.document import DocumentType
from backend.app.services.templates import (
    compute_phash,
    vendor_template_store,
)

SAMPLE_DIR = Path("sample_dataset")


@pytest.mark.asyncio
async def test_store_save_and_exact_gstin_match(db_session: AsyncSession):
    """Saving template allows immediate lookup via exact GSTIN."""
    sample_table = {
        "y_min_ratio": 0.25,
        "y_max_ratio": 0.75,
        "columns": [
            {"col_id": 0, "col_type": "INDEX", "x_start_ratio": 0.05, "x_end_ratio": 0.15},
            {"col_id": 1, "col_type": "DESCRIPTION", "x_start_ratio": 0.16, "x_end_ratio": 0.55},
            {"col_id": 2, "col_type": "QUANTITY", "x_start_ratio": 0.56, "x_end_ratio": 0.68},
            {"col_id": 3, "col_type": "RATE", "x_start_ratio": 0.69, "x_end_ratio": 0.82},
            {"col_id": 4, "col_type": "TOTAL", "x_start_ratio": 0.83, "x_end_ratio": 0.95},
        ],
    }

    phash_sample = "8f4b1e1ee92d9292"
    record = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Shree Ganesh Traders",
        gstin="27AABCS1429B1Z1",
        phash=phash_sample,
        doc_type="INVOICE",
        table_zone=sample_table,
    )

    assert record.id is not None
    assert record.sample_count == 1
    assert record.gstin == "27AABCS1429B1Z1"

    # Lookup by exact GSTIN (even if pHash has slight variation)
    matched, score = await vendor_template_store.find_match(
        session=db_session,
        phash="8f4b1e1ee92d9290",
        gstin="27AABCS1429B1Z1",
        vendor_name="Shree Ganesh",
        doc_type="INVOICE",
    )
    assert matched is not None
    assert matched.id == record.id
    assert score == 1.0


@pytest.mark.asyncio
async def test_store_dual_key_match_without_gstin(db_session: AsyncSession):
    """When GSTIN is absent, match requires Vendor Name Fuzzy >= 85% AND pHash distance <= 8."""
    sample_table = {"y_min_ratio": 0.20, "y_max_ratio": 0.80, "columns": []}
    phash_base = "8f4b1e1ee92d9292"

    record = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Mahalaxmi Electrical Stores",
        gstin=None,
        phash=phash_base,
        doc_type="INVOICE",
        table_zone=sample_table,
    )

    # 1. Matching case: Distance 2 bits, Name 90% fuzzy match
    # Flip 2 bits in phash: '8f4b1e1ee92d9292' -> '8f4b1e1ee92d9290' (dist 1)
    matched, score = await vendor_template_store.find_match(
        session=db_session,
        phash="8f4b1e1ee92d9290",
        gstin=None,
        vendor_name="Mahalaxmi Electrical",
        doc_type="INVOICE",
    )
    assert matched is not None
    assert matched.id == record.id
    assert score >= 0.85

    # 2. Reject case: Name matches but visual structure is completely different (> 8 bits)
    non_matched, score_fail = await vendor_template_store.find_match(
        session=db_session,
        phash="0000000000000000",  # completely different layout
        gstin=None,
        vendor_name="Mahalaxmi Electrical Stores",
        doc_type="INVOICE",
    )
    assert non_matched is None
    assert score_fail == 0.0


@pytest.mark.asyncio
async def test_store_sample_count_increment(db_session: AsyncSession):
    """Saving an already known template increments sample_count."""
    sample_table = {"y_min_ratio": 0.20, "y_max_ratio": 0.80, "columns": []}
    phash_base = "8f4b1e1ee92d9292"

    rec1 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Apex Spares",
        gstin="27AABCA1234A1Z5",
        phash=phash_base,
        doc_type="INVOICE",
        table_zone=sample_table,
    )
    assert rec1.sample_count == 1

    rec2 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Apex Spares Ltd",
        gstin="27AABCA1234A1Z5",
        phash=phash_base,
        doc_type="INVOICE",
        table_zone=sample_table,
    )
    assert rec2.id == rec1.id
    assert rec2.sample_count == 2


@pytest.mark.asyncio
async def test_store_crud_management(db_session: AsyncSession):
    """Test listing, retrieving, and deleting templates."""
    sample_table = {"y_min_ratio": 0.2, "y_max_ratio": 0.8, "columns": []}

    t1 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Vendor Alpha",
        gstin="27AABCA1111A1Z1",
        phash="1111111111111111",
        doc_type="INVOICE",
        table_zone=sample_table,
    )
    t2 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Vendor Beta",
        gstin="27AABCB2222B1Z2",
        phash="2222222222222222",
        doc_type="INVOICE",
        table_zone=sample_table,
    )

    all_tmpls = await vendor_template_store.list_templates(session=db_session)
    assert len(all_tmpls) >= 2
    ids = [t.id for t in all_tmpls]
    assert t1.id in ids
    assert t2.id in ids

    # Get single
    fetched = await vendor_template_store.get_template(session=db_session, template_id=t1.id)
    assert fetched is not None
    assert fetched.vendor_name == "Vendor Alpha"

    # Delete
    deleted = await vendor_template_store.delete_template(session=db_session, template_id=t1.id)
    assert deleted is True

    # Confirm deletion
    after_del = await vendor_template_store.get_template(session=db_session, template_id=t1.id)
    assert after_del is None


@pytest.mark.asyncio
async def test_dual_key_match_high_visual_similarity_loose_name(db_session: AsyncSession):
    """When visual pHash is nearly identical (<=4 bits), name match >= 60% qualifies as Dual-Key match."""
    sample_table = {"y_min_ratio": 0.2, "y_max_ratio": 0.8, "columns": []}
    phash_base = "8f4b1e1ee92d9292"

    rec = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Apex Global Corporation",
        gstin=None,
        phash=phash_base,
        doc_type="INVOICE",
        table_zone=sample_table,
    )

    # Abbreviated name ("Apex Global" vs "Apex Global Corporation" -> token sort ~69%), h_dist = 2
    matched, score = await vendor_template_store.find_match(
        session=db_session,
        phash="8f4b1e1ee92d9290",
        gstin=None,
        vendor_name="Apex Global",
        doc_type="INVOICE",
    )
    assert matched is not None
    assert matched.id == rec.id
    assert score >= 0.85


@pytest.mark.asyncio
async def test_save_or_update_human_name_correction_shorter(db_session: AsyncSession):
    """Human verification correcting a noisy long name to a clean shorter name must be saved."""
    sample_table = {"y_min_ratio": 0.2, "y_max_ratio": 0.8, "columns": []}
    phash_base = "8f4b1e1ee92d9292"

    rec1 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="SHREE GANESH GENERAL STORES PVT LTD DIST ROAD",
        gstin="27AABCS1429B1Z1",
        phash=phash_base,
        doc_type="INVOICE",
        table_zone=sample_table,
    )
    assert "PVT LTD" in rec1.vendor_name

    # Operator corrects name to shorter golden form
    rec2 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="SHREE GANESH GENERAL STORES",
        gstin="27AABCS1429B1Z1",
        phash=phash_base,
        doc_type="INVOICE",
        table_zone=sample_table,
    )
    assert rec2.id == rec1.id
    assert rec2.vendor_name == "SHREE GANESH GENERAL STORES"


@pytest.mark.asyncio
async def test_save_or_update_preserves_valid_columns_on_empty_harvest(db_session: AsyncSession):
    """If a subsequent document harvests 0 columns, it must not destroy existing valid column intervals."""
    valid_table = {
        "y_min_ratio": 0.2,
        "y_max_ratio": 0.8,
        "columns": [{"col_id": 0, "col_type": "QUANTITY", "x_start_ratio": 0.1, "x_end_ratio": 0.3}],
    }
    empty_table = {"y_min_ratio": 0.2, "y_max_ratio": 0.8, "columns": []}

    rec1 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Precision Spares",
        gstin="27AABCP9999P1Z9",
        phash="aaaaaaaaaaaaaaaa",
        doc_type="INVOICE",
        table_zone=valid_table,
    )
    assert len(json.loads(rec1.table_zone_json)["columns"]) == 1

    # Update with empty columns
    rec2 = await vendor_template_store.save_or_update(
        session=db_session,
        vendor_name="Precision Spares",
        gstin="27AABCP9999P1Z9",
        phash="aaaaaaaaaaaaaaaa",
        doc_type="INVOICE",
        table_zone=empty_table,
    )
    assert len(json.loads(rec2.table_zone_json)["columns"]) == 1
