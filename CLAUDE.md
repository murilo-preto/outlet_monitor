# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Outlet Watch" — a price tracker for the Lenovo **Brazil** outlet laptop catalogue. Three Docker
services: a Flask scraper/API, a Next.js UI, and a Telegram notifier bot. All user-facing strings
(UI, bot messages, error copy) are **pt-BR**.

`SETUP.md` is the de-facto README (install, deploy, common ops). `PLAN.md` is the design history —
read it before changing the scraper or the deployment topology; it records *why* things are the way
they are, including the reverse-engineered Lenovo endpoint and two production Docker bugs already
found and fixed.

## Commands

Everything runs in Docker; nothing is installed on the host.

```bash
docker compose up -d --build          # dev stack: frontend :3000, api :5000
docker compose logs -f api            # or frontend / notifier
docker compose down                   # data survives; `down -v` destroys the volumes
```

Tests — **two independent suites with separate dependency sets**, run separately:

```bash
docker compose run --rm api pytest -q
docker compose run --rm notifier pytest -q

# single test / single file
docker compose run --rm api pytest -q tests/test_storage.py::test_append_snapshots_skips_zero_price_rows
docker compose run --rm notifier pytest -q tests/test_report.py -k relisted
```

Frontend checks (no test runner is configured — `tsc` and `eslint` are the whole safety net):

```bash
docker compose run --rm frontend npx tsc --noEmit
docker compose run --rm frontend npm run lint
```

Other:

```bash
docker compose run --rm api python scripts/seed_db.py --reset   # synthetic history for UI work
curl -X POST http://localhost:5000/scrape                       # trigger a real scrape (dev)
docker compose -f docker-compose.prod.yml --env-file .env.prod build
```

### Edit-loop gotchas

- **`api` and `frontend` bind-mount their source** — Python edits need only a
  `docker compose restart api`; Next.js hot-reloads.
- **`notifier` does not.** Its `Dockerfile` `COPY`s `app/` and `tests/` into the image, so
  `docker compose run --rm notifier pytest` runs the *baked* code. Rebuild after every edit:
  `docker compose build notifier`. Forgetting this makes edits look like no-ops.
- `frontend/AGENTS.md` warns that Next.js 16 postdates the model's training data; consult
  `node_modules/next/dist/docs/` before using App Router APIs.

## Architecture

### Request path — the browser never talks to Flask

```
browser → Next.js Route Handler (frontend/src/app/api/*) → proxyToApi() → Flask (api:5000)
```

`frontend/src/lib/apiProxy.ts` is the single server-side hop. Flask **publishes no host port in
production** and is reachable only over the Docker network, so anything client-side must go through
a Route Handler and a relative `/api/...` path (`frontend/src/lib/api.ts`). Adding a Flask endpoint
means adding a matching Route Handler; there is no other way to reach it from the UI.

`POST /api/scrape` is the only authenticated route — it checks `x-scrape-token` against
`SCRAPE_SECRET`, and skips the check entirely when that env var is unset (so local dev needs no
config). GET routes are public.

### Storage is append-only, and everything interesting is derived at read time

`src/outlet_monitor/storage.py` owns one table, `price_history`: **one row per product per scrape**,
never updated. All products in a single scrape share one `timestamp`, which is load-bearing —
`currently_listed`, `changes_since_previous`, and the unique index all depend on it.

Derived, never stored: `lowest_price`/`highest_price` (all-time min/max from a `bounds` subquery),
`currently_listed` (this row's timestamp == the newest scrape's), and the category counts.

Two invariants that break silently if ignored:

- **The `COLUMNS` tuple drives everything downstream** — `_SELECT_COLUMNS`, `EXPORT_SQL`, the CSV
  export header, and `_row_to_dict`. Adding a column means touching `CREATE_TABLE_SQL`,
  `_MIGRATIONS`, `COLUMNS`, and `INSERT_SQL` together, or reads and writes drift apart.
- **`connect()` runs on every request.** It re-runs `CREATE TABLE IF NOT EXISTS`, `_apply_migrations`
  (PRAGMA `table_info` + `ALTER TABLE`), and index creation each time. Anything expensive must be
  one-time-guarded the way `_ensure_unique_snapshot_index` is (check `sqlite_master`, then do the
  work) — not `IF NOT EXISTS`, which would re-scan forever.

Dedup happens twice on purpose: `fetch_all_products` drops repeats caused by the paging race against
a live, price-sorted result set, and the UNIQUE index on `(timestamp, product_id)` +
`INSERT OR IGNORE` is the backstop.

### The scraper fails loud

`src/outlet_monitor/scrape.py` calls an undocumented Lenovo endpoint with a **double-URL-encoded**
`params` blob and two static IDs (`CLASSIFICATION_GROUP_IDS`, `PAGE_FILTER_ID`) captured from a live
page load. When those go stale, Lenovo returns HTTP 200 with **zero products** rather than an error —
so `fetch_all_products` raises `ScrapeError` on an empty result set. Never "fix" that by treating
empty as a legitimately empty outlet; it is the project's primary failure mode (see `PLAN.md` Risks).

Product `category` is inferred from the name via the `CATEGORY_PATTERNS` regex table (`ThinkPad`,
`IdeaPad`, `Legion`, … else `"Other"`) — Lenovo exposes no family field. Product URLs need the
`/br/outlet/pt` locale segment prepended or they 503.

### Notification path is fire-and-forget by design

```
POST /scrape → append_snapshots → changes_since_previous → send_price_changes_async
             → notifier POST /notify → per-subscriber filtering → Telegram
```

`src/outlet_monitor/notify.py` never raises and runs on a daemon thread; the compose files
deliberately have **no `depends_on` for the notifier**, so the bot being down can never hold back or
fail a scrape. `NOTIFIER_URL=""` disables notifications entirely.

`changes_since_previous` diffs only the two newest timestamps and emits an `event` of `price`, `new`,
or `relisted` (outlet stock churns — a sold-out config reappearing days later is worth distinguishing
from a first-ever listing). Delisted products are deliberately **not** reported. It returns `[]` when
only one scrape exists, so a fresh database doesn't produce a hundreds-long report.

The notifier owns a **separate SQLite database** (`subscribers.db`, its own volume) and never reads
the monitor's schema. `store.remember_lines()` auto-discovers new product lines from every `/notify`
payload, so the bot's filter menu grows without a redeploy.

New fields on the wire (`src/outlet_monitor/notify.py` → `telegram_notifier/app/schemas.py`) must be
**optional with a `None` default**, following the existing `event`/`category` pattern — the two
services deploy independently.

### Scheduler

`_run_scheduled_scrapes` (in `api.py`) is a daemon thread that **sleeps before its first scrape**, so
a container restart or redeploy never triggers an extra one. Preserve that ordering. On `ScrapeError`
it logs and continues rather than dying.

## Conventions

- Comments explain **why**, not what — the codebase is heavily commented with rationale (empirically
  discovered API quirks, why a guard exists, what breaks without it) and carries **zero** `TODO`/
  `FIXME` markers. Match that.
- Tests accompany every behaviour change. Python only; there is no frontend test framework.
- The backend is stdlib `sqlite3` + `requests` + Flask — no ORM, no migration framework. Schema
  changes go through the `_MIGRATIONS` tuple.
- `.env`, `.env.prod` are gitignored; `.env.prod.example` documents the surface. Config is env vars
  only — there are no CLI flags anywhere except `scripts/seed_db.py --reset`.
