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


class Exam(StatesGroup):
    answering = State()


TOPICS = [
    "Учёт строительных материалов",
    "Контроль качества работ",
    "Технический надзор",
    "Исполнительная документация",
    "Учёт затрат",
    "Приёмка работ",
    "Охрана труда",
    "Сметное дело",
    "Бухгалтерский учёт в строительстве",
    "Правовые основы строительства",
]


async def _generate_ticket(topic: str | None = None) -> dict:
    if topic:
        prompt = (
            f"Ты — преподаватель дисциплины «Учёт и контроль в строительстве». "
            f"Составь экзаменационный билет по теме «{topic}».\n\n"
            f"Билет должен содержать ровно 3 вопроса.\n"
            f"Формат ответа — строго:\n"
            f"1. Текст первого вопроса\n"
            f"2. Текст второго вопроса\n"
            f"3. Текст третьего вопроса\n\n"
            f"Вопросы должны проверять знание нормативных документов, "
            f"практических навыков учёта и контроля."
        )
    else:
        prompt = (
            "Ты — преподаватель дисциплины «Учёт и контроль в строительстве». "
            "Составь экзаменационный билет по любой теме дисциплины.\n\n"
            "Билет должен содержать ровно 3 вопроса.\n"
            "Формат ответа — строго:\n"
            "1. Текст первого вопроса\n"
            "2. Текст второго вопроса\n"
            "3. Третьего третьего вопроса\n\n"
            "Вопросы должны проверять знание нормативных документов, "
            "практических навыков учёта и контроля."
        )
    text = await ask(prompt)

    questions = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() and ". " in line[:4]):
            q = line.split(". ", 1)[1] if ". " in line else line
            questions.append(q)
    if len(questions) < 3:
        questions = [f"Вопрос {i+1}" for i in range(3)]

    return {"topic": topic or "Общий", "questions": questions, "answers": [], "scores": []}


async def _check_exam_answer(question: str, user_answer: str) -> str:
    prompt = (
        f"Ты — преподаватель. Оцени ответ студента на вопрос экзамена.\n\n"
        f"Вопрос: {question}\n\n"
        f"Ответ студента:\n{user_answer}\n\n"
        f"В ответе напиши:\n"
        f"1. **Вердикт**: зачтено/не зачтено\n"
        f"2. **Балл**: от 1 до 5\n"
        f"3. **Комментарий**: что верно, что неверно, что упущено\n"
        f"4. **Правильный ответ**: краткий эталон\n\n"
        f"Будь объективен."
    )
    return await ask(prompt)


def _parse_score(check_text: str) -> int:
    for line in check_text.split("\n"):
        if "Балл" in line:
            for word in line.split():
                word = word.strip(":.,")
                if word.isdigit():
                    return min(max(int(word), 1), 5)
    return 3


@router.message(Command("exam"))
async def cmd_exam(message: types.Message, state: FSMContext) -> None:
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    for i, t in enumerate(TOPICS, 1):
        kb.inline_keyboard.append([types.InlineKeyboardButton(text=t, callback_data=f"exam_topic_{i}")])
    kb.inline_keyboard.append([types.InlineKeyboardButton(text="Любая тема", callback_data="exam_topic_0")])

    await message.answer(
        "🎓 <b>Экзаменатор</b>\n\n"
        "Выбери тему билета:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("exam_topic_"))
async def pick_exam_topic(callback: types.CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.replace("exam_topic_", ""))
    topic = TOPICS[idx - 1] if 1 <= idx <= len(TOPICS) else None

    await callback.answer()
    wait = await callback.message.edit_text("⏳ Генерирую билет...")
    try:
        ticket = await _generate_ticket(topic)
        await state.update_data(ticket=ticket, current_q=0)

        q_text = ticket["questions"][0]
        await wait.edit_text(
            f"🎓 <b>Билет: {ticket['topic']}</b>\n\n"
            f"<b>Вопрос 1 из {len(ticket['questions'])}</b>\n\n"
            f"{q_text}\n\n"
            f"───\n<i>Напиши ответ. /skip — пропустить, /stop — выйти</i>"
        )
        await state.set_state(Exam.answering)
    except Exception:
        logger.exception("Ticket generation failed")
        await wait.edit_text("❌ Ошибка. Попробуй ещё раз /exam")


@router.message(Exam.answering, Command("stop"))
async def cmd_stop_exam(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Экзамен прерван. /exam — начать заново.")


@router.message(Exam.answering, Command("skip"))
async def cmd_skip_exam(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    ticket = data.get("ticket", {})
    q_idx = data.get("current_q", 0)
    questions = ticket.get("questions", [])

    ticket.setdefault("answers", []).append("")
    ticket.setdefault("scores", []).append(0)
    q_idx += 1

    if q_idx >= len(questions):
        await _finish_exam(message, state, ticket)
        return

    await state.update_data(ticket=ticket, current_q=q_idx)
    await message.answer(
        f"<b>Вопрос {q_idx + 1} из {len(questions)}</b>\n\n"
        f"{questions[q_idx]}\n\n"
        f"───\n<i>Напиши ответ. /skip — пропустить, /stop — выйти</i>"
    )


@router.message(Exam.answering)
async def process_exam_answer(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    ticket = data.get("ticket", {})
    q_idx = data.get("current_q", 0)
    questions = ticket.get("questions", [])
    user_answer = message.text.strip()

    wait = await message.answer("🔄 Проверяю ответ...")
    try:
        check = await _check_exam_answer(questions[q_idx], user_answer)
        score = _parse_score(check)

        ticket.setdefault("answers", []).append(user_answer)
        ticket.setdefault("scores", []).append(score)
        q_idx += 1

        if q_idx >= len(questions):
            await wait.delete()
            await _finish_exam(message, state, ticket)
            return

        await state.update_data(ticket=ticket, current_q=q_idx)
        await wait.edit_text(
            f"📊 <b>Результат вопроса {q_idx}</b>\n\n{md_to_html(check)}\n\n"
            f"───\n"
            f"<b>Вопрос {q_idx + 1} из {len(questions)}</b>\n\n"
            f"{questions[q_idx]}\n\n"
            f"───\n<i>Напиши ответ. /skip — пропустить, /stop — выйти</i>"
        )
    except Exception:
        logger.exception("Exam check failed")
        await wait.edit_text("❌ Ошибка при проверке. Попробуй ещё раз.")


async def _finish_exam(message: types.Message, state: FSMContext, ticket: dict) -> None:
    scores = ticket.get("scores", [])
    avg = sum(scores) / len(scores) if scores else 0
    total = sum(scores)

    if avg >= 4.5:
        grade = "Отлично 🎉"
    elif avg >= 3.5:
        grade = "Хорошо 👍"
    elif avg >= 2.5:
        grade = "Удовлетворительно 👌"
    else:
        grade = "Неудовлетворительно 😞"

    lines = [f"🎓 <b>Экзамен завершён</b>\n\n"]
    lines.append(f"Тема: <b>{ticket.get('topic', 'Общий')}</b>")
    lines.append(f"Оценка: <b>{grade}</b>")
    lines.append(f"Баллы: {', '.join(str(s) for s in scores)} | Средний: {avg:.1f}/5 | Сумма: {total}/{len(scores)*5}")
    lines.append("")

    questions = ticket.get("questions", [])
    answers = ticket.get("answers", [])
    for i, q in enumerate(questions):
        mark = "✅" if i < len(scores) and scores[i] >= 3 else "❌"
        ans = answers[i] if i < len(answers) else "(пропущен)"
        lines.append(f"{mark} <b>Вопрос {i+1}:</b> {q}")
        if ans and ans != "(пропущен)":
            lines.append(f"   Ответ: {ans[:100]}{'…' if len(ans) > 100 else ''}")

    result_msg = "\n".join(lines)
    await message.answer(result_msg)
    await state.clear()
