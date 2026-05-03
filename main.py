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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"

if not BOT_TOKEN or not DEEPSEEK_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و DEEPSEEK_API_KEY في متغيرات البيئة")

# ---------- عميل DeepSeek والبوت ----------
deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL)
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ---------- دالة الرد الذكية ----------
async def ask_deepseek(user_message: str) -> str:
    try:
        response = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "أنت مساعد ودود ومفيد بالعربية، اسمك DeepSeek. أسلوبك لطيف ومباشر، تحب تقديم النصائح المفيدة. أجب دائمًا بالعربية."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.9,
            max_tokens=2000
        )
        return str(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return "⚠️ حدث خطأ مؤقت، حاول بعد قليل."

# ---------- تطبيق FastAPI ----------
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    """استقبال رسائل تلغرام والرد عليها"""
    try:
        data = await request.json()
        logger.info(f"Update: {data}")
        update = Update.de_json(data, bot)
        if update.message and update.message.text:
            chat_id = update.message.chat_id
            text = update.message.text
            logger.info(f"رسالة من {chat_id}: {text}")
            reply = await ask_deepseek(text)
            await bot.send_message(chat_id, reply)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "MOSLIM CHAT BOT is running!"}
