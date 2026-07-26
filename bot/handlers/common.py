from __future__ import annotations

import logging
from base64 import b64encode

from aiogram import Router, types
from aiogram.filters import Command

from bot.services.docx_writer import create_answer_docx
from bot.services.file_reader import chunk_text, extract_text
from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

SUPPORTED_DOCS = {"pdf", "docx"}
MAX_CHUNKS = 5

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
        "• Читаю PDF и Word файлы, делаю выжимку в .docx\n"
        "• Объясняю нормативные документы\n\n"
        "📎 <b>Пришли фото, PDF, Word или просто напиши вопрос</b>"
    )
    await message.answer(text)


@router.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    text = (
        "💡 <b>Как пользоваться:</b>\n\n"
        "• Напиши вопрос текстом — я отвечу\n"
        "• Пришли фото задания — прочитаю и решу\n"
        "• Пришли PDF или Word — извлеку текст и отвечу в .docx\n"
        "• Пришли фото теста — перепишу вопросы и дам ответы\n\n"
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


@router.message(lambda msg: msg.document is not None)
async def handle_document(message: types.Message) -> None:
    doc = message.document
    ext = doc.file_name.rsplit(".", 1)[-1].lower() if doc.file_name else ""

    if ext not in SUPPORTED_DOCS:
        await message.answer("❌ Поддерживаю только PDF и DOCX")
        return

    wait_msg = await message.answer("⏳ Читаю файл...")
    try:
        file = await message.bot.get_file(doc.file_id)
        raw = await message.bot.download_file(file.file_path)
        file_bytes = raw.read()

        text = extract_text(file_bytes, ext)
        chunks = chunk_text(text)[:MAX_CHUNKS]

        caption = message.caption or ""
        results = []

        for i, chunk in enumerate(chunks, 1):
            await wait_msg.edit_text(f"⏳ Обрабатываю часть {i}/{len(chunks)}...")
            prompt = f"{caption}\n\n{chunk}" if caption else chunk
            answer = await ask(prompt)
            results.append(f"=== Часть {i} ===\n\n{answer}")

        full = "\n\n".join(results)
        docx_bytes = create_answer_docx(full)

        await message.answer_document(
            types.BufferedInputFile(docx_bytes.read(), filename="answer.docx"),
            caption="✅ Готово!",
        )
        await wait_msg.delete()
    except Exception:
        logger.exception("Error processing document")
        await wait_msg.edit_text("❌ Ошибка при обработке файла")


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
