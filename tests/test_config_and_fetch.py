from protego import Protego

from dealwatch.config import WatchItem, strip_tracking_params
from dealwatch.fetch import Fetcher

OZONE_ROBOTS = """
User-agent: *
Allow: /
Disallow: /sleasing/
Disallow: /*?q=
Disallow: /*?fbclid=
"""

EMAG_ROBOTS = """
User-agent: *
Disallow: /cart/*
Disallow: /product/
"""


def test_strip_tracking_params_keeps_variant():
    url = "https://gate.shop/bg/pants-1?variant=682041&_gl=1*abc*_up*MQ..&gclid=XYZ&utm_source=a"
    assert strip_tracking_params(url) == "https://gate.shop/bg/pants-1?variant=682041"


def test_strip_tracking_params_without_query_is_unchanged():
    url = "https://www.ozone.bg/product/x-1/"
    assert strip_tracking_params(url) == url
    assert strip_tracking_params(url + "?srsltid=AAA") == url


def test_watch_item_url_is_cleaned():
    item = WatchItem.model_validate(
        {"name": "n", "url": "https://s.bg/p/1?srsltid=AAA", "rules": [{"any_change": True}]}
    )
    assert item.url == "https://s.bg/p/1"


def _fetcher_with(origin: str, robots: str) -> Fetcher:
    fetcher = Fetcher("dealwatch/0.1")
    fetcher._robots[origin] = Protego.parse(robots)
    return fetcher


def test_robots_wildcards_are_honoured():
    fetcher = _fetcher_with("https://www.ozone.bg", OZONE_ROBOTS)
    assert fetcher._allowed("https://www.ozone.bg/product/x-1/")
    assert not fetcher._allowed("https://www.ozone.bg/drehi/?q=funko")
    assert not fetcher._allowed("https://www.ozone.bg/sleasing/abc")


def test_robots_plain_disallow():
    fetcher = _fetcher_with("https://www.emag.bg", EMAG_ROBOTS)
    assert not fetcher._allowed("https://www.emag.bg/product/x")
    assert fetcher._allowed("https://www.emag.bg/some-item/pd/ABC123/")
