"""Tests for Indic Numeral and Script Normalization."""

from backend.app.services.normalizer import (
    clean_currency_and_numbers,
    normalize_indic_numerals,
    normalize_text_field,
    parse_date_safely,
    parse_float_safely,
)


def test_devanagari_numerals_conversion():
    # '०१२३४५६७८९' -> '0123456789'
    input_text = "खाते क्रमांक: १२४५, रक्कम: ₹५००.५०"
    converted = normalize_indic_numerals(input_text)
    assert "1245" in converted
    assert "500.50" in converted


def test_kannada_numerals_conversion():
    # '೦೧೨೩೪೫೬೭೮೯' -> '0123456789'
    input_text = "ಮೊತ್ತ: ೧೪೫೦.೦೦"
    converted = normalize_indic_numerals(input_text)
    assert "1450.00" in converted


def test_currency_symbol_stripping():
    assert clean_currency_and_numbers("₹ 1,450.00") == "1450.00"
    assert clean_currency_and_numbers("Rs. 500/-") == "500"
    assert clean_currency_and_numbers("INR 12,345.67") == "12345.67"
    assert clean_currency_and_numbers("₹५,४००.००") == "5400.00"


def test_parse_float_safely():
    assert parse_float_safely("₹ 1,250.75") == 1250.75
    assert parse_float_safely("Rs 450/-") == 450.00
    assert parse_float_safely("४५.५०") == 45.50
    assert parse_float_safely(100) == 100.0
    assert parse_float_safely(None) is None
    assert parse_float_safely("invalid-text") is None


def test_parse_date_safely():
    assert parse_date_safely("31/10/2026") == "2026-10-31"
    assert parse_date_safely("2026-10-31") == "2026-10-31"
    assert parse_date_safely("28-10-2026") == "2026-10-28"
    assert parse_date_safely("२५-१०-२०२६") == "2026-10-25"
    assert parse_date_safely(None) is None
    assert parse_date_safely("not-a-date") is None


def test_normalize_text_field():
    assert normalize_text_field("  Shree   Ganesh   Stores  ") == "Shree Ganesh Stores"
    assert normalize_text_field(None) == ""
