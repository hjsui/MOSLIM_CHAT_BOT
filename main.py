import os
import logging
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from openai import OpenAI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة المفاتيح من البيئة
BOT_TOKEN = os.getenv("8757944445:AAF8YJ6Ee3GJ4j6UMuSYG7_A1mGkCpKgI3M")
DEEPSEEK_API_KEY = os.getenv("sk-0f1733b1ec0043b480b5bc77fa66edf4")
BASE_URL = "https://api.deepseek.com"

if not BOT_TOKEN or not DEEPSEEK_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و DEEPSEEK_API_KEY في متغيرات البيئة")

# عميل DeepSeek
deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL)
app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = app_bot.bot

# صياغة الردود
async def get_deepseek_reply(text: str) -> str:
    try:
        resp = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system",
                 "content": "أنت مساعد ودود ومفيد بالعربية، اسمك DeepSeek. "
                            "أسلوبك لطيف ومباشر، تحب تقديم النصائح المفيدة. "
                            "أجب دائمًا بالعربية."},
                {"role": "user", "content": text}
            ],
            temperature=0.9,
            max_tokens=2000
        )
        return str(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return "⚠️ حدث خطأ مؤقت، حاول بعد قليل."

# تطبيق FastAPI
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        if update.message and update.message.text:
            text = update.message.text
            chat_id = update.message.chat_id
            reply = await get_deepseek_reply(text)
            await bot.send_message(chat_id, reply)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "DeepSeek Bot is running!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
