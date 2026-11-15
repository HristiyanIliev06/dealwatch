from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup

from ..models import Observation
from ..pricing import parse_price
from . import ExtractionError

_IN_STOCK = ("instock", "limitedavailability", "onlineonly", "instoreonly", "preorder")


def extract(html: str, url: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")
    for node in _product_nodes(soup):
        observation = _from_product(node, url)
        if observation is not None:
            return observation
    observation = _from_meta(soup, url)
    if observation is not None:
        return observation
    raise ExtractionError("no schema.org Product or product meta tags found")


def _walk(data: Any) -> Iterator[dict]:
    if isinstance(data, list):
        for entry in data:
            yield from _walk(entry)
    elif isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (list, dict)):
                yield from _walk(value)


def _product_nodes(soup: BeautifulSoup) -> Iterator[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if "Product" in types:
                yield node


def _as_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return parse_price(str(value))[0]


def _from_product(node: dict, url: str) -> Observation | None:
    offers = node.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    prices: list[Decimal] = []
    currency: str | None = None
    availabilities: list[bool] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        raw = offer.get("price", offer.get("lowPrice"))
        price = _as_decimal(raw) if raw not in (None, "") else None
        if price is not None:
            prices.append(price)
        currency = currency or offer.get("priceCurrency")
        availability = offer.get("availability")
        if availability:
            availabilities.append(str(availability).rsplit("/", 1)[-1].lower() in _IN_STOCK)
    if not prices and not availabilities:
        return None
    return Observation(
        title=node.get("name"),
        price=min(prices) if prices else None,
        currency=currency,
        in_stock=any(availabilities) if availabilities else None,
        url=url,
    )


def _from_meta(soup: BeautifulSoup, url: str) -> Observation | None:
    def meta(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find(
                "meta", attrs={"name": name}
            )
            if tag and tag.get("content"):
                return str(tag["content"])
        return None

    raw_price = meta("product:price:amount", "og:price:amount")
    if raw_price is None:
        return None
    availability = meta("product:availability", "og:availability")
    return Observation(
        title=meta("og:title"),
        price=_as_decimal(raw_price),
        currency=meta("product:price:currency", "og:price:currency"),
        in_stock=None if availability is None else availability.lower().replace(" ", "") in _IN_STOCK,
        url=url,
    )
