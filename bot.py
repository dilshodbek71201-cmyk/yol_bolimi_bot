"""
Yo'l bo'limi boshliqlarini attestatsiya - Telegram Quiz Bot
=============================================================
Ikki rejim bor:

1) YAKKA REJIM (shaxsiy chatda /start) - eski rejim, barcha savollarni
   tasodifiy tartibda birma-bir so'raydi, shoshilmasdan javoblaysiz.

2) MUSOBAQA REJIMI (guruh chatida /start yoki /musobaqa):
   - Kamida 2 kishi "Qatnashaman" tugmasini bosishi kerak.
   - Shundan keyin istalgan qatnashchi "Boshlash" tugmasini bosadi.
   - 23 ta savol tasodifiy tanlanadi (imkon qadar javobi tasdiqlangan
     savollar ustuvor olinadi).
   - Har bir savolga 30 soniya vaqt beriladi (agar hamma javob bersa,
     vaqtdan oldin ham keyingi savolga o'tadi).
   - Har savoldan keyin joriy reyting ko'rsatiladi.
   - Oxirida yakuniy reyting va unvonlar e'lon qilinadi:
       1-o'rin - Kuchli prorab
       2-o'rin - Yaxshi prorab
       3-o'rin - Prorab

ISHGA TUSHIRISH:
    pip install -r requirements.txt
    export BOT_TOKEN="sizning_tokeningiz"
    python bot.py
"""

import json
import os
import random
import logging
import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(BASE_DIR, "questions.json")
ANSWERS_PATH = os.path.join(BASE_DIR, "answers.json")

TOKEN = os.environ.get("BOT_TOKEN")

with open(QUESTIONS_PATH, encoding="utf-8") as f:
    QUESTIONS = json.load(f)

with open(ANSWERS_PATH, encoding="utf-8") as f:
    ANSWERS = json.load(f)

LETTERS = ["a", "b", "v", "g"]
LETTER_LABEL = {"a": "А", "b": "Б", "v": "В", "g": "Г"}

QUESTIONS_PER_GAME = 25
QUESTION_TIME_SECONDS = 30

TITLES = {1: "🥇 Kuchli prorab", 2: "🥈 Yaxshi prorab", 3: "🥉 Prorab"}

# Telegram'ning tayyor (bepul) animatsion effektlari - FAQAT shaxsiy chatlarda ishlaydi
EFFECT_CONFETTI = "5046509860389126442"  # 🎉 to'g'ri javob uchun
EFFECT_THUMBSDOWN = "5104858069142078462"  # 👎 xato javob uchun

# ---------------------------------------------------------------------
# YAKKA REJIM (solo) - shaxsiy chat uchun xotira
# ---------------------------------------------------------------------
solo_sessions = {}


def build_question_text(qid: str, prefix: str = "") -> str:
    q = QUESTIONS[qid]
    lines = [f"{prefix}❓ {qid}-savol:\n{q['q']}\n"]
    for letter in LETTERS:
        if q.get(letter):
            lines.append(f"{LETTER_LABEL[letter]}) {q[letter]}")
    return "\n".join(lines)


def build_keyboard(qid: str, callback_prefix: str) -> InlineKeyboardMarkup:
    q = QUESTIONS[qid]
    row = []
    for letter in LETTERS:
        if q.get(letter):
            row.append(
                InlineKeyboardButton(
                    LETTER_LABEL[letter],
                    callback_data=f"{callback_prefix}:{qid}:{letter}",
                )
            )
    return InlineKeyboardMarkup([row])


async def solo_send_question(chat_id, context: ContextTypes.DEFAULT_TYPE, user_id):
    session = solo_sessions[user_id]
    if session["idx"] >= len(session["order"]):
        total = session["answered"]
        correct = session["correct"]
        unknown = session["unknown"]
        text = (
            f"✅ Test tugadi!\n\n"
            f"Jami savollar: {total}\n"
            f"To'g'ri javob kalitiga ega savollar: {total - unknown}\n"
            f"  — Siz to'g'ri javob berdingiz: {correct}\n"
            f"  — Xato: {total - unknown - correct}\n"
            f"Javob kaliti hali yo'q savollar: {unknown} ta\n\n"
            f"Qaytadan boshlash uchun /start bosing."
        )
        await context.bot.send_message(chat_id=chat_id, text=text)
        return

    qid = session["order"][session["idx"]]
    text = build_question_text(qid)
    kb = build_keyboard(qid, "solo")
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)


async def solo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = list(QUESTIONS.keys())
    random.shuffle(order)
    solo_sessions[user_id] = {
        "order": order,
        "idx": 0,
        "answered": 0,
        "correct": 0,
        "unknown": 0,
    }
    await update.message.reply_text(
        f"Assalomu alaykum! Jami {len(order)} ta savol bor.\n"
        f"Har safar tasodifiy tartibda so'rayman.\n"
        f"Boshlaymiz 👇"
    )
    await solo_send_question(update.effective_chat.id, context, user_id)


async def solo_handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in solo_sessions:
        await query.edit_message_text("Iltimos, /start bilan qayta boshlang.")
        return

    _, qid, chosen = query.data.split(":")
    session = solo_sessions[user_id]
    correct_letter = ANSWERS.get(qid)

    q = QUESTIONS[qid]
    chosen_text = f"{LETTER_LABEL[chosen]}) {q[chosen]}"

    session["answered"] += 1

    if correct_letter is None:
        result_line = "\n\n⚪ Bu savol uchun hali tasdiqlangan javob kaliti yo'q."
        session["unknown"] += 1
    elif chosen == correct_letter:
        result_line = "\n\n✅ To'g'ri!"
        session["correct"] += 1
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🎉 To'g'ri javob!",
                message_effect_id=EFFECT_CONFETTI,
            )
        except Exception:
            pass
    else:
        correct_text = f"{LETTER_LABEL[correct_letter]}) {q[correct_letter]}"
        result_line = f"\n\n❌ Noto'g'ri. To'g'ri javob: {correct_text}"
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Noto'g'ri javob.",
                message_effect_id=EFFECT_THUMBSDOWN,
            )
        except Exception:
            pass

    new_text = build_question_text(qid) + f"\n\nSiz tanladingiz: {chosen_text}" + result_line
    await query.edit_message_text(new_text)

    session["idx"] += 1
    await solo_send_question(query.message.chat_id, context, user_id)


# ---------------------------------------------------------------------
# MUSOBAQA REJIMI (guruh) - xotira: chat_id -> game state
# ---------------------------------------------------------------------
games = {}


def new_game_state():
    return {
        "phase": "lobby",  # lobby -> running -> finished
        "joined": {},  # user_id -> display name
        "order": [],
        "idx": 0,
        "scores": {},  # user_id -> correct count
        "answered_this_q": set(),
        "question_closed": False,
        "question_message_id": None,
        "question_base_text": "",
        "answer_order": [],  # ismlar, javob bergan tartibda
        "first_correct": None,  # birinchi to'g'ri javob topgan ism
        "choices_this_q": {},  # letter -> [ismlar]
    }


def pick_questions(n):
    known = [qid for qid, v in ANSWERS.items() if v]
    unknown = [qid for qid, v in ANSWERS.items() if not v]
    random.shuffle(known)
    random.shuffle(unknown)
    selected = known[:n]
    if len(selected) < n:
        selected += unknown[: (n - len(selected))]
    random.shuffle(selected)
    return selected


def display_name(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name


async def musobaqa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        await solo_start(update, context)
        return

    chat_id = chat.id
    if chat_id in games and games[chat_id]["phase"] == "running":
        await update.message.reply_text("Hozir musobaqa davom etmoqda, kuting.")
        return

    games[chat_id] = new_game_state()
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Qatnashaman", callback_data=f"join:{chat_id}")],
            [InlineKeyboardButton("🎮 Boshlash", callback_data=f"gostart:{chat_id}")],
        ]
    )
    await update.message.reply_text(
        f"🏁 Attestatsiya musobaqasi!\n\n"
        f"Boshlash uchun kamida 2 kishi \"Qatnashaman\" tugmasini bosishi kerak.\n"
        f"Har savolga {QUESTION_TIME_SECONDS} soniya vaqt beriladi, jami "
        f"{QUESTIONS_PER_GAME} ta savol bo'ladi.\n\n"
        f"Hozircha qatnashchilar: 0",
        reply_markup=kb,
    )


async def handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id_str = query.data.split(":")
    chat_id = int(chat_id_str)
    game = games.get(chat_id)

    if not game or game["phase"] != "lobby":
        await query.answer("Bu musobaqa allaqachon boshlangan yoki tugagan.", show_alert=True)
        return

    user = query.from_user
    if user.id in game["joined"]:
        await query.answer("Siz allaqachon ro'yxatdasiz.")
        return

    game["joined"][user.id] = display_name(user)
    await query.answer("Ro'yxatdan o'tdingiz!")

    names_list = "\n".join(f"• {n}" for n in game["joined"].values())
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Qatnashaman", callback_data=f"join:{chat_id}")],
            [InlineKeyboardButton("🎮 Boshlash", callback_data=f"gostart:{chat_id}")],
        ]
    )
    await query.edit_message_text(
        f"🏁 Attestatsiya musobaqasi!\n\n"
        f"Boshlash uchun kamida 2 kishi \"Qatnashaman\" tugmasini bosishi kerak.\n"
        f"Har savolga {QUESTION_TIME_SECONDS} soniya vaqt beriladi, jami "
        f"{QUESTIONS_PER_GAME} ta savol bo'ladi.\n\n"
        f"Qatnashchilar ({len(game['joined'])}):\n{names_list}",
        reply_markup=kb,
    )


async def handle_gostart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id_str = query.data.split(":")
    chat_id = int(chat_id_str)
    game = games.get(chat_id)

    if not game or game["phase"] != "lobby":
        await query.answer("Bu musobaqa allaqachon boshlangan yoki tugagan.", show_alert=True)
        return

    if len(game["joined"]) < 2:
        await query.answer(
            "Boshlash uchun kamida 2 kishi \"Qatnashaman\" tugmasini bosishi kerak.",
            show_alert=True,
        )
        return

    if query.from_user.id not in game["joined"]:
        await query.answer("Faqat ro'yxatdan o'tgan qatnashchilar boshlay oladi.", show_alert=True)
        return

    await query.answer("Boshlanmoqda!")
    game["phase"] = "running"
    game["order"] = pick_questions(QUESTIONS_PER_GAME)
    game["scores"] = {uid: 0 for uid in game["joined"]}
    game["idx"] = 0

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🚀 Musobaqa boshlandi! {len(game['order'])} ta savol, omad!",
    )
    await group_send_question(chat_id, context)


async def group_send_question(chat_id, context: ContextTypes.DEFAULT_TYPE):
    game = games[chat_id]
    game["answered_this_q"] = set()
    game["question_closed"] = False
    game["answer_order"] = []
    game["first_correct"] = None
    game["choices_this_q"] = {}

    qid = game["order"][game["idx"]]
    base_text = build_question_text(
        qid, prefix=f"[{game['idx'] + 1}/{len(game['order'])}] "
    ) + f"\n\n⏱ {QUESTION_TIME_SECONDS} soniya"
    game["question_base_text"] = base_text
    kb = build_keyboard(qid, "g")
    msg = await context.bot.send_message(chat_id=chat_id, text=base_text, reply_markup=kb)
    game["question_message_id"] = msg.message_id

    context.job_queue.run_once(
        question_timeout,
        when=QUESTION_TIME_SECONDS,
        chat_id=chat_id,
        data={"idx": game["idx"]},
        name=f"timeout_{chat_id}_{game['idx']}",
    )


async def question_timeout(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    idx = context.job.data["idx"]
    await finalize_question(chat_id, idx, context)


async def finalize_question(chat_id, idx, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(chat_id)
    if not game or game["idx"] != idx or game["question_closed"]:
        return
    game["question_closed"] = True

    qid = game["order"][idx]
    correct_letter = ANSWERS.get(qid)
    q = QUESTIONS[qid]

    if correct_letter:
        correct_text = f"{LETTER_LABEL[correct_letter]}) {q[correct_letter]}"
        anyone_correct = any(
            l == correct_letter for l in game["choices_this_q"].keys()
        )
        flair = "🎉🎉🎉 SALYUT! 🎉🎉🎉" if anyone_correct else "🟥🟥🟥 HECH KIM TOPMADI 🟥🟥🟥"
        reveal = f"{flair}\n⏰ Vaqt tugadi. To'g'ri javob: {correct_text}"
        if game["first_correct"]:
            reveal += f"\n🥇 Birinchi topgan: {game['first_correct']}"
    else:
        reveal = "⏰ Vaqt tugadi. Bu savol uchun hali javob kaliti yo'q (ball berilmadi)."

    total_joined = len(game["joined"]) or 1
    breakdown_lines = ["\n📊 Javoblar taqsimoti:"]
    for letter in LETTERS:
        if not q.get(letter):
            continue
        names = game["choices_this_q"].get(letter, [])
        pct = round(100 * len(names) / total_joined)
        mark = " ✅" if letter == correct_letter else ""
        names_str = ", ".join(names) if names else "—"
        breakdown_lines.append(
            f"{LETTER_LABEL[letter]}){mark} {pct}% ({len(names)}): {names_str}"
        )
    not_answered = [
        n for uid, n in game["joined"].items() if n not in game["answer_order"]
    ]
    if not_answered:
        breakdown_lines.append(f"Javob bermaganlar: {', '.join(not_answered)}")
    reveal += "\n" + "\n".join(breakdown_lines)

    scoreboard = build_scoreboard(game)
    await context.bot.send_message(chat_id=chat_id, text=f"{reveal}\n\n{scoreboard}")

    game["idx"] += 1
    if game["idx"] >= len(game["order"]):
        await finish_game(chat_id, context)
    else:
        await group_send_question(chat_id, context)


def build_scoreboard(game) -> str:
    ranked = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)
    lines = ["📊 Joriy reyting:"]
    for i, (uid, score) in enumerate(ranked, start=1):
        name = game["joined"].get(uid, str(uid))
        lines.append(f"{i}. {name} — {score} ball")
    return "\n".join(lines)


async def finish_game(chat_id, context: ContextTypes.DEFAULT_TYPE):
    game = games[chat_id]
    game["phase"] = "finished"
    ranked = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)

    lines = ["🏆 Musobaqa yakunlandi! Yakuniy natijalar:\n"]
    for i, (uid, score) in enumerate(ranked, start=1):
        name = game["joined"].get(uid, str(uid))
        title = TITLES.get(i)
        if title:
            lines.append(f"{title}: {name} — {score} ball")
        else:
            lines.append(f"{i}. {name} — {score} ball")

    lines.append("\nYangi musobaqa uchun /start ni qayta bosing.")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))
    del games[chat_id]


async def handle_group_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, qid, chosen = query.data.split(":")
    chat_id = query.message.chat_id
    game = games.get(chat_id)

    if not game or game["phase"] != "running":
        await query.answer("Bu savol uchun musobaqa faol emas.")
        return

    user = query.from_user
    if user.id not in game["joined"]:
        await query.answer("Siz bu musobaqada qatnashmagansiz.", show_alert=True)
        return

    if user.id in game["answered_this_q"]:
        await query.answer("Siz bu savolga allaqachon javob berdingiz.")
        return

    game["answered_this_q"].add(user.id)
    name = game["joined"].get(user.id, display_name(user))
    correct_letter = ANSWERS.get(qid)
    is_correct = bool(correct_letter and chosen == correct_letter)

    if is_correct:
        game["scores"][user.id] = game["scores"].get(user.id, 0) + 1
        if game["first_correct"] is None:
            game["first_correct"] = name
            await query.answer("✅ To'g'ri! Siz birinchi topdingiz 🥇")
        else:
            await query.answer("✅ To'g'ri!")
    elif correct_letter:
        await query.answer("❌ Noto'g'ri.")
    else:
        await query.answer("Qabul qilindi (javob kaliti hali yo'q).")

    game["answer_order"].append(name)
    game["choices_this_q"].setdefault(chosen, []).append(name)

    # savol xabarini "javob berganlar" ro'yxati bilan jonli yangilaymiz
    answered_list = "\n".join(f"• {n}" for n in game["answer_order"])
    live_text = (
        f"{game['question_base_text']}\n\n"
        f"👥 Javob berganlar ({len(game['answer_order'])}/{len(game['joined'])}):\n{answered_list}"
    )
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game["question_message_id"],
            text=live_text,
            reply_markup=build_keyboard(qid, "g"),
        )
    except Exception:
        pass  # xabar o'zgarmagan yoki savol allaqachon yopilgan bo'lishi mumkin

    # agar barcha qatnashchilar javob bergan bo'lsa, vaqtdan oldin yakunlaymiz
    if len(game["answered_this_q"]) >= len(game["joined"]):
        current_idx = game["idx"]
        for job in context.job_queue.get_jobs_by_name(f"timeout_{chat_id}_{current_idx}"):
            job.schedule_removal()
        await finalize_question(chat_id, current_idx, context)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    known = sum(1 for v in ANSWERS.values() if v)
    await update.message.reply_text(
        f"Jami savollar: {len(QUESTIONS)}\n"
        f"Tasdiqlangan javob kaliti: {known} ta\n"
        f"Hali tasdiqlanmagan: {len(QUESTIONS) - known} ta\n\n"
        f"Javob kalitini to'ldirish uchun answers.json faylini tahrirlang."
    )


def main():
    if not TOKEN:
        print("XATOLIK: BOT_TOKEN muhit o'zgaruvchisi topilmadi.")
        return
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", musobaqa_start))
    app.add_handler(CommandHandler("musobaqa", musobaqa_start))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CallbackQueryHandler(handle_join, pattern=r"^join:"))
    app.add_handler(CallbackQueryHandler(handle_gostart, pattern=r"^gostart:"))
    app.add_handler(CallbackQueryHandler(solo_handle_answer, pattern=r"^solo:"))
    app.add_handler(CallbackQueryHandler(handle_group_answer, pattern=r"^g:"))

    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
