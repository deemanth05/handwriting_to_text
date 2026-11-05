"""Regional Script & Numeral Normalizer.

Standardizes Indian regional numerals (Devanagari, Kannada), currency symbols,
and diverse date formats before consensus matching.
"""

import re

from dateutil import parser as date_parser

# Regional numeral translation tables
DEVANAGARI_DIGITS = "०१२३४५६७८९"
KANNADA_DIGITS = "೦೧೨೩೪೫೬೭೮೯"
ASCII_DIGITS = "0123456789"

_INDIC_TRANSLATION_TABLE = str.maketrans(
    DEVANAGARI_DIGITS + KANNADA_DIGITS, ASCII_DIGITS + ASCII_DIGITS
)

CURRENCY_PATTERN = re.compile(r"[₹\$\€\£]|rs\.?|inr|/-", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_indic_numerals(text: str) -> str:
    """Translate Devanagari and Kannada numerals to standard ASCII numerals."""
    if not text:
        return ""
    return str(text).translate(_INDIC_TRANSLATION_TABLE)


def clean_currency_and_numbers(text: str) -> str:
    """Strip currency symbols, commas, and trailing slashes."""
    if not text:
        return ""
    cleaned = normalize_indic_numerals(str(text))
    cleaned = CURRENCY_PATTERN.sub("", cleaned)
    cleaned = cleaned.replace(",", "").strip()
    return cleaned


def parse_float_safely(val: any) -> float | None:
    """Parse float from string or number with Indic numeral and currency tolerance."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return round(float(val), 2)
    cleaned = clean_currency_and_numbers(str(val))
    # Extract first valid floating point pattern
    match = re.search(r"[-+]?\d*\.?\d+", cleaned)
    if match:
        try:
            return round(float(match.group()), 2)
        except ValueError:
            return None
    return None


def parse_date_safely(date_str: any) -> str | None:
    """Parse various date formats into standardized ISO YYYY-MM-DD format."""
    if not date_str:
        return None
    cleaned = normalize_indic_numerals(str(date_str)).strip()
    try:
        # Common dayfirst formats in India: DD/MM/YYYY, DD-MM-YYYY
        dt = date_parser.parse(cleaned, dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        # Fallback to regex if date_parser fails
        match = re.search(r"(\d{1,4})[./\-](\d{1,2})[./\-](\d{1,4})", cleaned)
        if match:
            parts = [int(p) for p in match.groups()]
            if parts[0] > 1000:  # YYYY-MM-DD
                return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
            elif parts[2] > 1000:  # DD-MM-YYYY
                return f"{parts[2]:04d}-{parts[1]:02d}-{parts[0]:02d}"
    return None


def normalize_text_field(text: any) -> str:
    """Normalize general text by trimming, translating numerals, and collapsing whitespace."""
    if text is None:
        return ""
    normalized = normalize_indic_numerals(str(text))
    normalized = WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized
