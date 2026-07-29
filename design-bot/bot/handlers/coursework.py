from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.services.coursework_service import (
    delete,
    generate_project_docx,
    generate_section_prompt,
    generate_structure,
    load,
    new_project,
    parse_structure,
    save,
)
from bot.services.docx_writer import create_answer_docx
from bot.services.formatter import md_to_html
from bot.services.openrouter import ask

logger = logging.getLogger(__name__)

router = Router()


class Coursework(StatesGroup):
    topic = State()
    fill_section = State()


def _section_list(sections: list[dict]) -> str:
    lines = []
    for s in sections:
        mark = "✅" if s.get("done") else "⬜"
        lines.append(f"{mark} {s['number'].strip()}")
    return "\n".join(lines)


TOPICS = [
    "Проект 5-этажного жилого дома",
    "Проект 2-этажного коттеджа",
    "Проект административного здания",
    "Проект торгового центра",
    "Проект спортивного комплекса",
    "Проект детского сада",
    "Проект школы",
    "Проект производственного цеха",
    "Проект складского комплекса",
    "Проект автовокзала",
    "Реконструкция жилого дома",
    "Реконструкция административного здания",
    "Свой вариант (введу сам)",
]


@router.message(Command("coursework"))
async def cmd_coursework(message: types.Message, state: FSMContext) -> None:
    delete(message.from_user.id)
    await state.clear()

    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    for i, t in enumerate(TOPICS, 1):
        kb.inline_keyboard.append([types.InlineKeyboardButton(text=t, callback_data=f"cw_topic_{i}")])

    await message.answer(
        "📚 <b>Конструктор курсового проекта</b>\n\n"
        "Выбери тему из списка или напиши свою:",
        reply_markup=kb,
    )
    await state.set_state(Coursework.topic)


@router.callback_query(F.data.startswith("cw_topic_"))
async def pick_topic(callback: types.CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.replace("cw_topic_", "")) - 1
    topic = TOPICS[idx] if 0 <= idx < len(TOPICS) else ""

    if topic == "Свой вариант (введу сам)":
        await callback.message.edit_text("Напиши свою тему курсового проекта:")
        await callback.answer()
        return

    await callback.answer()
    await state.update_data(selected_topic=topic)
    await _start_coursework(callback.message, state, topic, user_id=callback.from_user.id)


async def _start_coursework(msg: types.Message, state: FSMContext, topic: str, user_id: int | None = None) -> None:
    uid = user_id or msg.from_user.id
    wait = await msg.answer(f"⏳ Генерирую структуру для «{topic}»...")
    try:
        structure_text = await generate_structure(topic)
        sections = parse_structure(structure_text)

        project = new_project(uid, topic)
        project["structure"] = structure_text
        project["sections"] = sections
        save(uid, project)

        sections_list = _section_list(sections)
        max_body = 3500
        display_text = md_to_html(structure_text)
        if len(display_text) > max_body:
            display_text = display_text[:max_body] + "…\n\n<i>(структура сокращена)</i>\n\n"

        body = (
            f"✅ <b>Структура сгенерирована</b>\n\n"
            f"Тема: <b>{md_to_html(topic)}</b>\n\n"
            f"{display_text}\n\n"
            f"<b>Доступные разделы:</b>\n{sections_list}\n\n"
            f"Напиши <b>номер раздела</b>, чтобы заполнить. /generate — собрать документ."
        )
        if len(body) > 4096:
            body = (
                f"✅ <b>Структура сгенерирована</b>\n\n"
                f"Тема: <b>{md_to_html(topic)}</b>\n\n"
                f"Доступные разделы:\n{sections_list}\n\n"
                f"Напиши номер раздела или /generate для сборки."
            )
        try:
            await wait.edit_text(body)
        except TelegramBadRequest:
            await msg.answer(body)
    except Exception:
        logger.exception("Structure generation failed")
        await wait.edit_text("❌ Ошибка. Попробуй ещё раз.")
        await state.clear()
        return

    await state.set_state(Coursework.fill_section)


@router.message(Coursework.topic)
async def process_topic(message: types.Message, state: FSMContext) -> None:
    topic = message.text.strip()
    if len(topic) < 5:
        await message.answer("Слишком короткая тема. Напиши подробнее.")
        return
    await _start_coursework(message, state, topic)


@router.message(Coursework.fill_section, Command("generate"))
async def cmd_generate(message: types.Message, state: FSMContext) -> None:
    project = load(message.from_user.id)
    if not project:
        await message.answer("❌ Нет данных. Начни сначала: /coursework")
        await state.clear()
        return

    empty = [s for s in project.get("sections", []) if not s.get("content")]
    if empty:
        await message.answer(
            f"❌ Заполнены не все разделы.\n"
            f"Пустые: {', '.join(s['number'].strip() for s in empty[:5])}\n\n"
            f"Заполни их или напиши /skip чтобы пропустить."
        )
        return

    wait = await message.answer("⏳ Собираю пояснительную записку...")
    try:
        full_text = await generate_project_docx(message.from_user.id)
        docx_bytes = create_answer_docx(full_text)
        await message.answer_document(
            types.BufferedInputFile(docx_bytes.read(), filename="coursework.docx"),
            caption="✅ Пояснительная записка готова!",
        )
        await wait.delete()
        delete(message.from_user.id)
        await state.clear()
    except Exception:
        logger.exception("Generate failed")
        await wait.edit_text("❌ Ошибка при сборке документа.")


@router.message(Coursework.fill_section, Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    delete(message.from_user.id)
    await state.clear()
    await message.answer("❌ Конструктор отменён.")


@router.message(Coursework.fill_section)
async def process_section(message: types.Message, state: FSMContext) -> None:
    text = message.text.strip()

    project = load(message.from_user.id)
    if not project:
        await message.answer("❌ Сессия истекла. Начни сначала: /coursework")
        await state.clear()
        return

    data = await state.get_data()
    editing_idx = data.get("editing_section")

    if editing_idx is not None:
        await _save_section_content(message, state, project, editing_idx, text)
        return

    sections = project.get("sections", [])

    if text == "/skip":
        if editing_idx is not None:
            sections[editing_idx]["done"] = True
            save(message.from_user.id, project)
            await state.update_data(editing_section=None)
            await message.answer(f"✅ Раздел пропущен.\n\n{_section_list(sections)}\n\nВыбери следующий раздел или /generate")
        return

    section = None
    for s in sections:
        s_clean = s["number"].strip().lower().split()[0].rstrip(".")
        if s_clean == text.lower().strip().rstrip("."):
            section = s
            break

    if not section:
        await message.answer(
            f"Раздел «{text}» не найден.\n\n"
            f"{_section_list(sections)}\n\n"
            f"Напиши номер раздела, /generate или /cancel"
        )
        return

    if section.get("done"):
        await message.answer(
            f"⚠️ Раздел «{section['number'].strip()}» уже заполнен.\n"
            f"Напиши его номер ещё раз, чтобы перезаписать."
        )

    idx = sections.index(section)
    await state.update_data(editing_section=idx)

    section_num = section["number"].strip()
    section_title = section_num.split(". ", 1)[1] if ". " in section_num else section_num

    wait = await message.answer(f"⏳ Генерирую содержание для раздела {section_num}...")
    try:
        prompt = await generate_section_prompt(project["topic"], section_num, section_title)
        content = await ask(prompt)

        await wait.edit_text(
            f"📝 <b>Раздел {md_to_html(section_num)}</b>\n\n"
            f"Проект содержания:\n\n"
            f"{md_to_html(content)}\n\n"
            f"───\n"
            f"Ты можешь:\n"
            f"• прислать <b>свой текст</b> — я сохраню его\n"
            f"• /done — оставить предложенный вариант\n"
            f"• /skip — пропустить раздел",
        )
        await state.update_data(generated_content=content)
    except Exception:
        logger.exception("Section generation failed")
        await wait.edit_text(f"❌ Ошибка при генерации раздела. Попробуй другой.")


async def _save_section_content(
    message: types.Message,
    state: FSMContext,
    project: dict,
    idx: int,
    text: str,
) -> None:
    if text == "/done":
        data = await state.get_data()
        text = data.get("generated_content", "")

    if text in ("/done", "/skip"):
        project["sections"][idx]["content"] = text if text != "/skip" else "Пропущено"
        project["sections"][idx]["done"] = True
        save(message.from_user.id, project)
        await state.update_data(editing_section=None, generated_content=None)
        await message.answer(
            f"✅ Раздел сохранён.\n\n"
            f"{_section_list(project['sections'])}\n\n"
            f"Выбери следующий раздел или /generate"
        )
        return

    if len(text) < 10:
        await message.answer("Слишком короткий текст. Напиши подробнее или /done чтобы оставить предложенный.")
        return

    project["sections"][idx]["content"] = text
    project["sections"][idx]["done"] = True
    save(message.from_user.id, project)
    await state.update_data(editing_section=None, generated_content=None)
    await message.answer(
        f"✅ Раздел сохранён (твой вариант).\n\n"
        f"{_section_list(project['sections'])}\n\n"
        f"Выбери следующий раздел или /generate"
    )
