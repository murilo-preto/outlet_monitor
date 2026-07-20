# Setup

Outlet Watch is a Lenovo Brazil outlet price tracker: a Flask API that scrapes
Lenovo's outlet listing API and stores snapshots in SQLite, and a Next.js
frontend that shows price history per product, grouped by category (ThinkPad,
IdeaPad, Yoga, etc). Everything runs in Docker; there's nothing to install on
the host besides Docker itself.

## Requirements

- Docker Engine with the Compose plugin (`docker compose version` — v2 or
  later)
- For a public deployment: a domain, and a reverse proxy already capable of
  terminating TLS for it (nginx, Caddy, or similar). This app does not
  terminate TLS itself.

## 1. Clone

```bash
git clone https://github.com/<you>/outlet_monitor.git
cd outlet_monitor
```

## 2. Local development

If you just want to run this on your own machine, this is the whole setup:

```bash
docker compose up -d --build
```

- Frontend: <http://localhost:3000>
- API: <http://localhost:5000>

No further configuration is needed. Source is bind-mounted, so edits on the
host are picked up live (`next dev` for the frontend, no rebuild needed for
Python changes to the API — restart the `api` container to pick those up).
Skip to [Common operations](#common-operations) if this is all you need.

## 3. Production deployment

This is the `git clone` → `docker compose build` → set up the reverse proxy
→ `docker compose up` flow, using the separate `docker-compose.prod.yml`
(not merged with the dev file — it's a complete, standalone definition of the
production stack).

### 3.1 Configure environment

```bash
cp .env.prod.example .env.prod
```

Edit `.env.prod`:

| Variable | Description |
|---|---|
| `SCRAPE_SECRET` | Password required to trigger a scrape (`POST /api/scrape`) from the internet. Generate one with `openssl rand -hex 24`. If left unset, the scrape endpoint is unauthenticated — fine for local dev, not recommended once this is public. |
| `HOURS_BETWEEN_FETCH` | How often, in hours, the API automatically scrapes and stores a new price snapshot in the background, independent of any manual "Atualizar preços" clicks. Defaults to `24` if unset. |

`.env.prod` is gitignored — never commit it.

### 3.2 Build

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod build
```

This builds the API image and the frontend's **production** target (`next
build` + `next start` against a standalone output — no dev server, no source
bind mount).

### 3.3 Set up the reverse proxy

`docker-compose.prod.yml` deliberately does **not** publish anything to the
public internet:
- `api` (Flask) publishes no host port at all — it's only reachable from
  `frontend` over the internal Docker network. The frontend's own `/api/*`
  routes proxy to it server-side.
- `frontend` (Next.js) publishes to `127.0.0.1:3001` only — reachable from a
  reverse proxy on the same host, not directly from outside. (Not the port
  your domain is actually served on — see the note below.)

You need a reverse proxy on the host that terminates TLS for your domain and
forwards to `127.0.0.1:3001`, preserving the `Host` header. `deploy/nginx-outlet-monitor.conf`
is a working example (nginx, reusing an existing certbot certificate, served
on a non-default port, `7716`). Adapt `listen`, `server_name`, and
`ssl_certificate*` to your own domain/port/cert, then either add it as its
own site or append it as an extra `server {}` block into wherever your
domain is already configured, and:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Any reverse proxy works as long as it terminates TLS and forwards to
`127.0.0.1:3001` — Caddy, Apache, Traefik, etc. If you have no existing
web server and ports 80/443 are free on the host, Caddy is the simplest
option since it can obtain and renew a certificate automatically with a
one-line config (`your-domain { reverse_proxy 127.0.0.1:3001 }`).

> **Why the internal port (`3001`) is different from the public port
> (`7716` in the example):** a `listen 7716 ssl;` directive with no host
> binds the *wildcard* address, which already covers `127.0.0.1:7716` —
> Docker can't then also bind that same host:port for the container. Pick
> any free internal port for `docker-compose.prod.yml`'s `ports:` line
> (`127.0.0.1:<internal-port>:3000`) and point `proxy_pass` at that same
> `<internal-port>`; it never needs to match the public-facing port, and
> nothing outside the host ever talks to it directly. If you change it from
> the `3001` default, update both `docker-compose.prod.yml` and your nginx
> (or other proxy) config to match.

### 3.4 Start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 3.5 Verify

```bash
curl -I https://your-domain[:port]/
```

Should return `200`. Open it in a browser, switch categories, click a
product to see its price chart. Click "Atualizar preços" to trigger a
scrape — the first time, it'll prompt for the `SCRAPE_SECRET` password
(remembered in the browser afterwards).

## Common operations

- Logs: `docker compose -f docker-compose.prod.yml logs -f`
- Stop (data persists): `docker compose -f docker-compose.prod.yml down`
- Run the backend test suite: `docker compose run --rm api pytest -q`
- Seed the database with synthetic price history for local UI testing (not
  real Lenovo data, not run by CI): `docker compose run --rm api python
  scripts/seed_db.py --reset`
- Manually trigger a scrape from the host:
  `curl -X POST -H "x-scrape-token: $SCRAPE_SECRET" http://127.0.0.1:3001/api/scrape`
- Price history lives in the `outlet-monitor-data` named Docker volume
  (`data/price_history.db` inside it) — survives `down`/`up`; only removed
  with `docker compose down -v`.
- Redeploying after a `git pull`: repeat steps 3.2 and 3.4
  (`build` then `up -d`).

## Architecture at a glance

- **`api`** (Flask/Python) — scrapes Lenovo's outlet API on request, stores
  snapshots in SQLite. In production, never exposed on a host port; only
  `frontend` can reach it, over the internal Docker network.
- **`frontend`** (Next.js) — the UI, plus a thin server-side proxy layer
  (`src/app/api/*` Route Handlers) that forwards browser requests to `api`.
  This is the only service a reverse proxy ever needs to point at.

See `PLAN.md` for the full design history and reasoning behind these choices.
