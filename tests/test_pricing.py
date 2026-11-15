from decimal import Decimal

import pytest

from dealwatch.pricing import parse_price


@pytest.mark.parametrize(
    "text, price, currency",
    [
        ("1 299,00 лв.", Decimal("1299.00"), "BGN"),
        ("$1,299.00", Decimal("1299.00"), "USD"),
        ("1.299,00 €", Decimal("1299.00"), "EUR"),
        ("€19.99", Decimal("19.99"), "EUR"),
        ("12,5 EUR", Decimal("12.5"), "EUR"),
        ("1,299", Decimal("1299"), None),
        ("0,999", Decimal("0.999"), None),
        ("£1,234,567.89", Decimal("1234567.89"), "GBP"),
    ],
)
def test_parse_price(text, price, currency):
    assert parse_price(text) == (price, currency)


def test_parse_price_without_number():
    assert parse_price("Out of stock") == (None, None)
