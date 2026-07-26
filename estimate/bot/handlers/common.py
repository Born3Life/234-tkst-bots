from __future__ import annotations

import asyncio
import logging
from base64 import b64encode

from aiogram import F, Router, types
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
MAX_CHUNKS = 15
MAX_PAGES = 30
MAX_TEXT_LEN = 4000


def is_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def strip_cmd(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


router = Router()

BOT_SPECIALTY = "estimate"
BOT_USERNAME = "@estimateTKST_bot"

SPECIALTY_INFO = {
    "accounting": {
        "name": "📐 Учёт и контроль",
        "desc": "Сметы, КС-2/КС-3, технадзор, документация, СНиП",
        "username": "@GroupTKST_bot",
    },
    "design": {
        "name": "🏗 Проектирование зданий",
        "desc": "AutoCAD, чертежи, АР/КР, записки, ГОСТ",
        "username": "@Group234TKST_bot",
    },
    "estimate": {
        "name": "📊 Сметное дело",
        "desc": "ФЕР, ТЕР, ГЭСН, индексы, ЛСР, КС-2, Гранд-Смета",
        "username": "@estimateTKST_bot",
    },
}


def mentioned(message: types.Message) -> bool:
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
        return True
    if message.text and BOT_USERNAME.lower() in message.text.lower():
        return True
    if message.caption and BOT_USERNAME.lower() in message.caption.lower():
        return True
    return False


@router.message(Command("start"))
async def handle_start(message: types.Message) -> None:
    text = (
        "📊 <b>Сметное дело — эксперт по сметам</b>\n\n"
        "Я помогаю с вопросами по дисциплине «Сметное дело»\n"
        "специальности «Строительство и эксплуатация зданий и сооружений».\n\n"
        "📝 <b>Что умею:</b>\n"
        "• Составляю и проверяю сметы (ЛСР, ОСР, ССРСС)\n"
        "• Анализирую КС-2, КС-3, КС-6а\n"
        "• Работаю с ФЕР, ТЕР, ГЭСН, индексами\n"
        "• Проверяю правильность расценок, НР, СП\n"
        "• Читаю фото смет и документов\n"
        "• Объясняю нормативную базу (МДС, Приказы Минстроя)\n"
        "• Консультирую по Гранд-Смете и другим программам\n\n"
        "📎 <b>Пришли фото сметы, PDF, Word или напиши вопрос</b>\n"
        "💾 <b>/word (текст)</b> — ответ в формате .docx"
    )
    await message.answer(text)


@router.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    text = (
        "💡 <b>Как пользоваться:</b>\n\n"
        "• Напиши вопрос по сметам — я отвечу\n"
        "• /ask (вопрос) — задать вопрос\n"
        "• /word (вопрос) — ответ в .docx\n"
        "• Пришли фото сметы/КС-2 — проанализирую\n"
        "• Пришли PDF со сметой — проверю\n\n"
        "👥 <b>В группе:</b>\n"
        "• /menu — кнопки со всеми направлениями\n"
        "• Нажми кнопку → напиши вопрос → я отвечу\n"
        "• Пришли файл/фото — обработаю\n"
        "• /word (вопрос) — ответ в формате .docx\n"
        "• /ask@bot (вопрос) — вызвать конкретного бота\n\n"
        "📌 <b>Примеры:</b> проверка сметы, подбор расценки, "
        "расчёт НР и СП, индексы пересчёта, КС-2, Гранд-Смета"
    )
    await message.answer(text)


@router.message(Command("about"))
async def handle_about(message: types.Message) -> None:
    text = (
        "🧠 <b>О боте</b>\n\n"
        "Модель: Google Gemma 4 26B\n"
        "Платформа: OpenRouter API\n"
        "Специализация: Сметное дело в строительстве\n"
        "Разряд: Инженер-сметчик\n\n"
        "Разработчик: @born3life"
    )
    await message.answer(text)


@router.message(Command("ping"))
async def handle_ping(message: types.Message) -> None:
    await message.answer("✅ Бот работает")


@router.message(Command("menu"))
async def handle_menu(message: types.Message) -> None:
    info = SPECIALTY_INFO[BOT_SPECIALTY]
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=info["name"], callback_data=f"info_{BOT_SPECIALTY}")],
    ])
    await message.answer(
        f"🎯 <b>{info['name']}</b>\n{info['desc']}\n\n"
        f"Нажми кнопку или напиши {info['username']} + вопрос",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("info_"))
async def handle_info_callback(callback: types.CallbackQuery) -> None:
    mode = callback.data.replace("info_", "")
    info = SPECIALTY_INFO.get(mode)
    if not info:
        await callback.answer("❌ Неизвестное направление")
        return
    await callback.message.edit_text(
        f"✅ <b>{info['name']}</b>\n{info['desc']}\n\n"
        f"Напиши: {info['username']} + твой вопрос\n"
        f"Или используй /ask@{info['username'].lstrip('@')} вопрос",
        reply_markup=None,
    )
    await callback.answer()


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
            caption = target.caption or "Что изображено на этом документе? Проанализируй подробно."
            answer = await ask(caption, image_base64=b64)
            await _send_result(message, answer, wait_msg, as_docx)
        except Exception:
            logger.exception("Error processing replied photo")
            await wait_msg.edit_text("❌ Ошибка при обработке изображения")
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
            pages = pdf_pages_as_base64(file_bytes, max_pages=MAX_PAGES)
            results = []
            for i, b64 in enumerate(pages, 1):
                await wait_msg.edit_text(f"⏳ Распознаю страницу {i}/{len(pages)}...")
                prompt = caption or "Прочитай и проанализируй этот сметный документ"
                try:
                    answer = await ask(prompt, image_base64=b64)
                    results.append(f"=== Страница {i} ===\n\n{answer}")
                except Exception:
                    logger.exception("Page %d failed", i)
                    results.append(f"=== Страница {i} ===\n\n⚠️ Ошибка распознавания")
                await asyncio.sleep(0.5)
            full = "\n\n".join(results)
        else:
            text = extract_text(file_bytes, ext)
            chunks = chunk_text(text)[:MAX_CHUNKS]
            results = []
            for i, chunk in enumerate(chunks, 1):
                await wait_msg.edit_text(f"⏳ Обрабатываю часть {i}/{len(chunks)}...")
                prompt = f"{caption}\n\n{chunk}" if caption else chunk
                try:
                    answer = await ask(prompt)
                    results.append(f"=== Часть {i} ===\n\n{answer}")
                except Exception:
                    logger.exception("Chunk %d failed", i)
                    results.append(f"=== Часть {i} ===\n\n⚠️ Ошибка обработки")
                await asyncio.sleep(0.5)
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

    text = strip_cmd(message.text)
    if not text:
        await message.answer(
            "❌ Напиши вопрос или ответь на сообщение с файлом/фото\n\n"
            "Пример: `/word проверь смету на завышение объёмов`"
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

    text = strip_cmd(message.text)
    if not text:
        await message.answer(
            "❌ Напиши вопрос или ответь на сообщение\n\n"
            "Пример: `/ask как применить индекс пересчёта к ФЕР`"
        )
        return

    wait_msg = await message.answer("⏳ Думаю...")
    try:
        answer = await ask(text)
        await _send_result(message, answer, wait_msg, as_docx=False)
    except Exception:
        logger.exception("Error processing /ask")
        await wait_msg.edit_text("❌ Ошибка. Попробуй ещё раз.")


@router.message(lambda msg: msg.document is not None)
async def handle_document(message: types.Message) -> None:
    if is_group(message) and not mentioned(message):
        return
    await _process_document(message, message.document, message.caption or "", as_docx=True)


@router.message()
async def handle_message(message: types.Message) -> None:
    if is_group(message) and not mentioned(message):
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
        caption = message.caption or "Что изображено на этом сметном документе? Проанализируй подробно."

        wait_msg = await message.answer("⏳ Анализирую изображение...")
        try:
            file = await message.bot.get_file(photo.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            b64 = b64encode(file_bytes.read()).decode()

            answer = await ask(caption, image_base64=b64)
            await _send_result(message, answer, wait_msg, as_docx=False)
        except Exception:
            logger.exception("Error processing photo")
            await wait_msg.edit_text("❌ Ошибка при обработке изображения. Попробуй ещё раз.")
