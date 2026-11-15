import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dealwatch.config import Config, Filters
from dealwatch.db import Database
from dealwatch.filters import matches
from dealwatch.models import DealItem
from dealwatch.runner import run
from dealwatch.sources import SourceError, cheapshark, rss

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def deal(game_id, title, price, normal, rating="90", count="500", store="1"):
    return {
        "storeID": store, "gameID": str(game_id), "title": title, "dealID": f"id%2B{game_id}",
        "salePrice": price, "normalPrice": normal,
        "savings": str((1 - float(price) / float(normal)) * 100),
        "steamRatingPercent": rating, "steamRatingCount": count,
    }


class FeedFetcher:
    def __init__(self, deals):
        self.deals = deals

    def get(self, url, browser=False, check_robots=True):
        return json.dumps(self.deals)


class Recorder:
    def __init__(self):
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


def make_config(**source):
    return Config.model_validate({
        "defaults": {"notify": ["rec"]},
        "discover": [{
            "name": "deals", "source": "cheapshark",
            "filters": {"max_price": 10, "min_discount_pct": 70, "min_rating": 80}, **source,
        }],
    })


def test_cheapshark_parsing():
    items = cheapshark._parse(deal(7, "Game - Deluxe", "4.99", "19.99"))
    assert items.item_id == "1:7"
    assert items.price == Decimal("4.99") and items.currency == "USD"
    assert items.url.endswith("id%2B7") and items.store == "Steam"
    assert cheapshark._parse({"title": "broken"}) is None


def test_zero_rating_means_unknown():
    item = cheapshark._parse(deal(1, "Unreviewed", "1.00", "10.00", rating="0", count="0"))
    assert item.rating is None


def test_filters():
    item = DealItem("1", "Super Roguelike Deluxe", "u", Decimal("5"), Decimal("20"), 75.0, "USD", 90, 500)
    assert matches(item, Filters(max_price=10, min_discount_pct=70, min_rating=80))
    assert not matches(item, Filters(max_price=4))
    assert not matches(item, Filters(min_discount_pct=80))
    assert not matches(item, Filters(min_rating_count=1000))
    assert matches(item, Filters(keywords_any=["ROGUELIKE", "puzzle"]))
    assert not matches(item, Filters(keywords_none=["deluxe"]))
    # A filter on a field the source lacks fails rather than passing silently.
    assert not matches(DealItem("2", "x", "u"), Filters(min_rating=50))


def test_baseline_then_alerts_only_for_new_matches():
    db, rec = Database(), Recorder()
    config = make_config()
    old = deal(1, "Old Deal", "3.00", "20.00")
    run(config, db, FeedFetcher([old]), {"rec": rec}, now=T0)
    assert rec.alerts == []                                     # baseline

    batch = [old, deal(2, "New Deal", "4.00", "20.00"), deal(3, "Too Pricey", "30.00", "60.00")]
    run(config, db, FeedFetcher(batch), {"rec": rec}, now=T0 + timedelta(hours=2))
    assert [a.title for a in rec.alerts] == ["New Deal"]

    run(config, db, FeedFetcher(batch), {"rec": rec}, now=T0 + timedelta(hours=4))
    assert len(rec.alerts) == 1                                 # nothing new


def test_item_that_starts_matching_later_alerts():
    db, rec = Database(), Recorder()
    config = make_config()
    run(config, db, FeedFetcher([deal(1, "Game", "30.00", "40.00")]), {"rec": rec}, now=T0)
    run(config, db, FeedFetcher([deal(1, "Game", "5.00", "40.00")]), {"rec": rec},
        now=T0 + timedelta(hours=2))
    assert [a.title for a in rec.alerts] == ["Game"]


def test_alert_limit_folds_extras_into_summary():
    db, rec = Database(), Recorder()
    config = make_config(max_alerts=2)
    run(config, db, FeedFetcher([deal(0, "Seed", "50.00", "60.00")]), {"rec": rec}, now=T0)
    many = [deal(i, f"Deal {i}", "2.00", "20.00") for i in range(1, 6)]
    run(config, db, FeedFetcher(many), {"rec": rec}, now=T0 + timedelta(hours=2))
    assert [a.kind for a in rec.alerts][-1] == "new_deals_more"
    assert len(rec.alerts) == 3 and rec.alerts[-1].priority == 2


def test_dry_run_writes_nothing():
    db, rec = Database(), Recorder()
    run(make_config(), db, FeedFetcher([deal(1, "G", "3.00", "20.00")]), {"rec": rec},
        dry_run=True, now=T0)
    assert db.seen("deals") == {}


RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>[Steam] Roguelike (-80%)</title><link>https://x/1</link><guid>g1</guid></item>
<item><title>No guid</title><link>https://x/2</link></item></channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom deal</title><link href="https://x/3"/><id>tag:3</id></entry></feed>"""


def test_rss_and_atom_parsing():
    assert [(i.item_id, i.url) for i in rss.parse(RSS)] == [("g1", "https://x/1"), ("https://x/2", "https://x/2")]
    assert [(i.item_id, i.title) for i in rss.parse(ATOM)] == [("tag:3", "Atom deal")]


def test_rss_rejects_garbage_and_entity_bombs():
    with pytest.raises(SourceError):
        rss.parse("<not xml")
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss>&b;</rss>'
    with pytest.raises(SourceError):
        rss.parse(bomb)
