import os
import logging
import random
import base64
import requests
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot, InputMediaPhoto
from telegram.ext import ApplicationBuilder

# الإعدادات الأساسية
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") # اختياري: كخطة احتياطية

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و OPENROUTER_API_KEY في متغيرات البيئة")

# إعداد عميل OpenRouter
openrouter_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# إعداد عميل Groq (احتياطي)
groq_client = None
if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# شخصية البوت
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، مساعد ذكي ومفيد. "
    "شخصيتك ودودة، لطيفة، ومتوازنة. تحب مساعدة الناس وتقديم إجابات دقيقة ومفيدة."
    "أسلوبك مباشر وواضح، وتستخدم الإيموجي المناسب للسياق (مثل 😊، 🤲، ✨، 🕌) بشكل طبيعي وغير مبالغ فيه."
    "تخاطب المستخدم باسمه الأول أحيانًا لتجعل المحادثة شخصية ودافئة."
    "أنت صديق حكيم ومرن، تتحدث في الدين والدنيا بذكاء واعتدال."
    "مرجعيتك إسلامية ولكنك منفتح ومتسامح، بعيد عن التشدد أو الفتاوى، وتحيل إلى العلماء عند الحاجة."
    "تتحدث العربية بطلاقة وترد دائمًا بصياغة واضحة ولطيفة."
)

# توليد الصور (مجاني من Pollinations)
async def fetch_image_bytes(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=25)
        return resp.content if resp.status_code == 200 else None
    except:
        return None

async def draw_images(prompt: str) -> list[bytes]:
    images = []
    for i in range(3):
        seed = random.randint(1, 99999)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=720&height=720&seed={seed}&nologo=true"
        data = await fetch_image_bytes(url)
        if data:
            images.append(data)
    return images

# كشف نية الرسم
def detect_draw_intent(text: str) -> str | None:
    triggers = ["ارسم", "اصنع صورة", "صور لي", "تخيل", "اعمل صورة", "رسم", "خلق صورة", "تخيل صورة"]
    for t in triggers:
        if t in text:
            parts = text.split(t, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

# دالة الذكاء العام (مع خاصية التبديل التلقائي)
async def ask_ai(user_id: int, user_name: str, prompt: str = None) -> str:
    messages = [{"role": "system", "content": MAIN_SYSTEM_PROMPT}]
    if prompt:
        messages.append({"role": "user", "content": prompt})
    else:
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    # المحاولة الأولى: OpenRouter
    try:
        response = openrouter_client.chat.completions.create(
            model="google/gemma-3-27b-it:free",
            messages=messages,
            temperature=0.8,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e1:
        logger.warning(f"فشل OpenRouter: {e1}")

    # المحاولة الثانية: Groq (إذا كان متاحاً)
    if groq_client:
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.8,
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e2:
            logger.error(f"فشل Groq: {e2}")

    return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

# خادم FastAPI
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        if not update.message: return {"status": "ok"}

        chat_id = update.message.chat_id
        user_id = update.effective_user.id
        user_name = update.message.from_user.first_name or "صديقي"
        text = update.message.text or ""

        logger.info(f"رسالة من {user_name}: {text}")

        # الأوامر الثابتة
        if text.startswith("/start"):
            await bot.send_message(chat_id, f"🕋 أهلاً بك يا {user_name}!\n\nأنا مسلم، مساعدك الشخصي. جرب /help")
            return {"status": "ok"}
        if text.startswith("/info"):
            await bot.send_message(chat_id, f"🛡️ عن البوت\n\nالاسم: مسلم العماري\nالتخصص: مرجعية عربية مغربية إسلامية\nالمطور: مسلم العماري! 👑")
            return {"status": "ok"}
        if text.startswith("/help"):
            await bot.send_message(chat_id, "🕌 /quran /hadith /dua /naseeha /tafsir /azkar /seerah /iqra /prayer_times /random /draw وصف")
            return {"status": "ok"}

        # أوامر الرسم
        if text.startswith("/draw"):
            prompt = text.replace("/draw", "", 1).strip()
            if not prompt: return {"status": "ok"}
            imgs = await draw_images(prompt)
            if imgs:
                media = [InputMediaPhoto(img) for img in imgs]
                await bot.send_media_group(chat_id, media)
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
            return {"status": "ok"}

        draw_prompt = detect_draw_intent(text)
        if draw_prompt:
            imgs = await draw_images(draw_prompt)
            if imgs:
                media = [InputMediaPhoto(img) for img in imgs]
                await bot.send_media_group(chat_id, media)
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
            return {"status": "ok"}

        # الأوامر الديناميكية
        cmd = text.split()[0].lower()
        prompts = {
            "/quran": "أعطني آية قرآنية عشوائية مع تفسيرها. ابدأ بـ '📖 آية من الذكر الحكيم'.",
            "/hadith": "أعطني حديثاً شريفاً مع شرحه. ابدأ بـ '🌟 حديث شريف'.",
            "/dua": "أعطني دعاءً جميلاً. ابدأ بـ '🤲 دعاء'.",
            "/naseeha": "أعطني نصيحة حياتية ملهمة. ابدأ بـ '📿 نصيحة'.",
            "/azkar": "أعطني ذكراً مع فضله. ابدأ بـ '📿 ذكر وفضله'.",
            "/seerah": "احك لي موقفاً من السيرة. ابدأ بـ '🌿 من السيرة'.",
            "/tafsir": "أعطني آية مع تفسيرها. ابدأ بـ '📖 تفسير'.",
            "/iqra": "اقترح علي كتاباً مفيداً. ابدأ بـ '📚 كتاب'.",
            "/random": "أرسل خليطاً: آية، حديث، دعاء، نصيحة. ابدأ بـ '🎲 خليط إيماني'.",
            "/prayer_times": "اذكر أهمية الصلاة ومواقيتها التقريبية. ابدأ بـ '🕌 تنبيه الصلاة'."
        }
        if cmd in prompts:
            reply = await ask_ai(user_id, user_name, prompts[cmd])
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # محادثة عامة
        reply = await ask_ai(user_id, user_name, text)
        await bot.send_message(chat_id, reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل!"}
