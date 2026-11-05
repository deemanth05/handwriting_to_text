"""Tests for Pydantic v2 Schemas & Deterministic Math Validation."""

from backend.app.schemas.document import (
    DocumentExtractionResponse,
    DocumentType,
    verify_document_math,
    verify_row_math,
)


def test_verify_row_math_valid():
    is_valid, disc = verify_row_math(quantity=2.0, unit_price=45.0, line_total=90.0)
    assert is_valid is True
    assert disc == 0.0


def test_verify_row_math_tolerance():
    # 2.0 * 33.33 = 66.66, extracted total is 66.68 (diff 0.02, within 0.05 tolerance)
    is_valid, disc = verify_row_math(quantity=2.0, unit_price=33.33, line_total=66.68)
    assert is_valid is True
    assert disc <= 0.05


def test_verify_row_math_invalid():
    # Model hallucinated: 2 * 45 = 100
    is_valid, disc = verify_row_math(quantity=2.0, unit_price=45.0, line_total=100.0)
    assert is_valid is False
    assert disc == 10.0


def test_verify_document_math_valid():
    result = verify_document_math(
        subtotal=1350.0,
        tax_amount=67.50,
        discount_amount=17.50,
        grand_total=1400.0,
        line_totals=[480.0, 480.0, 290.0, 100.0],
    )
    assert result.is_valid is True
    assert len(result.error_details) == 0


def test_verify_document_math_mismatch():
    result = verify_document_math(
        subtotal=1350.0,
        tax_amount=67.50,
        discount_amount=17.50,
        grand_total=1500.0,  # Expected: 1400, extracted: 1500
        line_totals=[480.0, 480.0, 290.0, 100.0],
    )
    assert result.is_valid is False
    assert len(result.error_details) > 0
    assert "Computed Grand Total" in result.error_details[0]


def test_document_extraction_response_needs_review_trigger():
    # Response with math error must automatically set status to NEEDS_REVIEW
    invalid_math = verify_document_math(
        subtotal=1000.0,
        tax_amount=0.0,
        discount_amount=0.0,
        grand_total=1200.0,
        line_totals=[1000.0],
    )
    res = DocumentExtractionResponse(
        document_id="test-uuid",
        document_type=DocumentType.INVOICE,
        overall_confidence=0.95,
        math_validation=invalid_math,
        fields={},
        line_items=[],
    )
    assert res.status == "NEEDS_REVIEW"
