import os
import json
import logging
import base64
import random
import requests
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot, InputMediaPhoto
from telegram.ext import ApplicationBuilder

# -------------------- الإعدادات --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")          # الأساسي
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")      # احتياطي
GROQ_API_KEY = os.getenv("GROQ_API_KEY")                  # اختياري

if not BOT_TOKEN or not CEREBRAS_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و CEREBRAS_API_KEY في متغيرات البيئة")

# عميل Cerebras الأساسي
cerebras_client = OpenAI(
    api_key=CEREBRAS_API_KEY,
    base_url="https://api.cerebras.ai/v1",
    timeout=20.0
)

# عميل OpenRouter الاحتياطي
openrouter_client = None
if OPENROUTER_API_KEY:
    openrouter_client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=20.0
    )

# عميل Groq الاختياري
groq_client = None
if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        timeout=20.0
    )

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

user_histories = defaultdict(list)
MAX_HISTORY = 10

DATA_FILE = "users_data.json"

def load_user_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_user_data(user_id: int, key: str, value):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    data[str(user_id)][key] = value
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_city(user_id: int) -> str:
    return load_user_data().get(str(user_id), {}).get("city", "الدار البيضاء")

SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، صديق ذكي ومتوازن. "
    "شخصيتك ودودة، لطيفة، ومتوازنة. تقدم إجابات دقيقة ومفيدة بأسلوب مباشر وواضح. "
    "تستخدم الإيموجي المناسب للسياق (😊، 🤲، ✨، 🕌) بشكل طبيعي وخفيف دون مبالغة. "
    "تخاطب المستخدم باسمه الأول أحياناً. "
    "مرجعيتك إسلامية معتدلة، بعيد عن التشدد. إذا سُئلت عن فتوى، تقول: 'هذه مسألة دينية دقيقة، يُفضل سؤال أهل العلم'. "
    "لا تبدأ أي رد بـ 'مسلم العماري:'. تحدث كصديق بشكل طبيعي. "
    "لا تستخدم كلمات مثل 'حبيبي' أو 'يا قلبي'. "
    "تتحدث بالعربية الفصحى بشكل افتراضي. إذا خاطبك المستخدم بالعامية، يمكنك الرد بنفس الأسلوب."
)

# قائمة النماذج الاحتياطية على OpenRouter (بما فيها النموذج الجديد)
OPENROUTER_FREE_MODELS = [
    "meta-llama/llama-4-maverick:free",           # نموذج جديد وقوي جداً
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "google/gemma-3-27b-it:free",
    "openrouter/free"
]

async def generate_single_image(prompt: str) -> bytes | None:
    try:
        seed = random.randint(1, 99999)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=768&height=768&seed={seed}&nologo=true"
        resp = requests.get(url, timeout=20)
        return resp.content if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"خطأ في توليد الصورة: {e}")
        return None

async def analyze_image_with_groq(image_bytes: bytes, user_name: str) -> str | None:
    if not groq_client:
        return None
    try:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        response = groq_client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"حلل هذه الصورة لـ {user_name} بأسلوب شيق."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
                ]
            }],
            temperature=0.5, max_tokens=500, timeout=20.0
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"فشل تحليل الصورة: {e}")
        return None

def detect_draw_intent(text: str) -> str | None:
    triggers = ["ارسم", "اصنع صورة", "صور لي", "تخيل", "اعمل صورة", "رسم", "خلق صورة", "تخيل صورة"]
    for t in triggers:
        if t in text:
            parts = text.split(t, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

async def ask_ai(user_id: int, user_name: str, user_message: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if user_id in user_histories:
        messages.extend(user_histories[user_id])
    messages.append({"role": "user", "content": user_message})

    # المحاولة 1: Cerebras
    try:
        response = cerebras_client.chat.completions.create(
            model="llama3.1-70b",
            messages=messages,
            temperature=0.85,
            max_tokens=500,
            timeout=15.0
        )
        reply = response.choices[0].message.content.strip()
        history = user_histories[user_id]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        if len(history) > MAX_HISTORY * 2:
            user_histories[user_id] = history[-(MAX_HISTORY * 2):]
        return reply
    except Exception as e:
        logger.warning(f"فشل Cerebras: {e}")

    # المحاولة 2: OpenRouter بجميع نماذجه
    if openrouter_client:
        for model in OPENROUTER_FREE_MODELS:
            try:
                response = openrouter_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.85,
                    max_tokens=500,
                    timeout=15.0
                )
                reply = response.choices[0].message.content.strip()
                history = user_histories[user_id]
                history.append({"role": "user", "content": user_message})
                history.append({"role": "assistant", "content": reply})
                if len(history) > MAX_HISTORY * 2:
                    user_histories[user_id] = history[-(MAX_HISTORY * 2):]
                return reply
            except Exception as e:
                logger.warning(f"فشل نموذج OpenRouter {model}: {e}")

    return "⚠️ جميع خدمات الذكاء الاصطناعي مشغولة حالياً. حاول لاحقاً."

async def get_real_prayer_times(city: str) -> str:
    try:
        url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country=Morocco"
        data = requests.get(url, timeout=5).json()
        if data["code"] == 200:
            timings = data["data"]["timings"]
            return (
                f"🕌 مواقيت الصلاة في {city} 🕌\n\n"
                f"🌅 الفجر: {timings['Fajr']}\n☀️ الشروق: {timings['Sunrise']}\n"
                f"🌤️ الظهر: {timings['Dhuhr']}\n🌇 العصر: {timings['Asr']}\n"
                f"🌆 المغرب: {timings['Maghrib']}\n🌙 العشاء: {timings['Isha']}\n\n"
                "🤲 لا تنسَ الصلاة على وقتها."
            )
        return "⚠️ لم أستطع جلب المواقيت."
    except Exception as e:
        logger.error(f"خطأ مواقيت الصلاة: {e}")
        return "⚠️ حدث خطأ في جلب المواقيت."

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        if not update.message:
            return {"status": "ok"}

        chat_id = update.message.chat_id
        user_id = update.effective_user.id
        user_name = update.message.from_user.first_name or "صديقي"

        # صورة
        if update.message.photo:
            await bot.send_message(chat_id, "👁️ جارٍ تحليل الصورة...")
            photo_file = await update.message.photo[-1].get_file()
            img_bytes = await photo_file.download_as_bytearray()
            desc = await analyze_image_with_groq(bytes(img_bytes), user_name)
            await bot.send_message(chat_id, desc or "⚠️ خدمة تحليل الصور غير مفعلة.")
            return {"status": "ok"}

        # صوت
        if update.message.voice:
            if not groq_client:
                await bot.send_message(chat_id, "⚠️ خدمة الصوت غير مفعلة.")
                return {"status": "ok"}
            file = await update.message.voice.get_file()
            file_path = f"voice_{user_id}.ogg"
            await file.download_to_drive(file_path)
            with open(file_path, "rb") as f:
                transcript = groq_client.audio.transcriptions.create(
                    model="whisper-large-v3", file=f, language="ar"
                )
            os.remove(file_path)
            text = transcript.text
            logger.info(f"صوت: {text}")
            reply = await ask_ai(user_id, user_name, text)
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # ملصق
        if update.message.sticker:
            await bot.send_message(chat_id, "😄 ملصق جميل!")
            return {"status": "ok"}

        # نص
        if not update.message.text:
            return {"status": "ok"}

        text = update.message.text.strip()
        if not text:
            return {"status": "ok"}

        logger.info(f"رسالة من {user_name}: {text}")

        if text.startswith("/start"):
            msg = f"✨ أهلاً بك {user_name}!\n\nأنا مسلم العماري، جرب /help"
            await bot.send_message(chat_id, msg)
            return {"status": "ok"}

        if text.startswith("/help"):
            msg = "🕌 /quran /hadith /dua /naseeha /tafsir /azkar /seerah /iqra /prayer_times /random /draw"
            await bot.send_message(chat_id, msg)
            return {"status": "ok"}

        if text.startswith("/info"):
            await bot.send_message(chat_id, "🛡️ مسلم العماري - مرجعية عربية مغربية إسلامية")
            return {"status": "ok"}

        if text.startswith("/clear"):
            user_histories.pop(user_id, None)
            await bot.send_message(chat_id, "🧹 تم مسح الذاكرة.")
            return {"status": "ok"}

        if text.startswith("/setcity"):
            parts = text.split(" ", 1)
            if len(parts) > 1:
                save_user_data(user_id, "city", parts[1].strip())
                await bot.send_message(chat_id, f"✅ تم حفظ مدينتك: {parts[1].strip()}")
            else:
                await bot.send_message(chat_id, "⚠️ استخدم: /setcity اسم_المدينة")
            return {"status": "ok"}

        if text.startswith("/draw"):
            prompt = text.replace("/draw", "", 1).strip()
            if not prompt:
                await bot.send_message(chat_id, "🎨 أرسل: /draw وصف")
                return {"status": "ok"}
            img = await generate_single_image(prompt)
            if img:
                await bot.send_photo(chat_id, photo=img, caption=f"🎨 صورة لك {user_name}")
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصورة.")
            return {"status": "ok"}

        draw_prompt = detect_draw_intent(text)
        if draw_prompt:
            img = await generate_single_image(draw_prompt)
            if img:
                await bot.send_photo(chat_id, photo=img, caption=f"🎨 صورة لك {user_name}")
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصورة.")
            return {"status": "ok"}

        if text.startswith("/prayer_times"):
            city = get_user_city(user_id)
            await bot.send_message(chat_id, await get_real_prayer_times(city))
            return {"status": "ok"}

        cmd = text.split()[0].lower()
        prompts = {
            "/quran": "أعطني آية قرآنية عشوائية مع تفسيرها. ابدأ بـ '📖'.",
            "/hadith": "أعطني حديثاً شريفاً مع شرحه. ابدأ بـ '🌟'.",
            "/dua": "أعطني دعاءً جميلاً. ابدأ بـ '🤲'.",
            "/naseeha": "أعطني نصيحة حياتية ملهمة. ابدأ بـ '📿'.",
            "/azkar": "أعطني ذكراً مع فضله. ابدأ بـ '📿'.",
            "/seerah": "احك لي موقفاً من السيرة. ابدأ بـ '🌿'.",
            "/tafsir": "أعطني آية مع تفسيرها. ابدأ بـ '📖'.",
            "/iqra": "اقترح علي كتاباً مفيداً. ابدأ بـ '📚'.",
            "/random": "أرسل خليطاً: آية، حديث، دعاء، نصيحة. ابدأ بـ '🎲'."
        }
        if cmd in prompts:
            reply = await ask_ai(user_id, user_name, prompts[cmd])
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        reply = await ask_ai(user_id, user_name, text)
        await bot.send_message(chat_id, reply)
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل ✨"}
