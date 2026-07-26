from __future__ import annotations

import logging
from base64 import b64encode

from aiogram import Router, types
from aiogram.filters import Command

from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("start"))
async def handle_start(message: types.Message) -> None:
    text = (
        "📐 <b>Учёт и контроль — эксперт по строительству</b>\n\n"
        "Я помогаю с вопросами по дисциплине «Учёт и контроль»\n"
        "специальности «Строительство и эксплуатация зданий и сооружений».\n\n"
        "📝 <b>Что умею:</b>\n"
        "• Отвечаю на вопросы по учёту, сметам, СНиПам\n"
        "• Читаю фото заданий, тестов, текстов\n"
        "• Решаю тесты, разбираю задачи\n"
        "• Объясняю нормативные документы\n\n"
        "📸 <b>Пришли фото с заданием или просто напиши вопрос</b>"
    )
    await message.answer(text)


@router.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    text = (
        "💡 <b>Как пользоваться:</b>\n\n"
        "• Напиши вопрос текстом — я отвечу\n"
        "• Пришли фото задания — прочитаю и решу\n"
        "• Пришли фото теста — перепишу вопросы и дам ответы\n"
        "• Пришли фото конспекта — проверю или объясню\n\n"
        "📌 <b>Пример тем:</b> сметное дело, КС-2, КС-3, технадзор, "
        "исполнительная документация, журналы работ, СНиП, СП, "
        "контроль качества, приёмка работ, охрана труда"
    )
    await message.answer(text)


@router.message(Command("about"))
async def handle_about(message: types.Message) -> None:
    text = (
        "🧠 <b>О боте</b>\n\n"
        "Модель: Google Gemma 4 26B\n"
        "Платформа: OpenRouter API\n"
        "Специализация: Учёт и контроль в строительстве\n\n"
        "Разработчик: @born3life"
    )
    await message.answer(text)


@router.message()
async def handle_message(message: types.Message) -> None:
    if message.text:
        text = message.text
        if text.startswith("/"):
            return

        if message.caption:
            text = message.caption

        wait_msg = await message.answer("⏳ Думаю...")
        try:
            answer = await ask(text)
            await wait_msg.edit_text(answer)
        except Exception:
            logger.exception("Error processing text")
            await wait_msg.edit_text("❌ Ошибка. Попробуй ещё раз.")

    elif message.photo:
        photo = message.photo[-1]
        caption = message.caption or "Что изображено на этом фото? Ответь подробно."

        wait_msg = await message.answer("⏳ Анализирую изображение...")
        try:
            file = await message.bot.get_file(photo.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            b64 = b64encode(file_bytes.read()).decode()

            answer = await ask(caption, image_base64=b64)
            await wait_msg.edit_text(answer)
        except Exception:
            logger.exception("Error processing photo")
            await wait_msg.edit_text("❌ Ошибка при обработке фото. Попробуй ещё раз.")
