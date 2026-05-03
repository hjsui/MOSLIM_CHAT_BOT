import os
import json
import logging
import base64
import random
import requests
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و GEMINI_API_KEY في متغيرات البيئة")

# عميل Google Gemini (مجاني وسخي)
gemini_client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# الذاكرة المؤقتة
user_histories = defaultdict(list)
MAX_HISTORY_LENGTH = 10

# ذاكرة طويلة المدى
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

# ==================== موجهات الشخصية ====================
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، صديق ذكي ومتوازن. "
    "هويتك الإسلامية جزء من شخصيتك، لكنك تتحدث في كل أمور الحياة ببساطة وذكاء. "
    "تقدم نصائح مفيدة في الدين، العلاقات، العمل، الصحة، والتفكير الإيجابي. "
    "أسلوبك عصري، مباشر، ودود، وتستخدم الرموز التعبيرية باعتدال. "
    "أنت لست شيخاً ولا مفتياً، بل صديق حكيم يستأنس برأيه. "
    "إذا سُئلت عن الفتاوى، اعتذر بلطف وأحل على أهل العلم. "
    "تحدث دائماً بالعربية. "
    "من أهم صفاتك أنك تنادي صديقك باسمه الأول بين الحين والآخر لتضفي على الحديث طابعاً وديّاً وشخصياً، ولكن دون مبالغة."
)

QURAN_PROMPT = "أنت 'مسلم العماري'. أعطني آية قرآنية عشوائية ومؤثرة مع تفسير مبسط وحديث. ابدأ الرد بـ '📖 آية من الذكر الحكيم'."
HADITH_PROMPT = "أنت 'مسلم العماري'. أعطني حديثاً نبوياً شريفاً عشوائياً مع شرح مختصر لمعناه. ابدأ الرد بـ '🌟 حديث شريف'."
DUA_PROMPT = "أنت 'مسلم العماري'. أعطني دعاءً جميلاً وشاملاً من القرآن أو السنة. ابدأ الرد بـ '🤲 دعاء مبارك'."
NASEHA_PROMPT = "أنت 'مسلم العماري'. أعطني نصيحة حياتية أو دينية عميقة وملهمة بأسلوب معاصر. ابدأ الرد بـ '📿 نصيحة اليوم'."
AZKAR_PROMPT = "أنت 'مسلم العماري'. أعطني ذكراً من الأذكار النبوية مع فضله. ابدأ الرد بـ '📿 ذكر وفضله'."
SEERAH_PROMPT = "أنت 'مسلم العماري'. احك لي موقفاً أو حدثاً عظيماً من السيرة النبوية. ابدأ الرد بـ '🌿 من السيرة النبوية'."
TAFSIR_PROMPT = "أنت 'مسلم العماري'. أعطني آية قرآنية عشوائية مع تفسيرها الميسر. ابدأ الرد بـ '📖 تفسير'."
BOOK_PROMPT = "أنت 'مسلم العماري'. اقترح علي كتاباً إسلامياً أو ثقافياً مفيداً مع وصف مختصر له. ابدأ الرد بـ '📚 كتاب اليوم'."
RANDOM_PROMPT = "أنت 'مسلم العماري'. أرسل لي خليطاً إيمانياً مميزاً: آية، وحديثاً، ودعاءً، ونصيحة. ابدأ الرد بـ '🎲 خليط إيماني'."

# ==================== توليد 3 صور (Pollinations + عشوائية) ====================
async def generate_three_images(prompt: str) -> list:
    """يولد 3 صور مختلفة باستخدام Pollinations مع بذور عشوائية"""
    urls = []
    base_url = "https://image.pollinations.ai/prompt/"
    for i in range(3):
        seed = random.randint(1, 99999)  # بذرة عشوائية لتغيير النتيجة
        url = f"{base_url}{prompt}?width=768&height=768&seed={seed}&nologo=true"
        urls.append(url)
    return urls

# ==================== تحليل الصور (باستخدام Gemini Vision) ====================
async def analyze_image(image_bytes: bytes, user_first_name: str) -> str:
    try:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        response = gemini_client.chat.completions.create(
            model="gemini-1.5-flash",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"أنت 'مسلم العماري'. حلل هذه الصورة بالعربية. صف ما تراه فيها بأسلوب ودود. إذا كان فيها نص، فاقرأه لي. تحدث كصديق ينظر إلى الصورة مع {user_first_name}."},
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
                f"🕌 مواقيت الصلاة في {city}\n\n"
                f"🌅 الفجر: {timings['Fajr']}\n☀️ الشروق: {timings['Sunrise']}\n🌤️ الظهر: {timings['Dhuhr']}\n"
                f"🌇 العصر: {timings['Asr']}\n🌆 المغرب: {timings['Maghrib']}\n🌙 العشاء: {timings['Isha']}\n\n"
                f"🤲 لا تنسَ الصلاة على وقتها."
            )
        return "⚠️ لم أستطع جلب المواقيت، تأكد من اسم المدينة."
    except Exception as e:
        logger.error(f"Prayer times error: {e}")
        return "⚠️ حدث خطأ في جلب مواقيت الصلاة."

# ==================== دالة الذكاء العام (Gemini) ====================
async def ask_gemini(system_prompt: str, user_id: int, user_first_name: str, user_message: str = None):
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "system", "content": f"أنت تتحدث الآن مع صديقك {user_first_name}."})

    if user_message:
        history = user_histories[user_id]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
    else:
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    try:
        response = gemini_client.chat.completions.create(
            model="gemini-1.5-flash",
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
        logger.error(f"Gemini error: {e}")
        return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

# ==================== تحليل المشاعر (أبسط بدون استدعاء إضافي) ====================
def analyze_sentiment_simple(text: str) -> str:
    positive = ["😊", "😂", "👍", "❤️", "رائع", "جميل", "الحمد لله"]
    negative = ["😢", "😡", "حزين", "متعب", "سيء", "مشكلة"]
    for w in positive:
        if w in text: return "إيجابي"
    for w in negative:
        if w in text: return "سلبي"
    return "محايد"

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
        return f"🕋 مرحباً {user_first_name}! أنا مسلم، مساعدك الشخصي. جرب /help"
    elif cmd == "/info":
        c = get_user_data(user_id).get("city", "لم تحدد")
        return f"🛡️ يا هلا {user_first_name}، مدينتك: {c}"
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
        return ("🎨 صورك جاهزة:", urls)
    elif cmd == "/quran": return await ask_gemini(QURAN_PROMPT, user_id, user_first_name)
    elif cmd == "/hadith": return await ask_gemini(HADITH_PROMPT, user_id, user_first_name)
    elif cmd == "/dua": return await ask_gemini(DUA_PROMPT, user_id, user_first_name)
    elif cmd == "/naseeha": return await ask_gemini(NASEHA_PROMPT, user_id, user_first_name)
    elif cmd == "/tafsir": return await ask_gemini(TAFSIR_PROMPT, user_id, user_first_name)
    elif cmd == "/azkar": return await ask_gemini(AZKAR_PROMPT, user_id, user_first_name)
    elif cmd == "/seerah": return await ask_gemini(SEERAH_PROMPT, user_id, user_first_name)
    elif cmd == "/prayer_times":
        city = get_user_data(user_id).get("city", "الدار البيضاء")
        return await get_real_prayer_times(city)
    elif cmd == "/iqra": return await ask_gemini(BOOK_PROMPT, user_id, user_first_name)
    elif cmd == "/random": return await ask_gemini(RANDOM_PROMPT, user_id, user_first_name)
    elif cmd == "/help":
        return "🕌 /quran /hadith /dua /naseeha /tafsir /azkar /seerah /iqra /prayer_times /random /draw"
    return None

# ==================== FastAPI ====================
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

        # صوت (مبسط بدون معالجة)
        if update.message.voice:
            await bot.send_message(chat_id, "🎙️ الصوت غير مدعوم حالياً، اكتب رسالتك نصياً.")
            return {"status": "ok"}

        # نص
        if update.message.text:
            text = update.message.text
            logger.info(f"رسالة من {user_first_name}: {text}")

            command_reply = await handle_command(text, user_first_name, user_id)
            if command_reply:
                if isinstance(command_reply, tuple):
                    caption, urls = command_reply
                    # إرسال ما يصل إلى 3 صور كألبوم
                    if urls:
                        media_group = [{"type": "photo", "media": url, "caption": caption if i == 0 else ""} for i, url in enumerate(urls)]
                        await bot.send_media_group(chat_id, media_group)
                else:
                    await bot.send_message(chat_id, command_reply)
                return {"status": "ok"}

            # كشف نية الرسم
            draw_prompt = detect_draw_intent(text)
            if draw_prompt:
                urls = await generate_three_images(draw_prompt)
                if urls:
                    media_group = [{"type": "photo", "media": url, "caption": f"🎨 تفضل يا {user_first_name}!" if i == 0 else ""} for i, url in enumerate(urls)]
                    await bot.send_media_group(chat_id, media_group)
                else:
                    await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
                return {"status": "ok"}

            # محادثة عامة
            sentiment = analyze_sentiment_simple(text)
            reply = await ask_gemini(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
            if sentiment == "سلبي":
                reply = f"🤲 أشعر بك يا {user_first_name}...\n\n{reply}"
            elif sentiment == "إيجابي":
                reply = f"😊 جميل يا {user_first_name}!\n\n{reply}"
            await bot.send_message(chat_id, reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل بقوة Gemini!"}
