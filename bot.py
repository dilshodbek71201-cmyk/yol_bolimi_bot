"""
Yo'l bo'limi boshliqlarini attestatsiya - Telegram Quiz Bot
=============================================================
271 ta savolni tasodifiy tartibda so'raydi, foydalanuvchi variant
tanlaydi (tugmalar orqali), agar javoblar.json faylida to'g'ri javob
belgilangan bo'lsa - to'g'ri/noto'g'ri ko'rsatadi va ballni sanaydi.
Javob kalitida bo'lmagan savollar uchun faqat tanlangan variant
saqlanadi (baholash keyinroq, kalit to'ldirilgach amalga oshiriladi).

O'RNATISH:
    pip install python-telegram-bot==21.6

ISHGA TUSHIRISH:
    1. Telegram'da @BotFather ga yozib, /newbot orqali token oling
    2. Terminalda: export BOT_TOKEN="sizning_tokeningiz"
       (yoki quyida TOKEN o'zgaruvchisiga to'g'ridan-to'g'ri yozing)
    3. python bot.py
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

TOKEN = os.environ.get("BOT_TOKEN", "8770486748:AAFWzy2Iy5RJcPfC6APmImP-zL4LAoTCXso")

with open(QUESTIONS_PATH, encoding="utf-8") as f:
    QUESTIONS = json.load(f)  # {"1": {"q":..., "a":..., "b":..., "v":..., "g":...}, ...}

with open(ANSWERS_PATH, encoding="utf-8") as f:
    ANSWERS = json.load(f)  # {"1": "v" yoki None, ...}

LETTERS = ["a", "b", "v", "g"]
LETTER_LABEL = {"a": "А", "b": "Б", "v": "В", "g": "Г"}

# har bir foydalanuvchi uchun sessiya holati (xotirada saqlanadi)
user_sessions = {}


def build_question_text(qid: str) -> str:
    q = QUESTIONS[qid]
    lines = [f"❓ {qid}-savol:\n{q['q']}\n"]
    for letter in LETTERS:
        if q.get(letter):
            lines.append(f"{LETTER_LABEL[letter]}) {q[letter]}")
    return "\n".join(lines)


def build_keyboard(qid: str) -> InlineKeyboardMarkup:
    q = QUESTIONS[qid]
    buttons = []
    row = []
    for letter in LETTERS:
        if q.get(letter):
            row.append(
                InlineKeyboardButton(
                    LETTER_LABEL[letter], callback_data=f"ans:{qid}:{letter}"
                )
            )
    buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def send_question(chat_id, context: ContextTypes.DEFAULT_TYPE, user_id):
    session = user_sessions[user_id]
    if session["idx"] >= len(session["order"]):
        # test tugadi
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
    kb = build_keyboard(qid)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    order = list(QUESTIONS.keys())
    random.shuffle(order)
    user_sessions[user_id] = {
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
    await send_question(update.effective_chat.id, context, user_id)


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_sessions:
        await query.edit_message_text("Iltimos, /start bilan qayta boshlang.")
        return

    _, qid, chosen = query.data.split(":")
    session = user_sessions[user_id]
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
    else:
        correct_text = f"{LETTER_LABEL[correct_letter]}) {q[correct_letter]}"
        result_line = f"\n\n❌ Noto'g'ri. To'g'ri javob: {correct_text}"

    new_text = build_question_text(qid) + f"\n\nSiz tanladingiz: {chosen_text}" + result_line
    await query.edit_message_text(new_text)

    session["idx"] += 1
    await send_question(query.message.chat_id, context, user_id)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    known = sum(1 for v in ANSWERS.values() if v)
    await update.message.reply_text(
        f"Jami savollar: {len(QUESTIONS)}\n"
        f"Tasdiqlangan javob kaliti: {known} ta\n"
        f"Hali tasdiqlanmagan: {len(QUESTIONS) - known} ta\n\n"
        f"Javob kalitini to'ldirish uchun answers.json faylini tahrirlang."
    )


def main():
    if TOKEN == "SIZNING_TOKENINGIZ_BU_YERGA":
        print("XATOLIK: Avval BOT_TOKEN ni sozlang (yuqoridagi izohga qarang).")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^ans:"))
    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
