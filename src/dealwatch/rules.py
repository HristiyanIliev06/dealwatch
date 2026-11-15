from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .config import Rule
from .models import Alert, Observation, Previous
from .pricing import format_money as _money

DEFAULT_PRIORITY = 3
# Informational alerts that should not buzz the phone.
QUIET_KINDS = {"out_of_stock": 2}


def evaluate(
    key: str, obs: Observation, prev: Previous | None, rules: list[Rule]
) -> list[Alert]:
    """Return alerts triggered by moving from `prev` to `obs`.

    The first sighting only sets a baseline, and threshold rules fire on crossing the
    threshold rather than while staying below it, so a price that sits under the target
    does not alert on every check.
    """
    if prev is None:
        return []
    alerts = []
    for rule in rules:
        alert = _check(key, obs, prev, rule)
        if alert is not None:
            priority = rule.priority or QUIET_KINDS.get(alert.kind, DEFAULT_PRIORITY)
            alerts.append(replace(alert, priority=priority))
    return alerts


def _check(key: str, obs: Observation, prev: Previous, rule: Rule) -> Alert | None:
    name = obs.title or key
    was = _money(prev.price, obs.currency)
    now = _money(obs.price, obs.currency)

    if rule.price_below is not None and obs.price is not None:
        crossed = obs.price < rule.price_below and (
            prev.price is None or prev.price >= rule.price_below
        )
        if crossed:
            return Alert(key, "price_below", f"Price below {rule.price_below}: {name}",
                         f"Now {now} (was {was}).", obs.url)

    elif rule.drop_percent is not None and obs.price is not None and prev.price:
        threshold = prev.price * (Decimal(1) - Decimal(str(rule.drop_percent)) / 100)
        if obs.price <= threshold:
            return Alert(key, "drop_percent", f"Price drop {rule.drop_percent:g}%+: {name}",
                         f"Now {now} (was {was}).", obs.url)

    elif rule.back_in_stock:
        if obs.in_stock and prev.in_stock is False:
            return Alert(key, "back_in_stock", f"Back in stock: {name}",
                         f"Available again at {now}.", obs.url)

    elif rule.out_of_stock:
        if obs.in_stock is False and prev.in_stock:
            return Alert(key, "out_of_stock", f"Out of stock: {name}",
                         f"Was available at {was}.", obs.url)

    elif rule.any_change:
        if obs.price != prev.price or obs.in_stock != prev.in_stock:
            return Alert(key, "any_change", f"Changed: {name}",
                         f"Price {was} -> {now}; in stock: {prev.in_stock} -> {obs.in_stock}.",
                         obs.url)

    elif rule.all_time_low:
        if obs.price is not None and prev.min_price is not None and obs.price < prev.min_price:
            return Alert(key, "all_time_low", f"New lowest price: {name}",
                         f"Now {now}, previous lowest {_money(prev.min_price, obs.currency)}.",
                         obs.url)

    return None
