import os
import logging
import random
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot, constants
from telegram.ext import ApplicationBuilder

# ==================== الإعدادات الأساسية ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("ينقص متغيرات البيئة BOT_TOKEN أو GROQ_API_KEY")

# ==================== عميل Groq الذكي ====================
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ==================== المحتوى الإسلامي الثري ====================
QURAN_VERSES = [
    ("﷽\n\n(إِنَّ مَعَ الْعُسْرِ يُسْرًا) 🍃", "سورة الشرح"),
    ("﷽\n\n(فَاذْكُرُونِي أَذْكُرْكُمْ وَاشْكُرُوا لِي وَلَا تَكْفُرُونِ) 🤲", "سورة البقرة"),
    ("﷽\n\n(إِنَّ اللَّهَ مَعَ الصَّابِرِينَ) 💪", "سورة البقرة"),
    ("﷽\n\n(وَقُل رَّبِّ ارْحَمْهُمَا كَمَا رَبَّيَانِي صَغِيرًا) 🌸", "سورة الإسراء"),
    ("﷽\n\n(وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا وَيَرْزُقْهُ مِنْ حَيْثُ لَا يَحْتَسِبُ) 🌟", "سورة الطلاق"),
    ("﷽\n\n(ادْعُونِي أَسْتَجِبْ لَكُمْ) 🤲", "سورة غافر"),
    ("﷽\n\n(فَإِنَّ مَعَ الْعُسْرِ يُسْرًا إِنَّ مَعَ الْعُسْرِ يُسْرًا) ✨", "سورة الشرح"),
    ("﷽\n\n(إِنَّ الصَّلَاةَ تَنْهَىٰ عَنِ الْفَحْشَاءِ وَالْمُنكَرِ) 🕌", "سورة العنكبوت"),
    ("﷽\n\n(وَبِالْوَالِدَيْنِ إِحْسَانًا) 💝", "سورة الإسراء"),
    ("﷽\n\n(قُلْ هُوَ اللَّهُ أَحَدٌ) 🕋", "سورة الإخلاص"),
]

AHADITH = [
    ("من صلى الفجر في جماعة فهو في ذمة الله. 🕌", "رواه مسلم"),
    ("الكلمة الطيبة صدقة. 🌸", "متفق عليه"),
    ("لا تغضب ولك الجنة. 😊", "رواه البخاري"),
    ("من كان يؤمن بالله واليوم الآخر فليقل خيراً أو ليصمت. 🤫", "متفق عليه"),
    ("تبسمك في وجه أخيك صدقة. 😊", "رواه الترمذي"),
    ("ازهد في الدنيا يحبك الله. 🌍", "رواه ابن ماجه"),
    ("المسلم من سلم المسلمون من لسانه ويده. 🤝", "متفق عليه"),
    ("إن الله رفيق يحب الرفق. 🌷", "رواه مسلم"),
    ("خيركم من تعلم القرآن وعلمه. 📖", "رواه البخاري"),
    ("من سلك طريقاً يلتمس فيه علماً سهل الله له طريقاً إلى الجنة. 🌟", "رواه مسلم"),
]

DUAS = [
    "اللهم إني أسألك الهدى والتقى والعفاف والغنى 🤲",
    "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ 🌸",
    "اللهم اغفر لي ولوالدي وللمؤمنين يوم يقوم الحساب 🕌",
    "اللهم إني أعوذ بك من الهم والحزن، وأعوذ بك من العجز والكسل 🍃",
    "رَبَّنَا لَا تُؤَاخِذْنَا إِن نَّسِينَا أَوْ أَخْطَأْنَا 🤲",
    "اللهم أصلح لي ديني الذي هو عصمة أمري، وأصلح لي دنياي التي فيها معاشي 🌍",
    "اللهم إني أسألك العفو والعافية في الدنيا والآخرة 💚",
    "يا مقلب القلوب ثبت قلبي على دينك 🕋",
]

NASEHA = [
    "حافظ على الصلوات الخمس، فهي عماد الدين. 🕌",
    "اقرأ ولو صفحة من القرآن يومياً. 📖",
    "بر الوالدين من أعظم القربات إلى الله. 💝",
    "الصدقة تطفئ غضب الرب. 💰",
    "ذكر الله يطمئن القلوب. 🧘",
    "سيرة النبي محمد ﷺ منهج حياة كامل. 🌟",
    "لا تحتقر من المعروف شيئاً. 🌱",
    "التوبة تمحو ما قبلها. 🍂",
]

AZKAR = [
    ("سبحان الله وبحمده، سبحان الله العظيم", "ثقيلتان في الميزان"),
    ("لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير", "كنز من كنوز الجنة"),
    ("أستغفر الله الذي لا إله إلا هو الحي القيوم وأتوب إليه", "غفرت ذنوبه"),
    ("سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر", "أحب الكلام إلى الله"),
    ("اللهم صل وسلم على نبينا محمد", "ترفع الدرجات"),
]

SEERAH = [
    "عندما دخل النبي ﷺ مكة فاتحاً، قال لأهلها: (اذهبوا فأنتم الطلقاء). 🌿",
    "كان النبي ﷺ يقوم الليل حتى تتفطر قدماه شكراً لله. 🌙",
    "حين أُوذي في الطائف، قال: (اللهم إني أشكو إليك ضعف قوتي) ثم عفا عنهم. 💚",
    "نبي الرحمة ﷺ كان يخصف نعله ويخدم أهله. 😊",
    "رغم جوعه ﷺ كان يشد الحجر على بطنه ويواصل رسالته. 🕋",
]

TAFSIR = [
    ("﷽\n(إِنَّ مَعَ الْعُسْرِ يُسْرًا)", "بعد الضيق يأتي الفرج، وعد الله لا يتخلف."),
    ("﷽\n(ادْعُونِي أَسْتَجِبْ لَكُمْ)", "الله قريب يجيب دعوة الداعي إذا دعاه."),
    ("﷽\n(إِنَّ اللَّهَ مَعَ الصَّابِرِينَ)", "المعية الإلهية لأهل الصبر؛ تأييد ونصر."),
]

BOOKS = [
    ("📚 رياض الصالحين", "للإمام النووي، يجمع أحاديث في الأخلاق والعبادات."),
    ("📚 فقه السنة", "للسيد سابق، يبسط الفقه بأسلوب سهل."),
    ("📚 الرحيق المختوم", "للمباركفوري، سيرة نبوية شاملة."),
    ("📚 لاتحزن", "للدكتور عائض القرني، رسائل إيمانية راقية."),
]

# ==================== أمر /prayer_times محاكاة ====================
PRAYER_TIMES_MSG = (
    "🕌 *تنبيه الصلاة*\n\n"
    "الصلاة خير من النوم.\n"
    "للمواقيت الدقيقة، استخدم تطبيقاً موثوقاً حسب مدينتك.\n"
    "ولا تنس: (إِنَّ الصَّلَاةَ كَانَتْ عَلَى الْمُؤْمِنِينَ كِتَابًا مَّوْقُوتًا).\n\n"
    "حافظ على صلاتك! 🤲"
)

# ==================== زخرفة الرسائل ====================
def format_identity():
    return "🕋 *مسلم العماري* 🕋\n\n"

def format_groq_reply(text):
    return f"✨ *مسلم العماري* يقول:\n\n{text}\n\n▫️ تفضل بسؤالي عن أي شيء آخر!"

# ==================== معالجة الأوامر ====================
async def handle_command(text: str) -> tuple[str, str] | None:
    command = text.split()[0].lower()
    
    if command == "/start":
        reply = (
            format_identity() +
            "📿 أهلاً بك في رحاب المعرفة الإسلامية!\n\n"
            "أنا *مسلم*، مساعدك الذكي. أقدم لك:\n"
            "🔥 نصائح واستشارات دينية ودنيوية\n"
            "🕋 آيات وأحاديث وأدعية\n"
            "👑 معلومات قيمة بأسلوب شيق\n\n"
            "📜 *الأوامر*:\n"
            "/quran | /hadith | /dua | /naseeha\n"
            "/tafsir | /azkar | /seerah | /iqra\n"
            "/prayer\_times | /random | /info"
        )
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/help":
        reply = (
            format_identity() +
            "🕌 *قائمة المساعدة*\n\n"
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
            "  /prayer\_times - تنبيه الصلاة\n"
            "  /random - مزيج عشوائي\n"
            "  /info - عن البوت"
        )
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/info":
        reply = (
            format_identity() +
            "🛡️ *عن البوت*\n\n"
            "الاسم: مسلم العماري\n"
            "الإصدار: 2.0 المتكاملة\n"
            "التخصص: مرجعية عربية مغربية إسلامية\n"
            "المطور: أنت! 👑\n"
            "التقنية: Groq AI + Python"
        )
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/quran":
        verse, surah = random.choice(QURAN_VERSES)
        reply = format_identity() + f"📖 *آية من الذكر الحكيم*\n\n{verse}\n\n_{surah}_"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/hadith":
        hadith, source = random.choice(AHADITH)
        reply = format_identity() + f"🌟 *حديث شريف*\n\n{hadith}\n\n_{source}_"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/dua":
        reply = format_identity() + f"🤲 *دعاء مبارك*\n\n{random.choice(DUAS)}"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/naseeha":
        reply = format_identity() + f"📿 *نصيحة اليوم*\n\n{random.choice(NASEHA)}"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/tafsir":
        verse, tafsir = random.choice(TAFSIR)
        reply = format_identity() + f"📖 *تفسير*\n\n{verse}\n\n_{tafsir}_"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/azkar":
        zekr, fadl = random.choice(AZKAR)
        reply = format_identity() + f"📿 *ذكر وفضله*\n\n{zekr}\n\n_{fadl}_"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/seerah":
        reply = format_identity() + f"🌿 *من السيرة النبوية*\n\n{random.choice(SEERAH)}"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/prayer_times":
        return format_identity() + PRAYER_TIMES_MSG, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/iqra":
        book, desc = random.choice(BOOKS)
        reply = format_identity() + f"📚 *كتاب اليوم*\n\n{book}\n_{desc}_"
        return reply, constants.ParseMode.MARKDOWN_V2
    
    elif command == "/random":
        items = [
            f"📖 آية:\n{random.choice(QURAN_VERSES)[0]}",
            f"🌟 حديث:\n{random.choice(AHADITH)[0]}",
            f"🤲 دعاء:\n{random.choice(DUAS)}",
            f"📿 نصيحة:\n{random.choice(NASEHA)}",
        ]
        reply = format_identity() + "🎲 *خليط إيماني*\n\n" + "\n\n".join(random.sample(items, 3))
        return reply, constants.ParseMode.MARKDOWN_V2
    
    return None

# ==================== دالة الرد العام ====================
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
            
            # تعامل مع الأوامر المحلية
            result = await handle_command(text)
            if result:
                reply, parse_mode = result
                await bot.send_message(chat_id, reply, parse_mode=parse_mode)
            else:
                # دردشة عامة مع Groq
                groq_reply = await ask_groq(text)
                formatted = format_groq_reply(groq_reply)
                await bot.send_message(chat_id, formatted, parse_mode=constants.ParseMode.MARKDOWN_V2)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "🕋 مسلم العماري يعمل!"}
