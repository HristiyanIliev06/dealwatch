from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from .models import Alert, DealItem, Observation, Previous

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    key TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    next_check_at TEXT,
    fail_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    ts TEXT NOT NULL,
    title TEXT,
    price TEXT,
    currency TEXT,
    in_stock INTEGER
);
CREATE INDEX IF NOT EXISTS idx_observations_key ON observations (key, id);
CREATE TABLE IF NOT EXISTS alerts_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    kind TEXT NOT NULL,
    ts TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_key_kind ON alerts_sent (key, kind, ts);
CREATE TABLE IF NOT EXISTS seen_items (
    feed TEXT NOT NULL,
    item_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    price TEXT,
    matched INTEGER NOT NULL,
    PRIMARY KEY (feed, item_id)
);
"""


def _iso(moment: datetime) -> str:
    return moment.isoformat()


class Database:
    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def is_due(self, key: str, now: datetime) -> bool:
        row = self.conn.execute(
            "SELECT next_check_at FROM products WHERE key = ?", (key,)
        ).fetchone()
        return row is None or row["next_check_at"] is None or row["next_check_at"] <= _iso(now)

    def schedule(self, key: str, url: str, next_check_at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO products (key, url, next_check_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET url = excluded.url, next_check_at = excluded.next_check_at",
            (key, url, _iso(next_check_at)),
        )
        self.conn.commit()

    def previous(self, key: str) -> Previous | None:
        last = self.conn.execute(
            "SELECT price, in_stock FROM observations WHERE key = ? ORDER BY id DESC LIMIT 1",
            (key,),
        ).fetchone()
        if last is None:
            return None
        prices = [
            Decimal(row["price"])
            for row in self.conn.execute(
                "SELECT price FROM observations WHERE key = ? AND price IS NOT NULL", (key,)
            )
        ]
        return Previous(
            price=Decimal(last["price"]) if last["price"] is not None else None,
            in_stock=None if last["in_stock"] is None else bool(last["in_stock"]),
            min_price=min(prices) if prices else None,
        )

    def record(self, key: str, obs: Observation, now: datetime) -> None:
        self.conn.execute(
            "INSERT INTO observations (key, ts, title, price, currency, in_stock) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                key,
                _iso(now),
                obs.title,
                None if obs.price is None else str(obs.price),
                obs.currency,
                None if obs.in_stock is None else int(obs.in_stock),
            ),
        )
        self.conn.execute("UPDATE products SET fail_count = 0 WHERE key = ?", (key,))
        self.conn.commit()

    def record_failure(self, key: str, url: str) -> int:
        self.conn.execute(
            "INSERT INTO products (key, url, fail_count) VALUES (?, ?, 1) "
            "ON CONFLICT(key) DO UPDATE SET fail_count = fail_count + 1",
            (key, url),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT fail_count FROM products WHERE key = ?", (key,)
        ).fetchone()["fail_count"]

    def recently_sent(self, key: str, kind: str, now: datetime, cooldown_hours: float) -> bool:
        since = _iso(now - timedelta(hours=cooldown_hours))
        row = self.conn.execute(
            "SELECT 1 FROM alerts_sent WHERE key = ? AND kind = ? AND ts > ? LIMIT 1",
            (key, kind, since),
        ).fetchone()
        return row is not None

    def log_alert(self, alert: Alert, now: datetime) -> None:
        self.conn.execute(
            "INSERT INTO alerts_sent (key, kind, ts, message) VALUES (?, ?, ?, ?)",
            (alert.key, alert.kind, _iso(now), alert.message),
        )
        self.conn.commit()

    def seen(self, feed: str) -> dict[str, bool]:
        """Items already seen in a feed, mapped to whether they matched the filters last time."""
        rows = self.conn.execute(
            "SELECT item_id, matched FROM seen_items WHERE feed = ?", (feed,)
        )
        return {row["item_id"]: bool(row["matched"]) for row in rows}

    def record_seen(self, feed: str, results: list[tuple[DealItem, bool]], now: datetime) -> None:
        self.conn.executemany(
            "INSERT INTO seen_items (feed, item_id, first_seen, price, matched) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(feed, item_id) DO UPDATE SET price = excluded.price, matched = excluded.matched",
            [
                (feed, item.item_id, _iso(now), None if item.price is None else str(item.price), int(ok))
                for item, ok in results
            ],
        )
        self.conn.execute("UPDATE products SET fail_count = 0 WHERE key = ?", (feed,))
        self.conn.commit()

    def history(self, key: str, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT ts, price, currency, in_stock FROM observations "
            "WHERE key = ? ORDER BY id DESC LIMIT ?",
            (key, limit),
        ).fetchall()
