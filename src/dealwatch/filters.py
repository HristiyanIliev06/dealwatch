from __future__ import annotations

from .config import Filters
from .models import DealItem


def matches(item: DealItem, filters: Filters) -> bool:
    """True when the item satisfies every filter that is set.

    A filter on a field the source does not provide (say a rating on an RSS entry) fails,
    so a loose feed cannot slip past a strict filter.
    """
    if filters.max_price is not None and (item.price is None or item.price > filters.max_price):
        return False
    if filters.min_discount_pct is not None and (
        item.discount_pct is None or item.discount_pct < filters.min_discount_pct
    ):
        return False
    if filters.min_rating is not None and (item.rating is None or item.rating < filters.min_rating):
        return False
    if filters.min_rating_count is not None and (
        item.rating_count is None or item.rating_count < filters.min_rating_count
    ):
        return False

    title = item.title.lower()
    if filters.keywords_any and not any(word.lower() in title for word in filters.keywords_any):
        return False
    if any(word.lower() in title for word in filters.keywords_none):
        return False
    return True
