import os
import logging
import random
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

# ==================== المحتوى الإسلامي ====================
QURAN_VERSES = [
    "﷽\n\n(إِنَّ مَعَ الْعُسْرِ يُسْرًا) 🍃 - سورة الشرح",
    "﷽\n\n(فَاذْكُرُونِي أَذْكُرْكُمْ وَاشْكُرُوا لِي وَلَا تَكْفُرُونِ) 🤲 - سورة البقرة",
    "﷽\n\n(إِنَّ اللَّهَ مَعَ الصَّابِرِينَ) 💪 - سورة البقرة",
    "﷽\n\n(وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا وَيَرْزُقْهُ مِنْ حَيْثُ لَا يَحْتَسِبُ) 🌟 - سورة الطلاق",
    "﷽\n\n(ادْعُونِي أَسْتَجِبْ لَكُمْ) 🤲 - سورة غافر",
    "﷽\n\n(فَإِنَّ مَعَ الْعُسْرِ يُسْرًا إِنَّ مَعَ الْعُسْرِ يُسْرًا) ✨ - سورة الشرح",
]

AHADITH = [
    "من صلى الفجر في جماعة فهو في ذمة الله. 🕌 (رواه مسلم)",
    "الكلمة الطيبة صدقة. 🌸 (متفق عليه)",
    "لا تغضب ولك الجنة. 😊 (رواه البخاري)",
    "من كان يؤمن بالله واليوم الآخر فليقل خيراً أو ليصمت. 🤫 (متفق عليه)",
    "تبسمك في وجه أخيك صدقة. 😊 (رواه الترمذي)",
]

DUAS = [
    "اللهم إني أسألك الهدى والتقى والعفاف والغنى 🤲",
    "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ 🌸",
    "اللهم اغفر لي ولوالدي وللمؤمنين يوم يقوم الحساب 🕌",
    "اللهم إني أعوذ بك من الهم والحزن، وأعوذ بك من العجز والكسل 🍃",
]

NASEHA = [
    "حافظ على الصلوات الخمس، فهي عماد الدين. 🕌",
    "اقرأ ولو صفحة من القرآن يومياً. 📖",
    "بر الوالدين من أعظم القربات إلى الله. 💝",
    "الصدقة تطفئ غضب الرب. 💰",
    "ذكر الله يطمئن القلوب. 🧘",
]

AZKAR = [
    "سبحان الله وبحمده، سبحان الله العظيم (ثقيلتان في الميزان)",
    "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير (كنز من كنوز الجنة)",
    "أستغفر الله الذي لا إله إلا هو الحي القيوم وأتوب إليه (غفرت ذنوبه)",
]

SEERAH = [
    "عندما دخل النبي ﷺ مكة فاتحاً، قال لأهلها: (اذهبوا فأنتم الطلقاء). 🌿",
    "كان النبي ﷺ يقوم الليل حتى تتفطر قدماه شكراً لله. 🌙",
    "حين أُوذي في الطائف، قال: (اللهم إني أشكو إليك ضعف قوتي) ثم عفا عنهم. 💚",
]

TAFSIR = [
    "﷽\n(إِنَّ مَعَ الْعُسْرِ يُسْرًا): بعد الضيق يأتي الفرج، وعد الله لا يتخلف.",
    "﷽\n(ادْعُونِي أَسْتَجِبْ لَكُمْ): الله قريب يجيب دعوة الداعي إذا دعاه.",
]

BOOKS = [
    "📚 رياض الصالحين - للإمام النووي، يجمع أحاديث في الأخلاق والعبادات.",
    "📚 الرحيق المختوم - للمباركفوري، سيرة نبوية شاملة.",
]

PRAYER_TIMES_MSG = (
    "🕌 تنبيه الصلاة\n\n"
    "الصلاة خير من النوم.\n"
    "للمواقيت الدقيقة، استخدم تطبيقاً موثوقاً حسب مدينتك.\n"
    "ولا تنس: (إِنَّ الصَّلَاةَ كَانَتْ عَلَى الْمُؤْمِنِينَ كِتَابًا مَّوْقُوتًا).\n\n"
    "حافظ على صلاتك! 🤲"
)

# ==================== دالة الأوامر (ردود نص عادي) ====================
async def handle_command(text: str) -> str | None:
    command = text.split()[0].lower()

    if command == "/start":
        return (
            "🕋 مسلم العماري 🕋\n\n"
            "📿 أهلاً بك في رحاب المعرفة الإسلامية!\n\n"
            "أنا مسلم، مساعدك الذكي. أقدم لك:\n"
            "🔥 نصائح واستشارات دينية ودنيوية\n"
            "🕋 آيات وأحاديث وأدعية\n"
            "👑 معلومات قيمة بأسلوب شيق\n\n"
            "📜 الأوامر:\n"
            "/quran | /hadith | /dua | /naseeha\n"
            "/tafsir | /azkar | /seerah | /iqra\n"
            "/prayer_times | /random | /info"
        )
    elif command == "/help":
        return (
            "🕌 قائمة المساعدة\n\n"
            "• اسألني أي سؤال في الدين أو الحياة.\n"
            "• الأوامر:\n"
            "  /quran - آية عشوائية\n"
            "  /hadith - حديث شريف\n"
            "  /dua - دعاء مبارك\n"
            "  /naseeha - نصيحة اليوم\n"
            "  /tafsir - تفسير آية\n"
            "  /azkar - ذكر وفضله\n"
            "  /seerah - من السيرة\n"
            "  /iqra - ملخص كتاب\n"
            "  /prayer_times - تنبيه الصلاة\n"
            "  /random - مزيج عشوائي\n"
            "  /info - عن البوت"
        )
    elif command == "/info":
        return (
            "🛡️ عن البوت\n\n"
            "الاسم: مسلم العماري\n"
            "الإصدار: 2.0 المستقرة\n"
            "التخصص: مرجعية عربية مغربية إسلامية\n"
            "المطور: أنت! 👑\n"
            "التقنية: Groq AI + Python"
        )
    elif command == "/quran":
        verse = random.choice(QURAN_VERSES)
        return f"📖 آية من الذكر الحكيم\n\n{verse}"
    elif command == "/hadith":
        hadith = random.choice(AHADITH)
        return f"🌟 حديث شريف\n\n{hadith}"
    elif command == "/dua":
        return f"🤲 دعاء مبارك\n\n{random.choice(DUAS)}"
    elif command == "/naseeha":
        return f"📿 نصيحة اليوم\n\n{random.choice(NASEHA)}"
    elif command == "/tafsir":
        tafsir = random.choice(TAFSIR)
        return f"📖 تفسير\n\n{tafsir}"
    elif command == "/azkar":
        zekr = random.choice(AZKAR)
        return f"📿 ذكر وفضله\n\n{zekr}"
    elif command == "/seerah":
        return f"🌿 من السيرة النبوية\n\n{random.choice(SEERAH)}"
    elif command == "/prayer_times":
        return PRAYER_TIMES_MSG
    elif command == "/iqra":
        book = random.choice(BOOKS)
        return f"📚 كتاب اليوم\n\n{book}"
    elif command == "/random":
        items = [
            f"📖 آية:\n{random.choice(QURAN_VERSES)}",
            f"🌟 حديث:\n{random.choice(AHADITH)}",
            f"🤲 دعاء:\n{random.choice(DUAS)}",
            f"📿 نصيحة:\n{random.choice(NASEHA)}",
        ]
        return "🎲 خليط إيماني\n\n" + "\n\n".join(random.sample(items, 3))
    else:
        return None

# ==================== دالة الذكاء العام ====================
async def ask_groq(user_message: str) -> str:
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "أنت 'مسلم العماري'، بوت ذكي ودود يقدم محتوى إسلامياً ثرياً. "
                        "تستخدم أسلوباً لطيفاً ومباشراً بالعربية، مع رموز تعبيرية خفيفة. "
                        "تركز على النصائح الدينية والأخلاقية والقيم الإسلامية. "
                        "إذا سألك أحد عن نفسك، قل أنك بوت إسلامي صمم لخدمة المسلمين. "
                        "ابتعد عن الفتاوى، وأحل على العلماء عند الحاجة."
                    )
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.9,
            max_tokens=2000
        )
        return str(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ حدث خطأ مؤقت، جرب مرة أخرى."

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
            logger.info(f"رسالة من {chat_id}: {text}")

            # فحص الأوامر المحلية أولاً
            command_reply = await handle_command(text)
            if command_reply:
                await bot.send_message(chat_id, command_reply)
            else:
                # دردشة عامة مع Groq
                groq_reply = await ask_groq(text)
                # نرسل الرد مع توقيع بسيط
                full_reply = f"✨ مسلم العماري يقول:\n\n{groq_reply}\n\n▫️ تفضل بسؤالي عن أي شيء آخر!"
                await bot.send_message(chat_id, full_reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "🕋 مسلم العماري يعمل!"}
