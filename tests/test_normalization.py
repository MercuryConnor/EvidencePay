"""Unit tests for number, date, and currency normalization."""

import pytest
from src.normalization.currency import normalize_currency
from src.normalization.dates import normalize_date, parse_date_safe
from src.normalization.numbers import parse_decimal, parse_number


class TestNumberNormalization:
    """Test suite for decimal and number normalization."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1.234,56", "1234.56"),
            ("1,234.56", "1234.56"),
            ("1 234,56", "1234.56"),
            ("1 234.56", "1234.56"),
            ("100", "100"),
            ("0", "0"),
            ("", ""),
            ("19%", "19"),
            ("-1.234,56", "-1234.56"),
            ("(500.25)", "-500.25"),
            ("€ 1,500.00", "1500.00"),
            ("$ 45.99", "45.99"),
        ],
    )
    def test_parse_number(self, raw, expected):
        assert parse_number(raw) == expected


class TestDateNormalization:
    """Test suite for date normalization."""

    @pytest.mark.parametrize(
        "raw,expected,is_ambig",
        [
            ("2026-03-15", "2026-03-15", False),
            ("15/03/2026", "2026-03-15", False),
            ("15.03.2026", "2026-03-15", False),
            ("15-03-2026", "2026-03-15", False),
            ("15 Mar 2026", "2026-03-15", False),
            ("March 15, 2026", "2026-03-15", False),
            ("15. März 2026", "2026-03-15", False),
            ("05/06/2026", "2026-06-05", True),  # ambiguous defaults to DD/MM/YYYY
        ],
    )
    def test_normalize_date(self, raw, expected, is_ambig):
        norm, ambig = normalize_date(raw)
        assert norm == expected
        assert ambig == is_ambig


class TestCurrencyNormalization:
    """Test suite for currency code normalization."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("€", "EUR"),
            ("EUR", "EUR"),
            ("Euro", "EUR"),
            ("$", "USD"),
            ("USD", "USD"),
            ("£", "GBP"),
            ("GBP", "GBP"),
            ("¥", "JPY"),
            ("₹", "INR"),
            ("CHF", "CHF"),
        ],
    )
    def test_normalize_currency(self, raw, expected):
        assert normalize_currency(raw) == expected
