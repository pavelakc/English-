import os
import re
import json
import httpx
import asyncio
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

# ─── CONFIG ───────────────────────────────────────────────
BOT_TOKEN = "8977905649:AAFerEKl6tNXNxypizZCvTKV3p-o_xv75HI"
SUPABASE_URL = "https://rbllzupvrgrtqhvboifl.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJibGx6dXB2cmdydHFodmJvaWZsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyOTM5NjIsImV4cCI6MjA5Nzg2OTk2Mn0.xO3oCxX6w4YzcdZJdCwWrpCXHcFg3DDR0JgYYJndXDo"
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MINI_APP_URL = "https://pavelakc.github.io/English-"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ─── MAIN MENU KEYBOARD ──────────────────────────────────
MAIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("📚 Учить слова"), KeyboardButton("📊 Статистика")],
    [KeyboardButton("🏆 Достижения"), KeyboardButton("💬 Пример слова")],
    [KeyboardButton("👨‍🏫 Стать учителем"), KeyboardButton("📤 Отправить слова")],
    [KeyboardButton("👥 Мои ученики"), KeyboardButton("📖 Мои слова")],
], resize_keyboard=True)

# ─── ACHIEVEMENTS ─────────────────────────────────────────
ACHIEVEMENTS = [
    {"id": "words_10",   "words": 10,  "emoji": "🌱", "title": "Начало пути",     "desc": "Добавил 10 слов"},
    {"id": "words_25",   "words": 25,  "emoji": "📖", "title": "Читатель",         "desc": "Добавил 25 слов"},
    {"id": "words_50",   "words": 50,  "emoji": "🎯", "title": "Целеустремлённый", "desc": "Добавил 50 слов"},
    {"id": "words_100",  "words": 100, "emoji": "🏆", "title": "100 слов!",        "desc": "Добавил 100 слов"},
    {"id": "words_250",  "words": 250, "emoji": "🌟", "title": "Звезда",           "desc": "Добавил 250 слов"},
    {"id": "words_500",  "words": 500, "emoji": "👑", "title": "Мастер слов",      "desc": "Добавил 500 слов"},
    {"id": "streak_3",   "streak": 3,  "emoji": "🔥", "title": "3 дня подряд",     "desc": "Занимался 3 дня подряд"},
    {"id": "streak_7",   "streak": 7,  "emoji": "💪", "title": "Неделя!",          "desc": "Занимался 7 дней подряд"},
    {"id": "streak_30",  "streak": 30, "emoji": "🚀", "title": "Месяц без пропусков","desc": "30 дней подряд"},
    {"id": "know_10",    "know": 10,   "emoji": "✅", "title": "Первые знания",    "desc": "Выучил 10 слов"},
    {"id": "know_50",    "know": 50,   "emoji": "🎓", "title": "Студент",          "desc": "Выучил 50 слов"},
    {"id": "know_100",   "know": 100,  "emoji": "🎓", "title": "Выпускник",        "desc": "Выучил 100 слов"},
]

# ─── CONVERSATION STATES ─────────────────────────────────
CHOOSE_STUDENT, ENTER_WORDS = range(2)

# ─── SUPABASE ─────────────────────────────────────────────
async def sb_get(path):
    async with httpx.AsyncClient() as client:
        r = await client.get(SUPABASE_URL + path, headers=HEADERS)
        return r.json() if r.status_code == 200 else []

async def sb_post(path, data):
    async with httpx.AsyncClient() as client:
        r = await client.post(SUPABASE_URL + path, headers=HEADERS, json=data)
        return r.json() if r.status_code in (200, 201) else None

async def sb_patch(path, data):
    async with httpx.AsyncClient() as client:
        h = {**HEADERS, "Prefer": "return=representation"}
        r = await client.patch(SUPABASE_URL + path, headers=h, json=data)
        return r.json() if r.status_code in (200, 201) else None

async def sb_delete(path):
    async with httpx.AsyncClient() as client:
        r = await client.delete(SUPABASE_URL + path, headers=HEADERS)
        return r.status_code == 204

# ─── AI ───────────────────────────────────────────────────
async def call_claude(prompt: str, max_tokens: int = 200) -> str:
    if not ANTHROPIC_KEY:
        return ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]}
            )
            data = r.json()
            return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"Claude error: {e}")
        return ""

async def auto_translate(word: str) -> str:
    text = await call_claude(f'Translate "{word}" to Russian. Reply ONLY JSON: {{"ru":"перевод"}}', 60)
    try:
        return json.loads(re.sub(r"```json|```", "", text).strip()).get("ru", "")
    except:
        return ""

async def generate_association(en: str, ru: str) -> str:
    text = await call_claude(
        f'Создай короткую смешную ассоциацию для запоминания "{en}" = "{ru}". '
        f'Ответь ТОЛЬКО JSON: {{"association":"1-2 предложения на русском"}}', 150
    )
    try:
        return json.loads(re.sub(r"```json|```", "", text).strip()).get("association", "")
    except:
        return ""

async def generate_example(en: str, ru: str) -> str:
    text = await call_claude(
        f'Give one short example sentence in English using "{en}" (meaning: {ru}). '
        f'Reply ONLY JSON: {{"example":"English sentence","translation":"Русский перевод"}}', 100
    )
    try:
        d = json.loads(re.sub(r"```json|```", "", text).strip())
        return f'_{d.get("example","")}_ — {d.get("translation","")}'
    except:
        return ""

# ─── PARSE ────────────────────────────────────────────────
def parse_word(text: str):
    text = text.strip()
    for sep in [" — ", " - ", " = ", " / ", " : "]:
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    parts = text.split(None, 1)
    if len(parts) == 2 and not parts[1][0].isupper():
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""

def parse_word_list(text: str) -> list:
    words = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        en, ru = parse_word(line)
        if en:
            words.append((en, ru))
    return words

# ─── STREAK & STATS ───────────────────────────────────────
async def get_streak(user_id: str) -> int:
    prog = await sb_get(f"/rest/v1/progress?user_id=eq.{user_id}&order=last_review.desc")
    if not prog:
        return 0
    dates = sorted(set(p["last_review"][:10] for p in prog if p.get("last_review")), reverse=True)
    streak = 0
    for i, d in enumerate(dates):
        expected = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        if d == expected:
            streak += 1
        else:
            break
    return streak

async def get_stats(user_id: str) -> dict:
    words = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}")
    prog = await sb_get(f"/rest/v1/progress?user_id=eq.{user_id}")
    prog_map = {p["word_id"]: p for p in prog}
    total = len(words)
    know = sum(1 for w in words if (prog_map.get(w["id"], {}).get("level", 0) or 0) >= 3)
    streak = await get_streak(user_id)
    return {"total": total, "know": know, "repeat": total - know, "streak": streak}

# ─── ACHIEVEMENTS CHECK ───────────────────────────────────
async def check_achievements(user_id: str, bot, stats: dict):
    # Get already unlocked
    unlocked = await sb_get(f"/rest/v1/achievements?user_id=eq.{user_id}")
    unlocked_ids = {a["achievement_id"] for a in (unlocked or [])}
    
    new_achievements = []
    for ach in ACHIEVEMENTS:
        if ach["id"] in unlocked_ids:
            continue
        earned = False
        if "words" in ach and stats["total"] >= ach["words"]:
            earned = True
        if "streak" in ach and stats["streak"] >= ach["streak"]:
            earned = True
        if "know" in ach and stats["know"] >= ach["know"]:
            earned = True
        if earned:
            await sb_post("/rest/v1/achievements", {
                "user_id": user_id,
                "achievement_id": ach["id"],
                "unlocked_at": datetime.datetime.utcnow().isoformat()
            })
            new_achievements.append(ach)
    
    # Send notifications
    for ach in new_achievements:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 *Новое достижение!*\n\n{ach['emoji']} *{ach['title']}*\n{ach['desc']}",
                parse_mode="Markdown"
            )
        except:
            pass

# ─── SAVE WORD ────────────────────────────────────────────
async def save_word(user_id: str, word_en: str, word_ru: str) -> dict:
    result = await sb_post("/rest/v1/words", {
        "user_id": user_id, "word_en": word_en, "word_ru": word_ru,
        "created_at": datetime.datetime.utcnow().isoformat()
    })
    if result:
        wd = result[0] if isinstance(result, list) else result
        await sb_post("/rest/v1/progress", {"user_id": user_id, "word_id": wd["id"], "level": 0})
        return wd
    return None

# ─── DAILY REMINDER ───────────────────────────────────────
async def send_daily_reminders(app):
    users = await sb_get("/rest/v1/words?select=user_id&order=user_id")
    unique_users = list(set(u["user_id"] for u in (users or [])))
    for user_id in unique_users:
        try:
            stats = await get_stats(user_id)
            repeat = stats["repeat"]
            streak = stats["streak"]
            if repeat == 0:
                continue
            streak_text = f"🔥 Стрик: {streak} дней\n" if streak > 0 else ""
            keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
            await app.bot.send_message(
                chat_id=user_id,
                text=f"🌅 *Доброе утро!*\n\n"
                     f"{streak_text}"
                     f"📚 К повторению: *{repeat}* слов\n\n"
                     f"Не забудь позаниматься сегодня!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            print(f"Reminder error for {user_id}: {e}")

async def reminder_job(app):
    while True:
        now = datetime.datetime.utcnow()
        # Send at 7:00 UTC (approx 9:00 MSK / 1:00 MST)
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += datetime.timedelta(days=1)
        wait = (next_run - now).total_seconds()
        await asyncio.sleep(wait)
        await send_daily_reminders(app)

# ─── HANDLERS ─────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я помогу учить английские слова.\n\n"
        "📝 *Как добавить слово:*\n"
        "`hello - привет`\n\n"
        "📋 *Или список сразу:*\n"
        "`Behaviour — поведение\nAgreement — соглашение`\n\n"
        "🤖 *Без перевода — переведу сам:*\n"
        "`Behaviour\nAgreement\nCourt`",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )
    await update.message.reply_text(
        "👆 Используй кнопки меню или просто пиши слова!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stats = await get_stats(user_id)
    streak_text = f"🔥 Стрик: *{stats['streak']}* дней подряд\n" if stats['streak'] > 0 else ""
    await update.message.reply_text(
        f"📊 *Твоя статистика:*\n\n"
        f"📝 Всего слов: *{stats['total']}*\n"
        f"✅ Знаю хорошо: *{stats['know']}*\n"
        f"🔄 К повторению: *{stats['repeat']}*\n"
        f"{streak_text}",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )

async def cmd_words(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    words = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}&order=created_at.desc&limit=10")
    if not words:
        await update.message.reply_text("У тебя пока нет слов.\n\nНапиши: `hello - привет`", parse_mode="Markdown")
        return
    text = f"📚 Последние {len(words)} слов:\n\n"
    for w in words:
        text += f"• *{w['word_en']}* — {w['word_ru']}\n"
    keyboard = [[InlineKeyboardButton("🎮 Учить слова", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_achievements(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stats = await get_stats(user_id)
    unlocked = await sb_get(f"/rest/v1/achievements?user_id=eq.{user_id}")
    unlocked_ids = {a["achievement_id"] for a in (unlocked or [])}
    
    text = "🏆 *Достижения:*\n\n"
    for ach in ACHIEVEMENTS:
        if ach["id"] in unlocked_ids:
            text += f"✅ {ach['emoji']} *{ach['title']}* — {ach['desc']}\n"
        else:
            # Show progress
            if "words" in ach:
                pct = min(100, int(stats['total'] / ach['words'] * 100))
                text += f"🔒 {ach['emoji']} {ach['title']} — {stats['total']}/{ach['words']} слов ({pct}%)\n"
            elif "streak" in ach:
                pct = min(100, int(stats['streak'] / ach['streak'] * 100))
                text += f"🔒 {ach['emoji']} {ach['title']} — {stats['streak']}/{ach['streak']} дней ({pct}%)\n"
            elif "know" in ach:
                pct = min(100, int(stats['know'] / ach['know'] * 100))
                text += f"🔒 {ach['emoji']} {ach['title']} — {stats['know']}/{ach['know']} выучено ({pct}%)\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_example(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = ctx.args
    if args:
        word_en = " ".join(args)
        # Find translation
        words = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}&word_en=ilike.{word_en}")
        word_ru = words[0]["word_ru"] if words else ""
    else:
        # Random word
        words = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}&order=created_at.desc&limit=20")
        if not words:
            await update.message.reply_text("Сначала добавь слова!")
            return
        import random
        w = random.choice(words)
        word_en, word_ru = w["word_en"], w["word_ru"]
    
    msg = await update.message.reply_text(f"📝 Генерирую пример для *{word_en}*...", parse_mode="Markdown")
    example = await generate_example(word_en, word_ru)
    if example:
        await msg.edit_text(
            f"📝 *{word_en}* — {word_ru}\n\n💬 {example}",
            parse_mode="Markdown"
        )
    else:
        await msg.edit_text(f"Не удалось получить пример для *{word_en}*", parse_mode="Markdown")

async def cmd_teacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if already teacher
    existing = await sb_get(f"/rest/v1/teacher_profiles?user_id=eq.{user_id}")
    if existing and len(existing) > 0:
        # Show teacher info
        students = await sb_get(f"/rest/v1/student_teacher?teacher_id=eq.{user_id}")
        student_count = len(students) if students else 0
        await update.message.reply_text(
            f"👨‍🏫 *Ты уже учитель!*

"
            f"👥 Учеников: *{student_count}*
"
            f"🔑 Твой код для учеников: `{user_id}`

"
            f"Ученик вводит этот код в приложении во вкладке Итоги → Подключиться к учителю.",
            parse_mode="Markdown"
        )
        return
    
    # Activate teacher mode
    await sb_post("/rest/v1/teacher_profiles", {
        "user_id": user_id,
        "name": user.first_name or "Учитель",
        "created_at": datetime.datetime.utcnow().isoformat()
    })
    
    await update.message.reply_text(
        f"👨‍🏫 *Режим учителя активирован!*

"
        f"🔑 Твой код для учеников:
`{user_id}`

"
        f"*Как добавить ученика:*
"
        f"Ученик открывает Mini App → вкладка Итоги → вводит твой код

"
        f"*Как отправить слова ученику:*
"
        f"`/send [ID ученика] слово - перевод`

"
        f"Например:
`/send 123456789 hello - привет`",
        parse_mode="Markdown"
    )

async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Check teacher status
    existing = await sb_get(f"/rest/v1/teacher_profiles?user_id=eq.{user_id}")
    if not existing:
        await update.message.reply_text("❌ Сначала активируй режим учителя: /teacher")
        return
    
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "❓ Формат: `/send [ID ученика] слово - перевод`

"
            "Например:
`/send 123456789 hello - привет`

"
            "Или список:
`/send 123456789
hello - привет
world - мир`",
            parse_mode="Markdown"
        )
        return
    
    student_id = ctx.args[0]
    rest = " ".join(ctx.args[1:])
    
    # Check student exists
    student = await sb_get(f"/rest/v1/student_teacher?teacher_id=eq.{user_id}&student_id=eq.{student_id}")
    if not student:
        await update.message.reply_text(f"❌ Ученик `{student_id}` не подключён к тебе.", parse_mode="Markdown")
        return
    
    # Parse words
    word_list = parse_word_list(rest)
    if not word_list:
        en, ru = parse_word(rest)
        if en:
            word_list = [(en, ru)]
    
    if not word_list:
        await update.message.reply_text("❓ Не понял слова. Напиши: `/send 123 hello - привет`", parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text(f"📤 Отправляю {len(word_list)} слов ученику...")
    sent = []
    for word_en, word_ru in word_list:
        if not word_ru:
            word_ru = await auto_translate(word_en)
        if not word_ru:
            continue
        await sb_post("/rest/v1/teacher_words", {
            "teacher_id": user_id,
            "student_id": student_id,
            "word_en": word_en,
            "word_ru": word_ru,
            "added": False
        })
        sent.append(f"• *{word_en}* — {word_ru}")
    
    await msg.edit_text(
        f"✅ Отправлено {len(sent)} слов ученику `{student_id}`:

" + "
".join(sent),
        parse_mode="Markdown"
    )
    
    # Notify student
    try:
        teacher_name = update.effective_user.first_name or "Учитель"
        keyboard = [[InlineKeyboardButton("📚 Посмотреть слова", web_app={"url": MINI_APP_URL})]]
        await ctx.bot.send_message(
            chat_id=student_id,
            text=f"📬 *{teacher_name}* прислал тебе {len(sent)} новых слов!

Открой приложение чтобы добавить их в словарь.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        pass

async def cmd_students(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    existing = await sb_get(f"/rest/v1/teacher_profiles?user_id=eq.{user_id}")
    if not existing:
        await update.message.reply_text("❌ Сначала активируй режим учителя: /teacher")
        return
    
    students = await sb_get(f"/rest/v1/student_teacher?teacher_id=eq.{user_id}")
    if not students:
        await update.message.reply_text(
            "👥 У тебя пока нет учеников.

"
            f"Поделись своим кодом: `{user_id}`",
            parse_mode="Markdown"
        )
        return
    
    text = f"👥 *Твои ученики ({len(students)}):

*"
    for s in students:
        stats = await get_stats(s['student_id'])
        text += f"• {s.get('student_name', s['student_id'])} — {stats['total']} слов, знает {stats['know']}
"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text.strip()
    
    if text.startswith("/"):
        return

    # Handle menu buttons
    if text == "📊 Статистика":
        await cmd_stats(update, ctx)
        return
    if text == "🏆 Достижения":
        await cmd_achievements(update, ctx)
        return
    if text == "💬 Пример слова":
        await cmd_example(update, ctx)
        return
    if text == "👨‍🏫 Стать учителем":
        await cmd_teacher(update, ctx)
        return
    if text == "📤 Отправить слова":
        await cmd_send(update, ctx)
        return
    if text == "👥 Мои ученики":
        await cmd_students(update, ctx)
        return
    if text == "📖 Мои слова":
        await cmd_words(update, ctx)
        return
    if text == "📚 Учить слова":
        keyboard = [[InlineKeyboardButton("📚 Открыть тренажёр", web_app={"url": MINI_APP_URL})]]
        await update.message.reply_text(
            "Нажми кнопку чтобы открыть тренажёр! 👇",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    word_list = parse_word_list(text)
    
    # MULTIPLE WORDS
    if len(word_list) >= 2:
        msg = await update.message.reply_text(f"📋 Нашёл {len(word_list)} слов. Обрабатываю...")
        saved = []
        skipped = []
        need_translate = [(en, ru) for en, ru in word_list if not ru]
        
        if need_translate:
            await msg.edit_text(f"🔄 Перевожу {len(need_translate)} слов...")
        
        for word_en, word_ru in word_list:
            existing = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}&word_en=ilike.{word_en}")
            if existing:
                skipped.append(word_en)
                continue
            if not word_ru:
                word_ru = await auto_translate(word_en)
            if not word_ru:
                skipped.append(f"{word_en} (?)")
                continue
            result = await save_word(user_id, word_en, word_ru)
            if result:
                saved.append(f"• *{word_en}* — {word_ru}")
        
        response = f"✅ Добавлено: {len(saved)}\n\n" + "\n".join(saved)
        if skipped:
            response += f"\n\n⚠️ Пропущено: {', '.join(skipped)}"
        
        keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
        await msg.edit_text(response, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Check achievements
        stats = await get_stats(user_id)
        await check_achievements(user_id, ctx.bot, stats)
        return
    
    # SINGLE WORD
    word_en, word_ru = word_list[0] if word_list else parse_word(text)
    
    if not word_en:
        await update.message.reply_text("❓ Не понял. Напиши:\n`hello - привет`", parse_mode="Markdown")
        return
    
    # Auto-translate if no translation
    if not word_ru:
        msg_tr = await update.message.reply_text(f"🔄 Перевожу *{word_en}*...", parse_mode="Markdown")
        word_ru = await auto_translate(word_en)
        if not word_ru:
            await msg_tr.edit_text(f"❓ Не могу перевести. Напиши:\n`{word_en} - перевод`", parse_mode="Markdown")
            return
        await msg_tr.delete()
    
    # Check duplicate
    existing = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}&word_en=ilike.{word_en}")
    if existing:
        await update.message.reply_text(f"⚠️ *{word_en}* уже есть в словаре!", parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text("✨ Сохраняю...")
    result = await save_word(user_id, word_en, word_ru)
    
    if result:
        keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
        await msg.edit_text(
            f"✅ Добавлено!\n\n• *{word_en}* — {word_ru}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # Check achievements
        stats = await get_stats(user_id)
        await check_achievements(user_id, ctx.bot, stats)
    else:
        await msg.edit_text("❌ Ошибка сохранения.")

async def post_init(app):
    asyncio.create_task(reminder_job(app))

# ─── MAIN ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("words", cmd_words))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("achievements", cmd_achievements))
    app.add_handler(CommandHandler("example", cmd_example))
    app.add_handler(CommandHandler("teacher", cmd_teacher))
    app.add_handler(CommandHandler("students", cmd_students))
    
    # Send words conversation
    send_conv = ConversationHandler(
        entry_points=[CommandHandler("send", cmd_send)],
        states={
            CHOOSE_STUDENT: [CallbackQueryHandler(choose_student)],
            ENTER_WORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_words)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)],
    )
    app.add_handler(send_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
