from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from pydantic import ValidationError

from .config import Config, load_config
from .db import Database
from .fetch import Fetcher
from .models import Alert
from .notify import NotifierConfigError, build_notifiers
from .notify.console import ConsoleNotifier
from .runner import run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dealwatch")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=os.environ.get("DEALWATCH_DB", "dealwatch.db"))
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--log-file", help="append log lines to this file instead of stderr")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="check all due items once")
    run_cmd.add_argument("--dry-run", action="store_true",
                         help="print alerts to the console; write nothing to the database")
    run_cmd.add_argument("--force", action="store_true", help="ignore the schedule")

    check_cmd = commands.add_parser("check", help="check one item now, ignoring its schedule")
    check_cmd.add_argument("name")
    check_cmd.add_argument("--dry-run", action="store_true")

    commands.add_parser("list", help="show configured items")
    commands.add_parser("notify-test", help="send a test alert through every configured channel")

    history_cmd = commands.add_parser("history", help="show recorded prices for an item")
    history_cmd.add_argument("name")
    history_cmd.add_argument("--limit", type=int, default=20)
    return parser


def _channels(config: Config) -> set[str]:
    names = set(config.defaults.notify)
    for target in [*config.watch, *config.discover]:
        names.update(target.notify or [])
    return names


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    # Windows consoles default to a legacy code page that cannot print Cyrillic titles.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        filename=args.log_file,
        encoding="utf-8" if args.log_file else None,
    )

    try:
        config = load_config(args.config)
    except (OSError, ValidationError) as exc:
        print(f"Cannot load {args.config}: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        for item in config.watch:
            print(f"watch\t{item.name}\t{item.url}")
        for source in config.discover:
            print(f"discover\t{source.name}\t{source.url or source.source}")
        return 0

    if args.command == "notify-test":
        try:
            notifiers = build_notifiers(_channels(config))
        except NotifierConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        alert = Alert("test", "test", "DealWatch test", "If you can read this, alerts work.")
        for name, notifier in notifiers.items():
            notifier.send(alert)
            print(f"sent test alert via {name}")
        return 0

    db = Database(args.db)
    try:
        if args.command == "history":
            for row in db.history(args.name, args.limit):
                print(f"{row['ts']}\t{row['price']} {row['currency'] or ''}\tin_stock={row['in_stock']}")
            return 0

        dry_run = args.dry_run
        try:
            if dry_run:
                notifiers = {name: ConsoleNotifier() for name in _channels(config)}
            else:
                notifiers = build_notifiers(_channels(config))
        except NotifierConfigError as exc:
            print(exc, file=sys.stderr)
            return 2

        defaults = config.defaults
        fetcher = Fetcher(
            defaults.user_agent, defaults.request_delay_seconds, respect_robots=defaults.respect_robots
        )
        only = args.name if args.command == "check" else None
        try:
            alerts = run(
                config, db, fetcher, notifiers,
                dry_run=dry_run, force=getattr(args, "force", False), only=only,
            )
        finally:
            fetcher.close()
        print(f"{len(alerts)} alert(s) sent." if not dry_run else f"{len(alerts)} alert(s) (dry run).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
