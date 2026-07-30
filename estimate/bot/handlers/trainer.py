from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.services.formatter import md_to_html
from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

router = Router()


class Trainer(StatesGroup):
    waiting_answer = State()


TOPICS = [
    "Расчёт локальной сметы на фундамент",
    "Расчёт сметы на отделочные работы",
    "Подбор расценки по ФЕР",
    "Расчёт накладных расходов (НР)",
    "Расчёт сметной прибыли (СП)",
    "Расчёт индекса пересчёта в текущие цены",
    "Проверка акта КС-2",
    "Расчёт объёмов земляных работ",
    "Расчёт сметы на кровельные работы",
    "Составление ССРСС",
    "Расчёт сметы на монтаж окон",
    "Расчёт сметы на бетонные работы",
]


async def _generate_task(topic: str | None = None) -> str:
    if topic:
        prompt = (
            f"Ты — преподаватель сметного дела. Составь учебное задание по теме «{topic}».\n\n"
            f"Формат:\n"
            f"### Задание\n"
            f"Описание задачи с исходными данными.\n\n"
            f"### Вопрос\n"
            f"Что нужно рассчитать.\n\n"
            f"### Подсказка\n"
            f"Краткая подсказка (методика, формула, ссылка на ФЕР/МДС).\n\n"
            f"Не пиши ответ! Только задание, вопрос и подсказку."
        )
    else:
        prompt = (
            "Ты — преподаватель сметного дела. Составь учебное задание "
            "по любой теме сметного дела (ФЕР, ТЕР, КС-2, НР, СП, индексы, "
            "объёмы работ, ССРСС).\n\n"
            "Формат:\n"
            "### Задание\n"
            "Описание задачи с исходными данными.\n\n"
            "### Вопрос\n"
            "Что нужно рассчитать.\n\n"
            "### Подсказка\n"
            "Краткая подсказка (методика, формула, ссылка на ФЕР/МДС).\n\n"
            "Не пиши ответ! Только задание, вопрос и подсказку."
        )
    return await ask(prompt)


async def _check_answer(task: str, user_answer: str) -> str:
    prompt = (
        f"Ты — преподаватель сметного дела. Проверь ответ студента.\n\n"
        f"Задание:\n{task}\n\n"
        f"Ответ студента:\n{user_answer}\n\n"
        f"Оцени:\n"
        f"1. **Вердикт**: правильно/частично/неправильно\n"
        f"2. **Комментарий**: что именно верно или неверно\n"
        f"3. **Правильное решение**: кратко покажи алгоритм\n"
        f"4. **Оценка**: по 5-балльной шкале\n\n"
        f"Будь строгим, но доброжелательным. Указывай на конкретные ошибки."
    )
    return await ask(prompt)


@router.message(Command("train"))
async def cmd_train(message: types.Message, state: FSMContext) -> None:
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    for i, t in enumerate(TOPICS, 1):
        kb.inline_keyboard.append([types.InlineKeyboardButton(text=t, callback_data=f"tr_topic_{i}")])
    kb.inline_keyboard.append([types.InlineKeyboardButton(text="Любая тема", callback_data="tr_topic_0")])
    kb.inline_keyboard.append([types.InlineKeyboardButton(text="🔙 Выйти", callback_data="train_exit")])

    await message.answer(
        "🎯 <b>Сметный тренажёр</b>\n\n"
        "Выбери тему для задания или начни с любой:",
        reply_markup=kb,
    )


@router.callback_query(F.data == "train_exit")
async def on_train_exit(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Тренажёр остановлен. /train — начать заново.")
    await callback.answer()


@router.callback_query(F.data.startswith("tr_topic_"))
async def pick_topic(callback: types.CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.replace("tr_topic_", ""))
    topic = TOPICS[idx - 1] if 1 <= idx <= len(TOPICS) else None

    await callback.answer()
    await state.update_data(train_topic=topic)

    wait = await callback.message.edit_text("⏳ Генерирую задание...")
    try:
        task = await _generate_task(topic)
        await state.update_data(current_task=task)
        exit_kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Выйти", callback_data="train_exit")],
        ])
        await wait.edit_text(
            f"📝 <b>Задание</b>\n\n{md_to_html(task)}\n\n"
            f"───\n<i>Напиши свой ответ. /skip — пропустить, /stop — выйти</i>",
            reply_markup=exit_kb,
        )
        await state.set_state(Trainer.waiting_answer)
    except Exception:
        logger.exception("Task generation failed")
        await wait.edit_text("❌ Ошибка. Попробуй еще раз /train")


@router.message(Trainer.waiting_answer, Command("skip"))
async def cmd_skip(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    task = data.get("current_task", "")
    wait = await message.answer("⏳ Показываю решение...")
    try:
        answer = await _check_answer(task, "Я не знаю, покажи решение")
        exit_kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Выйти", callback_data="train_exit")],
        ])
        await wait.edit_text(
            f"💡 <b>Решение</b>\n\n{md_to_html(answer)}",
            reply_markup=exit_kb,
        )
    except Exception:
        logger.exception("Skip failed")
        await wait.edit_text("❌ Ошибка.")
    await state.update_data(current_task="", train_topic=None)


@router.message(Trainer.waiting_answer, Command("start", "help", "cancel", "stop", "menu"))
async def cmd_exit_train(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Тренажёр: выход. /train — начать заново, /help — помощь.")


@router.message(Trainer.waiting_answer)
async def process_answer(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    task = data.get("current_task", "")
    if not task:
        await message.answer("Нет активного задания. /train")
        await state.clear()
        return

    user_answer = message.text.strip()
    wait = await message.answer("🔄 Проверяю ответ...")
    try:
        result = await _check_answer(task, user_answer)
        exit_kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Выйти", callback_data="train_exit")],
        ])
        await wait.edit_text(
            f"📊 <b>Результат проверки</b>\n\n{md_to_html(result)}",
            reply_markup=exit_kb,
        )
    except Exception:
        logger.exception("Check failed")
        await wait.edit_text("❌ Ошибка при проверке.")
