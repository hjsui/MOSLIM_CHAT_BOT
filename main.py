import os
import logging
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder

# ---------- الإعدادات ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # أصبح المفتاح لجيميناي

if not BOT_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و GEMINI_API_KEY في متغيرات البيئة")

# ---------- عميل Gemini (مجاني!) ----------
gemini = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ---------- دالة الرد الذكية ----------
async def ask_gemini(user_message: str) -> str:
    try:
        response = gemini.chat.completions.create(
            model="gemini-1.5-flash", # نموذج مجاني وسريع
            messages=[
                {"role": "system", "content": "أنت مساعد ودود ومفيد بالعربية، اسمك MOSLIM CHAT. أجب دائمًا بالعربية."},
                {"role": "user", "content": user_message}
            ],
        )
        return str(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "⚠️ حدث خطأ مؤقت، حاول بعد قليل."

# ---------- تطبيق FastAPI (لم يتغير) ----------
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    """استقبال رسائل تلغرام والرد عليها"""
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        if update.message and update.message.text:
            chat_id = update.message.chat_id
            text = update.message.text
            reply = await ask_gemini(text)
            await bot.send_message(chat_id, reply)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "MOSLIM CHAT BOT is running!"}
