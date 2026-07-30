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


class Calc(StatesGroup):
    waiting_params = State()


CALC_TYPES = [
    ("Объём бетона", "Рассчитать объём бетона на фундамент/плиту/колонну"),
    ("Объём кирпичной кладки", "Рассчитать количество кирпича и раствора на стену"),
    ("Расчёт арматуры", "Рассчитать количество и диаметр арматуры на конструкцию"),
    ("Потребность в материалах", "Рассчитать расход материалов на стяжку/штукатурку"),
    ("Трудоёмкость работ", "Рассчитать чел.-часы на бетонные/каменные работы"),
    ("Состав бригады", "Рассчитать численный состав бригады монтажников"),
    ("Расчёт крана", "Подобрать грузоподъёмность и вылет стрелы крана"),
    ("Объём земляных работ", "Рассчитать объём котлована/траншеи"),
    ("Расчёт опалубки", "Рассчитать площадь и количество щитов опалубки"),
    ("Расчёт кровли", "Рассчитать площадь, материалы и расходы на кровлю"),
]


@router.message(Command("calc"))
async def cmd_calc(message: types.Message, state: FSMContext) -> None:
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    for i, (title, _) in enumerate(CALC_TYPES, 1):
        kb.inline_keyboard.append([types.InlineKeyboardButton(text=title, callback_data=f"calc_type_{i}")])
    await message.answer(
        "🧮 <b>Калькулятор СМР</b>\n\n"
        "Выбери тип расчёта:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("calc_type_"))
async def pick_calc(callback: types.CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.replace("calc_type_", "")) - 1
    if idx < 0 or idx >= len(CALC_TYPES):
        await callback.answer("Неверный выбор")
        return

    title, desc = CALC_TYPES[idx]
    await callback.answer()

    exit_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Выйти", callback_data="calc_exit")],
    ])
    await state.update_data(calc_title=title, calc_desc=desc)
    await callback.message.edit_text(
        f"🧮 <b>{title}</b>\n\n"
        f"{desc}\n\n"
        f"Введи исходные данные (размеры, марки материалов, объёмы):",
        reply_markup=exit_kb,
    )
    await state.set_state(Calc.waiting_params)


@router.callback_query(F.data == "calc_exit")
async def on_calc_exit(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Выход из калькулятора. /calc — начать заново.")
    await callback.answer()


@router.message(Calc.waiting_params, Command("start", "help", "cancel", "stop", "menu"))
async def cmd_exit_calc(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Калькулятор: выход. /calc — начать заново, /help — помощь.")


@router.message(Calc.waiting_params)
async def process_calc(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    title = data.get("calc_title", "")
    desc = data.get("calc_desc", "")
    params = message.text.strip()

    wait = await message.answer("🔄 Рассчитываю...")
    try:
        prompt = (
            f"Ты — инженер ПТО. Выполни расчёт по теме «{title}».\n\n"
            f"Описание расчёта: {desc}\n\n"
            f"Исходные данные пользователя:\n{params}\n\n"
            f"Требования к ответу:\n"
            f"1. Напиши **алгоритм расчёта** (формулы, ссылки на СП/СНиП)\n"
            f"2. Подставь **исходные данные** в формулы\n"
            f"3. Напиши **результат** с единицами измерения\n"
            f"4. Сделай **вывод** (достаточно/недостаточно, рекомендации)\n\n"
            f"Используй **жирный** для ключевых терминов, ### для подзаголовков."
        )
        result = await ask(prompt)

        exit_kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Выйти", callback_data="calc_exit")],
        ])
        await wait.edit_text(
            f"📐 <b>Расчёт: {title}</b>\n\n{md_to_html(result)}",
            reply_markup=exit_kb,
        )
    except Exception:
        logger.exception("Calc failed")
        await wait.edit_text("❌ Ошибка при расчёте. Попробуй ещё раз.")
