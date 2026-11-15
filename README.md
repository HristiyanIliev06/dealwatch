# DealWatch

A config-driven watcher for online prices, stock and new deals. Point it at product pages or
deal feeds, describe in YAML what counts as interesting, and it pushes an alert to your phone
when a price drops, an item comes back in stock, or a new deal matching your filters appears.

Built as a small, dependency-light Python tool with a tested rule engine, SQLite history and
deliberately polite fetching (robots.txt, rate limiting, no bot-protection evasion).

## Features

- **Watch product pages.** Extract price and stock from schema.org JSON-LD (preferred, survives
  redesigns) or from CSS selectors you supply.
- **Discover new deals.** Scan the CheapShark API (Steam, GOG, Humble...) or any RSS/Atom feed
  and alert on new listings that match your filters.
- **Rules per product.** Price below a value, percentage drop, back in stock, went out of
  stock, any change, all-time low.
- **Alert hygiene.** The first sighting is only a baseline, identical alerts are throttled by a
  cooldown, threshold rules fire on *crossing* the threshold, and you get a "watcher broken"
  alert if extraction keeps failing (silent failure is the usual way scrapers die).
- **Phone alerts** via [ntfy.sh](https://ntfy.sh), with quiet (silent) and buzzing priorities.
- **History in SQLite**, queryable from the CLI.
- **Browser mode** (optional Playwright) for pages that need JavaScript.

## How it works

```
config.yaml ──► validated (pydantic, unknown keys rejected)
                   │
     ┌─────────────┴──────────────┐
     │ watch: product pages       │ discover: deal sources
     │ fetch → extract price/stock│ fetch → parse listings → filters
     └─────────────┬──────────────┘
                   ▼
        SQLite: observations, seen_items, alerts_sent
                   ▼
        rule engine (+ baseline, cooldown, crossing logic)
                   ▼
        notifiers: console · ntfy
```

`dealwatch run` is a short-lived process. A scheduler (Windows Task Scheduler, cron, ...)
starts it every few minutes; each item has its own `interval_minutes`, and the run only checks
items that are due. State lives in the SQLite database, so nothing runs in the background
between invocations.

Source order of preference, from most to least robust: official API/RSS, then JSON-LD / meta
tags, then CSS selectors, then a real browser.

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/HristiyanIliev06/dealwatch.git
cd dealwatch
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml     # Windows: copy config.example.yaml config.yaml
cp .env.example .env                   # Windows: copy .env.example .env
dealwatch run --dry-run --force        # fetch everything now, print alerts, write nothing
```

If the project path contains non-ASCII characters on Windows, `pip install -e` can fail
(setuptools writes a cp1252 `.pth` file). Install the dependencies directly and run with
`PYTHONPATH=src python -m dealwatch.cli ...` instead.

For phone alerts install the ntfy app, subscribe to a long random topic, put it in `.env` as
`NTFY_TOPIC`, add `ntfy` to `notify:` in `config.yaml` and run `dealwatch notify-test`.
Treat the topic like a password: anyone who knows it can read your alerts.

## Command line

| Command | What it does |
|---|---|
| `dealwatch list` | Show configured watches and discovery sources |
| `dealwatch run` | Check everything that is due, send alerts |
| `dealwatch run --dry-run --force` | Check everything now, print alerts, write and send nothing |
| `dealwatch check "NAME"` | Check one item now (add `--dry-run` to preview) |
| `dealwatch history "NAME"` | Show recorded prices and stock for an item |
| `dealwatch notify-test` | Send a test notification through the configured notifiers |

Global options: `--config PATH`, `--db PATH` (or `DEALWATCH_DB`), `-v`, `--log-file PATH`.

## Configuring what to track

Everything lives in `config.yaml` (your private copy of `config.example.yaml`; it is
gitignored). The file is validated on load, so typos in a key name are reported instead of
silently ignored.

### Defaults

```yaml
defaults:
  interval_minutes: 60        # how often each item is checked (per-item override below)
  notify: [ntfy]              # console, ntfy
  cooldown_hours: 24          # min gap between identical alerts for one item
  failure_threshold: 3        # consecutive failed checks before a "source broken" alert
  request_delay_seconds: 3    # min gap between requests to the same host
  respect_robots: true
```

### Watching a product page

```yaml
watch:
  - name: Mechanical keyboard          # unique label, used in alerts and CLI
    url: https://shop.example/p/123    # tracking params (utm_*, gclid, srsltid...) are stripped
    interval_minutes: 30               # optional: overrides the default
    notify: [ntfy]                     # optional: overrides the default
    fetch: http                        # or "browser" for JavaScript-rendered pages
    extract: {type: jsonld}            # see below
    rules:
      - price_below: 80
      - drop_percent: 15
      - back_in_stock: true
```

Keep variant parameters such as `?variant=682041`; only ad/analytics parameters are removed.

### Choosing what to read from the page (`extract`)

`type: jsonld` (default) reads the schema.org `Product` data most shops embed, falling back to
OpenGraph/product meta tags. No selectors needed. Try it first.

`type: css` reads the page with selectors you provide:

```yaml
extract:
  type: css
  title: h1
  price: "span.price"                     # required for css; crossed-out old prices are ignored
  stock: "#availability"                  # element whose text says whether it is in stock
  in_stock_text: ["in stock", "в наличност"]     # in stock if the element contains one of these
  out_of_stock_text: ["sold out", "изчерпан"]    # alternative: in stock unless it contains one of these
  stock_attribute: href                   # optional: read an attribute instead of the text
```

Finding a selector: open the product page, right-click the price, choose *Inspect*, and
right-click the highlighted element, *Copy → Copy selector*. Prefer stable `id` or semantic
class names over long generated paths, then confirm with
`dealwatch check "NAME" --dry-run`.

Prices are parsed locale-aware (`1 299,00 лв.`, `$1,299.00`, `14,31 €`) into exact decimals with
the currency recorded.

### Rules

Each rule has exactly one condition. Add as many rules to an item as you like.

| Rule | Fires when |
|---|---|
| `price_below: 80` | The price *crosses* below 80 (not on every check while it stays there) |
| `drop_percent: 15` | The price fell at least 15% from the previous recorded price |
| `back_in_stock: true` | The item changes from out of stock to in stock |
| `out_of_stock: true` | The item changes from in stock to out of stock (silent by default) |
| `any_change: true` | The price or stock changed in any way |
| `all_time_low: true` | The price is the lowest ever recorded for this item |

Add `priority: 1-5` to a rule to override its ntfy priority (default 3 buzzes; 2 and below is
silent). Out-of-stock and "watcher failing" alerts are silent by default.

The first check of an item is a baseline and never alerts, and the same alert for one item is
suppressed for `cooldown_hours`.

### Discovering new deals

```yaml
discover:
  - name: Game deals
    source: cheapshark          # or: rss (needs url:)
    stores: [1, 7]              # CheapShark store ids: 1 Steam, 7 GOG, 11 Humble Store
    interval_minutes: 120
    max_alerts: 3               # per run; extra matches fold into one summary alert
    filters:
      max_price: 10
      min_discount_pct: 80
      min_rating: 85            # percent positive reviews (CheapShark / Steam)
      min_rating_count: 200
      keywords_any: [roguelike, strategy]
      keywords_none: [soundtrack, dlc]

  - name: Deals feed
    source: rss
    url: https://example.com/deals.rss
    filters: {keywords_any: [roguelike]}
```

An item must satisfy every filter that is set; a filter on a field the source does not provide
fails rather than passing silently. The first run of a source only records what exists. After
that you are alerted for new matches and for items whose price falls into range.

### Changing things later

Edit `config.yaml` and save; the next run picks it up. Changing an item's `name` makes it a new
item with a fresh baseline and history. Run `dealwatch list` to confirm the file still
validates.

## Scheduling

Run `dealwatch run` every 5-15 minutes with any scheduler; per-item intervals decide what is
actually fetched.

Windows (Task Scheduler): `run-dealwatch.ps1` wraps the run with logging and log rotation. Create
a task that runs it every 15 minutes (hidden PowerShell, start when available, ignore a new
instance if one is still running). The script finds the project via its own location and expects the
virtual environment at `.venv`; the log goes to `%LOCALAPPDATA%\dealwatch\dealwatch.log`. Set
`DEALWATCH_DB` in `.env` to keep the database out of a synced folder such as OneDrive.

macOS/Linux (cron):

```
*/15 * * * * cd /path/to/dealwatch && .venv/bin/dealwatch run --log-file ~/.dealwatch.log
```

Only a computer that is awake and online runs checks; missed runs are simply made up at the
next one.

## Design notes

- **Pydantic v2 strict config.** Unknown keys, a rule with two conditions, or a CSS watch
  without a price selector fail at load time with a clear message.
- **Decimal money, parsed per locale.** No float rounding, and the currency is stored.
- **Pure, tested rule engine.** `rules.evaluate` takes an observation and the previous state
  and returns alerts, with no I/O, so every rule and edge case is unit tested.
- **Alert quality over alert count.** Baselines, crossing semantics, cooldown, per-listing
  dedup, an alert cap with a summary, and source-health alerts.
- **Polite by default.** robots.txt is parsed with `protego` (RFC 9309, wildcards), requests to
  one host are spaced with jitter, the User-Agent is honest, and defusedxml guards the RSS
  parser against entity bombs.
- **Pluggable edges.** Fetchers, extractors, discovery sources and notifiers are small
  adapters, so adding Telegram or a new source is one file.
- **Windows-aware.** UTF-8 console and log handling, and a documented workaround for
  non-ASCII project paths.

## Project layout

```
src/dealwatch/
  cli.py          commands            config.py    pydantic models, YAML loader
  runner.py       orchestration       rules.py     rule engine
  fetch.py        HTTP, robots, rate  browser.py   optional Playwright fetch
  extractors/     jsonld.py, css.py   sources/     cheapshark.py, rss.py
  filters.py      discovery filters   pricing.py   locale-aware price parsing
  db.py           SQLite              notify/      console.py, ntfy.py
tests/            pricing, extractors, rules, runner, config/fetch, discovery
```

## Tests

```bash
pytest -q
```

## Limitations and ethics

- Some shops block automated clients (for example with a 403). DealWatch does not try to evade
  bot protection; for such shops use an official API or feed, or ask the shop.
- Check a site's terms before adding it. The CheapShark adapter skips its robots.txt check
  because that API is documented for free programmatic use (one request per run); every other
  fetch honours robots.txt.
- Selectors break when a shop redesigns its pages. You will get a "watcher broken" alert
  rather than silence.
- There is no quantity-based "low stock" rule, because shops rarely expose quantities.

## Roadmap

Telegram notifier, more discovery sources, price-history charts and a small web UI.
