from __future__ import annotations

import logging
import os

import re

import aiohttp

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/v1/chat/completions"
TEXT_MODEL = "deepseek-chat"
VISION_MODEL = "deepseek-vl2"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

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
    "СТРОГИЕ ПРАВИЛА ОФОРМЛЕНИЯ ОТВЕТОВ — НАРУШЕНИЕ ЗАПРЕЩЕНО (штраф за нарушение):\n"
    "- ЗАПРЕЩЕНО использовать markdown: ###, **, *, _, ---, ===. ТОЛЬКО чистый текст.\n"
    "- ЗАПРЕЩЕНО копировать нумерацию из текста пользователя. Если пользователь "
    "прислал текст с '1.', '2.' и т.д. — ИГНОРИРУЙ эту нумерацию, пиши свою.\n"
    "- Нумерованные списки: используй 'N. ' (цифра + точка + пробел). "
    "НИКОГДА не дублируй номер: пиши '1. Текст', а не '1. 1. Текст'.\n"
    "- Маркированные списки: только дефис (-). Запрещены *, •, →, ➡.\n"
    "- Выделение текста: ЗАПРЕЩЕНО. Никаких жирного, курсива, кавычек для выделения.\n"
    "- Стрелки: только → (Юникод). Запрещены ->, =>, \\rightarrow, ➡.\n"
    "- Абзацы: разделяй пустой строкой. Не пиши стены текста.\n"
    "- Заголовки: обычный текст на отдельной строке, без знаков препинания в конце.\n\n"
    "Пример правильного оформления:\n"
    "Этапы контроля\n"
    "- Входной контроль материалов\n"
    "- Операционный контроль работ\n"
    "- Приёмочный контроль\n\n"
    "Входной контроль → проверка сертификатов.\n\n"
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


async def ask(prompt: str, image_base64: str | None = None) -> str:
    if image_base64:
        transcribed = await _transcribe_image(image_base64)
        if transcribed:
            prompt = f"Пользователь отправил фото с текстом:\n\n{transcribed}\n\n---\nЗапрос пользователя: {prompt}"
        else:
            prompt = f"{prompt}\n\n(фото не удалось распознать)"

    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.3,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=payload, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                data = await resp.json()

        if "error" in data:
            logger.warning("DeepSeek error: %s", data["error"])
            return f"❌ Ошибка модели: {data['error']}"

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        return _clean_response(content) or "❌ Пустой ответ от модели."
    except Exception:
        logger.exception("DeepSeek request failed")
        return "❌ Ошибка при запросе к DeepSeek. Баланс закончился?"


def _clean_response(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?m)^###\s*', '', text)
    text = re.sub(r'(?m)^(\d+)\.\s+\1\.', r'\1.', text)
    text = re.sub(r'(?m)^(\d+)\.\t+\d+\.', r'\1.', text)
    text = re.sub(r'(?m)^\*\s+', '- ', text)
    text = re.sub(r'(?m)^\s{2,}- ', '- ', text)
    text = re.sub(r'(?m)^\s{2,}(\d+\.)', r'\1', text)
    return text.strip()
