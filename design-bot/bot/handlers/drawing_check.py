from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.services.file_reader import pdf_pages_as_base64
from bot.services.formatter import md_to_html
from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

router = Router()


class DrawingCheck(StatesGroup):
    waiting = State()


exit_kb_draw = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="🔙 Выйти", callback_data="drawing_exit")],
])


@router.message(Command("check"))
async def cmd_check(message: types.Message, state: FSMContext) -> None:
    await state.set_state(DrawingCheck.waiting)
    await message.answer(
        "📐 <b>Проверка чертежа</b>\n\n"
        "Пришли фото чертежа, схему или PDF с проектной документацией.\n"
        "Я проверю соответствие ГОСТ, СП, ЕСКД и СПДС.",
        reply_markup=exit_kb_draw,
    )


@router.callback_query(F.data == "drawing_exit")
async def on_drawing_exit(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Проверка чертежей отменена. /check — начать заново.")
    await callback.answer()


@router.message(DrawingCheck.waiting, Command("start", "help", "cancel", "stop", "menu"))
async def cmd_exit_drawing(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Выход. /check — проверить чертёж, /help — помощь.")


@router.message(DrawingCheck.waiting, F.photo)
async def check_photo(message: types.Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    wait = await message.answer("🔄 Анализирую чертёж...")

    try:
        from base64 import b64encode

        from aiogram import Bot

        bot: Bot = message.bot
        file = await bot.get_file(file_id)
        photo_bytes = await bot.download_file(file.file_path)
        b64 = b64encode(photo_bytes.read()).decode()

        prompt = (
            "Ты — эксперт по проектированию зданий (ПГС). "
            "Проверь приложенный чертёж на соответствие ГОСТ, СП, ЕСКД, СПДС.\n\n"
            "В ответе укажи:\n"
            "1. **Что проверено** (тип чертежа, масштаб, разрезы)\n"
            "2. **Замечания** — что не соответствует нормам\n"
            "3. **Рекомендации** — как исправить\n"
            "4. **Что выполнено верно**\n\n"
            "Будь конкретен, указывай номера ГОСТ/СП."
        )
        result = await ask(prompt, image_base64=b64)

        await wait.edit_text(
            f"📋 <b>Результат проверки чертежа</b>\n\n{md_to_html(result)}",
            reply_markup=exit_kb_draw,
        )
    except Exception:
        logger.exception("Drawing check failed")
        await wait.edit_text("❌ Ошибка при анализе чертежа. Попробуй другое изображение.")
    finally:
        await state.clear()


@router.message(DrawingCheck.waiting, F.document)
async def check_document(message: types.Message, state: FSMContext) -> None:
    if message.document.mime_type not in ("application/pdf",):
        await message.answer("❌ Поддерживаются только PDF-файлы с чертежами.")
        return

    wait = await message.answer("🔄 Анализирую PDF...")
    try:
        pages = await pdf_pages_as_base64(message.document.file_id, message.bot, max_pages=10)
        if not pages:
            await wait.edit_text("❌ Не удалось прочитать PDF.")
            await state.clear()
            return

        prompt = (
            "Ты — эксперт по проектированию зданий (ПГС). "
            "Проверь приложенный PDF с проектной документацией "
            "на соответствие ГОСТ, СП, ЕСКД, СПДС.\n\n"
            "В ответе укажи:\n"
            "1. **Что проверено** (листы, разделы)\n"
            "2. **Замечания** — что не соответствует нормам\n"
            "3. **Рекомендации** — как исправить\n"
            "4. **Что выполнено верно**\n\n"
            "Будь конкретен, указывай номера ГОСТ/СП."
        )
        result = await ask(prompt, image_base64=pages[0])

        await wait.edit_text(
            f"📋 <b>Результат проверки PDF</b>\n\n{md_to_html(result)}",
            reply_markup=exit_kb_draw,
        )
    except Exception:
        logger.exception("Drawing check failed")
        await wait.edit_text("❌ Ошибка при анализе PDF.")
    finally:
        await state.clear()


@router.message(DrawingCheck.waiting)
async def check_no_media(message: types.Message, state: FSMContext) -> None:
    await message.answer("❌ Пришли фото чертежа или PDF-файл.")
