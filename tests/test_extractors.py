from decimal import Decimal

import pytest

from dealwatch.config import Extract
from dealwatch.extractors import ExtractionError, extract

JSONLD_PAGE = """
<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "WebSite", "name": "Shop"},
  {"@type": "Product", "name": "Keyboard",
   "offers": {"@type": "Offer", "price": "79.90", "priceCurrency": "EUR",
              "availability": "https://schema.org/InStock"}}
]}
</script></head><body></body></html>
"""

OG_PAGE = """
<html><head>
<meta property="og:title" content="Mouse">
<meta property="product:price:amount" content="25.00">
<meta property="product:price:currency" content="USD">
<meta property="product:availability" content="out of stock">
</head></html>
"""

CSS_PAGE = """
<div class="price">1 299,00 лв.</div><span class="stock">В наличност</span><h1>Monitor</h1>
"""


def test_jsonld_product_in_graph():
    obs = extract(JSONLD_PAGE, "http://x", Extract())
    assert (obs.title, obs.price, obs.currency, obs.in_stock) == (
        "Keyboard", Decimal("79.90"), "EUR", True
    )


def test_meta_fallback():
    obs = extract(OG_PAGE, "http://x", Extract())
    assert (obs.price, obs.currency, obs.in_stock) == (Decimal("25.00"), "USD", False)


def test_no_structured_data_raises():
    with pytest.raises(ExtractionError):
        extract("<html></html>", "http://x", Extract())


def test_css_extractor():
    spec = Extract(type="css", price=".price", stock=".stock", title="h1")
    obs = extract(CSS_PAGE, "http://x", spec)
    assert (obs.title, obs.price, obs.currency, obs.in_stock) == (
        "Monitor", Decimal("1299.00"), "BGN", True
    )


OZONE_LIKE_PAGE = """
<h1>Funko</h1>
<p id="availability-holder" class="availability out-of-stock">Изчерпан</p>
<span class="price" id="product-price-713001">14 ,31 €</span>
<span class="price" id="product-price-836936-upsell">10 ,99 €</span>
"""


def test_css_out_of_stock_text_and_main_product_price():
    spec = Extract(
        type="css",
        title="h1",
        price='span[id^="product-price-"]:not([id$="-upsell"])',
        stock="#availability-holder",
        out_of_stock_text=["изчерпан"],
    )
    obs = extract(OZONE_LIKE_PAGE, "http://x", spec)
    assert (obs.price, obs.currency, obs.in_stock) == (Decimal("14.31"), "EUR", False)

    in_stock_page = OZONE_LIKE_PAGE.replace("Изчерпан", "Наличен")
    assert extract(in_stock_page, "http://x", spec).in_stock is True


GATE_LIKE_PAGE = """
<article class="product-detail"><h1>Pants</h1><div class="product-price">
  <link itemprop="availability" href="http://schema.org/InStock">
  <span class="price is_sale_price"><del class="original-price">21,98 €</del> 10,99 €</span>
  <div class="flags-coupons"><span class="coupon-price">10,44 €</span> with code</div>
</div></article>
"""


def test_css_ignores_struck_through_price_and_reads_stock_attribute():
    spec = Extract(
        type="css",
        price="article.product-detail .product-price span.price",
        stock='article.product-detail .product-price link[itemprop="availability"]',
        stock_attribute="href",
        out_of_stock_text=["outofstock", "soldout"],
    )
    obs = extract(GATE_LIKE_PAGE, "http://x", spec)
    assert (obs.price, obs.currency, obs.in_stock) == (Decimal("10.99"), "EUR", True)

    sold_out = GATE_LIKE_PAGE.replace("InStock", "OutOfStock")
    assert extract(sold_out, "http://x", spec).in_stock is False


def test_css_missing_selector_raises():
    with pytest.raises(ExtractionError):
        extract(CSS_PAGE, "http://x", Extract(type="css", price=".nope"))
