import os
import re
import json
import httpx
import asyncio
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")  # Set BOT_TOKEN in Railway Variables
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rbllzupvrgrtqhvboifl.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJibGx6dXB2cmdydHFodmJvaWZsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyOTM5NjIsImV4cCI6MjA5Nzg2OTk2Mn0.xO3oCxX6w4YzcdZJdCwWrpCXHcFg3DDR0JgYYJndXDo")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MINI_APP_URL = "https://pavelakc.github.io/English-"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + SUPABASE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

CHOOSE_STUDENT, ENTER_WORDS, CHOOSE_NATIVE_LANG, CHOOSE_LEARN_LANG = range(4)

LANGUAGES = {
    "🇬🇧 Английский": {"code": "en", "name": "English", "flag": "🇬🇧"},
    "🇩🇪 Немецкий":   {"code": "de", "name": "Deutsch", "flag": "🇩🇪"},
    "🇪🇸 Испанский":  {"code": "es", "name": "Español", "flag": "🇪🇸"},
    "🇰🇷 Корейский":  {"code": "ko", "name": "Korean",  "flag": "🇰🇷"},
    "🇺🇦 Украинский": {"code": "uk", "name": "Ukrainian","flag": "🇺🇦"},
}

# User language cache: user_id -> language code
user_lang_cache = {}

async def get_user_lang(user_id: str) -> str:
    if user_id in user_lang_cache:
        return user_lang_cache[user_id]
    result = await sb_get("/rest/v1/user_settings?user_id=eq." + user_id)
    if result and result[0].get("language"):
        user_lang_cache[user_id] = result[0]["language"]
        return result[0]["language"]
    return "en"

async def set_user_lang(user_id: str, lang: str):
    user_lang_cache[user_id] = lang
    existing = await sb_get("/rest/v1/user_settings?user_id=eq." + user_id)
    if existing:
        await sb_patch("/rest/v1/user_settings?user_id=eq." + user_id, {"language": lang})
    else:
        await sb_post("/rest/v1/user_settings", {"user_id": user_id, "language": lang, "native_language": "ru"})

MAIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("📚 Учить слова"), KeyboardButton("🧠 Квиз в боте")],
    [KeyboardButton("📊 Статистика"), KeyboardButton("🏆 Достижения")],
    [KeyboardButton("💬 Пример слова"), KeyboardButton("🔍 Поиск слова")],
    [KeyboardButton("🌍 Язык изучения"), KeyboardButton("📖 Мои слова")],
    [KeyboardButton("🎓 Стать учителем"), KeyboardButton("❌ Выйти из учителя")],
    [KeyboardButton("📤 Отправить слова"), KeyboardButton("👥 Мои ученики")],
], resize_keyboard=True)

ACHIEVEMENTS = [
    {"id": "words_10",  "words": 10,  "emoji": "🌱", "title": "Начало пути",      "desc": "Добавил 10 слов"},
    {"id": "words_25",  "words": 25,  "emoji": "📖", "title": "Читатель",          "desc": "Добавил 25 слов"},
    {"id": "words_50",  "words": 50,  "emoji": "🎯", "title": "Целеустремленный",  "desc": "Добавил 50 слов"},
    {"id": "words_100", "words": 100, "emoji": "🏆", "title": "100 слов!",         "desc": "Добавил 100 слов"},
    {"id": "words_250", "words": 250, "emoji": "🌟", "title": "Звезда",            "desc": "Добавил 250 слов"},
    {"id": "streak_3",  "streak": 3,  "emoji": "🔥", "title": "3 дня подряд",      "desc": "Занимался 3 дня подряд"},
    {"id": "streak_7",  "streak": 7,  "emoji": "💪", "title": "Неделя!",           "desc": "Занимался 7 дней подряд"},
    {"id": "know_10",   "know": 10,   "emoji": "✅", "title": "Первые знания",     "desc": "Выучил 10 слов"},
    {"id": "know_50",   "know": 50,   "emoji": "🎓", "title": "Студент",           "desc": "Выучил 50 слов"},
    {"id": "know_100",  "know": 100,  "emoji": "🎓", "title": "Выпускник",         "desc": "Выучил 100 слов"},
]

# SUPABASE
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

# AI
async def call_claude(prompt, max_tokens=200):
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
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Claude error: {e}")
        return ""

async def auto_translate(word, from_lang="en"):
    if not ANTHROPIC_KEY:
        return ""
    lang_names = {"en": "English", "de": "German", "es": "Spanish", "ko": "Korean", "uk": "Ukrainian"}
    lang_name = lang_names.get(from_lang, "English")
    prompt = 'Translate ' + lang_name + ' word or phrase "' + word + '" to Russian. Reply ONLY JSON no markdown: {"ru":"перевод на русском"}'
    text = await call_claude(prompt, 80)
    if not text:
        return ""
    try:
        clean = re.sub(r"```json|```", "", text).strip()
        d = json.loads(clean)
        return d.get("ru", "")
    except:
        import re as re2
        match = re2.search(r'"ru"\s*:\s*"([^"]+)"', text)
        if match:
            return match.group(1)
        return ""

async def generate_example(word_en, word_ru):
    text = await call_claude(
        'Give one short example sentence using "' + word_en + '" (meaning: ' + word_ru + '). '
        'Reply ONLY JSON: {"example":"English sentence","translation":"Russian translation"}', 100
    )
    try:
        d = json.loads(re.sub(r"```json|```", "", text).strip())
        return "_" + d.get("example", "") + "_ — " + d.get("translation", "")
    except:
        return ""

# PARSE
def clean_word(text):
    """Remove transcription in brackets, extra symbols"""
    import re
    # Remove content in brackets (even unclosed)
    text = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]?', '', text)
    # Remove stray bracket characters
    text = re.sub(r'[\(\[\{\)\]\}]', '', text)
    # Remove extra punctuation at start/end
    text = text.strip('.,;:!?-—–')
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_word(text):
    text = text.strip()
    # Check for separator first
    for sep in [" — ", " - ", " = ", " / ", " : "]:
        if sep in text:
            parts = text.split(sep, 1)
            en = clean_word(parts[0].strip())
            ru = clean_word(parts[1].strip())
            return en, ru
    # No separator = treat entire text as English word/phrase (no translation)
    return clean_word(text), ""

def parse_word_list(text):
    words = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        en, ru = parse_word(line)
        if en:
            words.append((en, ru))
    return words

# STATS
async def get_streak(user_id):
    prog = await sb_get("/rest/v1/progress?user_id=eq." + user_id + "&order=last_review.desc")
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

async def get_stats(user_id):
    words = await sb_get("/rest/v1/words?user_id=eq." + user_id)
    prog = await sb_get("/rest/v1/progress?user_id=eq." + user_id)
    prog_map = {p["word_id"]: p for p in prog}
    total = len(words)
    know = sum(1 for w in words if (prog_map.get(w["id"], {}).get("level", 0) or 0) >= 3)
    streak = await get_streak(user_id)
    return {"total": total, "know": know, "repeat": total - know, "streak": streak}

async def check_achievements(user_id, bot, stats):
    unlocked = await sb_get("/rest/v1/achievements?user_id=eq." + user_id)
    unlocked_ids = {a["achievement_id"] for a in (unlocked or [])}
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
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="🎉 *Новое достижение!*\n\n" + ach["emoji"] + " *" + ach["title"] + "*\n" + ach["desc"],
                    parse_mode="Markdown"
                )
            except:
                pass

async def save_word(user_id, word_en, word_ru):
    result = await sb_post("/rest/v1/words", {
        "user_id": user_id, "word_en": word_en, "word_ru": word_ru,
        "created_at": datetime.datetime.utcnow().isoformat()
    })
    if result:
        wd = result[0] if isinstance(result, list) else result
        await sb_post("/rest/v1/progress", {"user_id": user_id, "word_id": wd["id"], "level": 0})
        return wd
    return None

# DAILY REMINDER
async def reminder_job(app):
    while True:
        now = datetime.datetime.utcnow()
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += datetime.timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        users = await sb_get("/rest/v1/words?select=user_id&order=user_id")
        unique = list(set(u["user_id"] for u in (users or [])))
        for uid in unique:
            try:
                stats = await get_stats(uid)
                if stats["repeat"] == 0:
                    continue
                streak_text = "🔥 Стрик: " + str(stats["streak"]) + " дней\n" if stats["streak"] > 0 else ""
                keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
                await app.bot.send_message(
                    chat_id=uid,
                    text="🌅 *Доброе утро!*\n\n" + streak_text + "📚 К повторению: *" + str(stats["repeat"]) + "* слов",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                print("Reminder error:", e)

# HANDLERS
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    # Check if new user
    settings = await sb_get("/rest/v1/user_settings?user_id=eq." + user_id)
    if not settings:
        # New user - start onboarding
        keyboard = [
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="native_ru")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="native_en")],
            [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="native_de")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="native_es")],
        ]
        await update.message.reply_text(
            "Привет, " + (user.first_name or "друг") + "! \n\n"
            "Я помогу учить иностранные слова.\n\n"
            "Для начала — какой твой родной язык?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    # Existing user
    keyboard = [[InlineKeyboardButton("📚 Открыть тренажер", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text(
        "С возвращением, " + (user.first_name or "друг") + "! 👋\n\n"
        "Просто пиши слова — переведу и сохраню!",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )
    await update.message.reply_text(
        "👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stats = await get_stats(user_id)
    streak_text = "🔥 Стрик: *" + str(stats["streak"]) + "* дней подряд\n" if stats["streak"] > 0 else ""
    await update.message.reply_text(
        "📊 *Твоя статистика:*\n\n"
        "📝 Всего слов: *" + str(stats["total"]) + "*\n"
        "✅ Знаю хорошо: *" + str(stats["know"]) + "*\n"
        "🔄 К повторению: *" + str(stats["repeat"]) + "*\n" + streak_text,
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )

async def cmd_words(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    words = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&order=created_at.desc&limit=10")
    if not words:
        await update.message.reply_text("У тебя пока нет слов.\n\nНапиши: `hello - привет`", parse_mode="Markdown")
        return
    text = "📚 Последние " + str(len(words)) + " слов:\n\n"
    for w in words:
        text += "• *" + w["word_en"] + "* — " + w["word_ru"] + "\n"
    keyboard = [[InlineKeyboardButton("🎮 Учить слова", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_achievements(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stats = await get_stats(user_id)
    unlocked = await sb_get("/rest/v1/achievements?user_id=eq." + user_id)
    unlocked_ids = {a["achievement_id"] for a in (unlocked or [])}
    text = "🏆 *Достижения:*\n\n"
    for ach in ACHIEVEMENTS:
        if ach["id"] in unlocked_ids:
            text += "✅ " + ach["emoji"] + " *" + ach["title"] + "* — " + ach["desc"] + "\n"
        else:
            if "words" in ach:
                pct = min(100, int(stats["total"] / ach["words"] * 100))
                text += "🔒 " + ach["emoji"] + " " + ach["title"] + " — " + str(stats["total"]) + "/" + str(ach["words"]) + " (" + str(pct) + "%)\n"
            elif "streak" in ach:
                pct = min(100, int(stats["streak"] / ach["streak"] * 100))
                text += "🔒 " + ach["emoji"] + " " + ach["title"] + " — " + str(stats["streak"]) + "/" + str(ach["streak"]) + " дней (" + str(pct) + "%)\n"
            elif "know" in ach:
                pct = min(100, int(stats["know"] / ach["know"] * 100))
                text += "🔒 " + ach["emoji"] + " " + ach["title"] + " — " + str(stats["know"]) + "/" + str(ach["know"]) + " выучено (" + str(pct) + "%)\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_example(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ctx.args:
        word_en = " ".join(ctx.args)
        words = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&word_en=ilike." + word_en)
        word_ru = words[0]["word_ru"] if words else ""
    else:
        import random
        words = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&order=created_at.desc&limit=20")
        if not words:
            await update.message.reply_text("Сначала добавь слова!")
            return
        w = random.choice(words)
        word_en, word_ru = w["word_en"], w["word_ru"]
    msg = await update.message.reply_text("📝 Генерирую пример для *" + word_en + "*...", parse_mode="Markdown")
    example = await generate_example(word_en, word_ru)
    if example:
        await msg.edit_text("📝 *" + word_en + "* — " + word_ru + "\n\n💬 " + example, parse_mode="Markdown")
    else:
        await msg.edit_text("Не удалось получить пример для *" + word_en + "*", parse_mode="Markdown")

async def cmd_teacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    existing = await sb_get("/rest/v1/teacher_profiles?user_id=eq." + user_id)
    if existing and len(existing) > 0:
        students = await sb_get("/rest/v1/student_teacher?teacher_id=eq." + user_id)
        student_count = len(students) if students else 0
        await update.message.reply_text(
            "🎓 *Ты учитель!*\n\n"
            "👥 Учеников: *" + str(student_count) + "*\n"
            "🔑 Твой код: `" + user_id + "`\n\n"
            "Отправь этот код ученику — он напишет боту /student и введёт код.\n\n"
            "Чтобы выйти из режима учителя: /unteacher",
            parse_mode="Markdown"
        )
        return
    await sb_post("/rest/v1/teacher_profiles", {
        "user_id": user_id,
        "name": user.first_name or "Учитель",
        "created_at": datetime.datetime.utcnow().isoformat()
    })
    await update.message.reply_text(
        "🎓 *Режим учителя активирован!*\n\n"
        "🔑 Твой код для учеников:\n`" + user_id + "`\n\n"
        "Ученик пишет боту /student и вводит твой код.\n\n"
        "Отправить слова ученику: кнопка 📤 Отправить слова",
        parse_mode="Markdown"
    )

async def onboarding_native(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="native_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="native_en")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="native_de")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="native_es")],
    ]
    await update.message.reply_text(
        "Добро пожаловать! Какой твой родной язык?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_NATIVE_LANG

async def onboarding_learn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    native = query.data.replace("native_", "")
    ctx.user_data["native_lang"] = native
    keyboard = [
        [InlineKeyboardButton("🇬🇧 Английский", callback_data="learn_en")],
        [InlineKeyboardButton("🇩🇪 Немецкий", callback_data="learn_de")],
        [InlineKeyboardButton("🇪🇸 Испанский", callback_data="learn_es")],
        [InlineKeyboardButton("🇰🇷 Корейский", callback_data="learn_ko")],
        [InlineKeyboardButton("🇺🇦 Украинский", callback_data="learn_uk")],
    ]
    await query.edit_message_text(
        "Какой язык хочешь изучать?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_LEARN_LANG

async def onboarding_finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    learn_lang = query.data.replace("learn_", "")
    native_lang = ctx.user_data.get("native_lang", "ru")
    await set_user_lang(user_id, learn_lang)
    await sb_patch("/rest/v1/user_settings?user_id=eq." + user_id, {"native_language": native_lang})
    lang_names = {"en": "Английский", "de": "Немецкий", "es": "Испанский", "ko": "Корейский", "uk": "Украинский"}
    await query.edit_message_text(
        "Отлично! Изучаешь: *" + lang_names.get(learn_lang, learn_lang) + "*\n\n"
        "Просто пиши слова — переведу и сохраню!",
        parse_mode="Markdown"
    )
    keyboard_web = [[InlineKeyboardButton("📚 Открыть тренажер", web_app={"url": MINI_APP_URL})]]
    await query.message.reply_text("Используй кнопки меню!", reply_markup=MAIN_MENU)
    await query.message.reply_text("👇", reply_markup=InlineKeyboardMarkup(keyboard_web))
    return ConversationHandler.END

async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cur_lang = await get_user_lang(user_id)
    keyboard = []
    for name, info in LANGUAGES.items():
        mark = " ✅" if info["code"] == cur_lang else ""
        keyboard.append([InlineKeyboardButton(name + mark, callback_data="lang_" + info["code"])])
    await update.message.reply_text(
        "🌍 *Выбери язык для изучения:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cmd_unteacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    existing = await sb_get("/rest/v1/teacher_profiles?user_id=eq." + user_id)
    if not existing:
        await update.message.reply_text("Ты не в режиме учителя.")
        return
    await sb_delete("/rest/v1/teacher_profiles?user_id=eq." + user_id)
    await update.message.reply_text("✅ Режим учителя отключён.")

async def cmd_student(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    if ctx.args:
        teacher_id = ctx.args[0].strip()
        # Check teacher exists
        teacher = await sb_get("/rest/v1/teacher_profiles?user_id=eq." + teacher_id)
        if not teacher:
            await update.message.reply_text("❌ Учитель с кодом `" + teacher_id + "` не найден.", parse_mode="Markdown")
            return
        # Check already connected
        existing = await sb_get("/rest/v1/student_teacher?teacher_id=eq." + teacher_id + "&student_id=eq." + user_id)
        if existing:
            await update.message.reply_text("✅ Ты уже подключён к этому учителю!")
            return
        await sb_post("/rest/v1/student_teacher", {
            "teacher_id": teacher_id,
            "student_id": user_id,
            "student_name": user.first_name or user_id,
            "created_at": datetime.datetime.utcnow().isoformat()
        })
        teacher_name = teacher[0].get("name", "Учитель")
        await update.message.reply_text(
            "✅ Подключился к учителю *" + teacher_name + "*!\n\n"
            "Когда учитель отправит слова — ты получишь уведомление.",
            parse_mode="Markdown"
        )
        # Notify teacher
        try:
            await ctx.bot.send_message(
                chat_id=teacher_id,
                text="🎉 Новый ученик: *" + (user.first_name or user_id) + "* подключился!",
                parse_mode="Markdown"
            )
        except:
            pass
    else:
        await update.message.reply_text(
            "Напиши код учителя:\n`/student КОД_УЧИТЕЛЯ`\n\nНапример:\n`/student 703218992`",
            parse_mode="Markdown"
        )

async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    existing = await sb_get("/rest/v1/teacher_profiles?user_id=eq." + user_id)
    if not existing:
        await update.message.reply_text("Сначала активируй режим учителя: нажми кнопку 🎓 Стать учителем")
        return ConversationHandler.END
    students = await sb_get("/rest/v1/student_teacher?teacher_id=eq." + user_id)
    if not students:
        await update.message.reply_text(
            "У тебя пока нет учеников.\n\nПоделись своим кодом: `" + user_id + "`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    keyboard = []
    for s in students:
        name = s.get("student_name") or s["student_id"]
        keyboard.append([InlineKeyboardButton("👤 " + name, callback_data="student_" + s["student_id"] + "_" + name)])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await update.message.reply_text(
        "👥 *Выбери ученика:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_STUDENT

async def choose_student(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Отменено")
        return ConversationHandler.END
    parts = query.data.split("_", 2)
    student_id = parts[1]
    student_name = parts[2] if len(parts) > 2 else student_id
    ctx.user_data["chosen_student_id"] = student_id
    ctx.user_data["chosen_student_name"] = student_name
    await query.edit_message_text(
        "👤 Ученик: *" + student_name + "*\n\n"
        "✏️ Напиши слова:\n\n"
        "`hello - привет`\n"
        "`world - мир`\n\n"
        "Или без перевода — переведу сам:\n"
        "`hello\nworld`\n\n"
        "/cancel чтобы отменить.",
        parse_mode="Markdown"
    )
    return ENTER_WORDS

async def enter_words(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    student_id = ctx.user_data.get("chosen_student_id")
    student_name = ctx.user_data.get("chosen_student_name", student_id)
    word_list = parse_word_list(text)
    if not word_list:
        en, ru = parse_word(text)
        if en:
            word_list = [(en, ru)]
    if not word_list:
        await update.message.reply_text("Не понял. Попробуй ещё раз или /cancel")
        return ENTER_WORDS
    msg = await update.message.reply_text("📤 Отправляю " + str(len(word_list)) + " слов...")
    sent = []
    for word_en, word_ru in word_list:
        if not word_ru:
            word_ru = await auto_translate(word_en)
        if not word_ru:
            continue
        await sb_post("/rest/v1/teacher_words", {
            "teacher_id": user_id, "student_id": student_id,
            "word_en": word_en, "word_ru": word_ru, "added": False
        })
        sent.append("• *" + word_en + "* — " + word_ru)
    await msg.edit_text(
        "✅ Отправлено *" + str(len(sent)) + "* слов ученику *" + student_name + "*:\n\n" + "\n".join(sent),
        parse_mode="Markdown"
    )
    try:
        teacher_name = update.effective_user.first_name or "Учитель"
        keyboard = [[InlineKeyboardButton("📚 Добавить слова", web_app={"url": MINI_APP_URL})]]
        await ctx.bot.send_message(
            chat_id=student_id,
            text="📬 *" + teacher_name + "* прислал тебе *" + str(len(sent)) + "* новых слов!\n\nОткрой приложение чтобы добавить их.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except:
        pass
    return ConversationHandler.END

async def cmd_students(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    existing = await sb_get("/rest/v1/teacher_profiles?user_id=eq." + user_id)
    if not existing:
        await update.message.reply_text("Сначала активируй режим учителя: нажми 🎓 Стать учителем")
        return
    students = await sb_get("/rest/v1/student_teacher?teacher_id=eq." + user_id)
    if not students:
        await update.message.reply_text(
            "У тебя пока нет учеников.\n\nПоделись кодом: `" + user_id + "`",
            parse_mode="Markdown"
        )
        return
    text = "👥 *Твои ученики (" + str(len(students)) + "):*\n\n"
    for s in students:
        stats = await get_stats(s["student_id"])
        name = s.get("student_name") or s["student_id"]
        text += "• " + name + " — " + str(stats["total"]) + " слов, знает " + str(stats["know"]) + "\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    import random
    words = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&order=created_at.desc&limit=50")
    if len(words) < 4:
        await update.message.reply_text("Нужно минимум 4 слова для квиза! Добавь ещё.")
        return
    correct = random.choice(words)
    wrong = random.sample([w for w in words if w["id"] != correct["id"]], 3)
    options = [correct] + wrong
    random.shuffle(options)
    ctx.user_data["quiz_answer"] = correct["id"]
    keyboard = [[InlineKeyboardButton(
        clean_word(w["word_ru"]),
        callback_data="quiz_" + w["id"]
    )] for w in options]
    await update.message.reply_text(
        "🧠 *Квиз!*\n\nКак переводится:\n*" + correct["word_en"] + "*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def quiz_answer_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    # Handle unteacher
    if query.data == "unteacher":
        user_id = str(update.effective_user.id)
        await sb_delete("/rest/v1/teacher_profiles?user_id=eq." + user_id)
        await query.edit_message_text("✅ Режим учителя отключён.")
        return

    # Handle quiz next
    if query.data == "quiz_next":
        user_id = str(update.effective_user.id)
        import random
        words = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&order=created_at.desc&limit=50")
        if len(words) < 4:
            await query.message.reply_text("Нужно минимум 4 слова для квиза!")
            return
        correct = random.choice(words)
        wrong = random.sample([w for w in words if w["id"] != correct["id"]], 3)
        options = [correct] + wrong
        random.shuffle(options)
        ctx.user_data["quiz_answer"] = correct["id"]
        keyboard = [[InlineKeyboardButton(
            clean_word(w["word_ru"]),
            callback_data="quiz_" + w["id"]
        )] for w in options]
        await query.message.reply_text(
            "🧠 *Квиз!*\n\nКак переводится:\n*" + correct["word_en"] + "*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not query.data.startswith("quiz_"):
        return

    user_id = str(update.effective_user.id)
    chosen_id = query.data.replace("quiz_", "")
    correct_id = ctx.user_data.get("quiz_answer")

    if not correct_id:
        await query.edit_message_text("❌ Сессия устарела. Напиши /quiz снова.")
        return

    if chosen_id == correct_id:
        await query.edit_message_text("✅ *Правильно!*", parse_mode="Markdown")
        prog = await sb_get("/rest/v1/progress?user_id=eq." + user_id + "&word_id=eq." + correct_id)
        cur_level = prog[0]["level"] if prog else 0
        await sb_post("/rest/v1/progress", {
            "user_id": user_id, "word_id": correct_id,
            "level": min(5, cur_level + 1),
            "last_review": datetime.datetime.utcnow().isoformat()
        })
    else:
        words = await sb_get("/rest/v1/words?id=eq." + correct_id)
        correct_word = words[0] if words else {}
        await query.edit_message_text(
            "❌ *Неверно!*\n\nПравильный ответ: *" + correct_word.get("word_ru", "") + "*",
            parse_mode="Markdown"
        )
    keyboard = [[InlineKeyboardButton("➡️ Следующий вопрос", callback_data="quiz_next")]]
    await query.message.reply_text("Продолжить?", reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_testkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ANTHROPIC_KEY:
        await update.message.reply_text("❌ ANTHROPIC_API_KEY не найден!")
        return
    await update.message.reply_text("🔄 Проверяю ключ...")
    result = await call_claude('Say "OK" in Russian. Reply only: {"result":"ОК"}', 30)
    if result:
        await update.message.reply_text("✅ Ключ работает! Ответ: " + result)
    else:
        await update.message.reply_text("❌ Ключ не работает. Проверь в Railway Variables.")

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not ctx.args:
        await update.message.reply_text("Напиши: `/search слово`", parse_mode="Markdown")
        return
    query = " ".join(ctx.args).lower()
    words = await sb_get("/rest/v1/words?user_id=eq." + user_id)
    results = [w for w in words if query in w["word_en"].lower() or query in w["word_ru"].lower()]
    if not results:
        await update.message.reply_text("Слово *" + query + "* не найдено в словаре.", parse_mode="Markdown")
        return
    text = "🔍 *Результаты поиска:*\n\n"
    for w in results[:10]:
        text += "• *" + w["word_en"] + "* — " + w["word_ru"] + "\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def all_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    data = query.data

    # Onboarding - native language
    if data.startswith("native_"):
        await onboarding_learn(update, ctx)
        return

    # Onboarding - learning language
    if data.startswith("learn_"):
        await onboarding_finish(update, ctx)
        return

    # Language selection
    if data.startswith("lang_"):
        user_id = str(update.effective_user.id)
        lang = data.replace("lang_", "")
        await set_user_lang(user_id, lang)
        lang_names = {"en": "🇬🇧 Английский", "de": "🇩🇪 Немецкий", "es": "🇪🇸 Испанский", "ko": "🇰🇷 Корейский", "uk": "🇺🇦 Украинский"}
        await query.edit_message_text("✅ Язык изменён: *" + lang_names.get(lang, lang) + "*", parse_mode="Markdown")
        return

    # Unteacher
    if data == "unteacher":
        user_id = str(update.effective_user.id)
        await sb_delete("/rest/v1/teacher_profiles?user_id=eq." + user_id)
        await query.edit_message_text("✅ Режим учителя отключён.")
        return

    # Quiz next
    if data == "quiz_next":
        import random
        user_id = str(update.effective_user.id)
        words = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&order=created_at.desc&limit=50")
        if len(words) < 4:
            await query.message.reply_text("Нужно минимум 4 слова!")
            return
        correct = random.choice(words)
        wrong = random.sample([w for w in words if w["id"] != correct["id"]], 3)
        options = [correct] + wrong
        random.shuffle(options)
        ctx.user_data["quiz_answer"] = correct["id"]
        keyboard = [[InlineKeyboardButton(clean_word(w["word_ru"]), callback_data="quiz_" + w["id"])] for w in options]
        await query.message.reply_text(
            "🧠 *Квиз!*\n\nКак переводится:\n*" + correct["word_en"] + "*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Quiz answer
    if data.startswith("quiz_"):
        user_id = str(update.effective_user.id)
        chosen_id = data.replace("quiz_", "")
        correct_id = ctx.user_data.get("quiz_answer")
        if not correct_id:
            await query.edit_message_text("Сессия устарела. Напиши 🧠 Квиз в боте снова.")
            return
        if chosen_id == correct_id:
            await query.edit_message_text("✅ *Правильно!*", parse_mode="Markdown")
            prog = await sb_get("/rest/v1/progress?user_id=eq." + user_id + "&word_id=eq." + correct_id)
            cur_level = prog[0]["level"] if prog else 0
            await sb_post("/rest/v1/progress", {
                "user_id": user_id, "word_id": correct_id,
                "level": min(5, cur_level + 1),
                "last_review": datetime.datetime.utcnow().isoformat()
            })
        else:
            words = await sb_get("/rest/v1/words?id=eq." + correct_id)
            correct_word = words[0] if words else {}
            await query.edit_message_text(
                "❌ *Неверно!*\n\nПравильно: *" + clean_word(correct_word.get("word_ru", "")) + "*",
                parse_mode="Markdown"
            )
        keyboard = [[InlineKeyboardButton("➡️ Следующий вопрос", callback_data="quiz_next")]]
        await query.message.reply_text("Продолжить?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Student selection in send conversation
    if data.startswith("student_"):
        await choose_student(update, ctx)
        return

    if data == "cancel":
        await query.edit_message_text("❌ Отменено")
        return

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    # Menu buttons
    if text == "📊 Статистика":
        await cmd_stats(update, ctx); return
    if text == "🏆 Достижения":
        await cmd_achievements(update, ctx); return
    if text == "💬 Пример слова":
        await cmd_example(update, ctx); return
    if text == "🌍 Язык изучения":
        await cmd_language(update, ctx); return
    if text == "🎓 Стать учителем":
        await cmd_teacher(update, ctx); return
    if text == "❌ Выйти из учителя":
        await cmd_unteacher(update, ctx); return
    if text == "📤 Отправить слова":
        await cmd_send(update, ctx); return
    if text == "👥 Мои ученики":
        await cmd_students(update, ctx); return
    if text == "📖 Мои слова":
        await cmd_words(update, ctx); return
    if text == "📚 Учить слова":
        keyboard = [[InlineKeyboardButton("📚 Открыть тренажер", web_app={"url": MINI_APP_URL})]]
        await update.message.reply_text("Нажми кнопку:", reply_markup=InlineKeyboardMarkup(keyboard)); return
    if text == "🧠 Квиз в боте":
        await cmd_quiz(update, ctx); return
    if text == "🔍 Поиск слова":
        await update.message.reply_text("Напиши: `/search слово`", parse_mode="Markdown"); return

    word_list = parse_word_list(text)

    # Multiple words
    if len(word_list) >= 2:
        msg = await update.message.reply_text("📋 Нашел " + str(len(word_list)) + " слов. Обрабатываю...")
        saved = []
        skipped = []
        for word_en, word_ru in word_list:
            existing = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&word_en=ilike." + word_en)
            if existing:
                skipped.append(word_en); continue
            if not word_ru:
                word_ru = await auto_translate(word_en)
            if not word_ru:
                skipped.append(word_en + " (?)"); continue
            result = await save_word(user_id, word_en, word_ru)
            if result:
                saved.append("• *" + word_en + "* — " + word_ru)
        response = "✅ Добавлено: " + str(len(saved)) + "\n\n" + "\n".join(saved)
        if skipped:
            response += "\n\n⚠️ Пропущено: " + ", ".join(skipped)
        keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
        await msg.edit_text(response, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        stats = await get_stats(user_id)
        await check_achievements(user_id, ctx.bot, stats)
        return

    # Single word
    word_en, word_ru = word_list[0] if word_list else parse_word(text)
    if not word_en:
        await update.message.reply_text("Не понял. Напиши:\n`hello - привет`", parse_mode="Markdown"); return

    if not word_ru:
        msg_tr = await update.message.reply_text("🔄 Перевожу *" + word_en + "*...", parse_mode="Markdown")
        word_ru = await auto_translate(word_en)
        if not word_ru:
            await msg_tr.edit_text("Не могу перевести. Напиши:\n`" + word_en + " - перевод`", parse_mode="Markdown"); return
        await msg_tr.delete()

    existing = await sb_get("/rest/v1/words?user_id=eq." + user_id + "&word_en=ilike." + word_en)
    if existing:
        await update.message.reply_text("⚠️ *" + word_en + "* уже есть в словаре!", parse_mode="Markdown"); return

    msg = await update.message.reply_text("✨ Сохраняю...")
    result = await save_word(user_id, word_en, word_ru)
    if result:
        keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
        await msg.edit_text(
            "✅ Добавлено!\n\n• *" + word_en + "* — " + word_ru,
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        stats = await get_stats(user_id)
        await check_achievements(user_id, ctx.bot, stats)
    else:
        await msg.edit_text("❌ Ошибка сохранения.")

async def post_init(app):
    asyncio.create_task(reminder_job(app))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("words", cmd_words))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("achievements", cmd_achievements))
    app.add_handler(CommandHandler("example", cmd_example))
    app.add_handler(CommandHandler("teacher", cmd_teacher))
    app.add_handler(CommandHandler("students", cmd_students))
    app.add_handler(CommandHandler("student", cmd_student))
    app.add_handler(CommandHandler("unteacher", cmd_unteacher))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("testkey", cmd_testkey))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(quiz_answer_handler, pattern="^quiz_"))
    send_conv = ConversationHandler(
        entry_points=[CommandHandler("send", cmd_send)],
        states={
            CHOOSE_STUDENT: [CallbackQueryHandler(choose_student)],
            ENTER_WORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_words)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )
    app.add_handler(send_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
