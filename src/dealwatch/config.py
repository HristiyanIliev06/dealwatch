from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_USER_AGENT = "dealwatch/0.1 (personal price monitor)"


_TRACKING_PARAMS = {"srsltid", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "_gl", "gad_source"}


def strip_tracking_params(url: str) -> str:
    """Drop ad/analytics query parameters (keeping e.g. ?variant=) so the fetched URL is stable."""
    parts = urlsplit(url)
    kept = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name.lower() not in _TRACKING_PARAMS and not name.lower().startswith("utm_")
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Defaults(_Strict):
    interval_minutes: int = Field(60, gt=0)
    notify: list[str] = ["console"]
    cooldown_hours: float = Field(24, ge=0)
    failure_threshold: int = Field(3, gt=0)
    request_delay_seconds: float = Field(3.0, ge=0)
    user_agent: str = DEFAULT_USER_AGENT
    respect_robots: bool = True


class Extract(_Strict):
    type: Literal["jsonld", "css"] = "jsonld"
    price: str | None = None
    stock: str | None = None
    # Read this attribute of the stock element (e.g. "href" on schema.org availability links)
    # instead of its text.
    stock_attribute: str | None = None
    title: str | None = None
    in_stock_text: list[str] = ["in stock", "в наличност"]
    # When set, the item counts as in stock unless the stock element contains one of these.
    out_of_stock_text: list[str] = []

    @model_validator(mode="after")
    def _css_needs_price_selector(self) -> Extract:
        if self.type == "css" and not self.price:
            raise ValueError("extract.type 'css' requires a 'price' selector")
        return self


class Rule(_Strict):
    price_below: Decimal | None = None
    drop_percent: float | None = Field(None, gt=0, le=100)
    back_in_stock: bool = False
    out_of_stock: bool = False
    any_change: bool = False
    all_time_low: bool = False
    # Overrides the default ntfy priority for this rule's alerts (1-5; 2 and below stay silent).
    priority: int | None = Field(None, ge=1, le=5)

    @model_validator(mode="after")
    def _exactly_one_condition(self) -> Rule:
        active = [
            self.price_below is not None,
            self.drop_percent is not None,
            self.back_in_stock,
            self.out_of_stock,
            self.any_change,
            self.all_time_low,
        ]
        if sum(active) != 1:
            raise ValueError("each rule must set exactly one condition")
        return self


class WatchItem(_Strict):
    name: str
    url: str
    # "browser" renders the page in a real browser; for shops that refuse plain HTTP clients.
    fetch: Literal["http", "browser"] = "http"
    extract: Extract = Extract()
    rules: list[Rule] = Field(min_length=1)
    interval_minutes: int | None = Field(None, gt=0)
    notify: list[str] | None = None

    @field_validator("url")
    @classmethod
    def _strip_tracking(cls, url: str) -> str:
        return strip_tracking_params(url)


class Filters(_Strict):
    """A discovered item must satisfy every filter that is set."""

    max_price: Decimal | None = None
    min_discount_pct: float | None = Field(None, ge=0, le=100)
    min_rating: int | None = Field(None, ge=0, le=100)  # percent positive reviews
    min_rating_count: int | None = Field(None, ge=0)
    keywords_any: list[str] = []
    keywords_none: list[str] = []


class DiscoverSource(_Strict):
    name: str
    source: Literal["cheapshark", "rss"]
    url: str | None = None  # feed address, for source "rss"
    stores: list[int] = [1]  # CheapShark store ids (1 Steam, 7 GOG, 11 Humble, ...)
    page_size: int = Field(60, ge=1, le=60)
    filters: Filters = Filters()
    interval_minutes: int | None = Field(None, gt=0)
    notify: list[str] | None = None
    max_alerts: int = Field(5, ge=1)  # per run; the rest are folded into one summary alert

    @model_validator(mode="after")
    def _rss_needs_url(self) -> DiscoverSource:
        if self.source == "rss" and not self.url:
            raise ValueError("source 'rss' requires a 'url'")
        return self


class Config(_Strict):
    defaults: Defaults = Defaults()
    watch: list[WatchItem] = []
    discover: list[DiscoverSource] = []

    @model_validator(mode="after")
    def _unique_names(self) -> Config:
        names = [item.name for item in self.watch] + [source.name for source in self.discover]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate watch names: {sorted(duplicates)}")
        return self


def load_config(path: str | Path) -> Config:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return Config.model_validate(raw)
