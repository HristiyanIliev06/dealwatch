from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from ..config import DiscoverSource
from ..models import DealItem
from . import SourceError, TextFetcher

API = "https://www.cheapshark.com/api/1.0/deals"
REDIRECT = "https://www.cheapshark.com/redirect?dealID="
STORES = {1: "Steam", 2: "GamersGate", 3: "GreenManGaming", 7: "GOG", 11: "Humble Store"}


def fetch(source: DiscoverSource, fetcher: TextFetcher) -> list[DealItem]:
    params = {
        "storeID": ",".join(str(store) for store in source.stores),
        "pageSize": source.page_size,
        "sortBy": "recent",
    }
    if source.filters.max_price is not None:
        params["upperPrice"] = source.filters.max_price
    try:
        # CheapShark's robots.txt disallows /api/1.0/ for crawlers, yet its docs offer the API
        # for free programmatic use (no key; heavy polling gets a 429). One request per run.
        payload = json.loads(fetcher.get(f"{API}?{urlencode(params)}", check_robots=False))
    except json.JSONDecodeError as exc:
        raise SourceError(f"CheapShark returned invalid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise SourceError(f"unexpected CheapShark response: {str(payload)[:100]}")
    return [item for deal in payload if (item := _parse(deal)) is not None]


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except ValueError:
        return None


def _parse(deal: dict) -> DealItem | None:
    try:
        store_id = int(deal["storeID"])
        # gameID + storeID is stable across price changes; dealID is not.
        item_id = f"{store_id}:{deal['gameID']}"
        title, deal_id = deal["title"], deal["dealID"]
    except (KeyError, ValueError, TypeError):
        return None
    rating = _int(deal.get("steamRatingPercent"))
    rating_count = _int(deal.get("steamRatingCount"))
    savings = _decimal(deal.get("savings"))
    return DealItem(
        item_id=item_id,
        title=title,
        url=REDIRECT + deal_id,  # dealID arrives already URL-encoded
        price=_decimal(deal.get("salePrice")),
        normal_price=_decimal(deal.get("normalPrice")),
        discount_pct=None if savings is None else float(savings),
        currency="USD",
        rating=rating or None,  # 0 means "no reviews", not "0% positive"
        rating_count=rating_count or None,
        store=STORES.get(store_id, f"store {store_id}"),
    )
