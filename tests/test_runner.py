from datetime import datetime, timedelta, timezone

from dealwatch.config import Config
from dealwatch.db import Database
from dealwatch.fetch import FetchError
from dealwatch.runner import run

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def page(price):
    return (
        '<script type="application/ld+json">{"@type":"Product","name":"Thing","offers":'
        f'{{"price":"{price}","priceCurrency":"EUR"}}}}</script>'
    )


class FakeFetcher:
    def __init__(self, body):
        self.body = body

    def get(self, url, browser=False):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Recorder:
    def __init__(self):
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


def make_config(**defaults):
    return Config.model_validate({
        "defaults": {"notify": ["rec"], "interval_minutes": 60, **defaults},
        "watch": [{"name": "thing", "url": "http://shop/x", "rules": [{"price_below": 50}]}],
    })


def test_alert_on_crossing_then_cooldown_and_schedule():
    db, rec = Database(), Recorder()
    config = make_config()
    notifiers = {"rec": rec}

    run(config, db, FakeFetcher(page("60")), notifiers, now=T0)            # baseline
    run(config, db, FakeFetcher(page("40")), notifiers, now=T0 + timedelta(hours=1))
    assert [a.kind for a in rec.alerts] == ["price_below"]

    # not due yet: nothing is fetched or recorded
    run(config, db, FakeFetcher(page("30")), notifiers, now=T0 + timedelta(hours=1, minutes=5))
    assert len(db.history("thing")) == 2

    # price rebounds above the threshold and drops again inside the cooldown window
    run(config, db, FakeFetcher(page("60")), notifiers, now=T0 + timedelta(hours=2))
    run(config, db, FakeFetcher(page("40")), notifiers, now=T0 + timedelta(hours=3))
    assert len(rec.alerts) == 1


def test_dry_run_writes_nothing():
    db, rec = Database(), Recorder()
    run(make_config(), db, FakeFetcher(page("60")), {"rec": rec}, dry_run=True, now=T0)
    assert db.history("thing") == []


def test_broken_source_alert_sent_once_at_threshold():
    db, rec = Database(), Recorder()
    config = make_config(failure_threshold=2)
    fetcher = FakeFetcher(FetchError("boom"))
    for step in range(4):
        run(config, db, fetcher, {"rec": rec}, force=True, now=T0 + timedelta(hours=step))
    assert [a.kind for a in rec.alerts] == ["source_broken"]
