import os
import logging
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

# ==================== دالة الذكاء العام للبوت ====================
async def ask_groq(system_prompt: str, user_message: str = None) -> str:
    """الدالة الموحدة لإرسال الطلبات إلى Groq"""
    messages = [{"role": "system", "content": system_prompt}]
    if user_message:
        messages.append({"role": "user", "content": user_message})
    else:
        # إذا لم تكن هناك رسالة مستخدم، فهذا أمر يتطلب رداً فورياً من النظام
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.9,
            max_tokens=2000
        )
        return str(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

# ==================== نظام الشخصية العامة (متوازن وغير متشدد) ====================
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، صديق ذكي ومتوازن. "
    "هويتك الإسلامية جزء من شخصيتك، لكنك تتحدث في كل أمور الحياة ببساطة وذكاء. "
    "تقدم نصائح مفيدة في الدين، العلاقات، العمل، الصحة، والتفكير الإيجابي. "
    "أسلوبك عصري، مباشر، ودود، وتستخدم الرموز التعبيرية باعتدال. "
    "أنت لست شيخاً ولا مفتياً، بل صديق حكيم يستأنس برأيه. "
    "إذا سُئلت عن الفتاوى، اعتذر بلطف وأحل على أهل العلم. "
    "تحدث دائماً بالعربية."
)

# ==================== أنظمة الأوامر (للتنويع وعدم التكرار) ====================
QURAN_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني آية قرآنية عشوائية ومؤثرة مع تفسير مبسط وحديث. "
    "ابدأ الرد بـ '📖 آية من الذكر الحكيم'."
)

HADITH_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني حديثاً نبوياً شريفاً عشوائياً مع شرح مختصر لمعناه. "
    "ابدأ الرد بـ '🌟 حديث شريف'."
)

DUA_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني دعاءً جميلاً وشاملاً من القرآن أو السنة. "
    "ابدأ الرد بـ '🤲 دعاء مبارك'."
)

NASEHA_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني نصيحة حياتية أو دينية عميقة وملهمة بأسلوب معاصر. "
    "ابدأ الرد بـ '📿 نصيحة اليوم'."
)

AZKAR_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني ذكراً من الأذكار النبوية مع فضله. "
    "ابدأ الرد بـ '📿 ذكر وفضله'."
)

SEERAH_PROMPT = (
    "أنت بوت 'مسلم العماري'. احك لي موقفاً أو حدثاً عظيماً من السيرة النبوية. "
    "ابدأ الرد بـ '🌿 من السيرة النبوية'."
)

TAFSIR_PROMPT = (
    "أنت بوت 'مسلم العماري'. أعطني آية قرآنية عشوائية مع تفسيرها الميسر. "
    "ابدأ الرد بـ '📖 تفسير'."
)

BOOK_PROMPT = (
    "أنت بوت 'مسلم العماري'. اقترح علي كتاباً إسلامياً أو ثقافياً مفيداً مع وصف مختصر له. "
    "ابدأ الرد بـ '📚 كتاب اليوم'."
)

PRAYER_TIMES_PROMPT = (
    "أنت بوت 'مسلم العماري'. اكتب رسالة تذكيرية جميلة عن أهمية الصلاة والحفاظ على مواقيتها. "
    "ابدأ الرد بـ '🕌 تنبيه الصلاة'."
)

RANDOM_PROMPT = (
    "أنت بوت 'مسلم العماري'. أرسل لي خليطاً إيمانياً مميزاً: آية، وحديثاً، ودعاءً، ونصيحة. "
    "ابدأ الرد بـ '🎲 خليط إيماني'."
)

# ==================== دالة معالجة الأوامر ====================
async def handle_command(text: str, user_first_name: str) -> str | None:
    command = text.split()[0].lower()

    if command == "/start":
        return (
            f"🕋 أهلاً بك يا {user_first_name}!\n\n"
            "أنا مسلم، مساعدك الشخصي. هنا لتسأل عن أي شيء:\n"
            "🔥 نصائح في الحياة والدين\n"
            "🕋 آيات وأحاديث وأدعية\n"
            "👑 محادثة ذكية ومفيدة\n\n"
            "📜 جرب الأوامر:\n"
            "/quran | /hadith | /dua | /naseeha\n"
            "/tafsir | /azkar | /seerah | /iqra\n"
            "/prayer_times | /random | /info"
        )
    elif command == "/info":
        # هنا نستخدم اسم المستخدم الحقيقي
        return (
            f"🛡️ أهلاً {user_first_name}،\n\n"
            "أنا مسلم العماري، رفيقك الذكي.\n"
            "مهمتي أكون معك بالنصيحة والمعلومة.\n"
            "اسألني اللي يخطر ببالك. 🤲✨"
        )
    elif command == "/quran":
        return await ask_groq(QURAN_PROMPT)
    elif command == "/hadith":
        return await ask_groq(HADITH_PROMPT)
    elif command == "/dua":
        return await ask_groq(DUA_PROMPT)
    elif command == "/naseeha":
        return await ask_groq(NASEHA_PROMPT)
    elif command == "/tafsir":
        return await ask_groq(TAFSIR_PROMPT)
    elif command == "/azkar":
        return await ask_groq(AZKAR_PROMPT)
    elif command == "/seerah":
        return await ask_groq(SEERAH_PROMPT)
    elif command == "/prayer_times":
        return await ask_groq(PRAYER_TIMES_PROMPT)
    elif command == "/iqra":
        return await ask_groq(BOOK_PROMPT)
    elif command == "/random":
        return await ask_groq(RANDOM_PROMPT)
    elif command == "/help":
        return (
            "🕌 قائمة المساعدة:\n\n"
            "/quran - آية عشوائية وتفسيرها\n"
            "/hadith - حديث شريف وشرحه\n"
            "/dua - دعاء مبارك\n"
            "/naseeha - نصيحة اليوم\n"
            "/tafsir - تفسير آية\n"
            "/azkar - ذكر وفضله\n"
            "/seerah - من السيرة النبوية\n"
            "/iqra - ملخص كتاب\n"
            "/prayer_times - تذكير بالصلاة\n"
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

        if update.message and update.message.text:
            chat_id = update.message.chat_id
            text = update.message.text
            # نستخرج اسم المستخدم الحقيقي
            user_first_name = update.message.from_user.first_name or "صديقي"

            logger.info(f"رسالة من {chat_id}: {text}")

            # فحص الأوامر
            command_reply = await handle_command(text, user_first_name)
            if command_reply:
                await bot.send_message(chat_id, command_reply)
            else:
                # دردشة عامة طبيعية (بدون توقيع المجلة)
                reply = await ask_groq(MAIN_SYSTEM_PROMPT, text)
                await bot.send_message(chat_id, reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل!"}
