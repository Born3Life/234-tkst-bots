from __future__ import annotations

import asyncio
import logging
from base64 import b64encode

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from bot.services.docx_writer import create_answer_docx
from bot.services.formatter import md_to_html
from bot.services.file_reader import (
    extract_text,
    is_scanned_pdf,
    pdf_pages_as_base64,
)
from bot.services.openrouter import ask
from bot.services.access import can_access, increment_daily_count

logger = logging.getLogger(__name__)

SUPPORTED_DOCS = {"pdf", "docx"}
MAX_PAGES = 30
MAX_TEXT_LEN = 4000

BATCH_TIMEOUT = 1.5
_batch: dict[tuple[int, int], list[types.Message]] = {}
_batch_tasks: dict[tuple[int, int], asyncio.Task] = {}


def _batch_key(message: types.Message) -> tuple[int, int]:
    return (message.chat.id, message.from_user.id)


async def _run_batch(bot: Bot, messages: list[types.Message]) -> None:
    await asyncio.sleep(BATCH_TIMEOUT)
    msg = messages[0]
    key = _batch_key(msg)
    _batch.pop(key, None)
    _batch_tasks.pop(key, None)

    allowed, reason = can_access(msg.from_user.id, BOT_KEY)
    if not allowed:
        await msg.answer(reason)
        return
    increment_daily_count(msg.from_user.id)

    if len(messages) == 1:
        m = messages[0]
        if m.text and not m.text.startswith("/"):
            await _handle_single_text(m)
        elif m.photo:
            await _handle_single_photo(m)
        elif m.document:
            await _handle_single_document(m)
        return

    text_parts: list[str] = []
    photo_count = 0
    file_descs: list[str] = []

    for m in messages:
        if m.text and not m.text.startswith("/"):
            text_parts.append(m.text)
        elif m.caption:
            text_parts.append(m.caption)
        if m.photo:
            photo_count += 1
        if m.document and m.document.file_name:
            file_descs.append(m.document.file_name)

    prompt_parts = []
    if text_parts:
        prompt_parts.append("Вопросы:\n" + "\n".join(text_parts))
    if file_descs:
        prompt_parts.append("Прикреплённые файлы: " + ", ".join(file_descs))
    if photo_count:
        prompt_parts.append(f"Фотографий: {photo_count}")

    prompt = "\n".join(prompt_parts)
    wait = await bot.send_message(msg.chat.id, "Думаю...")
    try:
        answer = await ask(prompt)
        await _send_result(msg, answer, wait, as_docx=False)
    except Exception:
        logger.exception("Batch error")
        await wait.edit_text("Ошибка при обработке.")


async def _handle_single_text(message: types.Message) -> None:
    allowed, reason = can_access(message.from_user.id, BOT_KEY)
    if not allowed:
        await message.answer(reason)
        return
    increment_daily_count(message.from_user.id)

    text = message.text
    if text.startswith("/"):
        return

    want_docx = any(kw in text.lower() for kw in ("ворд", "docx", ".docx", "в формате word", "документом"))

    wait = await message.answer("Думаю...")
    try:
        answer = await ask(text)
        await _send_result(message, answer, wait, as_docx=want_docx)
    except Exception:
        logger.exception("Error")
        await wait.edit_text("Ошибка.")


async def _handle_single_photo(message: types.Message) -> None:
    allowed, reason = can_access(message.from_user.id, BOT_KEY)
    if not allowed:
        await message.answer(reason)
        return
    increment_daily_count(message.from_user.id)

    photo = message.photo[-1]
    caption = message.caption or "Что изображено на этом чертеже или схеме? Проанализируй подробно."

    wait = await message.answer("Думаю...")
    try:
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        b64 = b64encode(file_bytes.read()).decode()
        answer = await ask(caption, image_base64=b64)
        await _send_result(message, answer, wait, as_docx=False)
    except Exception:
        logger.exception("Error")
        await wait.edit_text("Ошибка.")


async def _handle_single_document(message: types.Message) -> None:
    allowed, reason = can_access(message.from_user.id, BOT_KEY)
    if not allowed:
        await message.answer(reason)
        return
    increment_daily_count(message.from_user.id)

    await _process_document(message, message.document, message.caption or "", as_docx=True)


def is_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def strip_cmd(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


router = Router()

BOT_SPECIALTY = "design"
BOT_KEY = "design"
BOT_USERNAME = "@Group234TKST_bot"

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
    "smr": {
        "name": "🔧 Строительно-монтажные работы",
        "desc": "Технология СМР, ППР, стройплощадка, охрана труда, исполнительная документация",
        "username": "@smrTKST_bot",
    },
    "assistant": {
        "name": "🤖 Помощник группы",
        "desc": "Расписание, память 5 дней, помощь с учёбой",
        "username": "@AssistantAiGroup234_bot",
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
        "🏗 <b>Проектирование зданий — эксперт по проектированию</b>\n\n"
        "Я помогаю с вопросами по дисциплине «Проектирование зданий»\n"
        "специальности «Строительство и эксплуатация зданий и сооружений».\n\n"
        "📐 <b>Что умею:</b>\n"
        "• Помогаю с AutoCAD: команды, чертежи, печать, оформление\n"
        "• Анализирую фото чертежей и схем\n"
        "• Читаю PDF и Word с проектной документацией\n"
        "• Составляю пояснительные записки\n"
        "• Объясняю конструктивные решения и узлы\n"
        "• Ссылаюсь на ГОСТ, СП, СНиП, ЕСКД, СПДС\n\n"
        "📎 <b>Пришли фото чертежа, PDF проекта или напиши вопрос</b>\n"
        "💾 <b>/word (текст)</b> — ответ в формате .docx\n"
        "📚 <b>/coursework</b> — конструктор курсового проекта\n"
        "🔍 <b>/check</b> — проверка чертежа на соответствие ГОСТ и СП\n"
        "🧮 <b>/calc</b> — строительный калькулятор"
    )
    await message.answer(text)


@router.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    text = (
        "💡 <b>Как пользоваться:</b>\n\n"
        "• Напиши вопрос по проектированию — я отвечу\n"
        "• /ask (вопрос) — задать вопрос\n"
        "• /word (вопрос) — ответ в .docx\n"
        "• Пришли фото чертежа — проанализирую\n"
        "• Пришли PDF с проектом — извлеку данные и отвечу в .docx\n\n"
        "👥 <b>В группе:</b>\n"
        "• /menu — кнопки со всеми направлениями\n"
        "• Нажми кнопку → напиши вопрос → я отвечу\n"
        "• Пришли файл/фото — обработаю\n"
        "• /word (вопрос) — ответ в формате .docx\n"
        "• /ask@bot (вопрос) — вызвать конкретного бота\n"
        "• /coursework — конструктор курсового проекта\n"
        "• /check — проверка чертежа на ГОСТ/СП\n"
        "• /calc — строительный калькулятор\n\n"
        "📌 <b>Примеры тем:</b> AutoCAD команды, чертежи АР/КР, "
        "пояснительная записка, конструктивные схемы, фундаменты, "
        "узлы и детали, расчёт нагрузок, нормы проектирования"
    )
    await message.answer(text)


@router.message(Command("about"))
async def handle_about(message: types.Message) -> None:
    text = (
        "🧠 <b>О боте</b>\n\n"
        "Модель: Google Gemma 4 26B\n"
        "Платформа: OpenRouter API\n"
        "Специализация: Проектирование зданий\n"
        "Уровень: Инженер-проектировщик\n\n"
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
        [types.InlineKeyboardButton(text="🤖 Помощник группы", url="https://t.me/AssistantAiGroup234_bot")],
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
            caption = target.caption or "Что изображено на этом чертеже или схеме? Проанализируй подробно."
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
        await message.answer("❌ Поддерживаю только PDF и DOCX. Для DWG/DXF отправь скриншот чертежа.")
        return

    wait_msg = await message.answer("⏳ Читаю файл...")
    try:
        file = await message.bot.get_file(doc.file_id)
        raw = await asyncio.wait_for(message.bot.download_file(file.file_path), timeout=180)
        file_bytes = raw.read()

        if ext == "pdf":
            if not is_scanned_pdf(file_bytes):
                text = extract_text(file_bytes, ext)
                prompt = f"{caption}\n\nДокумент:\n{text}" if caption else f"Документ:\n{text}"
                await wait_msg.edit_text("⏳ Анализирую документ...")
                try:
                    answer = await ask(prompt)
                    full = answer
                except Exception:
                    logger.exception("Error processing PDF text")
                    full = "⚠️ Ошибка при анализе документа."
            else:
                pages = pdf_pages_as_base64(file_bytes, max_pages=MAX_PAGES)
                results = []
                for i, b64 in enumerate(pages, 1):
                    await wait_msg.edit_text(f"⏳ Распознаю страницу {i}/{len(pages)}...")
                    prompt = caption or "Прочитай и перепиши весь текст и данные с этого чертежа или документа"
                    try:
                        answer = await ask(prompt, image_base64=b64)
                        results.append(f"=== Страница {i} ===\n\n{answer}")
                    except Exception:
                        logger.exception("Page %d failed", i)
                        results.append(f"=== Страница {i} ===\n\n⚠️ Ошибка распознавания страницы")
                    await asyncio.sleep(0.5)
                full = "\n\n".join(results)
        else:
            text = extract_text(file_bytes, ext)
            prompt = f"{caption}\n\nДокумент:\n{text}" if caption else f"Документ:\n{text}"
            await wait_msg.edit_text("⏳ Анализирую документ...")
            try:
                answer = await ask(prompt)
                full = answer
            except Exception:
                logger.exception("Error processing full document")
                full = "⚠️ Ошибка при анализе документа. Попробуй ещё раз."

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
        html = md_to_html(text)
        await wait_msg.edit_text(html, parse_mode=ParseMode.HTML)


@router.message(Command("word"))
async def handle_word(message: types.Message) -> None:
    allowed, reason = can_access(message.from_user.id, BOT_KEY)
    if not allowed:
        await message.answer(reason)
        return
    increment_daily_count(message.from_user.id)

    if message.reply_to_message:
        await process_replied(message, as_docx=True)
        return

    text = strip_cmd(message.text)
    if not text:
        await message.answer(
            "❌ Напиши вопрос или ответь на сообщение с файлом/фото\n\n"
            "Пример: `/word состав структуры пояснительной записки`"
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
    allowed, reason = can_access(message.from_user.id, BOT_KEY)
    if not allowed:
        await message.answer(reason)
        return
    increment_daily_count(message.from_user.id)

    if message.reply_to_message:
        await process_replied(message, as_docx=False)
        return

    text = strip_cmd(message.text)
    if not text:
        await message.answer(
            "❌ Напиши вопрос или ответь на сообщение\n\n"
            "Пример: `/ask как настроить лист в AutoCAD для печати А3`"
        )
        return

    wait_msg = await message.answer("⏳ Думаю...")
    try:
        answer = await ask(text)
        await _send_result(message, answer, wait_msg, as_docx=False)
    except Exception:
        logger.exception("Error processing /ask")
        await wait_msg.edit_text("❌ Ошибка. Попробуй ещё раз.")


@router.message()
async def handle_message(message: types.Message) -> None:
    if is_group(message) and not mentioned(message):
        return

    if message.text and message.text.startswith("/"):
        return

    key = _batch_key(message)

    if key in _batch_tasks:
        _batch_tasks[key].cancel()

    if key not in _batch:
        _batch[key] = []
    _batch[key].append(message)

    _batch_tasks[key] = asyncio.create_task(_run_batch(message.bot, _batch[key]))
