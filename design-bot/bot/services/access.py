from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
COUNTS_FILE = DATA_DIR / "daily_counts.json"
CACHE_FILE = DATA_DIR / "subscriptions_cache.json"

ADMIN_IDS = [7740217463, 5700759986]
DAILY_LIMIT = 3
ASSISTANT_BOT_URL = os.environ.get("ASSISTANT_BOT_URL", "")


def _get_today() -> str:
    return date.today().strftime("%Y%m%d")


def _load_counts() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not COUNTS_FILE.exists():
        return {}
    try:
        return json.loads(COUNTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_counts(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COUNTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_daily_count(user_id: int) -> int:
    counts = _load_counts()
    key = f"{user_id}_{_get_today()}"
    return counts.get(key, 0)


def increment_daily_count(user_id: int) -> None:
    counts = _load_counts()
    key = f"{user_id}_{_get_today()}"
    counts[key] = counts.get(key, 0) + 1
    old_keys = [k for k in counts if not k.endswith(_get_today())]
    for k in old_keys:
        counts.pop(k, None)
    _save_counts(counts)


def check_subscription(user_id: int, bot_key: str) -> bool:
    if is_admin(user_id):
        return True
    cache = _load_cache()
    entry = cache.get(str(user_id))
    if not entry:
        return False
    if entry.get("expires", 0) < time.time():
        return False
    return bot_key in entry.get("bots", [])


def can_access(user_id: int, bot_key: str) -> tuple[bool, str]:
    if is_admin(user_id):
        return True, ""

    if check_subscription(user_id, bot_key):
        return True, ""

    daily = get_daily_count(user_id)
    if daily < DAILY_LIMIT:
        return True, ""

    return False, (
        "Дневной лимит (3 вопроса) исчерпан.\n\n"
        "Купи подписку для доступа без ограничений:\n"
        "@AssistantAiGroup234_bot → /buy"
    )


async def sync_subscriptions() -> None:
    if not ASSISTANT_BOT_URL:
        return
    url = f"{ASSISTANT_BOT_URL}/api/subscriptions"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("Sync failed: status %d", resp.status)
                    return
                data = await resp.json()
                _save_cache(data)
                logger.info("Subscriptions synced (%d entries)", len(data))
    except Exception:
        logger.exception("Sync failed, using cache")
