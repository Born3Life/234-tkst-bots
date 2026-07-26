from __future__ import annotations

import logging
from base64 import b64encode

from aiogram import Router, types
from aiogram.filters import Command

from bot.services.docx_writer import create_answer_docx
from bot.services.file_reader import (
    chunk_text,
    extract_text,
    is_scanned_pdf,
    pdf_pages_as_base64,
)
from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

SUPPORTED_DOCS = {"pdf", "docx"}
MAX_CHUNKS = 5
MAX_TEXT_LEN = 4000


def is_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


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
        "📎 <b>Пришли фото, PDF, Word или напиши вопрос</b>\n"
        "💾 <b>/word (текст)</b> — ответ в формате .docx"
    )
    await message.answer(text)


@router.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    text = (
        "💡 <b>Как пользоваться:</b>\n\n"
        "• Напиши вопрос текстом — я отвечу\n"
        "• /ask (вопрос) — задать вопрос\n"
        "• /word (вопрос) — ответ в .docx\n"
        "• Пришли фото задания — прочитаю и решу\n"
        "• Пришли PDF или Word — извлеку текст и отвечу в .docx\n\n"
        "👥 <b>В группе:</b>\n"
        "• Ответь на сообщение командой /ask или /word\n"
        "• Бот обработает файл, фото или текст, на который ты ответил\n"
        "• Без команды бот в группе молчит\n\n"
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


async def process_replied(message: types.Message, as_docx: bool = False) -> None:
    target = message.reply_to_message
    if not target:
        return

    if target.text:
        wait_msg = await message.answer("⏳ Думаю...")
        try:
            answer = await ask(target.text)
            await _send_result(message, answer, wait_msg, as_docx)
        except Exception:
            logger.exception("Error processing replied text")
            await wait_msg.edit_text("❌ Ошибка")
        return

    if target.photo:
        wait_msg = await message.answer("⏳ Анализирую изображение...")
        try:
            photo = target.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            raw = await message.bot.download_file(file.file_path)
            b64 = b64encode(raw.read()).decode()
            caption = target.caption or "Что изображено на этом фото? Ответь подробно."
            answer = await ask(caption, image_base64=b64)
            await _send_result(message, answer, wait_msg, as_docx)
        except Exception:
            logger.exception("Error processing replied photo")
            await wait_msg.edit_text("❌ Ошибка при обработке фото")
        return

    if target.document:
        await _process_document(message, target.document, target.caption or "", as_docx)
        return

    await message.answer("❌ Нет текста, фото или файла для обработки")


async def _process_document(
    message: types.Message,
    doc: types.Document,
    caption: str,
    as_docx: bool = False,
) -> None:
    ext = doc.file_name.rsplit(".", 1)[-1].lower() if doc.file_name else ""
    if ext not in SUPPORTED_DOCS:
        await message.answer("❌ Поддерживаю только PDF и DOCX")
        return

    wait_msg = await message.answer("⏳ Читаю файл...")
    try:
        file = await message.bot.get_file(doc.file_id)
        raw = await message.bot.download_file(file.file_path)
        file_bytes = raw.read()

        if ext == "pdf" and is_scanned_pdf(file_bytes):
            pages = pdf_pages_as_base64(file_bytes)
            results = []
            for i, b64 in enumerate(pages, 1):
                await wait_msg.edit_text(f"⏳ Распознаю страницу {i}/{len(pages)}...")
                prompt = caption or "Прочитай и перепиши весь текст с этого изображения"
                answer = await ask(prompt, image_base64=b64)
                results.append(f"=== Страница {i} ===\n\n{answer}")
            full = "\n\n".join(results)
        else:
            text = extract_text(file_bytes, ext)
            chunks = chunk_text(text)[:MAX_CHUNKS]
            results = []
            for i, chunk in enumerate(chunks, 1):
                await wait_msg.edit_text(f"⏳ Обрабатываю часть {i}/{len(chunks)}...")
                prompt = f"{caption}\n\n{chunk}" if caption else chunk
                answer = await ask(prompt)
                results.append(f"=== Часть {i} ===\n\n{answer}")
            full = "\n\n".join(results)

        await _send_result(message, full, wait_msg, as_docx)
    except Exception:
        logger.exception("Error processing document")
        await wait_msg.edit_text("❌ Ошибка при обработке файла")


async def _send_result(
    message: types.Message,
    text: str,
    wait_msg: types.Message,
    as_docx: bool,
) -> None:
    if as_docx or len(text) > MAX_TEXT_LEN:
        docx_bytes = create_answer_docx(text)
        await message.answer_document(
            types.BufferedInputFile(docx_bytes.read(), filename="answer.docx"),
            caption="✅ Готово!",
        )
        await wait_msg.delete()
    else:
        await wait_msg.edit_text(text)


@router.message(Command("word"))
async def handle_word(message: types.Message) -> None:
    if message.reply_to_message:
        await process_replied(message, as_docx=True)
        return

    text = message.text.removeprefix("/word").strip()
    if not text:
        await message.answer(
            "❌ Напиши вопрос или ответь на сообщение с файлом/фото\n\n"
            "Пример: `/word перечисли СНиПы`"
        )
        return

    wait_msg = await message.answer("⏳ Думаю...")
    try:
        answer = await ask(text)
        docx_bytes = create_answer_docx(answer)
        await message.answer_document(
            types.BufferedInputFile(docx_bytes.read(), filename="answer.docx"),
            caption="✅ Готово!",
        )
        await wait_msg.delete()
    except Exception:
        logger.exception("Error processing /word")
        await wait_msg.edit_text("❌ Ошибка. Попробуй ещё раз.")


@router.message(Command("ask"))
async def handle_ask(message: types.Message) -> None:
    if message.reply_to_message:
        await process_replied(message, as_docx=False)
        return

    text = message.text.removeprefix("/ask").strip()
    if not text:
        await message.answer(
            "❌ Напиши вопрос или ответь на сообщение\n\n"
            "Пример: `/ask что такое КС-2?`"
        )
        return

    wait_msg = await message.answer("⏳ Думаю...")
    try:
        answer = await ask(text)
        await _send_result(message, answer, wait_msg, as_docx=False)
    except Exception:
        logger.exception("Error processing /ask")
        await wait_msg.edit_text("❌ Ошибка. Попробуй ещё раз.")


@router.message(lambda msg: msg.document is not None and not is_group(msg))
async def handle_document(message: types.Message) -> None:
    await _process_document(message, message.document, message.caption or "", as_docx=True)


@router.message()
async def handle_message(message: types.Message) -> None:
    if is_group(message):
        return

    if message.text:
        text = message.text
        if text.startswith("/"):
            return

        if message.caption:
            text = message.caption

        want_docx = any(kw in text.lower() for kw in ("ворд", "docx", ".docx", "в формате word", "документом"))

        wait_msg = await message.answer("⏳ Думаю...")
        try:
            answer = await ask(text)
            await _send_result(message, answer, wait_msg, as_docx=want_docx)
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
            await _send_result(message, answer, wait_msg, as_docx=False)
        except Exception:
            logger.exception("Error processing photo")
            await wait_msg.edit_text("❌ Ошибка при обработке фото. Попробуй ещё раз.")
