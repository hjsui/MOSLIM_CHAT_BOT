import os
import json
import logging
import base64
import random
import time
import requests
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot, InputMediaPhoto
from telegram.ext import ApplicationBuilder

# ==================== الإعدادات ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و GROQ_API_KEY في متغيرات البيئة")

groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ==================== الذاكرة المؤقتة ====================
user_histories = defaultdict(list)
MAX_HISTORY_LENGTH = 10

# ==================== الذاكرة طويلة المدى ====================
DATA_FILE = "users_data.json"

def load_all_users():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_user_data(user_id: int, key: str, value):
    data = load_all_users()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"name": "", "city": "الدار البيضاء", "preferences": {}}
    data[uid][key] = value
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id: int):
    data = load_all_users()
    return data.get(str(user_id), {"name": "", "city": "الدار البيضاء", "preferences": {}})

# ==================== شخصية البوت الحيوية ====================
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، صديق ودود ومبهج ومليء بالطاقة الإيجابية! 😊✨ "
    "تحب مساعدة الناس وتقديم النصائح الذكية والعصرية في الدين والحياة والعمل والصحة. "
    "أسلوبك دافئ ومباشر، وتستخدم الإيموجي 🎉❤️🔥 باعتدال لتعزيز مشاعرك. "
    "عندما تتحدث، تشعر الشخص وكأنه يتحدث مع صديقه المفضل. "
    "تنادي الشخص باسمه بين الحين والآخر لتجعل المحادثة شخصية. "
    "أنت مسلم معتدل ومتوازن، بعيد عن التشدد، وإذا سُئلت عن فتوى تحيل إلى العلماء. "
    "لو شعرت أن صديقك حزين أو متضايق، تواسيه بكلمات لطيفة 🤲💚. "
    "دائماً تبدأ ردودك أو تنهيها بابتسامة أو إيموجي يعبر عن الموقف. "
    "تحدث بالعربية."
)

# ==================== أوامر المحتوى الإسلامي ====================
QURAN_PROMPT = "أنت 'مسلم العماري'. أعطني آية قرآنية مؤثرة مع تفسيرها. ابدأ بـ '📖 آية من الذكر الحكيم'."
HADITH_PROMPT = "أنت 'مسلم العماري'. أعطني حديثاً شريفاً مع شرحه. ابدأ بـ '🌟 حديث شريف'."
DUA_PROMPT = "أنت 'مسلم العماري'. أعطني دعاءً جميلاً. ابدأ بـ '🤲 دعاء مبارك'."
NASEHA_PROMPT = "أنت 'مسلم العماري'. أعطني نصيحة حياتية ملهمة. ابدأ بـ '📿 نصيحة اليوم'."
AZKAR_PROMPT = "أنت 'مسلم العماري'. أعطني ذكراً مع فضله. ابدأ بـ '📿 ذكر وفضله'."
SEERAH_PROMPT = "أنت 'مسلم العماري'. احك لي موقفاً من السيرة. ابدأ بـ '🌿 من السيرة'."
TAFSIR_PROMPT = "أنت 'مسلم العماري'. أعطني آية مع تفسيرها. ابدأ بـ '📖 تفسير'."
BOOK_PROMPT = "أنت 'مسلم العماري'. اقترح كتاباً مفيداً. ابدأ بـ '📚 كتاب اليوم'."
RANDOM_PROMPT = "أنت 'مسلم العماري'. أرسل خليطاً إيمانياً: آية، حديث، دعاء، نصيحة. ابدأ بـ '🎲 خليط إيماني'."

# ==================== توليد 3 صور فريدة ====================
async def generate_three_images(prompt: str) -> list:
    urls = []
    base_url = "https://image.pollinations.ai/prompt/"
    for i in range(3):
        seed = random.randint(1, 99999)
        url = f"{base_url}{prompt}?width=768&height=768&seed={seed}&nologo=true"
        urls.append(url)
    return urls

# ==================== تحليل الصورة (Groq Vision) ====================
async def analyze_image(image_bytes: bytes, user_first_name: str) -> str:
    try:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        response = groq_client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"أنت 'مسلم العماري'، صديق ودود. حلل هذه الصورة بالعربية بأسلوب شيّق ومفعم بالطاقة. تحدث مع {user_first_name}."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
                    ]
                }
            ],
            temperature=0.5,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"تحليل الصورة فشل: {e}")
        return "⚠️ لم أستطع تحليل الصورة، حاول مرة أخرى."

# ==================== مواقيت الصلاة ====================
async def get_real_prayer_times(city: str, country: str = "Morocco"):
    try:
        url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}"
        data = requests.get(url, timeout=5).json()
        if data["code"] == 200:
            timings = data["data"]["timings"]
            return (
                f"🕌 مواقيت الصلاة في {city} 🕌\n\n"
                f"🌅 الفجر: {timings['Fajr']}\n"
                f"☀️ الشروق: {timings['Sunrise']}\n"
                f"🌤️ الظهر: {timings['Dhuhr']}\n"
                f"🌇 العصر: {timings['Asr']}\n"
                f"🌆 المغرب: {timings['Maghrib']}\n"
                f"🌙 العشاء: {timings['Isha']}\n\n"
                f"🤲 لا تنسَ الصلاة على وقتها 🤲"
            )
        return "⚠️ لم أستطع جلب المواقيت، تأكد من اسم المدينة."
    except Exception as e:
        logger.error(f"خطأ في مواقيت الصلاة: {e}")
        return "⚠️ حدث خطأ في جلب المواقيت."

# ==================== المحادثة مع احتياطي ضد الأخطاء ====================
async def ask_groq_with_fallback(system_prompt: str, user_id: int, user_first_name: str, user_message: str = None):
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "system", "content": f"اسم صديقك الذي تتحدث معه هو {user_first_name}."})

    if user_message:
        history = user_histories[user_id]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
    else:
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    for attempt, model in enumerate(models):
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.9,
                max_tokens=2000
            )
            reply = response.choices[0].message.content
            if user_message:
                history = user_histories[user_id]
                history.append({"role": "user", "content": user_message})
                history.append({"role": "assistant", "content": reply})
                if len(history) > MAX_HISTORY_LENGTH * 2:
                    user_histories[user_id] = history[-(MAX_HISTORY_LENGTH * 2):]
            return reply
        except Exception as e:
            if "429" in str(e) and attempt == 0:
                logger.warning("النموذج الأساسي مشغول، جارٍ التبديل للنموذج الاحتياطي...")
                time.sleep(1)
                continue
            else:
                logger.error(f"فشل الاتصال: {e}")
                return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

# ==================== كشف نية الرسم ====================
def detect_draw_intent(text: str) -> str | None:
    triggers = ["ارسم", "اصنع صورة", "صور لي", "تخيل", "اعمل صورة", "رسم", "خلق صورة", "تخيل صورة"]
    for t in triggers:
        if t in text:
            parts = text.split(t, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

# ==================== معالجة الأوامر ====================
async def handle_command(text: str, user_first_name: str, user_id: int):
    cmd = text.split()[0].lower()
    if cmd == "/start":
        return f"🕋 مرحباً {user_first_name}! 🌟\n\nأنا مسلم، صديقك الذكي. جرب /help"
    elif cmd == "/info":
        c = get_user_data(user_id).get("city", "لم تحدد")
        return f"🛡️ يا هلا {user_first_name}!\nمدينتك: {c}\nأنا مسلم العماري، رفيقك الذكي. 🤲✨"
    elif cmd == "/setcity":
        parts = text.split(" ", 1)
        if len(parts) > 1:
            save_user_data(user_id, "city", parts[1].strip())
            return f"✅ تم حفظ مدينتك: {parts[1].strip()}"
        return "⚠️ استخدم: /setcity اسم_المدينة"
    elif cmd == "/draw":
        parts = text.split(" ", 1)
        if len(parts) < 2: return "🎨 أرسل: /draw وصف"
        urls = await generate_three_images(parts[1])
        if urls:
            media = [InputMediaPhoto(media=url, caption=f"🎨 صورة {i+1}/3") for i, url in enumerate(urls)]
            await bot.send_media_group(chat_id=None, media=media)  # سنعيدها لاحقًا
            return None  # يُعالج بالخارج
        return "⚠️ فشل توليد الصور."
    elif cmd == "/quran": return await ask_groq_with_fallback(QURAN_PROMPT, user_id, user_first_name)
    elif cmd == "/hadith": return await ask_groq_with_fallback(HADITH_PROMPT, user_id, user_first_name)
    elif cmd == "/dua": return await ask_groq_with_fallback(DUA_PROMPT, user_id, user_first_name)
    elif cmd == "/naseeha": return await ask_groq_with_fallback(NASEHA_PROMPT, user_id, user_first_name)
    elif cmd == "/tafsir": return await ask_groq_with_fallback(TAFSIR_PROMPT, user_id, user_first_name)
    elif cmd == "/azkar": return await ask_groq_with_fallback(AZKAR_PROMPT, user_id, user_first_name)
    elif cmd == "/seerah": return await ask_groq_with_fallback(SEERAH_PROMPT, user_id, user_first_name)
    elif cmd == "/prayer_times":
        city = get_user_data(user_id).get("city", "الدار البيضاء")
        return await get_real_prayer_times(city)
    elif cmd == "/iqra": return await ask_groq_with_fallback(BOOK_PROMPT, user_id, user_first_name)
    elif cmd == "/random": return await ask_groq_with_fallback(RANDOM_PROMPT, user_id, user_first_name)
    elif cmd == "/help":
        return "🕌 /quran /hadith /dua /naseeha /tafsir /azkar /seerah /iqra /prayer_times /random /draw"
    return None

# ==================== خادم FastAPI ====================
app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        if not update.message: return {"status": "ok"}

        chat_id = update.message.chat_id
        user_id = update.effective_user.id
        user_first_name = update.message.from_user.first_name or "صديقي"
        save_user_data(user_id, "name", user_first_name)

        # صورة
        if update.message.photo:
            await bot.send_message(chat_id, "👁️ جارٍ تحليل الصورة...")
            photo_file = await update.message.photo[-1].get_file()
            img_bytes = await photo_file.download_as_bytearray()
            description = await analyze_image(bytes(img_bytes), user_first_name)
            await bot.send_message(chat_id, description)
            return {"status": "ok"}

        # صوت
        if update.message.voice:
            file = await update.message.voice.get_file()
            file_path = f"voice_{user_id}.ogg"
            await file.download_to_drive(file_path)
            with open(file_path, "rb") as audio_file:
                transcription = groq_client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=audio_file,
                    language="ar"
                )
            text = transcription.text
            os.remove(file_path)
            logger.info(f"🎙️ صوت: {text}")
            reply = await ask_groq_with_fallback(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # نص
        if update.message.text:
            text = update.message.text
            logger.info(f"رسالة من {user_first_name}: {text}")

            # معالجة الأمر /draw بشكل خاص
            if text.lower().startswith("/draw"):
                parts = text.split(" ", 1)
                if len(parts) < 2:
                    await bot.send_message(chat_id, "🎨 أرسل: /draw وصف")
                    return {"status": "ok"}
                urls = await generate_three_images(parts[1])
                if urls:
                    media = [InputMediaPhoto(media=url, caption=f"🎨 صورة {i+1}/3 ل {user_first_name} ✨" if i == 0 else "") for i, url in enumerate(urls)]
                    await bot.send_media_group(chat_id, media)
                else:
                    await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
                return {"status": "ok"}

            # باقي الأوامر
            command_reply = await handle_command(text, user_first_name, user_id)
            if command_reply:
                await bot.send_message(chat_id, command_reply)
                return {"status": "ok"}

            # كشف نية الرسم
            draw_prompt = detect_draw_intent(text)
            if draw_prompt:
                urls = await generate_three_images(draw_prompt)
                if urls:
                    media = [InputMediaPhoto(media=url, caption=f"🎨 صورة {i+1}/3 ل {user_first_name} ✨" if i == 0 else "") for i, url in enumerate(urls)]
                    await bot.send_media_group(chat_id, media)
                else:
                    await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
                return {"status": "ok"}

            # محادثة عامة
            reply = await ask_groq_with_fallback(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
            await bot.send_message(chat_id, reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل بقوة وحيوية 🚀!"}
