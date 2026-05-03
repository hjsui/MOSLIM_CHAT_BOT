import os
import json
import logging
import base64
import requests
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # اختياري، لتوليد وتعديل الصور

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("ينقص متغيرات البيئة BOT_TOKEN و GROQ_API_KEY")

groq_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
# عميل Gemini (اختياري)
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = OpenAI(api_key=GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# الذاكرة المؤقتة
user_histories = defaultdict(list)
MAX_HISTORY_LENGTH = 10

# ذاكرة طويلة المدى (JSON)
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

# موجهات الشخصية والأوامر
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

# ========== دالة توليد الصورة المطورة (Gemini أولاً، Pollinations احتياط) ==========
async def generate_image(prompt: str):
    # المحاولة الأولى: Google Gemini Imagen (الجودة الاحترافية)
    if gemini_client:
        try:
            response = gemini_client.images.generate(
                model="imagen-3.0-generate-001",
                prompt=f"Generate a high-quality, realistic image: {prompt}",
                n=1,
                size="1024x1024"
            )
            return response.data[0].url
        except Exception as e:
            logger.warning(f"Gemini image generation failed, falling back to Pollinations: {e}")

    # المحاولة الثانية: Pollinations.ai (البديل المجاني الدائم)
    try:
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=768&height=768&nologo=true"
        return url
    except Exception as e:
        logger.error(f"فشل توليد الصورة تماماً: {e}")
        return None

# تحليل الصورة (باستخدام Groq Vision)
async def analyze_image(image_bytes: bytes, user_first_name: str) -> str:
    try:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        response = groq_client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"أنت 'مسلم العماري'. حلل هذه الصورة بالعربية. صف ما تراه فيها بأسلوب ودود. إذا كان فيها نص، فاقرأه لي. إذا كان فيها مشهد، فصفه. تحدث كصديق ينظر إلى الصورة مع {user_first_name}."},
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

# تعديل الصورة عبر Gemini (إن وجد، وإلا يعتذر)
async def edit_image_with_gemini(image_bytes: bytes, edit_prompt: str, user_first_name: str) -> str | None:
    if not gemini_client:
        return None
    try:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        response = gemini_client.chat.completions.create(
            model="gemini-2.0-flash-exp-image-generation",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Edit this image based on: {edit_prompt}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
                    ]
                }
            ],
            temperature=0.5,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"تعديل الصورة عبر Gemini فشل: {e}")
        return None

# مواقيت الصلاة الحقيقية
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

# دالة الذكاء العام (محادثة)
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

# تحليل المشاعر
async def analyze_sentiment(text: str) -> str:
    prompt = f"حلل مشاعر هذا النص: '{text}'. رد بكلمة واحدة فقط: 'إيجابي' أو 'سلبي' أو 'محايد'."
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=10
        )
        return r.choices[0].message.content.strip()
    except:
        return "محايد"

# اكتشاف نية الرسم
def detect_draw_intent(text: str) -> str | None:
    triggers = ["ارسم", "اصنع صورة", "صور لي", "صوّر", "تخيل صورة", "اعمل صورة", "رسم", "خلق صورة"]
    text_lower = text.lower()
    for trigger in triggers:
        if trigger in text_lower:
            parts = text.split(trigger, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

# اكتشاف نية التعديل
def detect_edit_intent(text: str) -> str | None:
    triggers = ["عدل", "حرر", "غير", "أصلح", "زد", "أنقص", "حسن", "بدل", "تعديل"]
    text_lower = text.lower()
    for trigger in triggers:
        if trigger in text_lower and ("صورة" in text_lower or "الصورة" in text_lower):
            return text
    return None

# معالجة الأوامر
async def handle_command(text: str, user_first_name: str, user_id: int):
    command = text.split()[0].lower()

    if command == "/start":
        return f"🕋 مرحباً {user_first_name}!\n\nنورت المحادثة. أنا مسلم، مساعدك الشخصي.\n🔥 نصائح\n🕋 آيات وأحاديث\n👑 محادثة ذكية\n🎨 رسم صور (/draw)\n👁️ قراءة الصور (أرسل صورة)\n🖌️ تعديل الصور (أرسل صورة مع أمر)\n\n📜 /help للقائمة."
    elif command == "/info":
        c = get_user_data(user_id).get("city", "لم تحدد")
        return f"🛡️ يا هلا {user_first_name}،\n\nمدينتك: {c}\nأنا مسلم العماري، رفيقك الذكي.\nمهمتي أكون معك بالنصيحة والمعلومة."
    elif command == "/setcity":
        parts = text.split(" ", 1)
        if len(parts) > 1:
            save_user_data(user_id, "city", parts[1].strip())
            return f"✅ تم حفظ مدينتك: {parts[1].strip()}"
        return "⚠️ استخدم: /setcity اسم_المدينة"
    elif command == "/draw":
        parts = text.split(" ", 1)
        if len(parts) < 2:
            return "🎨 أرسل الأمر هكذا: /draw وصف الصورة التي تريدها"
        img_url = await generate_image(parts[1])
        if img_url:
            return ("🎨 صورة من خيال مسلم:", img_url)
        else:
            return "⚠️ فشل توليد الصورة."
    elif command == "/quran": return await ask_groq(QURAN_PROMPT, user_id, user_first_name)
    elif command == "/hadith": return await ask_groq(HADITH_PROMPT, user_id, user_first_name)
    elif command == "/dua": return await ask_groq(DUA_PROMPT, user_id, user_first_name)
    elif command == "/naseeha": return await ask_groq(NASEHA_PROMPT, user_id, user_first_name)
    elif command == "/tafsir": return await ask_groq(TAFSIR_PROMPT, user_id, user_first_name)
    elif command == "/azkar": return await ask_groq(AZKAR_PROMPT, user_id, user_first_name)
    elif command == "/seerah": return await ask_groq(SEERAH_PROMPT, user_id, user_first_name)
    elif command == "/prayer_times":
        city = get_user_data(user_id).get("city", "الدار البيضاء")
        return await get_real_prayer_times(city)
    elif command == "/iqra": return await ask_groq(BOOK_PROMPT, user_id, user_first_name)
    elif command == "/random": return await ask_groq(RANDOM_PROMPT, user_id, user_first_name)
    elif command == "/help":
        return (
            f"🕌 أهلاً {user_first_name}:\n\n"
            "/quran /hadith /dua /naseeha\n"
            "/tafsir /azkar /seerah /iqra\n"
            "/prayer_times /setcity /random\n"
            "/draw وصف – صنع صورة بالذكاء الاصطناعي 🎨\n"
            "أرسل صورة – قراءة وتحليل الصور 👁️\n"
            "أرسل صورة مع أمر – تعديل الصورة 🖌️"
        )
    return None

# تطبيق FastAPI
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

        save_user_data(user_id, "name", user_first_name)

        # صورة
        if update.message.photo:
            has_caption = update.message.caption
            if has_caption and detect_edit_intent(has_caption):
                await bot.send_message(chat_id, "🖌️ جارٍ تعديل الصورة...")
                photo_file = await update.message.photo[-1].get_file()
                img_bytes = await photo_file.download_as_bytearray()
                edited_image_url = await edit_image_with_gemini(bytes(img_bytes), has_caption, user_first_name)
                if edited_image_url:
                    await bot.send_photo(chat_id, photo=edited_image_url, caption=f"🖼️ تم التعديل يا {user_first_name}!")
                else:
                    await bot.send_message(chat_id, "🛡️ تعديل الصور يتطلب Gemini API مدفوع أو غير متاح حاليًا. باقي الميزات تعمل!")
                return {"status": "ok"}
            # تحليل
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
            reply = await ask_groq(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # نص
        if update.message.text:
            text = update.message.text
            logger.info(f"رسالة من {user_first_name}: {text}")

            command_reply = await handle_command(text, user_first_name, user_id)

            # إذا كان نتيجة أمر draw هي tuple (وصف، رابط)
            if command_reply and isinstance(command_reply, tuple):
                caption, img_url = command_reply
                if img_url:
                    await bot.send_photo(chat_id, photo=img_url, caption=f"🖼️ {user_first_name}، هذه صورتك!")
                else:
                    await bot.send_message(chat_id, caption)
                return {"status": "ok"}

            if command_reply:
                await bot.send_message(chat_id, command_reply)
                return {"status": "ok"}

            # كشف نية الرسم
            draw_prompt = detect_draw_intent(text)
            if draw_prompt:
                img_url = await generate_image(draw_prompt)
                if img_url:
                    await bot.send_photo(chat_id, photo=img_url, caption=f"🎨 تفضل يا {user_first_name}!")
                else:
                    await bot.send_message(chat_id, "⚠️ فشل توليد الصورة.")
                return {"status": "ok"}

            # محادثة عامة
            sentiment = await analyze_sentiment(text)
            reply = await ask_groq(MAIN_SYSTEM_PROMPT, user_id, user_first_name, text)
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
