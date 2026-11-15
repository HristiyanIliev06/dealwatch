from __future__ import annotations

from typing import Protocol

from ..config import DiscoverSource
from ..models import DealItem


class SourceError(Exception):
    pass


class TextFetcher(Protocol):
    def get(self, url: str, browser: bool = False, check_robots: bool = True) -> str: ...


def fetch_items(source: DiscoverSource, fetcher: TextFetcher) -> list[DealItem]:
    from . import cheapshark, rss

    if source.source == "cheapshark":
        return cheapshark.fetch(source, fetcher)
    return rss.fetch(source, fetcher)
