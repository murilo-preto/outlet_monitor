"""Telegram messaging service.

One process, two jobs:
  * a long-polling Telegram bot handling /start and /parar
  * an internal HTTP API the price monitor calls when it detects a change

Both share the asyncio loop that uvicorn owns, so the bot is started and
stopped from the FastAPI lifespan.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import store
from .bot import build_application
from .broadcast import broadcast
from .schemas import CountResponse, NotifyRequest, NotifyResponse

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# httpx logs every request URL at INFO — and PTB puts the bot token in the path,
# so that would spill the token into `docker compose logs`.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    application = build_application()

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    app.state.bot = application.bot
    logger.info("bot polling started (%d subscribers)", store.count_subscribers())

    try:
        yield
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("bot polling stopped")


app = FastAPI(title="Outlet Monitor Notifier", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "subscribers": store.count_subscribers()}


@app.get("/subscribers/count", response_model=CountResponse)
async def subscribers_count():
    return CountResponse(count=store.count_subscribers())


@app.post("/notify", response_model=NotifyResponse)
async def notify(payload: NotifyRequest):
    bot = getattr(app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="bot is not ready yet")

    result = await broadcast(bot, payload)
    logger.info("notify: %s", result)
    return NotifyResponse(**result)
