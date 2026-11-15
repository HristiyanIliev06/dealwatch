from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Observation:
    title: str | None
    price: Decimal | None
    currency: str | None
    in_stock: bool | None
    url: str


@dataclass(frozen=True)
class DealItem:
    """One listing returned by a discovery source (a deal API or a feed)."""

    item_id: str
    title: str
    url: str
    price: Decimal | None = None
    normal_price: Decimal | None = None
    discount_pct: float | None = None
    currency: str | None = None
    rating: int | None = None  # percent positive, where the source provides it
    rating_count: int | None = None
    store: str | None = None


@dataclass(frozen=True)
class Previous:
    """State recorded before the current check."""

    price: Decimal | None
    in_stock: bool | None
    min_price: Decimal | None


@dataclass(frozen=True)
class Alert:
    key: str
    kind: str
    title: str
    message: str
    url: str | None = None
    priority: int = 3  # ntfy scale: 2 = low (silent), 3 = default, 4 = high
