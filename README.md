# DealWatch

Config-driven watcher for product prices and stock. Checks pages on a schedule, remembers
what it saw in SQLite, and pushes an alert (console, ntfy.sh) when a rule fires.

Status: Phases 1-2 done (watching product pages, discovering new deals, browser fetch mode,
ntfy). Telegram, more sources and a UI are planned.

## Setup (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install requests beautifulsoup4 pyyaml pydantic python-dotenv pytest
copy config.example.yaml config.yaml    # edit your products
copy .env.example .env                   # set NTFY_TOPIC to enable phone alerts
$env:PYTHONPATH = "src"
```

`pip install -e .` fails when the project path contains non-ASCII characters (setuptools
writes the `.pth` file in cp1252), hence the `PYTHONPATH` approach. In a plain ASCII path
`pip install -e ".[dev]"` works and gives you the `dealwatch` command.

## Usage

```powershell
python -m dealwatch.cli list                      # configured items
python -m dealwatch.cli run --dry-run --force     # fetch everything, print alerts, write nothing
python -m dealwatch.cli run                       # check items that are due
python -m dealwatch.cli check "Example product (JSON-LD)"
python -m dealwatch.cli history "Example product (JSON-LD)"
```

## Rules

One condition per rule entry: `price_below`, `drop_percent`, `back_in_stock`, `any_change`,
`all_time_low`. The first check of an item is a baseline and never alerts. Threshold rules
fire when the price crosses the threshold, and identical alerts for one item are suppressed
for `cooldown_hours`. After `failure_threshold` consecutive failed checks you get a
`source_broken` alert.

## Discovery (new deals)

`discover:` entries scan a source for listings and alert on new ones that match your filters
(`max_price`, `min_discount_pct`, `min_rating`, `min_rating_count`, `keywords_any`,
`keywords_none`). Sources: `cheapshark` (Steam, GOG, Humble... deals, prices in USD) and `rss`
(any RSS/Atom feed, filter by title keywords). The first run of a source only records what
exists; afterwards you are alerted for new matches, or for items that start matching (their
price fell into range). At most `max_alerts` alerts per run, the rest fold into one summary.
CheapShark's robots.txt disallows its API for crawlers, but its docs offer the API for
programmatic use, so that one adapter skips the robots check (one request per run).

## Alert priority

Price drops, back-in-stock and new deals use ntfy's default priority (sound and vibration).
Out-of-stock and "watcher failing" are low priority (silent, no pop-up). Override per rule with
`priority: 1-5`.

## Scheduling (Windows Task Scheduler)

The task `DealWatch` runs `run-dealwatch.ps1` every 15 minutes while you are logged in; each
item's own `interval_minutes` decides whether it is due. The database and log live in
`%LOCALAPPDATA%\dealwatch\` (not in the OneDrive-synced project folder).

```powershell
Start-ScheduledTask -TaskName DealWatch                      # run now
Get-ScheduledTask -TaskName DealWatch | Get-ScheduledTaskInfo # last/next run, last result
Disable-ScheduledTask -TaskName DealWatch                    # pause
Unregister-ScheduledTask -TaskName DealWatch -Confirm:$false # remove
Get-Content "$env:LOCALAPPDATA\dealwatch\dealwatch.log" -Tail 20 -Encoding utf8
```

## Phone alerts (ntfy)

`NTFY_TOPIC` in `.env` is a random topic name; anyone who knows it can read your alerts, so
treat it like a password. Install the ntfy app, subscribe to that topic, then check with
`python -m dealwatch.cli notify-test`.

## Politeness

robots.txt is honoured and requests to one host are spaced by `request_delay_seconds`.
Check each shop's terms before adding it; prefer official APIs/feeds where they exist.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
