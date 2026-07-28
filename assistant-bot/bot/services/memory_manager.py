from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
MEMORY_DAYS = 5
MEMORY_SECONDS = MEMORY_DAYS * 24 * 3600
MAX_MEMORY_ENTRIES = 50


class MemoryManager:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _file_path(self, chat_id: int) -> Path:
        return DATA_DIR / f"memory_{chat_id}.json"

    def add_entry(self, chat_id: int, role: str, content: str) -> None:
        path = self._file_path(chat_id)
        entries = []
        if path.exists():
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                entries = []

        now = int(time.time())
        entries = [e for e in entries if now - e.get("timestamp", 0) < MEMORY_SECONDS]
        entries.append({"role": role, "content": content[:500], "timestamp": now})

        if len(entries) > MAX_MEMORY_ENTRIES:
            entries = entries[-MAX_MEMORY_ENTRIES:]

        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_context(self, chat_id: int) -> str:
        path = self._file_path(chat_id)
        if not path.exists():
            return ""

        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""

        now = int(time.time())
        entries = [e for e in entries if now - e.get("timestamp", 0) < MEMORY_SECONDS]
        if not entries:
            return ""

        lines = []
        for e in entries:
            label = "Студент" if e["role"] == "user" else "Ассистент"
            lines.append(f"{label}: {e['content']}")

        return "\n".join(lines)

    def clear(self, chat_id: int) -> None:
        path = self._file_path(chat_id)
        if path.exists():
            path.unlink()

    def clean_all(self) -> None:
        now = int(time.time())
        for f in DATA_DIR.glob("memory_*.json"):
            try:
                entries = json.loads(f.read_text(encoding="utf-8"))
                entries = [e for e in entries if now - e.get("timestamp", 0) < MEMORY_SECONDS]
                if entries:
                    f.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
                else:
                    f.unlink()
            except (json.JSONDecodeError, OSError):
                f.unlink()
