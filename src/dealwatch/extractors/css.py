from __future__ import annotations

from bs4 import BeautifulSoup

from ..config import Extract
from ..models import Observation
from ..pricing import parse_price
from . import ExtractionError


def extract(html: str, url: str, spec: Extract) -> Observation:
    soup = BeautifulSoup(html, "html.parser")

    price_element = soup.select_one(spec.price)
    if price_element is None:
        raise ExtractionError(f"price selector {spec.price!r} matched nothing")
    for struck in price_element.find_all(["del", "s", "strike"]):
        struck.decompose()  # crossed-out old prices sit next to the real one
    price_text = price_element.get_text(" ", strip=True)
    price, currency = parse_price(price_text)
    if price is None:
        raise ExtractionError(f"no number in price text {price_text!r}")

    in_stock = None
    if spec.stock:
        stock_element = soup.select_one(spec.stock)
        if stock_element is not None:
            if spec.stock_attribute:
                text = str(stock_element.get(spec.stock_attribute, "")).lower()
            else:
                text = stock_element.get_text(" ", strip=True).lower()
            if spec.out_of_stock_text:
                in_stock = not any(marker.lower() in text for marker in spec.out_of_stock_text)
            else:
                in_stock = any(marker.lower() in text for marker in spec.in_stock_text)

    title = None
    if spec.title:
        title_element = soup.select_one(spec.title)
        title = title_element.get_text(" ", strip=True) if title_element else None

    return Observation(title=title, price=price, currency=currency, in_stock=in_stock, url=url)
