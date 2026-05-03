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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و OPENROUTER_API_KEY في متغيرات البيئة")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    timeout=15.0
)

groq_client = None
if GROQ_API_KEY:
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        timeout=15.0
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
    data = load_user_data()
    return data.get(str(user_id), {}).get("city", "الدار البيضاء")

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

FREE_MODELS = [
    "meta-llama/llama-4-maverick:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openrouter/free"
]

async def generate_single_image(prompt: str) -> bytes | None:
    try:
        seed = random.randint(1, 99999)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=768&height=768&seed={seed}&nologo=true"
        resp = requests.get(url, timeout=15)
        return resp.content if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"خطأ في توليد الصورة: {e}")
        return None

async def analyze_image(image_bytes: bytes, user_name: str) -> str | None:
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
            temperature=0.5,
            max_tokens=400,
            timeout=15.0
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"فشل تحليل الصورة: {e}")
        return "⚠️ لم أستطع تحليل الصورة حالياً."

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

    for model in FREE_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.85,
                max_tokens=450,
                timeout=12.0
            )
            reply = response.choices[0].message.content.strip()

            history = user_histories[user_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": reply})
            if len(history) > MAX_HISTORY * 2:
                user_histories[user_id] = history[-(MAX_HISTORY * 2):]

            return reply
        except Exception as e:
            logger.warning(f"فشل النموذج {model}: {e}")

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
        return "⚠️ لم أستطع جلب المواقيت. تأكد من اسم المدينة."
    except Exception as e:
        logger.error(f"خطأ مواقيت الصلاة: {e}")
        return "⚠️ حدث خطأ في جلب مواقيت الصلاة."

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

        if update.message.photo:
            await bot.send_message(chat_id, "👁️ جارٍ تحليل الصورة...")
            photo_file = await update.message.photo[-1].get_file()
            img_bytes = await photo_file.download_as_bytearray()
            description = await analyze_image(bytes(img_bytes), user_name)
            if description:
                await bot.send_message(chat_id, description)
            else:
                await bot.send_message(chat_id, "⚠️ خدمة تحليل الصور غير مفعلة حالياً.")
            return {"status": "ok"}

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

        if update.message.sticker:
            await bot.send_message(chat_id, "😄 ملصق جميل!")
            return {"status": "ok"}

        if not update.message.text:
            return {"status": "ok"}

        text = update.message.text.strip()
        if not text:
            return {"status": "ok"}

        logger.info(f"رسالة من {user_name} ({user_id}): {text}")

        if text.startswith("/start"):
            msg = (
                f"✨ أهلاً وسهلاً بك يا {user_name}!\n\n"
                "أنا **مسلم العماري**، رفيقك الذكي. ✨\n"
                "أنا هنا عشان أساعدك في أي شيء تحتاجه، من النصيحة للمعلومة، ومن القرآن للرسم.\n\n"
                "🎯 وش تقدر تسألني عنه؟\n"
                "• أسئلة دينية وثقافية واجتماعية.\n"
                "• آيات قرآنية وأحاديث وأدعية.\n"
                "• نصايح يومية وتفسير.\n"
                "• مواقيت الصلاة التقريبية.\n"
                "• رسم صورة من خيالك (أرسل 'ارسم وصف').\n\n"
                "📜 اكتب /help عشان تشوف كل الأوامر.\n"
                "يا هلا فيك، ابدأ بسؤالك الأول! 🤲"
            )
            await bot.send_message(chat_id, msg)
            return {"status": "ok"}

        if text.startswith("/help"):
            msg = (
                "🕌 **قائمة المساعدة** 🕌\n\n"
                "⚡️ **أوامر المحتوى الإسلامي:**\n"
                "/quran - آية قرآنية عشوائية مع تفسيرها.\n"
                "/hadith - حديث شريف مع شرحه.\n"
                "/dua - دعاء مبارك.\n"
                "/naseeha - نصيحة حياتية أو دينية.\n"
                "/azkar - ذكر من الأذكار مع فضله.\n"
                "/seerah - موقف من السيرة النبوية.\n"
                "/tafsir - تفسير ميسر لآية.\n"
                "/iqra - اقتراح كتاب مفيد.\n"
                "/random - خليط إيماني مميز.\n"
                "/prayer_times - مواقيت الصلاة (حسب مدينتك إن عيّنتها).\n\n"
                "🎨 **الرسم:**\n"
                "/draw وصف - أرسم لك صورة.\n"
                "أو اكتب 'ارسم لي ...' وأنا أفهمك.\n\n"
                "⚙️ **النظام:**\n"
                "/setcity اسم_مدينتك - لضبط مواقيت الصلاة.\n"
                "/clear - مسح ذاكرة المحادثة.\n"
                "/info - عن البوت.\n\n"
                "💬 تقدر تسألني أي سؤال بشكل طبيعي!"
            )
            await bot.send_message(chat_id, msg)
            return {"status": "ok"}

        if text.startswith("/info"):
            await bot.send_message(chat_id,
                "🛡️ **عن البوت**\n\n"
                "الاسم: مسلم العماري\n"
                "التخصص: مرجعية عربية مغربية إسلامية\n"
                "المطور: مسلم العماري 👑\n"
                "أنا بوت ذكي لمساعدتك وتقديم المعلومة."
            )
            return {"status": "ok"}

        if text.startswith("/clear"):
            if user_id in user_histories:
                del user_histories[user_id]
            await bot.send_message(chat_id, "🧹 تم مسح ذاكرة المحادثة.")
            return {"status": "ok"}

        if text.startswith("/setcity"):
            parts = text.split(" ", 1)
            if len(parts) > 1:
                city = parts[1].strip()
                save_user_data(user_id, "city", city)
                await bot.send_message(chat_id, f"✅ تم حفظ مدينتك: {city}")
            else:
                await bot.send_message(chat_id, "⚠️ استخدم: /setcity اسم_المدينة")
            return {"status": "ok"}

        if text.startswith("/draw"):
            prompt = text.replace("/draw", "", 1).strip()
            if not prompt:
                await bot.send_message(chat_id, "🎨 أرسل: /draw وصف الصورة")
                return {"status": "ok"}
            img_data = await generate_single_image(prompt)
            if img_data:
                await bot.send_photo(chat_id, photo=img_data, caption=f"🎨 صورة لك يا {user_name}")
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصورة.")
            return {"status": "ok"}

        draw_prompt = detect_draw_intent(text)
        if draw_prompt:
            img_data = await generate_single_image(draw_prompt)
            if img_data:
                await bot.send_photo(chat_id, photo=img_data, caption=f"🎨 صورة لك يا {user_name}")
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصورة.")
            return {"status": "ok"}

        if text.startswith("/prayer_times"):
            city = get_user_city(user_id)
            reply = await get_real_prayer_times(city)
            await bot.send_message(chat_id, reply)
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
