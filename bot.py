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
import time
from datetime import datetime, timedelta, timezone, time as dtime

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.error import RetryAfter
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
STATS_DIR = os.environ.get("STATS_DIR", BASE_DIR)
STATS_PATH = os.path.join(STATS_DIR, "user_stats.json")
CHATS_PATH = os.path.join(STATS_DIR, "registered_chats.json")
QCOUNT_PATH = os.path.join(STATS_DIR, "question_count.json")

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

EDIT_MIN_INTERVAL = 2.5  # bitta xabarni bundan tezroq qayta tahrirlamaymiz (flood control)


async def safe_send(bot, chat_id, text, **kwargs):
    """Flood control bo'lsa kutib, qayta urinib ko'radi - bot hech qachon to'xtab qolmaydi."""
    for attempt in range(3):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception:
            return None
    return None


async def safe_edit(bot, chat_id, message_id, text, **kwargs):
    try:
        return await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, **kwargs
        )
    except RetryAfter:
        return None  # tahrirlashni o'tkazib yuboramiz, keyingi tiklashda ko'rinadi
    except Exception:
        return None

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
    try:
        await query.edit_message_text(new_text)
    except Exception:
        pass

    session["idx"] += 1
    await solo_send_question(query.message.chat_id, context, user_id)


# ---------------------------------------------------------------------
# MUSOBAQA REJIMI (guruh) - xotira: chat_id -> game state
# ---------------------------------------------------------------------
games = {}
question_history = {}  # (chat_id, idx) -> batafsil taqsimot matni


def load_stats():
    if os.path.exists(STATS_PATH):
        try:
            with open(STATS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_stats(stats):
    try:
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


USER_STATS = load_stats()

TASHKENT_TZ = timezone(timedelta(hours=5))
ATTESTATION_DT = datetime(2026, 8, 10, 9, 0, tzinfo=TASHKENT_TZ)


def load_json_safe(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json_safe(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


REGISTERED_CHATS = set(load_json_safe(CHATS_PATH, []))


def register_chat(chat_id: int):
    if chat_id not in REGISTERED_CHATS:
        REGISTERED_CHATS.add(chat_id)
        save_json_safe(CHATS_PATH, list(REGISTERED_CHATS))


def format_countdown(target: datetime) -> str:
    now = datetime.now(TASHKENT_TZ)
    delta = target - now
    note = (
        "\n\n💡 Bilim — kuch, tayyorgarlik — g'alaba kaliti!\n"
        "❗️Agar qaysidir savolda xatolik bor deb hisoblasangiz, "
        "Adminga @D_Saidxojayev savol raqamini yozing va o'zingizning "
        "to'g'ri deb bilgan javobingizni yuboring — birgalikda testni "
        "yanada mukammal qilamiz! 🙌"
    )
    if delta.total_seconds() <= 0:
        return "⏰ Attestatsiya sanasi allaqachon boshlangan yoki o'tib ketgan." + note
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return (
        f"🎯 Attestatsiyaga sanoq boshlandi!\n\n"
        f"📅 Qoldi: {days} kun, {hours} soat, {minutes} daqiqa\n"
        f"🗓 Sana: {target.strftime('%d.%m.%Y')}, soat {target.strftime('%H:%M')}\n\n"
        f"💪 Har bir daqiqa muhim — mashq qilishda davom eting!"
        f"{note}"
    )


async def qolgan_vaqt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        register_chat(update.effective_chat.id)
    await update.message.reply_text(format_countdown(ATTESTATION_DT))


async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    text = format_countdown(ATTESTATION_DT)
    for chat_id in list(REGISTERED_CHATS):
        await safe_send(context.bot, chat_id, text)


async def check_new_questions(context: ContextTypes.DEFAULT_TYPE):
    prev = load_json_safe(QCOUNT_PATH, {}).get("count", 0)
    current = len(QUESTIONS)
    if current > prev:
        diff = current - prev
        text = (
            f"📢 E'tibor bering! {diff} ta yangi savol qo'shildi.\n"
            f"Hozir jami {current} ta savol mavjud."
        )
        for chat_id in list(REGISTERED_CHATS):
            await safe_send(context.bot, chat_id, text)
    save_json_safe(QCOUNT_PATH, {"count": current})




def record_result(user_id: int, name: str, percent: int):
    key = str(user_id)
    entry = USER_STATS.setdefault(key, {"name": name, "history": []})
    entry["name"] = name
    entry["history"].append(percent)
    save_stats(USER_STATS)


def build_analysis_text(user_id: int) -> str:
    key = str(user_id)
    entry = USER_STATS.get(key)
    if not entry or not entry["history"]:
        return "Siz hali birorta ham musobaqada qatnashmagansiz. Guruhda /start bilan boshlang!"

    history = entry["history"]
    n = len(history)
    first, last = history[0], history[-1]
    avg = sum(history) / n

    lines = [
        f"📈 Sizning tahliliz:",
        f"Jami qatnashgan safaringiz: {n} ta",
        f"Birinchi natijangiz: {first}%",
        f"Oxirgi natijangiz: {last}%",
        f"O'rtacha natija: {round(avg)}%",
    ]

    if n >= 2:
        growth_per_session = (last - first) / (n - 1)
        if growth_per_session > 0:
            remaining_pct = 100 - last
            more_sessions = remaining_pct / growth_per_session
            more_sessions = max(0, round(more_sessions))
            lines.append(f"O'sish sur'atingiz: safar boshiga ~{round(growth_per_session, 1)}%")
            if more_sessions == 0:
                lines.append("🏆 Siz allaqachon 100% natijaga erishgansiz yoki juda yaqinsiz!")
            else:
                lines.append(
                    f"Shu sur'atda yana taxminan {more_sessions} marta qatnashsangiz, "
                    f"~100% natijaga erishishingiz mumkin."
                )
        elif growth_per_session == 0:
            lines.append("Natijangiz barqaror — o'sish yoki pasayish kuzatilmayapti.")
        else:
            lines.append("So'nggi natijalaringiz pasayish tendensiyasida — ko'proq mashq qiling!")
    else:
        lines.append("Tendensiyani ko'rish uchun yana kamida 1 marta qatnashing.")

    return "\n".join(lines)


async def tahlil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_analysis_text(update.effective_user.id)
    await update.message.reply_text(text)



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
        "no_answer_streak": 0,  # ketma-ket hech kim javob bermagan savollar soni
        "last_edit_ts": 0,  # flood control uchun oxirgi tahrirlash vaqti
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
    register_chat(chat_id)
    if chat_id in games and games[chat_id]["phase"] == "running":
        await update.message.reply_text("Hozir musobaqa davom etmoqda, kuting.")
        return

    games[chat_id] = new_game_state()
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎮 Boshlash", callback_data=f"gostart:{chat_id}")]]
    )
    await update.message.reply_text(
        f"🏁 Attestatsiya musobaqasi!\n\n"
        f"Boshlash uchun \"Boshlash\" tugmasini bosing.\n"
        f"Har savolga {QUESTION_TIME_SECONDS} soniya vaqt beriladi, jami "
        f"{QUESTIONS_PER_GAME} ta savol bo'ladi.\n"
        f"Test davomida istalgan vaqtda yangi odam qo'shilishi mumkin — "
        f"variantni tanlashning o'zi yetarli.",
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

    await query.answer("Boshlanmoqda!")
    game["phase"] = "running"
    game["order"] = pick_questions(QUESTIONS_PER_GAME)
    game["idx"] = 0

    await safe_send(
        context.bot,
        chat_id,
        f"🚀 Musobaqa boshlandi! {len(game['order'])} ta savol, omad!\n"
        f"Istalgan vaqtda variant tanlab, o'yinga qo'shilishingiz mumkin.",
    )
    await group_send_question(chat_id, context)


async def group_send_question(chat_id, context: ContextTypes.DEFAULT_TYPE):
    game = games[chat_id]
    game["answered_this_q"] = set()
    game["question_closed"] = False
    game["answer_order"] = []
    game["first_correct"] = None
    game["choices_this_q"] = {}
    game["seconds_left"] = QUESTION_TIME_SECONDS

    qid = game["order"][game["idx"]]
    stem_text = build_question_text(
        qid, prefix=f"[{game['idx'] + 1}/{len(game['order'])}] "
    )
    game["question_stem_text"] = stem_text
    kb = build_keyboard(qid, "g")
    msg = await safe_send(context.bot, chat_id, build_live_text(game), reply_markup=kb)
    if msg is None:
        return
    game["question_message_id"] = msg.message_id

    context.job_queue.run_once(
        question_timeout,
        when=QUESTION_TIME_SECONDS,
        chat_id=chat_id,
        data={"idx": game["idx"]},
        name=f"timeout_{chat_id}_{game['idx']}",
    )
    context.job_queue.run_repeating(
        countdown_tick,
        interval=3,
        first=3,
        chat_id=chat_id,
        data={"idx": game["idx"]},
        name=f"countdown_{chat_id}_{game['idx']}",
    )


def build_live_text(game) -> str:
    timer_icon = "🔴" if game["seconds_left"] <= 10 else "⏱"
    text = f"{game['question_stem_text']}\n\n{timer_icon} {game['seconds_left']} soniya"
    if game["answer_order"]:
        answered_list = "\n".join(f"• {n}" for n in game["answer_order"])
        text += (
            f"\n\n👥 Javob berganlar ({len(game['answer_order'])}/{len(game['joined'])}):\n"
            f"{answered_list}"
        )
    return text


async def countdown_tick(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    idx = job.data["idx"]
    game = games.get(chat_id)

    if not game or game["idx"] != idx or game["question_closed"]:
        try:
            job.schedule_removal()
        except Exception:
            pass
        return

    game["seconds_left"] = max(0, game["seconds_left"] - 3)

    qid = game["order"][idx]
    now = time.time()
    if now - game.get("last_edit_ts", 0) >= EDIT_MIN_INTERVAL:
        game["last_edit_ts"] = now
        await safe_edit(
            context.bot,
            chat_id,
            game["question_message_id"],
            build_live_text(game),
            reply_markup=build_keyboard(qid, "g"),
        )

    if game["seconds_left"] <= 0:
        try:
            job.schedule_removal()
        except Exception:
            pass


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
    detail_lines = []
    for letter in LETTERS:
        if not q.get(letter):
            continue
        names = game["choices_this_q"].get(letter, [])
        pct = round(100 * len(names) / total_joined)
        mark = " ✅" if letter == correct_letter else ""
        breakdown_lines.append(f"{LETTER_LABEL[letter]}){mark} {pct}%")
        names_str = ", ".join(names) if names else "—"
        detail_lines.append(f"{LETTER_LABEL[letter]}){mark} {pct}% ({len(names)}): {names_str}")
    not_answered = [
        n for uid, n in game["joined"].items() if n not in game["answer_order"]
    ]
    if not_answered:
        detail_lines.append(f"Javob bermaganlar: {', '.join(not_answered)}")
    reveal += "\n" + "\n".join(breakdown_lines)

    question_history[(chat_id, idx)] = "\n".join(detail_lines)

    if len(game["answered_this_q"]) == 0:
        game["no_answer_streak"] += 1
    else:
        game["no_answer_streak"] = 0

    await safe_send(context.bot, chat_id, reveal)

    game["idx"] += 1

    if game["idx"] >= len(game["order"]):
        await finish_game(chat_id, context)
        return

    if game["no_answer_streak"] >= 2:
        game["phase"] = "paused"
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("▶️ Testni davom ettirish", callback_data=f"resume:{chat_id}")]]
        )
        await safe_send(
            context.bot,
            chat_id,
            "⏸ Ketma-ket 2 ta savolga hech kim javob bermadi. Test pauza qilindi.",
            reply_markup=kb,
        )
        return

    await group_send_question(chat_id, context)


async def handle_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id_str = query.data.split(":")
    chat_id = int(chat_id_str)
    game = games.get(chat_id)

    if not game or game["phase"] != "paused":
        await query.answer("Bu test hozir pauzada emas.", show_alert=True)
        return

    await query.answer("Davom etmoqda!")
    game["phase"] = "running"
    game["no_answer_streak"] = 0
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
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
    total_q = len(game["order"]) or 1

    lines = ["🏆 Musobaqa yakunlandi! Yakuniy natijalar:\n"]
    for i, (uid, score) in enumerate(ranked, start=1):
        name = game["joined"].get(uid, str(uid))
        title = TITLES.get(i)
        if title:
            lines.append(f"{title}: {name} — {score} ball")
        else:
            lines.append(f"{i}. {name} — {score} ball")
        percent = round(100 * score / total_q)
        record_result(uid, name, percent)

    lines.append("\nShaxsiy tahlilingizni ko'rish uchun botga shaxsiy chatda /tahlil yozing.")
    lines.append("Yangi musobaqa uchun /start ni qayta bosing.")
    await safe_send(context.bot, chat_id, "\n".join(lines))
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
        game["joined"][user.id] = display_name(user)
        game["scores"].setdefault(user.id, 0)

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

    # savol xabarini "javob berganlar" ro'yxati bilan jonli yangilaymiz (tez-tez bo'lsa - o'tkazib yuboramiz)
    now = time.time()
    if now - game.get("last_edit_ts", 0) >= EDIT_MIN_INTERVAL:
        game["last_edit_ts"] = now
        await safe_edit(
            context.bot,
            chat_id,
            game["question_message_id"],
            build_live_text(game),
            reply_markup=build_keyboard(qid, "g"),
        )

    # agar barcha qatnashchilar javob bergan bo'lsa, vaqtdan oldin yakunlaymiz
    if len(game["answered_this_q"]) >= len(game["joined"]):
        current_idx = game["idx"]
        for job in context.job_queue.get_jobs_by_name(f"timeout_{chat_id}_{current_idx}"):
            try:
                job.schedule_removal()
            except Exception:
                pass
        for job in context.job_queue.get_jobs_by_name(f"countdown_{chat_id}_{current_idx}"):
            try:
                job.schedule_removal()
            except Exception:
                pass
        await finalize_question(chat_id, current_idx, context)


async def handle_showvotes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id_str, idx_str = query.data.split(":")
    detail = question_history.get((int(chat_id_str), int(idx_str)))
    if not detail:
        await query.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    new_text = f"{query.message.text}\n\n👁 Ovozlar:\n{detail}"
    try:
        await query.edit_message_text(new_text)
    except Exception:
        pass
    await query.answer()


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    known = sum(1 for v in ANSWERS.values() if v)
    await update.message.reply_text(
        f"Jami savollar: {len(QUESTIONS)}\n"
        f"Tasdiqlangan javob kaliti: {known} ta\n"
        f"Hali tasdiqlanmagan: {len(QUESTIONS) - known} ta\n\n"
        f"Javob kalitini to'ldirish uchun answers.json faylini tahrirlang."
    )


async def global_error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Ushlanmagan xatolik:", exc_info=context.error)


def main():
    if not TOKEN:
        print("XATOLIK: BOT_TOKEN muhit o'zgaruvchisi topilmadi.")
        return
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", musobaqa_start))
    app.add_handler(CommandHandler("musobaqa", musobaqa_start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("tahlil", tahlil))
    app.add_handler(CommandHandler("qolgan_vaqt", qolgan_vaqt))

    app.add_handler(CallbackQueryHandler(handle_gostart, pattern=r"^gostart:"))
    app.add_handler(CallbackQueryHandler(handle_resume, pattern=r"^resume:"))
    app.add_handler(CallbackQueryHandler(solo_handle_answer, pattern=r"^solo:"))
    app.add_handler(CallbackQueryHandler(handle_group_answer, pattern=r"^g:"))
    app.add_error_handler(global_error_handler)

    # har 3 soatda eslatma yuboriladi
    app.job_queue.run_repeating(daily_reminder, interval=3 * 3600, first=10)
    # bot ishga tushganda, savollar soni oshgan bo'lsa xabar beriladi
    app.job_queue.run_once(check_new_questions, when=5)

    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
