from __future__ import annotations

import logging
import re

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
    "Технология бетонных работ",
    "Технология каменной кладки",
    "Технология кровельных работ",
    "Монтаж сборных железобетонных конструкций",
    "Монолитное строительство",
    "Производство отделочных работ",
    "Устройство полов и покрытий",
    "Монтаж инженерных систем",
    "Производство земляных работ",
    "Сварочные и монтажные работы",
    "Контроль качества СМР",
    "Составление ППР на строительство",
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
        "📚 <b>Конструктор курсового проекта по СМР</b>\n\n"
        "Выбери тему из списка или напиши свою:",
        reply_markup=kb,
    )
    await state.set_state(Coursework.topic)


@router.callback_query(F.data.startswith("cw_topic_"))
async def pick_topic(callback: types.CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.replace("cw_topic_", "")) - 1
    topic = TOPICS[idx] if 0 <= idx < len(TOPICS) else ""

    if topic == "Свой вариант (введу сам)":
        await callback.message.edit_text("Напиши свою тему курсового проекта по СМР:")
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

    sections = project.get("sections", [])

    parts = message.text.split(maxsplit=1)
    args_str = parts[1].strip() if len(parts) > 1 else ""
    args = [a.strip() for a in args_str.split(",") if a.strip()]

    if args:
        indices = []
        for arg in args:
            found = None
            for i, s in enumerate(sections):
                s_clean = s["number"].strip().lower().split()[0].rstrip(".")
                if s_clean == arg.lower().strip().rstrip("."):
                    found = i
                    break
            if found is None:
                await message.answer(f"❌ Раздел «{arg}» не найден. Проверь номера.")
                return
            indices.append(found)

        empty = [sections[i] for i in indices if not sections[i].get("content")]
        if empty:
            await message.answer(
                f"❌ Раздел(ы) не заполнены:\n"
                f"{chr(10).join(s['number'].strip() for s in empty[:5])}\n\n"
                f"Сначала заполни их, потом /generate"
            )
            return
        use_sections = [sections[i] for i in indices]
    else:
        use_sections = [s for s in sections if s.get("content")]
        empty = [s for s in sections if not s.get("content")]
        if not use_sections:
            await message.answer(
                "❌ Нет заполненных разделов.\n"
                "Заполни хотя бы один, написав его номер."
            )
            return

    wait = await message.answer("⏳ Собираю пояснительную записку...")
    try:
        full_text = await generate_project_docx(message.from_user.id, use_sections)
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
        return

    numbers = _extract_numbers(text)
    matched = _find_sections(sections, numbers)

    if not matched:
        await message.answer(
            f"Раздел «{text}» не найден.\n\n"
            f"{_section_list(sections)}\n\n"
            f"Напиши номер раздела, /generate или /cancel"
        )
        return

    section = matched[0]
    remaining = [m["number"].strip().lower().split()[0].rstrip(".") for m in matched[1:]]

    idx = sections.index(section)
    await state.update_data(editing_section=idx, section_queue=remaining)

    section_num = section["number"].strip()
    section_title = section_num.split(". ", 1)[1] if ". " in section_num else section_num

    wait = await message.answer(f"⏳ Генерирую содержание для раздела {section_num}...")
    try:
        prompt = await generate_section_prompt(project["topic"], section_num, section_title)
        content = await ask(prompt)

        queue_hint = f"\n\n<i>Очередь: {', '.join(s['number'].strip() for s in matched[1:4])}</i>" if remaining else ""

        await wait.edit_text(
            f"📝 <b>Раздел {md_to_html(section_num)}</b>\n\n"
            f"Проект содержания:\n\n"
            f"{md_to_html(content)}\n\n"
            f"───\n"
            f"Ты можешь:\n"
            f"• прислать <b>свой текст</b> — я сохраню его\n"
            f"• /done — оставить предложенный вариант\n"
            f"• /skip — пропустить раздел"
            f"{queue_hint}",
        )
        await state.update_data(generated_content=content)
    except Exception:
        logger.exception("Section generation failed")
        await wait.edit_text("❌ Ошибка при генерации раздела. Попробуй другой.")


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
    else:
        if len(text) < 10:
            await message.answer("Слишком короткий текст. Напиши подробнее или /done чтобы оставить предложенный.")
            return
        project["sections"][idx]["content"] = text

    project["sections"][idx]["done"] = True
    save(message.from_user.id, project)
    await state.update_data(editing_section=None, generated_content=None)

    data = await state.get_data()
    queue = data.get("section_queue", [])

    if queue:
        next_num = queue.pop(0)
        await state.update_data(section_queue=queue)

        sections = project.get("sections", [])
        for s in sections:
            s_clean = s["number"].strip().lower().split()[0].rstrip(".")
            if s_clean == next_num:
                next_idx = sections.index(s)
                await state.update_data(editing_section=next_idx)
                section_num = s["number"].strip()
                section_title = section_num.split(". ", 1)[1] if ". " in section_num else section_num
                wait = await message.answer(f"⏳ Генерирую содержание для раздела {section_num}...")
                try:
                    prompt = await generate_section_prompt(project["topic"], section_num, section_title)
                    content = await ask(prompt)
                    queue_names = []
                    for _q in queue:
                        for _s in sections:
                            if _s["number"].strip().lower().split()[0].rstrip(".") == _q:
                                queue_names.append(_s["number"].strip())
                                break
                    queue_hint = f"\n\n<i>Очередь: {', '.join(queue_names[:3])}</i>" if queue_names else ""
                    await wait.edit_text(
                        f"📝 <b>Раздел {md_to_html(section_num)}</b>\n\n"
                        f"Проект содержания:\n\n"
                        f"{md_to_html(content)}\n\n"
                        f"───\n"
                        f"Ты можешь:\n"
                        f"• прислать <b>свой текст</b> — я сохраню его\n"
                        f"• /done — оставить предложенный вариант\n"
                        f"• /skip — пропустить раздел"
                        f"{queue_hint}",
                    )
                    await state.update_data(generated_content=content)
                except Exception:
                    logger.exception("Section generation failed")
                    await wait.edit_text("❌ Ошибка при генерации раздела. Попробуй другой.")
                return

    await message.answer(
        f"✅ Раздел сохранён.\n\n"
        f"{_section_list(project['sections'])}\n\n"
        f"Выбери следующий раздел или /generate"
    )


def _extract_numbers(text: str) -> list[str]:
    """Извлекает номера разделов из текста вида '1.2 и 2.2' или '1.2, 2.2'."""
    text = text.replace("и", ",").replace(",", " ").replace(". ", " ")
    parts = text.split()
    numbers = []
    for p in parts:
        p = p.strip().rstrip(".")
        if re.match(r"^\d+(\.\d+)*$", p):
            numbers.append(p)
    return numbers


def _find_sections(sections: list[dict], numbers: list[str]) -> list[dict]:
    """Ищет разделы по номерам в указанном порядке."""
    matched = []
    seen = set()
    for num in numbers:
        for s in sections:
            s_clean = s["number"].strip().lower().split()[0].rstrip(".")
            if s_clean == num and id(s) not in seen:
                matched.append(s)
                seen.add(id(s))
                break
    return matched
