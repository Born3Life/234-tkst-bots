from __future__ import annotations

import logging
from os import getenv

import aiohttp

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemma-4-26b-a4b-it:free"

SYSTEM_PROMPT = (
    "Ты — профессиональный эксперт по дисциплине «Учёт и контроль в строительстве» "
    "специальности «Строительство и эксплуатация зданий и сооружений». "
    "Ты глубоко разбираешься в: сметном деле, нормативной документации (СНиП, ГОСТ, СП), "
    "контроле качества строительных работ, авторском и техническом надзоре, "
    "исполнительной документации, приёмке работ, учёте материалов и конструкций, "
    "проверке смет и актов выполненных работ (КС-2, КС-3, КС-6), "
    "журналах производства работ (общий и специальные журналы), "
    "лабораторном контроле, геодезическом контроле, "
    "правилах техники безопасности и охраны труда в строительстве.\n\n"
    "Отвечай подробно, профессионально, со ссылками на нормативные документы. "
    "Если пользователь отправил фото с заданием, текстом или тестом — "
    "внимательно прочитай изображение, перепиши вопрос и под ним дай правильный ответ "
    "с пояснением. Форматируй ответ понятно, используй нумерацию вопросов."
)


async def ask(prompt: str, image_base64: str | None = None) -> str:
    key = getenv("OPENROUTER_API_KEY")
    if not key:
        return "❌ OPENROUTER_API_KEY не настроен в .env"

    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_base64:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            }
        )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                data = await resp.json()

        if "error" in data:
            err = data["error"]
            logger.warning("OpenRouter error: %s", err.get("message", err))
            return "❌ Сервис временно недоступен. Попробуй позже."

        content = data["choices"][0]["message"]["content"] or ""
        return content.strip() or "❌ Пустой ответ от модели."
    except Exception:
        logger.exception("OpenRouter request failed")
        return "❌ Ошибка при запросе. Попробуй позже."
