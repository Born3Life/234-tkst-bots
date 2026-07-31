from __future__ import annotations

import asyncio
import logging
import sys
from os import getenv
from pathlib import Path

from aiohttp import ClientSession, web
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).parent.parent / ".env")

BOT_TOKEN: str | None = getenv("DESIGN_BOT_TOKEN")
TELEGRAM_PROXY: str | None = getenv("TELEGRAM_PROXY")
PORT = int(getenv("PORT", "8080"))
RENDER_URL: str | None = getenv("RENDER_EXTERNAL_URL")


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


async def _keep_alive() -> None:
    if not RENDER_URL:
        return
    logger.info("keep-alive enabled: %s (ping every 10 min)", RENDER_URL)
    try:
        while True:
            await asyncio.sleep(600)
            try:
                async with ClientSession() as s:
                    await s.get(RENDER_URL, timeout=10)
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def main() -> None:
    if not BOT_TOKEN:
        msg = "DESIGN_BOT_TOKEN is not set in .env"
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

    keep_alive_task = asyncio.create_task(_keep_alive())

    for attempt in range(3):
        wh = await bot.get_webhook_info()
        logger.info("Webhook check (%d): url=%s, pending=%s", attempt + 1, wh.url, wh.pending_update_count)
        if not wh.url:
            break
        await bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1.0)

    logger.info("design-bot started")
    try:
        await dp.start_polling(bot)
    finally:
        keep_alive_task.cancel()
        await bot.session.close()
        await health_runner.cleanup()
