from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .config import Config, DiscoverSource, WatchItem
from .db import Database
from .extractors import ExtractionError, extract
from .fetch import FetchError
from .filters import matches
from .models import Alert, DealItem
from .notify.base import Notifier
from .pricing import format_money
from .rules import evaluate
from .sources import SourceError, fetch_items

log = logging.getLogger(__name__)


class HtmlFetcher(Protocol):
    def get(self, url: str, browser: bool = False) -> str: ...


def run(
    config: Config,
    db: Database,
    fetcher: HtmlFetcher,
    notifiers: dict[str, Notifier],
    *,
    dry_run: bool = False,
    force: bool = False,
    only: str | None = None,
    now: datetime | None = None,
) -> list[Alert]:
    """Check every due watch item and discovery source once and deliver surviving alerts.

    With dry_run nothing is written to the database; callers pass console-only notifiers.
    """
    now = now or datetime.now(timezone.utc)
    defaults = config.defaults
    delivered: list[Alert] = []

    targets: list[WatchItem | DiscoverSource] = [*config.watch, *config.discover]
    for target in targets:
        if only and target.name != only:
            continue
        if not (force or only) and not db.is_due(target.name, now):
            continue

        if isinstance(target, WatchItem):
            alerts = _check_item(target, config, db, fetcher, dry_run, now)
            address = target.url
        else:
            alerts = _check_source(target, config, db, fetcher, dry_run, now)
            address = target.url or target.source
        if not dry_run:
            interval = target.interval_minutes or defaults.interval_minutes
            db.schedule(target.name, address, now + timedelta(minutes=interval))

        for alert in alerts:
            if db.recently_sent(alert.key, alert.kind, now, defaults.cooldown_hours):
                log.info("suppressed %s for %s (cooldown)", alert.kind, alert.key)
                continue
            _deliver(alert, target, defaults.notify, notifiers)
            if not dry_run:
                db.log_alert(alert, now)
            delivered.append(alert)
    return delivered


def _failure_alert(
    name: str, address: str, exc: Exception, db: Database, config: Config
) -> list[Alert]:
    failures = db.record_failure(name, address)
    if failures != config.defaults.failure_threshold:
        return []
    return [Alert(name, "source_broken", f"Watcher failing: {name}",
                  f"{failures} consecutive failures. Last error: {exc}", address, priority=2)]


def _check_item(
    item: WatchItem,
    config: Config,
    db: Database,
    fetcher: HtmlFetcher,
    dry_run: bool,
    now: datetime,
) -> list[Alert]:
    try:
        html = fetcher.get(item.url, browser=item.fetch == "browser")
        observation = extract(html, item.url, item.extract)
    except (FetchError, ExtractionError) as exc:
        log.warning("check failed for %s: %s", item.name, exc)
        return [] if dry_run else _failure_alert(item.name, item.url, exc, db, config)

    previous = db.previous(item.name)
    alerts = evaluate(item.name, observation, previous, item.rules)
    if not dry_run:
        db.record(item.name, observation, now)
    log.info("%s: price=%s in_stock=%s", item.name, observation.price, observation.in_stock)
    return alerts


def _check_source(
    source: DiscoverSource,
    config: Config,
    db: Database,
    fetcher: HtmlFetcher,
    dry_run: bool,
    now: datetime,
) -> list[Alert]:
    """Alert on listings that newly match the filters.

    The first run of a source only records what exists (a baseline) so you are not flooded
    with the whole current catalogue. Afterwards an item alerts when it is new and matches,
    or when it was seen before without matching and now does (e.g. its price fell into range).
    """
    try:
        items = fetch_items(source, fetcher)
    except (FetchError, SourceError) as exc:
        log.warning("discovery failed for %s: %s", source.name, exc)
        return [] if dry_run else _failure_alert(source.name, source.url or source.source, exc, db, config)

    seen = db.seen(source.name)
    results = [(item, matches(item, source.filters)) for item in items]
    fresh = [item for item, ok in results if ok and not seen.get(item.item_id, False)]
    if not dry_run:
        db.record_seen(source.name, results, now)

    log.info("%s: %d listings, %d match filters, %d new", source.name, len(items),
             sum(ok for _, ok in results), len(fresh))
    if not seen:
        for item in fresh[:10]:
            log.info("  baseline match: %s", _describe(item))
        return []

    alerts = [_deal_alert(source.name, item) for item in fresh[: source.max_alerts]]
    extra = len(fresh) - len(alerts)
    if extra > 0:
        alerts.append(Alert(source.name, "new_deals_more", f"{extra} more deals: {source.name}",
                            "More listings matched than the per-run alert limit.", priority=2))
    return alerts


def _describe(item: DealItem) -> str:
    return f"{item.title} - {_details(item)}"


def _details(item: DealItem) -> str:
    parts = [format_money(item.price, item.currency)]
    if item.discount_pct is not None:
        parts.append(f"-{item.discount_pct:.0f}%")
    if item.normal_price is not None:
        parts.append(f"was {format_money(item.normal_price, item.currency)}")
    if item.rating is not None:
        parts.append(f"{item.rating}% positive ({item.rating_count or '?'} reviews)")
    if item.store:
        parts.append(item.store)
    return ", ".join(parts)


def _deal_alert(feed: str, item: DealItem) -> Alert:
    # The item id is part of the kind so the cooldown applies per listing, not per feed.
    return Alert(feed, f"new_deal:{item.item_id}", item.title, _details(item), item.url)


def _deliver(
    alert: Alert,
    target: WatchItem | DiscoverSource,
    default_channels: list[str],
    notifiers: dict[str, Notifier],
) -> None:
    for channel in target.notify or default_channels:
        notifier = notifiers.get(channel)
        if notifier is None:
            log.error("notifier %r is not configured; alert for %s dropped", channel, alert.key)
            continue
        try:
            notifier.send(alert)
        except Exception:  # one broken channel must not block the others
            log.exception("notifier %r failed for %s", channel, alert.key)
