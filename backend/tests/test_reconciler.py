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


def test_digit_confusion_repair():
    runs = [
        RawModelOutput(
            model_name="gemini_vlm",
            model_identifier="gemini-2.0",
            raw_text="",
            parsed_json={
                "line_items": [
                    {
                        "description": "Premium Notebooks",
                        "quantity": 5.0,
                        "unit_price": 18.0,  # 8 is confused with 3
                        "line_total": 65.0,
                    }
                ]
            },
        )
    ]
    res = reconciler.reconcile("doc-conf", DocumentType.INVOICE, runs)
    assert len(res.line_items) == 1
    item = res.line_items[0]
    # Unit price 18.0 should be auto-repaired to 13.0 (5 * 13 == 65)
    assert item.unit_price.value == 13.0
    assert item.quantity.value == 5.0
    assert item.line_total.value == 65.0
    assert item.row_math_valid is True


def test_ledger_balance_solver():
    runs = [
        RawModelOutput(
            model_name="rapidocr_local",
            model_identifier="rapidocr-onnx",
            raw_text="",
            parsed_json={
                "book_title": "Petty Cash Book",
                "ledger_items": [
                    {
                        "entry_date": "01/02",
                        "particulars": "Opening Balance",
                        "cash_out_debit": 0.0,
                        "cash_in_credit": 200.0,
                        "running_balance": 200.0,
                    },
                    {
                        "entry_date": "05/02",
                        "particulars": "Stamps",
                        "cash_out_debit": 4.30,  # 3 was confused with 8 (actual is 4.80)
                        "cash_in_credit": 0.0,
                        "running_balance": 195.20,
                    },
                    {
                        "entry_date": "07/02",
                        "particulars": "Milk & tea",
                        "cash_out_debit": 0.0,  # smudged / missing out debit
                        "cash_in_credit": 0.0,
                        "running_balance": 189.05,
                    },
                ],
            },
        )
    ]
    res = reconciler.reconcile("doc-ledger", DocumentType.CASH_BOOK, runs)
    assert len(res.ledger_items) == 3
    # Row 2: 4.30 auto-repaired to 4.80
    assert res.ledger_items[1].cash_out_debit.value == 4.80
    assert res.ledger_items[1].balance_math_valid is True
    # Row 3: smudged out debit recovered: 195.20 - 189.05 = 6.15
    assert res.ledger_items[2].cash_out_debit.value == 6.15
    assert res.ledger_items[2].balance_math_valid is True
    assert res.math_validation.is_valid is True


def test_kuhn_munkres_alignment():
    runs = [
        RawModelOutput(
            model_name="model_a",
            model_identifier="m-a",
            raw_text="",
            parsed_json={
                "line_items": [
                    {"description": "Item Alpha", "quantity": 1.0, "unit_price": 10.0, "line_total": 10.0},
                    {"description": "Item Beta", "quantity": 2.0, "unit_price": 20.0, "line_total": 40.0},
                    {"description": "Item Gamma", "quantity": 3.0, "unit_price": 30.0, "line_total": 90.0},
                ]
            },
        ),
        RawModelOutput(
            model_name="model_b",
            model_identifier="m-b",
            raw_text="",
            parsed_json={
                "line_items": [
                    {"description": "Item Gamma Extra", "quantity": 3.0, "unit_price": 30.0, "line_total": 90.0},
                    {"description": "Item Alpha Prime", "quantity": 1.0, "unit_price": 10.0, "line_total": 10.0},
                    {"description": "Item Beta Plus", "quantity": 2.0, "unit_price": 20.0, "line_total": 40.0},
                ]
            },
        ),
    ]
    res = reconciler.reconcile("doc-km", DocumentType.INVOICE, runs)
    assert len(res.line_items) == 3
    b_matched_descs = [item.description.candidates.get("model_b") for item in res.line_items]
    assert len(b_matched_descs) == len(set(b_matched_descs)), "No duplicate candidate assignments"


def test_ledger_smudged_balance_recovery():
    """Verify smudged balance is recovered when out/in amount is known."""
    runs = [
        RawModelOutput(
            model_name="rapidocr_local",
            model_identifier="rapidocr-onnx",
            raw_text="",
            parsed_json={
                "ledger_items": [
                    {"entry_date": "01/02", "particulars": "Opening Balance", "cash_out_debit": 0.0, "cash_in_credit": 200.0, "running_balance": 200.0},
                    {"entry_date": "05/02", "particulars": "Courier charges", "cash_out_debit": 18.75, "cash_in_credit": 0.0, "running_balance": 0.0}, # smudged balance
                ]
            },
        )
    ]
    res = reconciler.reconcile("doc-smudge-bal", DocumentType.CASH_BOOK, runs)
    assert len(res.ledger_items) == 2
    assert res.ledger_items[1].running_balance.value == 181.25
    assert res.ledger_items[1].balance_math_valid is True


def test_ledger_zero_row_not_repaired():
    """Verify that an unextracted row with 0 out, 0 in, 0 bal does NOT invent a fake out debit."""
    from backend.app.services.reconciler import repair_ledger_balance_row
    o, i, b, was_repaired = repair_ledger_balance_row(prev_balance=200.0, out_val=0.0, in_val=0.0, bal_val=0.0)
    assert was_repaired is False
    assert o == 0.0


def test_cash_book_period_scalar_field():
    """Verify period string (e.g. Month: FEB 2025) is preserved as text and not wiped by date parser."""
    runs = [
        RawModelOutput(
            model_name="rapidocr_local",
            model_identifier="rapidocr-onnx",
            raw_text="",
            parsed_json={
                "book_title": "Petty Cash Book",
                "period": "Month: FEB 2025",
                "page_no": "1",
            },
        )
    ]
    res = reconciler.reconcile("doc-period", DocumentType.CASH_BOOK, runs)
    assert res.fields["period"].value == "Month: FEB 2025"
    assert res.fields["period"].confidence > 0.0

