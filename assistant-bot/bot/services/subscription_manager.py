from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SUBS_FILE = DATA_DIR / "subscriptions.json"

ADMIN_IDS = [7740217463, 5700759986]

BOT_KEYS = {
    "design": {"name": "Проектирование зданий", "price": 100},
    "estimate": {"name": "Сметное дело", "price": 100},
    "accounting": {"name": "Учёт и контроль", "price": 100},
    "smr": {"name": "СМР", "price": 100},
}

ALL_BOTS_PRICE = 300
ALL_BOTS = list(BOT_KEYS.keys())

SUBSCRIPTION_DAYS = 30


def _load() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SUBS_FILE.exists():
        return {}
    try:
        return json.loads(SUBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_subscription(user_id: int, bot_keys: list[str]) -> None:
    data = _load()
    user_id_str = str(user_id)
    expires = int(time.time()) + SUBSCRIPTION_DAYS * 86400

    if user_id_str in data:
        existing = data[user_id_str]
        new_bots = list(set(existing.get("bots", []) + bot_keys))
        existing_expires = existing.get("expires", 0)
        if existing_expires > time.time():
            existing["expires"] = existing_expires + SUBSCRIPTION_DAYS * 86400
        else:
            existing["expires"] = expires
        existing["bots"] = new_bots
    else:
        data[user_id_str] = {
            "user_id": user_id,
            "expires": expires,
            "bots": bot_keys,
        }

    _save(data)


def remove_subscription(user_id: int) -> None:
    data = _load()
    user_id_str = str(user_id)
    data.pop(user_id_str, None)
    _save(data)


def get_subscription(user_id: int) -> dict | None:
    data = _load()
    entry = data.get(str(user_id))
    if not entry:
        return None
    if entry.get("expires", 0) < time.time():
        data.pop(str(user_id), None)
        _save(data)
        return None
    return entry


def check_subscription(user_id: int, bot_key: str) -> bool:
    entry = get_subscription(user_id)
    if not entry:
        return False
    return bot_key in entry.get("bots", []) or "all" in entry.get("bots", [])


def get_all_active() -> dict:
    data = _load()
    now = time.time()
    expired = [uid for uid, entry in data.items() if entry.get("expires", 0) < now]
    for uid in expired:
        data.pop(uid, None)
    if expired:
        _save(data)
    return {int(k): v for k, v in data.items()}
