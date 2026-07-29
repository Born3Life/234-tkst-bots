from __future__ import annotations

import logging

from aiogram import F, Router, types
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


@router.message(Command("coursework"))
async def cmd_coursework(message: types.Message, state: FSMContext) -> None:
    delete(message.from_user.id)
    await state.clear()
    await message.answer(
        "📚 <b>Конструктор курсового проекта</b>\n\n"
        "Я помогу тебе собрать пояснительную записку пошагово.\n\n"
        "Напиши <b>тему</b> курсового проекта.\n\n"
        "Пример: «Проект 5-этажного жилого дома в г. Краснодар»"
    )
    await state.set_state(Coursework.topic)


@router.message(Coursework.topic)
async def process_topic(message: types.Message, state: FSMContext) -> None:
    topic = message.text.strip()
    if len(topic) < 5:
        await message.answer("Слишком короткая тема. Напиши подробнее.")
        return

    wait = await message.answer("⏳ Генерирую структуру проекта...")
    try:
        structure_text = await generate_structure(topic)
        sections = parse_structure(structure_text)

        project = new_project(message.from_user.id, topic)
        project["structure"] = structure_text
        project["sections"] = sections
        save(message.from_user.id, project)

        await wait.edit_text(
            f"✅ <b>Структура сгенерирована</b>\n\n"
            f"Тема: <b>{md_to_html(topic)}</b>\n\n"
            f"{md_to_html(structure_text)}\n\n"
            f"<b>Как заполнять:</b>\n"
            f"1. Напиши <b>номер раздела</b> (например, 1 или 2.1)\n"
            f"2. Я предложу содержание — ты отредактируешь\n"
            f"3. Когда все разделы готовы — /generate\n\n"
            f"Доступные разделы:\n{_section_list(sections)}",
        )
    except Exception:
        logger.exception("Structure generation failed")
        await wait.edit_text("❌ Ошибка при генерации структуры. Попробуй ещё раз.")
        return

    await state.set_state(Coursework.fill_section)


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
