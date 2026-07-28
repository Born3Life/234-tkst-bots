from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

EMPTY_SCHEDULE: dict[str, list[dict[str, str]]] = {d: [] for d in WEEKDAYS}


class ScheduleManager:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._remind_times: dict[int, str] = {}

    def _file_path(self, chat_id: int) -> Path:
        return DATA_DIR / f"schedule_{chat_id}.json"

    def _remind_file_path(self, chat_id: int) -> Path:
        return DATA_DIR / f"remind_time_{chat_id}.txt"

    def get_schedule(self, chat_id: int) -> dict[str, list[dict[str, str]]]:
        path = self._file_path(chat_id)
        if not path.exists():
            return dict(EMPTY_SCHEDULE)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for d in WEEKDAYS:
                if d not in data:
                    data[d] = []
            return data
        except (json.JSONDecodeError, OSError):
            return dict(EMPTY_SCHEDULE)

    def save_schedule(self, chat_id: int, schedule: dict[str, list[dict[str, str]]]) -> None:
        path = self._file_path(chat_id)
        clean = {}
        for d in WEEKDAYS:
            clean[d] = schedule.get(d, [])
        path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_lesson(self, chat_id: int, weekday: str, time_str: str, subject: str, room: str = "", teacher: str = "", week_type: str = "") -> None:
        schedule = self.get_schedule(chat_id)
        if weekday not in schedule:
            schedule[weekday] = []
        schedule[weekday].append({
            "time": time_str,
            "subject": subject,
            "room": room,
            "teacher": teacher,
            "week_type": week_type,
        })
        schedule[weekday].sort(key=lambda x: x["time"])
        self.save_schedule(chat_id, schedule)

    def remove_lesson(self, chat_id: int, weekday: str, index: int) -> bool:
        schedule = self.get_schedule(chat_id)
        if weekday not in schedule:
            return False
        if index < 0 or index >= len(schedule[weekday]):
            return False
        schedule[weekday].pop(index)
        self.save_schedule(chat_id, schedule)
        return True

    def set_schedule_from_text(self, chat_id: int, text: str) -> None:
        lines = text.strip().split("\n")
        schedule = dict(EMPTY_SCHEDULE)
        current_day = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            line_lower = line.lower()
            for i, ru in enumerate(WEEKDAYS_RU):
                if ru in line_lower or WEEKDAYS[i] in line_lower:
                    current_day = WEEKDAYS[i]
                    break
            if not current_day:
                continue
            parts = line.split(",")
            if len(parts) >= 2:
                time_str = parts[0].strip()
                subject = parts[1].strip()
                room = ""
                teacher = ""
                week_type = ""
                if len(parts) >= 3:
                    room = parts[2].strip()
                if len(parts) >= 4:
                    teacher = parts[3].strip()
                schedule[current_day].append({
                    "time": time_str,
                    "subject": subject,
                    "room": room,
                    "teacher": teacher,
                    "week_type": week_type,
                })

        for d in WEEKDAYS:
            schedule[d].sort(key=lambda x: x["time"])

        self.save_schedule(chat_id, schedule)

    def get_today_schedule(self, chat_id: int) -> list[dict[str, str]]:
        today_idx = date.today().weekday()
        weekday = WEEKDAYS[today_idx]
        schedule = self.get_schedule(chat_id)
        return schedule.get(weekday, [])

    def get_today_schedule_text(self, chat_id: int) -> str:
        lessons = self.get_today_schedule(chat_id)
        if not lessons:
            return "Сегодня пар нет."

        ru_day = WEEKDAYS_RU[date.today().weekday()]
        lines = [f"Расписание на {ru_day}:"]
        for lesson in lessons:
            parts = [lesson["time"], lesson["subject"]]
            if lesson.get("room"):
                parts.append(f"(ауд. {lesson['room']})")
            if lesson.get("week_type"):
                parts.append(f"[{lesson['week_type']}]")
            lines.append("- " + " — ".join(parts))
        return "\n".join(lines)

    def schedule_to_text(self, chat_id: int) -> str:
        schedule = self.get_schedule(chat_id)
        lines = []
        for i, ru in enumerate(WEEKDAYS_RU):
            day_schedule = schedule[WEEKDAYS[i]]
            if not day_schedule:
                lines.append(f"{ru}: пар нет")
                continue
            day_lines = [f"{ru}:"]
            for lesson in day_schedule:
                parts = [lesson["time"], lesson["subject"]]
                if lesson.get("room"):
                    parts.append(f"ауд. {lesson['room']}")
                if lesson.get("teacher"):
                    parts.append(f"({lesson['teacher']})")
                day_lines.append("  " + " — ".join(parts))
            lines.append("\n".join(day_lines))
        return "\n\n".join(lines)

    def get_remind_time(self, chat_id: int) -> str:
        path = self._remind_file_path(chat_id)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return "08:00"

    def set_remind_time(self, chat_id: int, time_str: str) -> None:
        path = self._remind_file_path(chat_id)
        path.write_text(time_str.strip(), encoding="utf-8")

    def get_all_chat_ids(self) -> list[int]:
        ids = set()
        for f in DATA_DIR.glob("schedule_*.json"):
            try:
                ids.add(int(f.stem.split("_")[1]))
            except (IndexError, ValueError):
                pass
        for f in DATA_DIR.glob("remind_time_*.txt"):
            try:
                ids.add(int(f.stem.split("_")[2]))
            except (IndexError, ValueError):
                pass
        return list(ids)

    def load_chat_schedules(self) -> None:
        for chat_id in self.get_all_chat_ids():
            remind = self.get_remind_time(chat_id)
            if remind:
                self._remind_times[chat_id] = remind
