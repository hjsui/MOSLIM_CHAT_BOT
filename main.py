import os
import json
import logging
import requests
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder

# ==================== الإعدادات ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("ينقص متغيرات البيئة BOT_TOKEN أو GROQ_API_KEY")

# ==================== عميل Groq ====================
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ==================== الذاكرة المؤقتة (آخر 10 رسائل) ====================
user_histories = defaultdict(list)
MAX_HISTORY_LENGTH = 10

# ==================== الذاكرة طويلة المدى (ملف JSON) ====================
DATA_FILE = "users_data.json"

def load_all_users():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_user_data(user_id: int, key: str, value):
    data = load_all_users()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"name": "", "city": "الدار البيضاء", "preferences": {}}
    data[uid][key] = value
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id: int):
    data = load_all_users()
    return data.get(str(user_id), {"name": "", "city": "الدار البيضاء", "preferences": {}})

# ==================== نظام الشخصية العامة ====================
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

# ==================== أنظمة الأوامر ====================
QURAN_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني آية قرآنية عشوائية ومؤثرة مع تفسير مبسط وحديث. ابدأ الرد بـ '📖 آية من الذكر الحكيم'."
)
HADITH_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني حديثاً نبوياً شريفاً عشوائياً مع شرح مختصر لمعناه. ابدأ الرد بـ '🌟 حديث شريف'."
)
DUA_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني دعاءً جميلاً وشاملاً من القرآن أو السنة. ابدأ الرد بـ '🤲 دعاء مبارك'."
)
NASEHA_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني نصيحة حياتية أو دينية عميقة وملهمة بأسلوب معاصر. ابدأ الرد بـ '📿 نصيحة اليوم'."
)
AZKAR_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني ذكراً من الأذكار النبوية مع فضله. ابدأ الرد بـ '📿 ذكر وفضله'."
)
SEERAH_PROMPT = (
    "أنت بوت 'مسلم العماري'. احك لي موقفاً أو حدثاً عظيماً من السيرة النبوية. ابدأ الرد بـ '🌿 من السيرة النبوية'."
)
TAFSIR_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني آية قرآنية عشوائية مع تفسيرها الميسر. ابدأ الرد بـ '📖 تفسير'."
)
BOOK_PROMPT = (
    "أنت بوت 'مسلم العماري'. اقترح علي كتاباً إسلامياً أو ثقافياً مفيداً مع وصف مختصر له. ابدأ الرد بـ '📚 كتاب اليوم'."
)
RANDOM_PROMPT = (
    "أنت بوت 'مسلم العماري'. أرسل لي خليطاً إيمانياً مميزاً: آية، وحديثاً، ودعاءً، ونصيحة. ابدأ الرد بـ '🎲 خليط إيماني'."
)

# ==================== مواقيت الصلاة الحقيقية ====================
async def get_real_prayer_times(city: str, country: str = "Morocco"):
    try:
        url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}"
        response = requests.get(url, timeout=5)
        data = response.json()
        if data["code"] == 200:
            timings = data["data"]["timings"]
            return (
                f"🕌 *مواقيت الصلاة في {city}*\n\n"
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
        logger.error(f"Prayer times error: {e}")
        return "⚠️ حدث خطأ في جلب مواقيت الصلاة."

# ==================== دالة الذكاء العام ====================
async def ask_groq(system_prompt: str, user_id: int, user_first_name: str, user_message: str = None):
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "system", "content": f"أنت تتحدث الآن مع صديقك {user_first_name}."})

    if user_message:
        history = user_histories[user_id]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
    else:
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.9,
            max_tokens=2000
        )
        reply = str(response.choices[0].message.content)

        if user_message:
            history = user_histories[user_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": reply})
            if len(history) > MAX_HISTORY_LENGTH * 2:
                user_histories[user_id] = history[-(MAX_HISTORY_LENGTH * 2):]

        return reply
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

# ==================== تحليل المشاعر ====================
async def analyze_sentiment(text: str) -> str:
    prompt = f"حلل مشاعر هذا النص: '{text}'. رد بكلمة واحدة فقط: 'إيجابي' أو 'سلبي' أو 'محايد'."
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=10
        )
        return str(response.choices[0].message.content).strip()
    except:
        return "محايد"

# ==================== معالجة الأوامر ====================
async def handle_command(text: str, user_first_name: str, user_id: int) -> str | None:
    command = text.split()[0].lower()

    if command == "/start":
        return (
            f"🕋 مرحباً {user_first_name}!\n\n"
            "نورت المحادثة. أنا مسلم، مساعدك الشخصي. "
            "هنا لتسأل عن أي شيء يخطر ببالك:\n"
            "🔥 نصائح في الحياة والدين\n"
            "🕋 آيات وأحاديث وأدعية\n"
            "👑 محادثة ذكية ومفيدة\n\n"
            "📜 جرب الأوامر:\n"
            "/quran | /hadith | /dua | /naseeha\n"
            "/tafsir | /azkar | /seerah | /iqra\n"
            "/prayer_times | /setcity | /random | /info"
        )
    elif command == "/info":
        user_data = get_user_data(user_id)
        city = user_data.get("city", "لم تحدد بعد")
        return (
            f"🛡️ يا هلا {user_first_name}،\n\n"
            f"مدينتك: {city}\n"
            "أنا مسلم العماري، رفيقك الذكي.\n"
            "مهمتي أكون معك بالنصيحة والمعلومة.\n"
            "اسألني اللي يخطُر ببالك. 🤲✨"
        )
    elif command == "/setcity":
        parts = text.split(" ", 1)
        if len(parts) > 1:
            city = parts[1].strip()
            save_user_data(user_id, "city", city)
            return f"✅ تم حفظ مدينتك: {city}"
        return "⚠️ استخدم: /setcity اسم_المدينة"
    elif command == "/quran":
        return await ask_groq(QURAN_PROMPT, user_id, user_first_name)
    elif command == "/hadith":
        return await ask_groq(HADITH_PROMPT, user_id, user_first_name)
    elif command == "/dua":
        return await ask_groq(DUA_PROMPT, user_id, user_first_name)
    elif command == "/naseeha":
        return await ask_groq(NASEHA_PROMPT, user_id, user_first_name)
    elif command == "/tafsir":
        return await ask_groq(TAFSIR_PROMPT, user_id, user_first_name)
    elif command == "/azkar":
        return await ask_groq(AZKAR_PROMPT, user_id, user_first_name)
    elif command == "/seerah":
        return await ask_groq(SEERAH_PROMPT, user_id, user_first_name)
    elif command == "/prayer_times":
        user_data = get_user_data(user_id)
        city = user_data.get("city", "الدار البيضاء")
        return await get_real_prayer_times(city)
    elif command == "/iqra":
        return await ask_groq(BOOK_PROMPT, user_id, user_first_name)
    elif command == "/random":
        return await ask_groq(RANDOM_PROMPT, user_id, user_first_name)
    elif command == "/help":
        return (
            f"🕌 أهلاً {user_first_name}، هذه قائمة المساعدة:\n\n"
            "/quran - آية عشوائية وتفسيرها\n"
            "/hadith - حديث شريف وشرحه\n"
            "/dua - دعاء مبارك\n"
            "/naseeha - نصيحة اليوم\n"
            "/tafsir - تفسير آية\n"
            "/azkar - ذكر وفضله\n"
            "/seerah - من السيرة النبوية\n"
            "/iqra - ملخص كتاب\n"
            "/prayer_times - مواقيت الصلاة\n"
            "/setcity مدينة - تعيين مدينتك\n"
            "/random - خليط إيماني\n"
            "/info - عن البوت"
        )
    return None

# ==================== خادم FastAPI ====================
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
        user_first_name = update.message.from_user.first_name or "صديقي"

        # حفظ الاسم تلقائيا في الذاكرة طويلة المدى
        save_user_data(user_id, "name", user_first_name)

        # تحويل الصوت إلى نص
        if update.message.voice:
            file = await update.message.voice.get_file()
            file_path = f"voice_{user_id}.ogg"
            await file.download_to_drive(file_path)

            # فتح الملف الصوتي وإرساله إلى Groq
            with open(file_path, "rb") as audio_file:
                transcription = groq_client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=audio_file,
                    language="ar"
                )
            text = transcription.text
            os.remove(file_path)
            logger.info(f"🎙️ صوت من {user_first_name}: {text}")

            reply = await ask_groq(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # التعامل مع النص
        if update.message.text:
            text = update.message.text
            logger.info(f"رسالة من {user_first_name} ({chat_id}): {text}")

            # تحليل المشاعر
            sentiment = await analyze_sentiment(text)
            logger.info(f"شعور {user_first_name}: {sentiment}")

            command_reply = await handle_command(text, user_first_name, user_id)
            if command_reply:
                await bot.send_message(chat_id, command_reply)
            else:
                reply = await ask_groq(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
                # تعديل الرد بناء على المشاعر
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
    return {"message": "مسلم العماري يعمل بكل الميزات!"}
