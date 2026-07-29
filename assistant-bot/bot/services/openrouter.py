from __future__ import annotations

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/v1/chat/completions"
TEXT_MODEL = "deepseek-chat"
VISION_MODEL = "deepseek-vl2"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

SYSTEM_PROMPT = (
    "Ты — умный ассистент учебной группы. Твоя задача — помогать студентам с вопросами по учёбе, "
    "напоминать о расписании, отвечать на вопросы по домашним заданиям, объяснять сложные темы.\n\n"
    "Ты можешь:\n"
    "- Отвечать на вопросы по любым учебным дисциплинам\n"
    "- Объяснять сложные темы простым языком\n"
    "- Помогать с домашними заданиями (но не решать их полностью)\n"
    "- Подсказывать где искать информацию\n"
    "- Напоминать о парах по расписанию\n\n"
    "ФОРМАТИРОВАНИЕ ОТВЕТОВ — используй Markdown:\n"
    "- Заголовки: ### перед названием раздела.\n"
    "- Жирный текст: **текст** для ключевых терминов и названий.\n"
    "- Курсив: *текст* для выделения.\n"
    "- Маркированные списки: начинай строку с дефиса (-).\n"
    "- Нумерованные списки: '1. ' (цифра + точка + пробел).\n"
    "- Код: `текст` в обратных кавычках.\n"
    "- Стрелки: → (Юникод).\n"
    "- Абзацы: разделяй пустой строкой.\n\n"
    "Пример оформления:\n"
    "### Тема раздела\n"
    "- **Первый пункт** — описание\n"
    "- Второй пункт — *уточнение*\n\n"
)


async def _transcribe_image(image_base64: str) -> str:
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Перепиши весь текст с этого изображения максимально точно и полностью, ничего не добавляя от себя. Только текст который ты видишь."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                ],
            },
        ],
        "stream": False,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=payload, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                data = await resp.json()
        if "error" in data:
            logger.warning("Vision model error: %s", data["error"])
            return ""
        return (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
    except Exception:
        logger.exception("Transcription failed")
        return ""


async def ask(prompt: str, image_base64: str | None = None, memory_context: str = "") -> str:
    if image_base64:
        transcribed = await _transcribe_image(image_base64)
        if transcribed:
            prompt = f"Пользователь отправил фото с текстом:\n\n{transcribed}\n\n---\nЗапрос пользователя: {prompt}"
        else:
            prompt = f"{prompt}\n\n(фото не удалось распознать)"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    if memory_context:
        messages.append({"role": "system", "content": f"Контекст предыдущих разговоров (последние 5 дней):\n{memory_context}"})

    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": TEXT_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.5,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=payload, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                data = await resp.json()

        if "error" in data:
            logger.warning("DeepSeek error: %s", data["error"])
            return f"Ошибка модели: {data['error']}"

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        return content or "Пустой ответ от модели."
    except Exception:
        logger.exception("DeepSeek request failed")
        return "Ошибка при запросе к DeepSeek."

