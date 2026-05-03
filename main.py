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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و GROQ_API_KEY في متغيرات البيئة")

# ---------- عميل Groq ----------
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ---------- دالة الرد الذكية ----------
async def ask_groq(user_message: str) -> str:
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "أنت مساعد ودود ومفيد بالعربية، اسمك MOSLIM CHAT. "
                        "أسلوبك لطيف ومباشر، تحب تقديم النصائح المفيدة. "
                        "أجب دائمًا بالعربية."
                    )
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.9,
            max_tokens=2000
        )
        return str(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ حدث خطأ مؤقت، حاول بعد قليل."

# ---------- تطبيق FastAPI ----------
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
            logger.info(f"رسالة من {chat_id}: {text}")
            reply = await ask_groq(text)
            await bot.send_message(chat_id, reply)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "MOSLIM CHAT BOT is running!"}
