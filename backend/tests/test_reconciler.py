"""Tests for Consensus Reconciler, Hungarian Alignment, and Confidence Scoring."""

from backend.app.schemas.document import DocumentType
from backend.app.services.models.base import RawModelOutput
from backend.app.services.reconciler import reconciler


def test_scalar_field_3_of_3_agreement():
    runs = [
        RawModelOutput(
            model_name="gemini_vlm",
            model_identifier="gemini-2.0",
            raw_text="",
            parsed_json={"vendor_name": "Shree Ganesh General Stores", "grand_total": 1400.0},
        ),
        RawModelOutput(
            model_name="qwen_vl",
            model_identifier="qwen-2.5",
            raw_text="",
            parsed_json={"vendor_name": "Shree Ganesh General Stores", "grand_total": 1400.0},
        ),
        RawModelOutput(
            model_name="hybrid_ocr",
            model_identifier="hybrid-struct",
            raw_text="",
            parsed_json={"vendor_name": "Shree Ganesh Gen Stores", "grand_total": 1400.0},
        ),
    ]

    res = reconciler.reconcile("doc-1", DocumentType.INVOICE, runs)
    vendor = res.fields["vendor_name"]
    assert vendor.agreement == "3/3"
    assert vendor.confidence == 0.98
    assert vendor.needs_review is False

    total = res.fields["grand_total"]
    assert total.agreement == "3/3"
    assert total.value == 1400.0


def test_scalar_field_2_of_3_majority_vote():
    runs = [
        RawModelOutput(
            model_name="gemini_vlm",
            model_identifier="gemini-2.0",
            raw_text="",
            parsed_json={"invoice_number": "INV-2026-089"},
        ),
        RawModelOutput(
            model_name="qwen_vl",
            model_identifier="qwen-2.5",
            raw_text="",
            parsed_json={"invoice_number": "INV-2026-089"},
        ),
        RawModelOutput(
            model_name="hybrid_ocr",
            model_identifier="hybrid-struct",
            raw_text="",
            parsed_json={"invoice_number": "INV-2026-000"},  # Dissenter
        ),
    ]

    res = reconciler.reconcile("doc-2", DocumentType.INVOICE, runs)
    inv = res.fields["invoice_number"]
    assert inv.value == "INV-2026-089"
    assert inv.agreement == "2/3"
    assert inv.confidence == 0.82


def test_scalar_field_total_disagreement():
    runs = [
        RawModelOutput(
            model_name="gemini_vlm",
            model_identifier="gemini-2.0",
            raw_text="",
            parsed_json={"customer_name": "Alpha Corp"},
        ),
        RawModelOutput(
            model_name="qwen_vl",
            model_identifier="qwen-2.5",
            raw_text="",
            parsed_json={"customer_name": "Beta Industries"},
        ),
        RawModelOutput(
            model_name="hybrid_ocr",
            model_identifier="hybrid-struct",
            raw_text="",
            parsed_json={"customer_name": "Gamma Ltd"},
        ),
    ]

    res = reconciler.reconcile("doc-3", DocumentType.INVOICE, runs)
    cust = res.fields["customer_name"]
    assert cust.confidence == 0.20
    assert cust.needs_review is True


def test_line_item_bipartite_matching():
    # Test alignment even when rows are ordered differently across models
    runs = [
        RawModelOutput(
            model_name="gemini_vlm",
            model_identifier="gemini-2.0",
            raw_text="",
            parsed_json={
                "line_items": [
                    {
                        "description": "Atta 5kg",
                        "quantity": 2.0,
                        "unit_price": 240.0,
                        "line_total": 480.0,
                    },
                    {
                        "description": "Toor Dal 1kg",
                        "quantity": 3.0,
                        "unit_price": 160.0,
                        "line_total": 480.0,
                    },
                ]
            },
        ),
        RawModelOutput(
            model_name="qwen_vl",
            model_identifier="qwen-2.5",
            raw_text="",
            parsed_json={
                "line_items": [
                    # Scrambled order
                    {
                        "description": "Toor Dal 1kg",
                        "quantity": 3.0,
                        "unit_price": 160.0,
                        "line_total": 480.0,
                    },
                    {
                        "description": "Atta 5kg Premium",
                        "quantity": 2.0,
                        "unit_price": 240.0,
                        "line_total": 480.0,
                    },
                ]
            },
        ),
    ]

    res = reconciler.reconcile("doc-4", DocumentType.INVOICE, runs)
    assert len(res.line_items) == 2
    row1 = res.line_items[0]
    assert "Atta" in row1.description.value
    assert row1.quantity.value == 2.0
    assert row1.unit_price.value == 240.0
    assert row1.line_total.value == 480.0
    assert row1.row_math_valid is True
