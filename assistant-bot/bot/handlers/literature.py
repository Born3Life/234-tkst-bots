from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from bot.services.formatter import md_to_html
from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

router = Router()

FOCUS = "строительству, проектированию, сметному делу, учёту и контролю качества"


@router.message(Command("gost"))
async def cmd_gost(message: types.Message) -> None:
    topic = message.text.removeprefix("/gost").strip()
    if not topic:
        await message.answer(
            "📚 <b>Генератор списка литературы</b>\n\n"
            "Напиши тему, по которой нужны нормативные документы.\n"
            "Например: <code>/gost фундаменты</code>"
        )
        return

    wait = await message.answer("⏳ Ищу нормативные документы...")
    try:
        prompt = (
            f"Ты — эксперт по {FOCUS}.\n\n"
            f"Составь список нормативных документов (ГОСТ, СП, СНиП, РД, приказы Минстроя, МДС, ФЕР) "
            f"по теме: «{topic}».\n\n"
            f"Формат ответа:\n"
            f"### Раздел\n"
            f"- **СП 22.13330.2016** — Основания зданий и сооружений\n"
            f"- **ГОСТ 25100-2020** — Грунты. Классификация\n\n"
            f"Группируй документы по разделам. Укажи полное название и область применения. "
            f"Не добавляй лишнего текста."
        )
        result = await ask(prompt)

        await wait.edit_text(
            f"📚 <b>Нормативные документы: {md_to_html(topic)}</b>\n\n{md_to_html(result)}\n\n"
            f"───\n/gost (тема) — новый поиск"
        )
    except Exception:
        logger.exception("GOST search failed")
        await wait.edit_text("❌ Ошибка. Попробуй ещё раз.")
