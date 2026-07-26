from __future__ import annotations

import logging
import sys
from os import getenv
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).parent.parent / ".env")

BOT_TOKEN: str | None = getenv("ESTIMATE_BOT_TOKEN")
TELEGRAM_PROXY: str | None = getenv("TELEGRAM_PROXY")
PORT = int(getenv("PORT", "8080"))


async def health(_request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def _start_health() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("health endpoint on 0.0.0.0:%d", PORT)
    return runner


async def main() -> None:
    if not BOT_TOKEN:
        msg = "ESTIMATE_BOT_TOKEN is not set in .env"
        raise RuntimeError(msg)

    health_runner = await _start_health()

    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.enums import ParseMode

    from bot.handlers import routers

    session = AiohttpSession(proxy=TELEGRAM_PROXY, timeout=600) if TELEGRAM_PROXY else AiohttpSession(timeout=600)

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    for router in routers:
        dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("estimate-bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await health_runner.cleanup()
