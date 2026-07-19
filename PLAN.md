# Lenovo Outlet Price Monitor — Plan

## Goal
Track laptop listings on the Lenovo Brazil outlet (`https://www.lenovo.com/br/outlet/pt/laptops/`) over time by periodically collecting product + price data into a CSV, so price fluctuations (drops, restocks, discount changes) can be analyzed later.

## Key finding: this is not a simple `curl` job
Investigated the target page directly:

- `curl` with a browser User-Agent returns HTTP 200, but the HTML is a **client-rendered shell** — no product names or prices are present in the raw response (only empty `R$` price-label templates waiting to be filled by JS).
- The page is protected by **Akamai bot detection** (present in page assets).
- `robots.txt` does **not** disallow `/br/outlet/pt/laptops/`, so scraping this path is not against Lenovo's stated crawl policy — but we should still be a well-behaved client (identify with a normal browser UA, low request frequency, no parallel hammering).

**Implication:** a plain `curl`/`requests` GET will never see product data. We have two real options:

1. **Headless browser (recommended)** — Use Playwright to load the page, let JS execute, and either read the rendered DOM or intercept the XHR/fetch call the page itself makes to fetch product JSON. Intercepting the network call is preferable if we can find it (cleaner structured data, faster, less brittle than DOM scraping), with DOM scraping as the fallback.
2. **Reverse-engineered API only** — If step 1 reveals a stable JSON endpoint (e.g. a commerce/catalog API) that doesn't require session cookies or Akamai sensor tokens, we can call it directly with `requests` and drop the browser dependency entirely for regular runs. This needs to be verified empirically (Akamai often requires a valid `_abck`/sensor cookie minted by real browser JS, in which case direct calls will be blocked even with the right URL).

Phase 0 below resolves this before we build anything else.

## Phase 0 findings (resolved 2026-07-19)
Recon was done with the Playwright npm CLI (headless Chromium) inside the Debian dev container, capturing all network traffic while loading `https://www.lenovo.com/br/outlet/pt/laptops/`.

**Result: option 2 wins outright.** The page calls a clean JSON product-search API, and — contrary to the original assumption — it requires **no Akamai sensor cookie and no browser session at all**. A cold `fetch`/`requests` call with just a few headers returns full product data at HTTP 200. Playwright is *not* needed for regular scraping runs; it was only used for this one-time recon.

**Endpoint:**
```
GET https://openapi.lenovo.com/br/outlet/pt/ofp/search/dlp/product/query/get/_tsc
```
**Required query params:**
- `pageFilterId` — a filter/category id, e.g. `8e869e6a-e5b2-4a4b-b190-d4564c4eb084` for the laptops outlet listing. Appears to be a static id tied to the category, not a per-session nonce (worked cold, no prior page load).
- `subSeriesCode` — empty string for the unfiltered listing.
- `loyalty` — `false`.
- `params` — a JSON object, **double URL-encoded** (`encodeURIComponent(encodeURIComponent(JSON.stringify(obj)))`), containing:
  ```json
  {
    "classificationGroupIds": "400001",
    "pageFilterId": "8e869e6a-e5b2-4a4b-b190-d4564c4eb084",
    "facets": [],
    "page": "1",
    "pageSize": 20,
    "groupCode": "",
    "init": true,
    "sorts": ["priceUp"],
    "version": "v2",
    "enablePreselect": true,
    "subseriesCode": ""
  }
  ```
  Increment `"page"` (1-indexed) to paginate; response includes `data.pageCount`.

**Required headers** (no cookies needed):
- `User-Agent` — any normal browser UA string.
- `Referer` — must be `https://www.lenovo.com/br/outlet/pt/laptops/` (confirmed: requests without it, or with only UA/Accept, get `403 Forbidden` from an `openresty` edge WAF — this is a lighter-weight check than Akamai's, header-based only).
- `Accept: application/json`
- `Accept-Language: pt-BR`

**Response shape:** `{ status, msg, data: { pageCount, data: [{ products: [...] }] } }` — products are nested one level under groups; flatten with `data.data.flatMap(g => g.products)`.

**Per-product fields available (mapped to our CSV schema):**
| CSV column | JSON field |
|---|---|
| `product_id` | `id` (includes a unique suffix, e.g. `82X5X00900_64c9a7c6b7468-...`) — safest unique key per listing |
| `sku` | `productCode` (model code, e.g. `82X5X00900`) |
| `name` | `productName` |
| `url` | `https://www.lenovo.com` + `url` (relative path returned, e.g. `/p/laptops/ideapad/ideapad-100/88ips101778/82x5x00900`) |
| `list_price` | `webPrice` |
| `sale_price` | `finalPrice` (equivalently `instantSavingPrice`) |
| `discount_pct` | `savePercent` |
| `condition` | `productCondition` (e.g. `"Remanufaturado Certificado"`) |
| `availability` | `marketingStatus` (e.g. `"Available"`) and/or `inventoryStatus` (int) |
| `raw_specs` | `classification[].b` joined (CPU, OS, GPU, RAM, storage, display, warranty — each entry has `a` = label, `b` = value) |

**Risk noted for later:** `pageFilterId` and `classificationGroupIds` are currently hardcoded values scraped from one page load. If Lenovo changes their category/filter IDs, calls will start returning empty results rather than erroring — Phase 1 should treat an unexpectedly empty `products` array as a failure condition worth surfacing loudly, not a silent "0 items found."

### Example request (Python)
Verified working cold (no prior page load, no cookies) from inside the dev container:
```python
import json
import urllib.parse
import requests

BASE_URL = "https://openapi.lenovo.com/br/outlet/pt/ofp/search/dlp/product/query/get/_tsc"
PAGE_FILTER_ID = "8e869e6a-e5b2-4a4b-b190-d4564c4eb084"  # laptops outlet category

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR",
    "Referer": "https://www.lenovo.com/br/outlet/pt/laptops/",
}


def fetch_page(page: int) -> dict:
    params_obj = {
        "classificationGroupIds": "400001",
        "pageFilterId": PAGE_FILTER_ID,
        "facets": [],
        "page": str(page),
        "pageSize": 20,
        "groupCode": "",
        "init": True,
        "sorts": ["priceUp"],
        "version": "v2",
        "enablePreselect": True,
        "subseriesCode": "",
    }
    # API expects the params blob URL-encoded twice
    encoded_params = urllib.parse.quote(urllib.parse.quote(json.dumps(params_obj)))
    query = (
        f"pageFilterId={PAGE_FILTER_ID}&subSeriesCode=&loyalty=false"
        f"&params={encoded_params}"
    )
    resp = requests.get(f"{BASE_URL}?{query}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


data = fetch_page(1)
products = [p for group in data["data"]["data"] for p in group["products"]]
print(f"{len(products)} products, {data['data']['pageCount']} total pages")
```
Equivalent raw URL for page 1 (for manual `curl -H ... "<url>"` testing):
```
https://openapi.lenovo.com/br/outlet/pt/ofp/search/dlp/product/query/get/_tsc?pageFilterId=8e869e6a-e5b2-4a4b-b190-d4564c4eb084&subSeriesCode=&loyalty=false&params=%257B%2522classificationGroupIds%2522%253A%2522400001%2522%252C%2522pageFilterId%2522%253A%25228e869e6a-e5b2-4a4b-b190-d4564c4eb084%2522%252C%2522facets%2522%253A%255B%255D%252C%2522page%2522%253A%25221%2522%252C%2522pageSize%2522%253A20%252C%2522groupCode%2522%253A%2522%2522%252C%2522init%2522%253Atrue%252C%2522sorts%2522%253A%255B%2522priceUp%2522%255D%252C%2522version%2522%253A%2522v2%2522%252C%2522enablePreselect%2522%253Atrue%252C%2522subseriesCode%2522%253A%2522%2522%257D
```

### Example response (trimmed to one product)
```json
{
  "xrid": "9cbe453d9cb2b1a5ac1816f3b6af7bd8",
  "status": 200,
  "msg": "operation successful!",
  "data": {
    "pageCount": 2,
    "data": [
      {
        "products": [
          {
            "id": "82X5X00900_64c9a7c6b7468-4a6c-b2f7-695ca23a0803",
            "productCode": "82X5X00900",
            "productName": "IdeaPad 1i Intel Core i3-1215U 4GB 256GB SSD Linux 14\" HD",
            "webPrice": "2634.99",
            "finalPrice": "2252.92",
            "savePercent": "14",
            "marketingStatus": "Available",
            "inventoryStatus": 1,
            "productCondition": "Remanufaturado Certificado",
            "url": "/p/laptops/ideapad/ideapad-100/88ips101778/82x5x00900",
            "classification": [
              { "a": "Processador", "b": "AMD Ryzen 3 7320U" },
              { "a": "Sistema Operacional", "b": "Linux" },
              { "a": "Placa de Vídeo", "b": "Integrada" },
              { "a": "Memória", "b": "4GB" },
              { "a": "Armazenamento", "b": "256 GB SSD" },
              { "a": "Tela", "b": "15.6\" HD" },
              { "a": "Garantia", "b": "3 meses de garantia" }
            ]
          }
        ]
      }
    ]
  }
}
```

## Decisions made
- **Language:** Python.
- **Execution model:** manual runs — you (or the frontend, later) call `POST /scrape` yourself when you want a fresh snapshot (no cron/systemd for now; can revisit later).
- **Alerting:** none for v1 — data collection only. Price-drop notifications are a possible future phase.
- **Dev environment:** development happens inside the Debian docker container defined in `Dockerfile` (`debian:bookworm-slim` + Python), not on the host directly. Launched via `docker compose` (see below), not plain `docker run`.
- **Recon tooling (Phase 0, done):** bot-detection validation was done with the Playwright **npm CLI** (`npx playwright ...`) in a temporary Node-enabled container, to launch a real browser and capture network traffic. That confirmed no browser is needed for regular runs (see Phase 0 findings above), so Node/Playwright were dropped from the project's `Dockerfile` — Phases 1+ only need Python + `requests`.

## Running it — `docker compose`
Two services in the root `docker-compose.yml`:
- **`api`** — backend (scraper + SQLite storage + Flask API, Phases 0-3), `http://localhost:5000`, healthcheck-gated on `GET /health`.
- **`frontend`** — Next.js UI (Phase 5), `http://localhost:3000`.

Common commands:
- `docker compose up -d` — builds (if needed) and starts both services.
- `docker compose down` — stops and removes the containers (images and named volumes persist).
- `docker compose run --rm api pytest -q` — run the backend test suite inside the same image, one-off, without leaving a container behind.
- `docker compose run --rm api bash` / `docker compose run --rm frontend bash` — interactive shell in either environment, for ad hoc debugging.
- `docker compose build <service>` — rebuild a single service; needed when `pyproject.toml` (backend) or `package.json` (frontend) dependencies change. Source in both is otherwise bind-mounted, so ordinary code edits on the host are picked up live without rebuilding.
- `data/price_history.db` lives in a **named Docker volume** (`outlet-monitor-data`), not a bind-mounted host path — this was a deliberate choice to avoid the SQLite file being written as `root`-owned on the host (the containers have no non-root `USER`), which caused permission friction during earlier dev-container sessions. Verified: data survives `docker compose down && docker compose up -d` (full container recreation, not just a restart). The frontend's `node_modules` is on its own named volume (`frontend-node-modules`) for the same root-ownership reason.

## Data to capture per product, per run
| Field | Notes |
|---|---|
| `timestamp` | UTC ISO8601, time of this scrape |
| `product_id` / `sku` | Stable identifier if the API/DOM exposes one (needed to track the *same* item over time) |
| `name` | Product title as listed |
| `url` | Link to the product detail page |
| `list_price` | Original/"de" price, if shown |
| `sale_price` | Current outlet price, if shown |
| `discount_pct` | Discount %, if shown (or computed) |
| `condition` | Outlet items are often "novo"/"open box"/refurb grade — capture if available |
| `availability` | In stock / sold out, if the listing exposes it |
| `raw_specs` | Optional: CPU/RAM/storage summary string, if easily available on the listing card |

Open question to settle during Phase 0: does the outlet listing expose a stable per-item ID, or only a URL/slug? The URL is likely the best natural key if no explicit ID exists.

## SQLite storage design
- **Append-only history table**: `data/price_history.db`, table `price_history` — one row per (product, run), never overwritten or upserted. This is the source of truth for fluctuation analysis.
  - Columns: `id (PK autoincrement), timestamp, product_id, sku, name, url, list_price, sale_price, discount_pct, condition, availability, raw_specs`
  - Indexes on `product_id` and `timestamp` to keep later "price history for product X" / "latest snapshot per product" queries fast.
- No separate "latest snapshot" table initially — it's a `MAX(timestamp)`-per-`product_id` query away. Keep v1 simple: one file, one writer, append-only.
- Uses Python's stdlib `sqlite3` (no extra dependency). Schema created idempotently (`CREATE TABLE IF NOT EXISTS`) on every connect, so no separate migration step for v1.
- Prices stored as `REAL` (plain decimal, no currency symbol/thousands separator) so downstream analysis doesn't need cleanup; `timestamp` stored as ISO8601 UTC text (SQLite has no native datetime type).

## Project structure (proposed)
```
outlet_monitor/
├── PLAN.md
├── README.md
├── pyproject.toml            # or requirements.txt
├── src/
│   └── outlet_monitor/
│       ├── __init__.py
│       ├── scrape.py         # requests fetch + parse -> list[ProductSnapshot]
│       ├── models.py         # ProductSnapshot dataclass
│       ├── storage.py        # SQLite append-only history + query logic
│       └── api.py            # Flask app: POST /scrape, GET /products, GET /products/<id>/history
├── data/
│   └── price_history.db      # gitignored
└── tests/
    ├── test_scrape.py        # field-mapping/URL-building logic, no network calls
    ├── test_storage.py       # SQLite append/query logic, no network calls (uses in-memory/tmp db)
    └── test_api.py           # Flask test client, fetch_all_products monkeypatched, no network calls
```

## Build phases

**Phase 0 — Reconnaissance (do this first, before writing the scraper)**
- Use Playwright (or manual browser devtools) to load the outlet laptops page and capture the network traffic.
- Identify: is there a discrete JSON/XHR call returning product data? What's the URL, method, required headers/cookies? Does it work without a full browser session (i.e., can `requests` call it directly), or is it gated by an Akamai sensor cookie minted client-side?
- Decide DOM-scrape vs API-call approach based on this. Document the chosen endpoint/selectors in this file once known.

**Phase 1 — Core scraper**
- Implement fetch + parse using the `python-requests` call to the JSON endpoint documented above (no Playwright/browser dependency needed for regular runs) → list of `ProductSnapshot` records.
- Handle pagination by looping `page` 1..`data.pageCount`.

**Phase 2 — SQLite storage**
- Append snapshots to `data/price_history.db` (`price_history` table) via stdlib `sqlite3`, with idempotent schema creation and basic validation (e.g. skip rows with no price).

**Phase 3 — REST API (done, replaces the originally-planned bare CLI)**
- Flask app in `src/outlet_monitor/api.py`, run via `python -m outlet_monitor.api` (dev server on `0.0.0.0:5000`).
- Routes:
  | Method & path | Behavior |
  |---|---|
  | `GET /health` | `{"status": "ok"}` liveness check |
  | `POST /scrape` | Runs `fetch_all_products()` and `append_snapshots()`, returns `{fetched, written, timestamp}` (201). Returns 502 with `{"error": ...}` if `ScrapeError` is raised (e.g. stale filter ids returning zero products). |
  | `GET /products` | Latest snapshot per `product_id` (one row each, most recent `timestamp`) |
  | `GET /products/<product_id>/history` | Full price-history rows for one product, oldest first. 404 if `product_id` is unknown. |
- `create_app(db_path=...)` factory takes the DB path as a parameter (defaults to `storage.DEFAULT_DB_PATH`) so tests use per-test tmp/isolated SQLite files instead of the real `data/price_history.db`.
- A plain CLI (`python -m outlet_monitor.cli`) remains a possible future addition if HTTP is inconvenient for some workflow, but isn't needed now that the API covers "trigger a fetch" and "read the data" manually via `curl`/browser.

**Phase 4 — Basic analysis helper (optional, nice-to-have)**
- Superseded by Phase 5's frontend for interactive use; a standalone script/notebook is no longer planned unless a non-UI analysis need comes up later.

**Phase 5 — Frontend (scaffolded 2026-07-19; homepage built 2026-07-19)**
- **Stack:** Next.js 16 (App Router, Turbopack dev server), React 19, TypeScript 5, Tailwind CSS 4, Framer Motion (animation), Recharts (price-history charts), Lucide Icons, Embla Carousel.
- **Location:** `frontend/` — a separate Node project alongside the Python backend, own `package.json`/`Dockerfile`, scaffolded via `create-next-app` (`--typescript --tailwind --eslint --app --src-dir --import-alias "@/*"`).
- **Container:** own service (`frontend`) in the root `docker-compose.yml`, built from `frontend/Dockerfile` (same "copy Node from the official Node image onto `debian:bookworm-slim`" pattern used for Phase 0's recon container — reused here since Node is a first-class need for this container, unlike the backend). Runs `npm run dev -H 0.0.0.0` on port 3000, source bind-mounted for live edits, `node_modules` on its own named volume (`frontend-node-modules`) so host bind-mounting doesn't clash with the container-installed packages or leave root-owned files on the host.
- **Talking to the backend:** `NEXT_PUBLIC_API_URL=http://localhost:5000` is passed into the container — this only works for **client-side** fetches from the browser (which resolves `localhost` against the host's port mapping). If server-side rendering/fetching from within the Next.js container is added later, it will need the Docker-network service name (`http://api:5000`) instead, since `localhost` inside that container doesn't reach the `api` container.
- Verified: `docker compose up -d` brings up both `api` (healthy) and `frontend` simultaneously, on ports 5000 and 3000 respectively.
- Note for future work: Next.js 16 is newer than this assistant's training data cutoff — `create-next-app` auto-generated `frontend/AGENTS.md`, which warns of this and points at `node_modules/next/dist/docs/` for current API docs; worth reading before writing pages that touch newer/changed Next.js APIs.

**Backend additions that shipped alongside the homepage:**
- `category` field added to `ProductSnapshot`/the `price_history` table: inferred from `productName` via regex against known Lenovo family names (ThinkPad, ThinkBook, IdeaPad, Yoga, Legion, LOQ, "V Series"; anything else falls back to `"Other"`) in `scrape._infer_category()` — the outlet API has no clean family field of its own. Live distribution as of this scrape: IdeaPad 13, V Series 9, ThinkPad 5, LOQ 3, ThinkBook 3, Legion 1, Yoga 1.
- `image_url` field added: pulled from the raw product JSON's `media.heroImage.imageAddress` (falls back to the first `media.gallery[]` entry), protocol-relative URLs (`//...`) normalized to `https://...`.
- `storage.py` gained a small migration mechanism (`_apply_migrations`, `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`) so a pre-existing `data/price_history.db` volume (from before these two fields existed) upgrades in place instead of breaking — old rows backfill as `category='Other'`, `image_url=''`.
- New endpoints: `GET /categories` (distinct categories with product counts, based on each category's *latest* snapshot only, not raw historical rows) and `?category=` filtering on `GET /products`.
- CORS (`Access-Control-Allow-Origin: *`) added to every response, since the frontend calls the API cross-origin from the browser (no auth/cookies involved, so unrestricted is fine for this local dev tool).

**Homepage (`frontend/src/app/page.tsx`) — what it does:**
- Header with title, a "Atualizar preços" button that calls `POST /scrape` then refetches, sticky on scroll.
- Hero section with 3 stat tiles (products tracked, average discount, category count — computed from the unfiltered `/products` + `/categories` calls, so they don't change when switching category tabs).
- Category tabs (`CategoryTabs.tsx`): pill buttons with a Framer Motion `layoutId`-animated active background, one fixed color dot per category (see below) and a live product count per category from `/categories`.
- Product carousel (`ProductCarousel.tsx`, Embla): horizontally scrollable cards (`ProductCard.tsx`) — product image, category dot, availability, discount badge, list/sale price — for the selected category, refetched via `GET /products?category=`.
- Product detail (`ProductDetail.tsx`): clicking a card shows a larger panel with full specs and a `PriceHistoryChart.tsx` (Recharts area/line chart) for that product, fetched via `GET /products/<id>/history`. Keyed by `product_id` so switching products naturally resets the chart's local state (no manual "clear" logic needed) and drives the Framer Motion cross-fade. Shows a friendly empty state instead of a chart when fewer than 2 history points exist yet.
- **Design system:** followed the `dataviz` skill's method — colors assigned by job (categorical dots per category, using the skill's validated 8-hue CVD-safe palette in fixed order — never re-cycled per dataset order), chart drawn as a single un-legended series (2px line, ~10% opacity area wash, hairline gridlines, hover tooltip, no per-point labels), light/dark tokens defined once in `globals.css` as CSS custom properties (chart chrome & ink roles from the skill's reference palette) and consumed via `var(...)`, so the whole UI (not just charts) reswaps automatically on `prefers-color-scheme`.
- **Verified live** (Playwright screenshots, both light and dark, desktop and mobile widths) against the real backend after a live scrape: category switching, product selection, chart rendering, and responsive layout all confirmed working with zero browser console errors. `npx tsc --noEmit` and `npm run lint` both clean.
- **Structured specs (added 2026-07-19):** the flattened `raw_specs` string was lossy for display (some values, e.g. "Tela", contain commas indistinguishable from the join separator). Added a `specs` field/DB column (JSON array of `{label, value}`, migrated like `category`/`image_url`) and a `SpecsTable.tsx` component rendering it as a real table below the price chart, in `ProductDetail.tsx`.
- **Hydration-mismatch fix (2026-07-19):** the Darkreader browser extension rewrites inline `style="..."` attributes before React hydrates, which React flags as a (harmless but noisy) hydration error. Fixed by moving essentially all per-element `style={{color: "var(--color-x)"}}` usage to real Tailwind utility classes (`text-ink`, `bg-surface`, etc., generated from the same `@theme` tokens) across every component — Darkreader's inline-style rewrite only targets elements that already have an inline `style` attribute, so removing them removes the mismatch surface. Chart-internal Recharts SVG props (not DOM `style` attributes) were left as-is.

**Future / not in v1**
- Scheduling (cron/systemd timer) once manual runs are validated.
- Price-drop notifications (email/desktop).
- Broader category coverage beyond laptops.

## Production deployment (`www.murilopreto.com.br:7716`)
The app is deployed on a server that already runs a separate homepage on the same domain (nginx on ports 80/443, proxying to a different app on `127.0.0.1:5000`). This app is exposed on a **non-default port, 7716**, reusing that existing nginx + its certbot-issued cert, rather than running its own reverse proxy — a dedicated Caddy instance was the initial plan, but Caddy's automatic HTTPS needs port 80/443 (already taken) or a DNS-01 challenge, and there's no Caddy/libdns DNS provider plugin for Registro.br (`murilopreto.com.br`'s registrar/DNS host — confirmed via `dig NS`), so building one would've been its own project. Reusing the working nginx setup sidesteps that entirely.

**Architecture change for this:** the frontend's browser-side code used to call the Flask API directly via `NEXT_PUBLIC_API_URL` — fine on localhost, but a browser on any other machine can't resolve `localhost` back to the server. Fixed by adding Next.js **Route Handlers** (`frontend/src/app/api/{products,categories,scrape}/route.ts`, `frontend/src/app/api/products/[id]/history/route.ts`) that proxy server-side to Flask over the internal Docker network (`API_INTERNAL_URL=http://api:5000`, via the shared `frontend/src/lib/apiProxy.ts` helper). The browser now only ever talks to the Next.js server, same-origin, in both dev and prod — `frontend/src/lib/api.ts` calls relative `/api/...` paths instead of an absolute URL. This also means Flask (`api`) never needs a published host port at all, in dev *or* prod.

**Auth:** `POST /api/scrape` (only) checks an `x-scrape-token` header against `SCRAPE_SECRET` (server-only env var) before forwarding to Flask; 401 if missing/wrong. If `SCRAPE_SECRET` isn't set at all (the default for local dev), the check is skipped — no config needed to keep `docker compose up` working as before. `ScrapeButton.tsx` prompts for the password on first use (or after a 401) and caches it in `localStorage`. GET routes stay unauthenticated (public Lenovo price data).

**Frontend production build:** `frontend/Dockerfile` is now multi-stage — `dev` (unchanged, default for `docker-compose.yml`, explicitly pinned via `target: dev` since it's no longer the last stage) and `prod` (runs `next build`, then `next start` against the `output: "standalone"` bundle from `next.config.ts` — no bind mount, no dev tooling). Two bugs found and fixed by actually running the built images (not just `tsc`/lint): (1) Docker auto-sets `HOSTNAME=<container-id>` as an env var, which the standalone server misreads as its bind address and crash-loops on a failed DNS lookup — fixed with `ENV HOSTNAME=0.0.0.0` in the `prod` stage. (2) `docker-compose.prod.yml` initially had no explicit `image:` names, so building it silently overwrote the `outlet_monitor-api`/`outlet_monitor-frontend` tags the *dev* compose file also defaults to (same directory name) — fixed by giving the prod services explicit distinct image names (`outlet-monitor-api-prod`, `outlet-monitor-frontend-prod`).

**Files:**
- `docker-compose.prod.yml` — standalone compose file (not a `-f`-merged overlay, to avoid Compose's list-merge semantics for `ports:`), `api` (no published ports) + `frontend` (`target: prod`, published to `127.0.0.1:3000` only — reachable from nginx on the same host, never directly from the internet).
- `.env.prod.example` — documents `SCRAPE_SECRET` (generate with `openssl rand -hex 24`); real `.env.prod` is gitignored.
- `deploy/nginx-outlet-monitor.conf` — the third `server` block (reference copy) added to the server's existing `/etc/nginx/sites-available/murilopreto.com.br`, listening on `7716 ssl`, reusing the existing cert, `proxy_pass http://127.0.0.1:3000`.

**Bring-up:**
```bash
# on the server, in the repo directory
cp .env.prod.example .env.prod   # fill in SCRAPE_SECRET
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# append deploy/nginx-outlet-monitor.conf's server block to the existing site file, then:
sudo nginx -t && sudo systemctl reload nginx
```
Verify: `https://www.murilopreto.com.br:7716` loads the homepage; the existing default homepage on 80/443 is untouched; `curl -I http://127.0.0.1:5000` on the server still hits the *other* app, not this one (Flask here has no host port at all).

## Risks / things to watch
- The API is unauthenticated and only lightly gated (UA + Referer header check by an `openresty` edge WAF, confirmed in Phase 0) — it could still start requiring stronger checks (Akamai cookie, rate limiting) at any time without notice. If direct calls start failing, fall back to Playwright (already validated as working in the dev container) to re-derive the current request shape.
- Site markup/API can change without notice — scraper should fail loudly (clear error) rather than silently writing empty/garbage rows. In particular, treat an empty `products` array as a probable `pageFilterId`/`classificationGroupIds` staleness issue, not "0 items currently on sale."
- Be a polite client: manual runs at reasonable intervals (e.g. not more than a few times a day) avoids putting load on their infra and reduces risk of IP-level blocking.
