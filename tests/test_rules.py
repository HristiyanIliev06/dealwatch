from decimal import Decimal

from dealwatch.config import Rule
from dealwatch.models import Observation, Previous
from dealwatch.rules import evaluate


def obs(price, in_stock=True):
    return Observation("Item", None if price is None else Decimal(price), "EUR", in_stock, "http://x")


def prev(price, in_stock=True, min_price=None):
    p = Decimal(price)
    return Previous(p, in_stock, Decimal(min_price) if min_price else p)


def kinds(alerts):
    return [a.kind for a in alerts]


def test_first_sighting_is_baseline_only():
    assert evaluate("k", obs("10"), None, [Rule(price_below=50)]) == []


def test_price_below_fires_on_crossing_only():
    rules = [Rule(price_below=50)]
    assert kinds(evaluate("k", obs("40"), prev("60"), rules)) == ["price_below"]
    assert evaluate("k", obs("35"), prev("40"), rules) == []


def test_drop_percent():
    rules = [Rule(drop_percent=20)]
    assert kinds(evaluate("k", obs("79"), prev("100"), rules)) == ["drop_percent"]
    assert evaluate("k", obs("85"), prev("100"), rules) == []


def test_back_in_stock():
    rules = [Rule(back_in_stock=True)]
    assert kinds(evaluate("k", obs("10", True), prev("10", False), rules)) == ["back_in_stock"]
    assert evaluate("k", obs("10", True), prev("10", None), rules) == []


def test_out_of_stock():
    rules = [Rule(out_of_stock=True)]
    assert kinds(evaluate("k", obs("10", False), prev("10", True), rules)) == ["out_of_stock"]
    assert evaluate("k", obs("10", False), prev("10", False), rules) == []
    assert evaluate("k", obs("10", None), prev("10", True), rules) == []


def test_priorities_buzz_for_deals_and_stay_quiet_for_out_of_stock():
    drop = evaluate("k", obs("79"), prev("100"), [Rule(drop_percent=20)])[0]
    gone = evaluate("k", obs("10", False), prev("10", True), [Rule(out_of_stock=True)])[0]
    forced = evaluate("k", obs("10", False), prev("10", True), [Rule(out_of_stock=True, priority=4)])[0]
    assert (drop.priority, gone.priority, forced.priority) == (3, 2, 4)


def test_any_change():
    rules = [Rule(any_change=True)]
    assert kinds(evaluate("k", obs("11"), prev("10"), rules)) == ["any_change"]
    assert evaluate("k", obs("10"), prev("10"), rules) == []


def test_all_time_low():
    rules = [Rule(all_time_low=True)]
    assert kinds(evaluate("k", obs("8"), prev("10", min_price="9"), rules)) == ["all_time_low"]
    assert evaluate("k", obs("9.5"), prev("10", min_price="9"), rules) == []
