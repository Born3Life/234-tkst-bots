from __future__ import annotations

import asyncio
import logging
from asyncio import CancelledError
from base64 import b64encode
from datetime import datetime

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command

from bot.services.context import memory_mgr, schedule_mgr
from bot.services.docx_writer import create_answer_docx
from bot.services.file_reader import (
    extract_text,
    is_scanned_pdf,
    pdf_pages_as_base64,
)
from bot.services.openrouter import ask as deepseek_ask
from bot.services.schedule_manager import WEEKDAYS_RU

logger = logging.getLogger(__name__)

router = Router()

SUPPORTED_DOCS = {"pdf", "docx"}
MAX_PAGES = 30
MAX_TEXT_LEN = 4000

_reminder_tasks: dict[int, asyncio.Task] = {}


def is_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


def ru_to_weekday(ru: str) -> str | None:
    mapping = {
        "пн": "monday", "понедельник": "monday", "пн.": "monday",
        "вт": "tuesday", "вторник": "tuesday", "вт.": "tuesday",
        "ср": "wednesday", "среда": "wednesday", "ср.": "wednesday",
        "чт": "thursday", "четверг": "thursday", "чт.": "thursday",
        "пт": "friday", "пятница": "friday", "пт.": "friday",
        "сб": "saturday", "суббота": "saturday", "сб.": "saturday",
        "вс": "sunday", "воскресенье": "sunday", "вс.": "sunday",
    }
    return mapping.get(ru.strip().lower())


async def start_reminder(bot: Bot, chat_id: int) -> None:
    if chat_id in _reminder_tasks:
        _reminder_tasks[chat_id].cancel()

    async def reminder_loop():
        while True:
            try:
                remind_time_str = schedule_mgr.get_remind_time(chat_id)
                parts = remind_time_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0

                now = datetime.now()
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= now:
                    target = target.replace(day=target.day + 1)

                wait_seconds = (target - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                schedule_text = schedule_mgr.get_today_schedule_text(chat_id)
                msg = f"Доброе утро!\n\n{schedule_text}"
                await bot.send_message(chat_id, msg)
            except CancelledError:
                break
            except Exception:
                logger.exception("Reminder error")
                await asyncio.sleep(60)

    _reminder_tasks[chat_id] = asyncio.create_task(reminder_loop())


async def restore_reminders(bot: Bot, sm: object) -> None:
    for chat_id in schedule_mgr.get_all_chat_ids():
        schedule = schedule_mgr.get_schedule(chat_id)
        if any(schedule[d] for d in schedule):
            await start_reminder(bot, chat_id)


@router.message(Command("start"))
async def handle_start(message: types.Message) -> None:
    text = (
        "Привет! Я помощник учебной группы.\n\n"
        "Что я умею:\n"
        "- Помню историю диалогов за последние 5 дней\n"
        "- Храню расписание и напоминаю о парах каждый день\n"
        "- Могу прочитать расписание с фото или PDF и сохранить его\n"
        "- Отвечаю на вопросы по учёбе\n\n"
        "Команды:\n"
        "/schedule — расписание на сегодня\n"
        "/fullschedule — полное расписание на неделю\n"
        "/setschedule — (админ) загрузить расписание (ответь на фото/файл)\n"
        "/addlesson — (админ) добавить пару\n"
        "/removelesson — (админ) удалить пару\n"
        "/setremind — (админ) установить время напоминания\n"
        "/clearmemory — очистить историю диалогов\n"
        "/menu — другие боты группы"
    )
    await message.answer(text)


@router.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    text = (
        "Команды:\n"
        "/schedule — расписание на сегодня\n"
        "/fullschedule — полное расписание\n"
        "/setschedule — (админ) загрузить расписание (ответь на фото/файл с расписанием)\n"
        "/addlesson день время предмет [ауд] — добавить пару\n"
        "  Пример: /addlesson понедельник 09:00 Математика 301\n"
        "/removelesson день номер — удалить пару\n"
        "  Пример: /removelesson понедельник 1\n"
        "/setremind ЧЧ:ММ — время ежедневного напоминания\n"
        "  Пример: /setremind 07:45\n"
        "/clearmemory — очистить историю\n"
        "/menu — другие боты"
    )
    await message.answer(text)


@router.message(Command("menu"))
async def handle_menu(message: types.Message) -> None:
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Проектирование зданий", url="https://t.me/Group234TKST_bot")],
        [types.InlineKeyboardButton(text="Сметное дело", url="https://t.me/estimateTKST_bot")],
        [types.InlineKeyboardButton(text="Учёт и контроль", url="https://t.me/GroupTKST_bot")],
        [types.InlineKeyboardButton(text="СМР", url="https://t.me/Group234SMRTKST_bot")],
    ])
    await message.answer("Другие боты группы:", reply_markup=kb)


@router.message(Command("schedule"))
async def handle_schedule(message: types.Message) -> None:
    text = schedule_mgr.get_today_schedule_text(message.chat.id)
    await message.answer(text)


@router.message(Command("fullschedule"))
async def handle_fullschedule(message: types.Message) -> None:
    text = schedule_mgr.schedule_to_text(message.chat.id)
    if not text.strip():
        text = "Расписание не задано. Админ может загрузить его через /setschedule"
    await message.answer(text)


@router.message(Command("setschedule"))
async def handle_setschedule(message: types.Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Эта команда только для админов группы.")
        return

    target = message.reply_to_message
    if not target:
        await message.answer("Ответь на сообщение с фото расписания или файлом (PDF).")
        return

    try:
        if target.photo:
            photo = target.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            raw = await message.bot.download_file(file.file_path)
            b64 = b64encode(raw.read()).decode()
            await message.answer("Анализирую расписание...")
            result = await deepseek_ask(
                "Из этого изображения извлеки расписание пар. "
                "Для каждого дня недели укажи время и название предмета. "
                "Формат: день_недели, время, предмет, аудитория(если есть). "
                "Если день не указан, определи по контексту. "
                "Верни данные в формате:\n"
                "понедельник\n"
                "09:00, Математика, 301\n"
                "10:45, Физика, 205\n"
                "вторник\n"
                "...",
                image_base64=b64,
            )
            if result:
                schedule_mgr.set_schedule_from_text(message.chat.id, result)
                await message.answer(f"Расписание сохранено:\n\n{schedule_mgr.get_today_schedule_text(message.chat.id)}")
                await start_reminder(message.bot, message.chat.id)
            else:
                await message.answer("Не удалось распознать расписание. Попробуй более чёткое фото.")

        elif target.document:
            ext = target.document.file_name.rsplit(".", 1)[-1].lower() if target.document.file_name else ""
            if ext not in SUPPORTED_DOCS:
                await message.answer("Поддерживаю только PDF и DOCX.")
                return
            file = await message.bot.get_file(target.document.file_id)
            raw = await message.bot.download_file(file.file_path)
            file_bytes = raw.read()

            if ext == "pdf" and is_scanned_pdf(file_bytes):
                pages = pdf_pages_as_base64(file_bytes, max_pages=5)
                result = ""
                for b64 in pages:
                    part = await deepseek_ask("Извлеки расписание с этого изображения. Формат: день_недели, время, предмет", image_base64=b64)
                    result += part + "\n"
            else:
                text = extract_text(file_bytes, ext)
                result = await deepseek_ask(f"Извлеки расписание из текста и верни в формате:\nдень_недели\nвремя, предмет, аудитория\n\nТекст:\n{text}")

            if result:
                schedule_mgr.set_schedule_from_text(message.chat.id, result)
                await message.answer(f"Расписание сохранено:\n\n{schedule_mgr.get_today_schedule_text(message.chat.id)}")
                await start_reminder(message.bot, message.chat.id)
            else:
                await message.answer("Не удалось распознать расписание.")
        else:
            await message.answer("Ответь на фото или файл с расписанием.")
    except Exception:
        logger.exception("Error processing schedule")
        await message.answer("Ошибка при обработке расписания.")


@router.message(Command("addlesson"))
async def handle_addlesson(message: types.Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Эта команда только для админов группы.")
        return

    parts = message.text.split(maxsplit=4)
    if len(parts) < 4:
        await message.answer("Формат: /addlesson день время предмет [аудитория]\nПример: /addlesson понедельник 09:00 Математика 301")
        return

    weekday_ru = parts[1]
    time_str = parts[2]
    subject = parts[3]
    room = parts[4] if len(parts) > 4 else ""

    weekday = ru_to_weekday(weekday_ru)
    if not weekday:
        await message.answer(f"Неизвестный день недели: {weekday_ru}. Используй: пн, вт, ср, чт, пт, сб, вс")
        return

    schedule_mgr.add_lesson(message.chat.id, weekday, time_str, subject, room)
    await message.answer(f"Добавлено: {weekday_ru} {time_str} — {subject}" + (f" ({room})" if room else ""))
    await start_reminder(message.bot, message.chat.id)


@router.message(Command("removelesson"))
async def handle_removelesson(message: types.Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Эта команда только для админов группы.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /removelesson день номер\nПример: /removelesson понедельник 1\nНомер можно узнать через /fullschedule")
        return

    weekday_ru = parts[1]
    try:
        index = int(parts[2]) - 1
    except ValueError:
        await message.answer("Номер должен быть числом.")
        return

    weekday = ru_to_weekday(weekday_ru)
    if not weekday:
        await message.answer(f"Неизвестный день: {weekday_ru}")
        return

    if schedule_mgr.remove_lesson(message.chat.id, weekday, index):
        await message.answer("Пара удалена.")
        await start_reminder(message.bot, message.chat.id)
    else:
        await message.answer("Неверный номер. Используй /fullschedule чтобы увидеть номера пар.")


@router.message(Command("setremind"))
async def handle_setremind(message: types.Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Эта команда только для админов группы.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /setremind ЧЧ:ММ\nПример: /setremind 07:45")
        return

    time_str = parts[1].strip()
    try:
        parts_time = time_str.split(":")
        hour = int(parts_time[0])
        minute = int(parts_time[1]) if len(parts_time) > 1 else 0
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Неверный формат времени. Используй ЧЧ:ММ (например 07:45).")
        return

    schedule_mgr.set_remind_time(message.chat.id, time_str)
    await start_reminder(message.bot, message.chat.id)
    await message.answer(f"Время напоминания установлено на {time_str}.")


@router.message(Command("clearmemory"))
async def handle_clearmemory(message: types.Message) -> None:
    memory_mgr.clear(message.chat.id)
    await message.answer("История диалогов очищена.")


@router.message(Command("word"))
async def handle_word(message: types.Message) -> None:
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Напиши вопрос после /word\nПример: /word расскажи о теореме Пифагора")
        return

    wait_msg = await message.answer("Думаю...")
    try:
        answer = await deepseek_ask(text[1])
        docx_bytes = create_answer_docx(answer)
        await message.answer_document(
            types.BufferedInputFile(docx_bytes.read(), filename="answer.docx"),
            caption="Готово!",
        )
        await wait_msg.delete()
    except Exception:
        logger.exception("Error processing /word")
        await wait_msg.edit_text("Ошибка.")


@router.message()
async def handle_message(message: types.Message) -> None:
    if message.text and message.text.startswith("/"):
        return

    wait_msg = await message.answer("Думаю...")
    try:
        if message.text:
            user_text = message.text

            context = memory_mgr.get_context(message.chat.id)
            memory_mgr.add_entry(message.chat.id, "user", user_text)

            today_schedule = schedule_mgr.get_today_schedule_text(message.chat.id)
            if "расписание" in user_text.lower() or "пары" in user_text.lower():
                answer = today_schedule
                if "помен" in user_text.lower() or "измен" in user_text.lower() or "исправ" in user_text.lower():
                    if await is_admin(message.bot, message.chat.id, message.from_user.id):
                        answer = "Напиши /addlesson чтобы добавить пару или /setschedule чтобы загрузить новое расписание."
                    else:
                        answer = "Изменить расписание может только админ группы."
            else:
                answer = await deepseek_ask(user_text, memory_context=context)

            memory_mgr.add_entry(message.chat.id, "assistant", answer)
            await _send_result(message, answer, wait_msg)

        elif message.photo:
            photo = message.photo[-1]
            caption = message.caption or ""
            file = await message.bot.get_file(photo.file_id)
            raw = await message.bot.download_file(file.file_path)
            b64 = b64encode(raw.read()).decode()

            memory_mgr.add_entry(message.chat.id, "user", f"[Фото] {caption}")

            if "расписание" in caption.lower():
                result = await deepseek_ask(
                    "Извлеки расписание с этого изображения. Формат: день_недели, время, предмет, аудитория",
                    image_base64=b64,
                )
                if result:
                    schedule_mgr.set_schedule_from_text(message.chat.id, result)
                    answer = f"Расписание сохранено:\n\n{schedule_mgr.get_today_schedule_text(message.chat.id)}"
                    await start_reminder(message.bot, message.chat.id)
                else:
                    answer = "Не удалось распознать расписание."
            else:
                context = memory_mgr.get_context(message.chat.id)
                answer = await deepseek_ask(caption or "Что на этом изображении?", image_base64=b64, memory_context=context)

            memory_mgr.add_entry(message.chat.id, "assistant", answer)
            await _send_result(message, answer, wait_msg)

        elif message.document:
            ext = message.document.file_name.rsplit(".", 1)[-1].lower() if message.document.file_name else ""
            if ext not in SUPPORTED_DOCS:
                await message.answer("Поддерживаю только PDF и DOCX.")
                return

            file = await message.bot.get_file(message.document.file_id)
            raw = await message.bot.download_file(file.file_path)
            file_bytes = raw.read()
            caption = message.caption or ""

            memory_mgr.add_entry(message.chat.id, "user", f"[Файл {message.document.file_name}] {caption}")

            if "расписание" in caption.lower():
                if ext == "pdf" and is_scanned_pdf(file_bytes):
                    pages = pdf_pages_as_base64(file_bytes, max_pages=5)
                    result = ""
                    for b64 in pages:
                        part = await deepseek_ask("Извлеки расписание с этого изображения. Формат: день_недели, время, предмет", image_base64=b64)
                        result += part + "\n"
                else:
                    text = extract_text(file_bytes, ext)
                    result = await deepseek_ask(f"Извлеки расписание из текста. Формат:\nдень_недели\nвремя, предмет, аудитория\n\n{text}")

                if result:
                    schedule_mgr.set_schedule_from_text(message.chat.id, result)
                    answer = f"Расписание сохранено:\n\n{schedule_mgr.get_today_schedule_text(message.chat.id)}"
                    await start_reminder(message.bot, message.chat.id)
                else:
                    answer = "Не удалось распознать расписание."
            else:
                if ext == "pdf" and is_scanned_pdf(file_bytes):
                    pages = pdf_pages_as_base64(file_bytes, max_pages=3)
                    result = ""
                    for b64 in pages:
                        part = await deepseek_ask("Прочитай текст с этого изображения", image_base64=b64)
                        result += part + "\n"
                else:
                    text = extract_text(file_bytes, ext)
                    context = memory_mgr.get_context(message.chat.id)
                    result = await deepseek_ask(f"Проанализируй документ:\n\n{text}", memory_context=context)
                answer = result

            memory_mgr.add_entry(message.chat.id, "assistant", answer)
            await _send_result(message, answer, wait_msg)

    except Exception:
        logger.exception("Error processing message")
        await wait_msg.edit_text("Ошибка при обработке. Попробуй ещё раз.")


async def _send_result(message: types.Message, text: str, wait_msg: types.Message) -> None:
    if len(text) > MAX_TEXT_LEN:
        docx_bytes = create_answer_docx(text)
        await message.answer_document(
            types.BufferedInputFile(docx_bytes.read(), filename="answer.docx"),
            caption="Готово!",
        )
        await wait_msg.delete()
    else:
        await wait_msg.edit_text(text)

