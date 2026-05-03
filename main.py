import os
import logging
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

# ==================== الذاكرة المؤقتة (جديد) ====================
# تخزين تاريخ المحادثة لكل مستخدم. المفتاح: user_id، القيمة: قائمة من الرسائل
user_histories = defaultdict(list)
MAX_HISTORY_LENGTH = 10  # نتذكر آخر 10 رسائل بين الطرفين

# ==================== نظام الشخصية العامة ====================
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، صديق ذكي ومتوازن. "
    "هويتك الإسلامية جزء من شخصيتك، لكنك تتحدث في كل أمور الحياة ببساطة وذكاء. "
    "تقدم نصائح مفيدة في الدين، العلاقات، العمل، الصحة، والتفكير الإيجابي. "
    "أسلوبك عصري، مباشر، ودود، وتستخدم الرموز التعبيرية باعتدال. "
    "أنت لست شيخاً ولا مفتياً، بل صديق حكيم يستأنس برأيه. "
    "إذا سُئلت عن الفتاوى، اعتذر بلطف وأحل على أهل العلم. "
    "تحدث دائماً بالعربية."
)

# ==================== أنظمة الأوامر ====================
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

# ==================== دالة الذكاء العام (معدلة لتشمل التاريخ) ====================
async def ask_groq(system_prompt: str, user_id: int, user_message: str = None):
    """
    user_id: لاستخراج تاريخ المحادثة الخاص به.
    إذا كان user_message فارغاً، فهذا يعني أنه أمر لا يحتاج إلى سياق (مثل /quran).
    """
    # بناء الرسائل: نبدأ برسالة النظام
    messages = [{"role": "system", "content": system_prompt}]
    
    if user_message:
        # إذا كانت هناك رسالة مستخدم (دردشة عامة)، نضيف تاريخ المحادثة
        history = user_histories[user_id]
        # history عبارة عن قائمة رسائل user/assistant، نضيفها قبل الرسالة الجديدة ليكون السياق كاملاً
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
    else:
        # إذا كان أمراً (مثل /quran)، لا نحتاج لتاريخ، بل نرسل طلباً بسيطاً
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.9,
            max_tokens=2000
        )
        reply = str(response.choices[0].message.content)
        
        # إذا كانت دردشة عامة، نقوم بتحديث الذاكرة
        if user_message:
            history = user_histories[user_id]  # إعادة الحصول على المرجع بعد التعديل
            # نحفظ سؤال المستخدم
            history.append({"role": "user", "content": user_message})
            # نحفظ رد البوت
            history.append({"role": "assistant", "content": reply})
            # نحافظ على ألا يتجاوز طول التاريخ الحد الأقصى
            if len(history) > MAX_HISTORY_LENGTH * 2:  # لأن كل دورة تضيف رسالتين
                user_histories[user_id] = history[-(MAX_HISTORY_LENGTH * 2):]
        
        return reply
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

# ==================== دالة معالجة الأوامر ====================
async def handle_command(text: str, user_first_name: str, user_id: int) -> str | None:
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
        return (
            f"🛡️ أهلاً {user_first_name}،\n\n"
            "أنا مسلم العماري، رفيقك الذكي.\n"
            "مهمتي أكون معك بالنصيحة والمعلومة.\n"
            "اسألني اللي يخطُر ببالك. 🤲✨"
        )
    elif command == "/quran":
        return await ask_groq(QURAN_PROMPT, user_id)
    elif command == "/hadith":
        return await ask_groq(HADITH_PROMPT, user_id)
    elif command == "/dua":
        return await ask_groq(DUA_PROMPT, user_id)
    elif command == "/naseeha":
        return await ask_groq(NASEHA_PROMPT, user_id)
    elif command == "/tafsir":
        return await ask_groq(TAFSIR_PROMPT, user_id)
    elif command == "/azkar":
        return await ask_groq(AZKAR_PROMPT, user_id)
    elif command == "/seerah":
        return await ask_groq(SEERAH_PROMPT, user_id)
    elif command == "/prayer_times":
        return await ask_groq(PRAYER_TIMES_PROMPT, user_id)
    elif command == "/iqra":
        return await ask_groq(BOOK_PROMPT, user_id)
    elif command == "/random":
        return await ask_groq(RANDOM_PROMPT, user_id)
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
            user_id = update.effective_user.id
            text = update.message.text
            user_first_name = update.message.from_user.first_name or "صديقي"

            logger.info(f"رسالة من {chat_id}: {text}")

            # فحص الأوامر
            command_reply = await handle_command(text, user_first_name, user_id)
            if command_reply:
                await bot.send_message(chat_id, command_reply)
            else:
                # دردشة عامة مع ذاكرة
                reply = await ask_groq(MAIN_SYSTEM_PROMPT, user_id, text)
                await bot.send_message(chat_id, reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل!"}
