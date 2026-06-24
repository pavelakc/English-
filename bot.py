import os
import re
import json
import httpx
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ─── CONFIG ───────────────────────────────────────────────
BOT_TOKEN = "8977905649:AAFerEKl6tNXNxypizZCvTKV3p-o_xv75HI"
SUPABASE_URL = "https://rbllzupvrgrtqhvboifl.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJibGx6dXB2cmdydHFodmJvaWZsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyOTM5NjIsImV4cCI6MjA5Nzg2OTk2Mn0.xO3oCxX6w4YzcdZJdCwWrpCXHcFg3DDR0JgYYJndXDo"
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # добавь свой ключ
MINI_APP_URL = "https://pavelakc.github.io/English-"  # замени на свой GitHub Pages URL

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

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

# ─── AI ASSOCIATION ───────────────────────────────────────
async def generate_association(word_en: str, word_ru: str) -> dict:
    if not ANTHROPIC_KEY:
        return {"association": "", "image_url": ""}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 200,
                    "messages": [{
                        "role": "user",
                        "content": f"""Создай короткую смешную ассоциацию для запоминания английского слова.
Слово: "{word_en}" = "{word_ru}"
Ответь ТОЛЬКО JSON без лишнего текста:
{{"association": "1-2 предложения на русском, смешная ассоциация"}}"""
                    }]
                }
            )
            data = r.json()
            text = data["content"][0]["text"].strip()
            text = re.sub(r"```json|```", "", text).strip()
            result = json.loads(text)
            return {"association": result.get("association", ""), "image_url": ""}
    except Exception as e:
        print(f"AI error: {e}")
        return {"association": "", "image_url": ""}

# ─── PARSE WORD ───────────────────────────────────────────
def parse_word(text: str):
    """
    Форматы:
    - hello - привет
    - hello — привет  
    - hello = привет
    - hello / привет
    - hello : привет
    - hello привет (два слова)
    """
    text = text.strip()
    for sep in [" — ", " - ", " = ", " / ", " : "]:
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    # Попробуй разделить по пробелу если два слова
    parts = text.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text, ""

# ─── HANDLERS ─────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "друг"
    
    keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\n"
        "Я помогу тебе учить английские слова.\n\n"
        "📝 *Как добавить слово:*\n"
        "Просто напиши в чат:\n"
        "`hello - привет`\n"
        "`give up - сдаваться`\n"
        "`hire foreigners — нанимать иностранцев`\n\n"
        "🎮 Нажми кнопку ниже чтобы учить слова!",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text.strip()
    
    # Игнорируй команды
    if text.startswith("/"):
        return
    
    # Парсим слово
    word_en, word_ru = parse_word(text)
    
    if not word_en:
        await update.message.reply_text("❓ Не понял. Напиши так:\n`hello - привет`", parse_mode="Markdown")
        return
    
    if not word_ru:
        await update.message.reply_text(
            f"❓ Не вижу перевод для *{word_en}*\n\nНапиши так:\n`{word_en} - перевод`",
            parse_mode="Markdown"
        )
        return
    
    # Сообщение о процессе
    msg = await update.message.reply_text("✨ Генерирую ассоциации и картинки...")
    
    # Генерируем AI ассоциацию
    ai = await generate_association(word_en, word_ru)
    
    # Сохраняем в Supabase
    result = await sb_post("/rest/v1/words", {
        "user_id": user_id,
        "word_en": word_en,
        "word_ru": word_ru,
        "association": ai["association"],
        "image_url": ai["image_url"]
    })
    
    if result:
        word_data = result[0] if isinstance(result, list) else result
        
        # Инициализируем прогресс
        await sb_post("/rest/v1/progress", {
            "user_id": user_id,
            "word_id": word_data["id"],
            "level": 0
        })
        
        # Ответ пользователю
        assoc_text = f"\n\n💡 _{ai['association']}_" if ai["association"] else ""
        
        keyboard = [[InlineKeyboardButton("📚 Учить слова", web_app={"url": MINI_APP_URL})]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"✅ Добавлено карточек: 1\n\n"
            f"• *{word_en}* — {word_ru}"
            f"{assoc_text}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await msg.edit_text("❌ Ошибка сохранения. Попробуй ещё раз.")

async def my_words(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    words = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}&order=created_at.desc&limit=10")
    
    if not words:
        await update.message.reply_text("У тебя пока нет слов. Добавь первое!\n\nНапиши: `hello - привет`", parse_mode="Markdown")
        return
    
    text = f"📚 Твои последние {len(words)} слов:\n\n"
    for w in words:
        text += f"• *{w['word_en']}* — {w['word_ru']}\n"
    
    keyboard = [[InlineKeyboardButton("🎮 Учить слова", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    words = await sb_get(f"/rest/v1/words?user_id=eq.{user_id}")
    progress = await sb_get(f"/rest/v1/progress?user_id=eq.{user_id}")
    
    total = len(words)
    know = sum(1 for p in progress if p.get("level", 0) >= 3)
    repeat = total - know
    
    await update.message.reply_text(
        f"📊 *Твоя статистика:*\n\n"
        f"📝 Всего слов: *{total}*\n"
        f"✅ Знаю хорошо: *{know}*\n"
        f"🔄 К повторению: *{repeat}*",
        parse_mode="Markdown"
    )

async def learn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📚 Открыть тренажёр", web_app={"url": MINI_APP_URL})]]
    await update.message.reply_text(
        "🎮 Нажми кнопку чтобы учить слова!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── MAIN ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("words", my_words))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("learn", learn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
