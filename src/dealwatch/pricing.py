from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(r"\d(?:[\d\s  .,]*\d)?")
_SPACES = re.compile(r"[\s  ]")
_CURRENCIES = (
    ("лв", "BGN"),
    ("bgn", "BGN"),
    ("€", "EUR"),
    ("eur", "EUR"),
    ("$", "USD"),
    ("usd", "USD"),
    ("£", "GBP"),
    ("gbp", "GBP"),
)


def format_money(price: Decimal | None, currency: str | None) -> str:
    return "n/a" if price is None else f"{price} {currency or ''}".strip()


def parse_price(text: str) -> tuple[Decimal | None, str | None]:
    """Extract (price, currency) from display text such as '1 299,00 лв.' or '$1,299.00'."""
    match = _NUMBER.search(text)
    if not match:
        return None, None
    price = _to_decimal(_SPACES.sub("", match.group()))
    lowered = text.lower()
    currency = next((code for marker, code in _CURRENCIES if marker in lowered), None)
    return price, currency


def _to_decimal(raw: str) -> Decimal | None:
    commas, dots = raw.count(","), raw.count(".")
    if commas and dots:
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
    elif commas or dots:
        sep = "," if commas else "."
        head, _, tail = raw.rpartition(sep)
        repeated = raw.count(sep) > 1
        # "1,299" is thousands; "0,999" and "12,5" are decimals.
        thousands = repeated or (len(tail) == 3 and head not in ("", "0"))
        decimal_sep = None if thousands else sep
    else:
        decimal_sep = None

    if decimal_sep:
        integer, _, fraction = raw.rpartition(decimal_sep)
        normalized = re.sub(r"[.,]", "", integer) + "." + fraction
    else:
        normalized = re.sub(r"[.,]", "", raw)
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None
