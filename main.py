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

# ==================== شخصية المساعد (مثلي تمامًا) ====================
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، مساعد ذكي ومفيد تمامًا مثل DeepSeek. "
    "شخصيتك ودودة، لطيفة، ومتوازنة. تحب مساعدة الناس وتقديم إجابات دقيقة ومفيدة. "
    "أسلوبك مباشر وواضح، وتستخدم الإيموجي المناسب للسياق (مثل 😊، 🤲، ✨، 🕌، 💚) بشكل طبيعي وغير مبالغ فيه. "
    "عندما تتحدث، تخاطب المستخدم باسمه الأول أحيانًا لتجعل المحادثة شخصية ودافئة. "
    "أنت صديق حكيم ومرن، تتحدث في الدين والدنيا بذكاء واعتدال. "
    "مرجعيتك إسلامية ولكنك منفتح ومتسامح، بعيد عن التشدد أو الفتاوى، وتحيل إلى العلماء عند الحاجة. "
    "إذا شعرت أن صديقك حزين أو قلق، تواسيه بلطف وتشجعه. "
    "تتحدث العربية بطلاقة وترد دائمًا بصياغة واضحة ولطيفة."
)

# ==================== أوامر المحتوى الإسلامي ====================
QURAN_PROMPT = "أعطني آية قرآنية عشوائية مع تفسيرها بلغة واضحة. ابدأ بـ '📖 آية من الذكر الحكيم'."
HADITH_PROMPT = "أعطني حديثًا شريفًا قصيرًا مع شرحه. ابدأ بـ '🌟 حديث شريف'."
DUA_PROMPT = "أعطني دعاءً جميلاً من القرآن أو السنة. ابدأ بـ '🤲 دعاء'."
NASEHA_PROMPT = "أعطني نصيحة حياتية أو دينية ملهمة. ابدأ بـ '📿 نصيحة'."
AZKAR_PROMPT = "أعطني ذكرًا من الأذكار مع فضله. ابدأ بـ '📿 ذكر وفضله'."
SEERAH_PROMPT = "احكِ لي موقفًا من السيرة النبوية. ابدأ بـ '🌿 من السيرة'."
TAFSIR_PROMPT = "أعطني آية قرآنية مع تفسيرها الميسر. ابدأ بـ '📖 تفسير'."
BOOK_PROMPT = "اقترح عليّ كتابًا مفيدًا مع وصف مختصر. ابدأ بـ '📚 كتاب اليوم'."
RANDOM_PROMPT = "أرسل خليطًا إيمانيًا مميزًا: آية، حديث، دعاء، نصيحة. ابدأ بـ '🎲 خليط إيماني'."

# ==================== توليد الصور (تحميل آمن) ====================
async def download_image(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.content
        else:
            return None
    except Exception as e:
        logger.error(f"فشل تحميل الصورة: {e}")
        return None

async def generate_three_images(prompt: str) -> list[bytes]:
    """يولد 3 صور ويحملها كـ bytes لتجنب خطأ webpage_curl"""
    images = []
    base_url = "https://image.pollinations.ai/prompt/"
    for i in range(3):
        seed = random.randint(1, 99999)
        url = f"{base_url}{prompt}?width=768&height=768&seed={seed}&nologo=true"
        img_bytes = await download_image(url)
        if img_bytes:
            images.append(img_bytes)
        else:
            # إذا فشل التحميل، نرسل صورة بديلة بسيطة
            fallback_url = f"{base_url}abstract%20art?width=768&height=768&seed={seed}&nologo=true"
            fb = await download_image(fallback_url)
            if fb:
                images.append(fb)
    return images

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
                        {"type": "text", "text": f"أنت مسلم العماري، صديق ودود. حلل هذه الصورة بالعربية لـ {user_first_name} بأسلوب شيق."},
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
                f"🤲 لا تنسَ الصلاة على وقتها."
            )
        return "⚠️ لم أستطع جلب المواقيت، تأكد من اسم المدينة."
    except Exception as e:
        logger.error(f"خطأ مواقيت الصلاة: {e}")
        return "⚠️ حدث خطأ في جلب المواقيت."

# ==================== الذكاء العام (مع احتياطي) ====================
async def ask_groq_with_fallback(system_prompt: str, user_id: int, user_first_name: str, user_message: str = None):
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "system", "content": f"أنت تتحدث مع {user_first_name}. خاطبه باسمه بود."})

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
                logger.warning("النموذج الأساسي مشغول، جارٍ التبديل...")
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
        return f"🕋 أهلاً {user_first_name}! نورت 😊 أنا مسلم، مساعدك الذكي. جرب /help"
    elif cmd == "/info":
        c = get_user_data(user_id).get("city", "لم تحدد")
        return f"🛡️ أهلاً {user_first_name}!\nمدينتك: {c}\nأنا مسلم العماري، هنا لخدمتك 🤲✨"
    elif cmd == "/setcity":
        parts = text.split(" ", 1)
        if len(parts) > 1:
            save_user_data(user_id, "city", parts[1].strip())
            return f"✅ تم حفظ مدينتك: {parts[1].strip()}"
        return "⚠️ استخدم: /setcity اسم_المدينة"
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
                img_bytes_list = await generate_three_images(parts[1])
                if img_bytes_list:
                    media = [InputMediaPhoto(media=img_bytes, caption=f"🎨 صورة {i+1}/3 لك {user_first_name} ✨" if i == 0 else "") for i, img_bytes in enumerate(img_bytes_list)]
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
                img_bytes_list = await generate_three_images(draw_prompt)
                if img_bytes_list:
                    media = [InputMediaPhoto(media=img_bytes, caption=f"🎨 صورة {i+1}/3 لك {user_first_name} ✨" if i == 0 else "") for i, img_bytes in enumerate(img_bytes_list)]
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
    return {"message": "مسلم العماري يعمل بقوة وذكاء! 🚀"}
