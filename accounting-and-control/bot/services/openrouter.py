from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)

# После запуска Colab заменить на URL из вывода ноутбука
API_URL = "http://localhost:11434/api/chat"
MODEL = "llava"

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
    "с пояснением. Форматируй ответ понятно, используй нумерацию вопросов.\n\n"
    "Правила оформления ответов:\n"
    "- НЕ используй звёздочки (*) для выделения текста. Вместо **жирного** просто пиши текст как есть.\n"
    "- Для стрелок используй символ → (например: Материал → Работа → Конструкция), "
    "а не LaTeX-конструкции вроде \\rightarrow.\n"
    "- Для заголовков используй просто текст на новой строке без решёток (#).\n"
    "- Для списков используй дефис (-) без звёздочек.\n"
    "- Не используй Markdown-форматирование."
)


async def ask(prompt: str, image_base64: str | None = None) -> str:
    content = prompt

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
        },
    }
    if image_base64:
        payload["messages"][1]["images"] = [image_base64]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                data = await resp.json()

        if "error" in data:
            logger.warning("Ollama error: %s", data["error"])
            return "❌ Модель недоступна. Проверь Colab."

        content = data["message"]["content"] or ""
        return content.strip() or "❌ Пустой ответ от модели."
    except Exception:
        logger.exception("Ollama request failed")
        return "❌ Ошибка при запросе к модели. Проверь Colab."
