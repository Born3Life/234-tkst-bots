from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _user_path(user_id: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"coursework_{user_id}.json"


def load(user_id: int) -> dict | None:
    path = _user_path(user_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save(user_id: int, data: dict) -> None:
    path = _user_path(user_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete(user_id: int) -> None:
    path = _user_path(user_id)
    if path.exists():
        path.unlink()


def new_project(user_id: int, topic: str) -> dict:
    project = {
        "topic": topic,
        "created_at": int(time.time()),
        "sections": [],
        "structure": "",
    }
    save(user_id, project)
    return project


async def generate_structure(topic: str) -> str:
    prompt = (
        f"Ты — преподаватель курса «Проектирование зданий».\n\n"
        f"Студент пишет курсовой проект на тему: «{topic}».\n"
        f"Составь подробную структуру пояснительной записки.\n\n"
        f"Формат ответа — строго:\n"
        f"1. Название первого раздела\n"
        f"  1.1. Название подраздела\n"
        f"  1.2. Название подраздела\n"
        f"2. Название второго раздела\n"
        f"  2.1. ...\n\n"
        f"Разделы должны включать:\n"
        f"- Введение\n"
        f"- Архитектурно-строительный раздел\n"
        f"- Конструктивный раздел\n"
        f"- Технико-экономические показатели\n"
        f"- Заключение\n"
        f"- Список литературы\n\n"
        f"Не добавляй лишнего текста, только структуру."
    )
    return await ask(prompt)


def parse_structure(text: str) -> list[dict]:
    sections = []
    for line in text.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            continue
        sections.append({
            "number": stripped,
            "content": "",
            "done": False,
        })
    return sections


async def generate_section_prompt(topic: str, section_number: str, section_title: str) -> str:
    return (
        f"Ты — инженер-проектировщик. Напиши содержание раздела "
        f"«{section_title}» для курсового проекта на тему «{topic}».\n\n"
        f"Требования:\n"
        f"- Объём: 2-5 абзацев\n"
        f"- Используй профессиональную терминологию\n"
        f"- Ссылайся на ГОСТ, СП, СНиП где уместно\n"
        f"- Используй **жирный** для ключевых терминов\n"
        f"- Используй ### для подзаголовков внутри раздела\n"
        f"- Если нужны формулы/расчёты — напиши их текстом\n\n"
        f"Напиши только содержание раздела, без лишних слов."
    )


async def generate_project_docx(user_id: int, use_sections: list[dict] | None = None) -> str:
    project = load(user_id)
    if not project:
        return ""

    sections_text = []
    for s in (use_sections or project.get("sections", [])):
        if s.get("content"):
            sections_text.append(f"{s['number']}\n{s['content']}")

    prompt = (
        f"Собери готовую пояснительную записку курсового проекта "
        f"на тему «{project['topic']}» из следующих разделов:\n\n"
        f"{chr(10).join(sections_text)}\n\n"
        f"Оформи как единый документ:\n"
        f"- В начале — титульная информация (тема проекта)\n"
        f"- Разделы идут по порядку\n"
        f"- ### перед каждым разделом\n"
        f"- **жирный** для ключевых терминов\n"
        f"- В конце — список литературы\n"
        f"- Без лишних комментариев, только текст"
    )
    return await ask(prompt)
