# Telegram notifier

Standalone messaging service. It knows nothing about the price monitor's
database or code — the only interface between the two is the HTTP API below.

## What it does

- Runs a Telegram bot (long polling): `/start` subscribes, `/parar` unsubscribes,
  `/ajuda` shows status and commands. Each has aliases (see below); anything else
  starting with `/` gets a "não conheço esse comando" reply.
- Keeps subscriber chat ids in its own SQLite file (`/data/subscribers.db`,
  backed by the `notifier-data` volume).
- Exposes an internal HTTP API on port `8000`, reachable from the other compose
  services as `http://notifier:8000`. Not published to the host.

Bot polling and HTTP API share one process and one asyncio loop; the bot is
started/stopped from the FastAPI lifespan.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Put it in the env file compose reads (`.env` for dev, `.env.prod` for prod):

   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   ```

3. `docker compose up -d --build notifier`
4. Send `/start` to your bot on Telegram.

## Bot commands

Only the first of each row appears in the Telegram menu; the rest are aliases
registered on the same handler.

| Action      | Menu command | Aliases                                                     |
| ----------- | ------------ | ----------------------------------------------------------- |
| Subscribe   | `/start`     | `/inscrever` `/assinar` `/iniciar` `/comecar`               |
| Pick lines  | `/produtos`  | `/filtros` `/seguir` `/linhas` `/escolher`                  |
| Unsubscribe | `/parar`     | `/stop` `/cancelar` `/cancel` `/sair` `/descadastrar` `/unsubscribe` |
| Help/status | `/ajuda`     | `/help` `/status` `/comandos`                               |

Command names are limited to `[a-z0-9_]` — Telegram has no accented commands and
python-telegram-bot rejects them at registration, so `/comecar` has no cedilla twin.

## Per-subscriber filters

`/start` and `/produtos` open an inline keyboard of Lenovo product lines. Tapping
one toggles it; `📋 Tudo` clears the selection.

**No selection means every change** — that is the default for a fresh subscriber
and the behaviour existing subscribers keep after upgrading. A subscriber with
filters only gets the slice of the report whose product names contain one of
their lines (case-insensitive substring), and is skipped entirely when nothing
matches.

Filtering lives entirely in this service: the monitor keeps posting the *full*
list of changes to `/notify` and knows nothing about who follows what.

The menu is seeded from `PRODUCT_LINES` and grows on its own — every `/notify`
payload is scanned and the leading token of a product name that no known line
covers is added to `known_lines`. So a new Lenovo family shows up in the menu
after its first price change, with no redeploy.

## API

### `POST /notify`

```jsonc
{
  "title": "Alerta de preços — Lenovo Outlet",   // optional header
  "changes": [
    {
      "name": "ThinkPad E14 Gen 5",
      "old_price": 5499.00,
      "new_price": 4799.00,
      "url": "https://www.lenovo.com/br/outlet/pt/..."  // optional
    },
    {
      "name": "ThinkPad T14s Gen 4",
      "new_price": 7299.00        // no old_price => rendered as a new listing
    }
  ]
}
```

Response:

```json
{ "subscribers": 12, "sent": 9, "skipped": 3, "failed": 0, "removed": 0 }
```

`skipped` counts subscribers whose filters matched nothing in this payload;
`removed` counts subscribers dropped because they blocked the bot.

### `GET /subscribers/count`

```json
{ "count": 12 }
```

### `GET /health`

```json
{ "status": "ok", "subscribers": 12 }
```

## How the price monitor calls it

Wired up in `src/outlet_monitor/`:

- `storage.changes_since_previous(conn)` diffs the two most recent scrape runs
  and returns price moves plus newly listed products.
- `notify.send_price_changes_async(changes)` hands the POST to a daemon thread,
  so `/scrape` returns without waiting on Telegram. Every failure is logged and
  swallowed — a notifier that is down never costs a price snapshot.
- Both scrape paths call it: `POST /scrape` and the scheduled scrape loop.

The `api` service has no `depends_on: notifier` on purpose; the two containers
restart independently. `NOTIFIER_URL=""` disables notifications entirely.

To trigger a broadcast by hand from inside the Docker network:

```bash
curl -X POST http://notifier:8000/notify \
  -H 'Content-Type: application/json' \
  -d '{"changes":[{"name":"ThinkPad E14","old_price":5499,"new_price":4799}]}'
```

## Environment variables

| Variable                  | Default                 | Purpose                              |
| ------------------------- | ----------------------- | ------------------------------------ |
| `TELEGRAM_BOT_TOKEN`      | — (required)            | BotFather token                      |
| `SUBSCRIBERS_DB_PATH`     | `/data/subscribers.db`  | SQLite location                      |
| `BROADCAST_DELAY_SECONDS` | `0.05`                  | Delay between sends (~20 msg/s)      |
| `PRODUCT_LINES`           | `ThinkPad,ThinkBook,IdeaPad,Yoga,Legion,LOQ,ThinkCentre,ThinkStation` | Comma-separated lines seeding the menu |
| `LOG_LEVEL`               | `INFO`                  | Logging level                        |
