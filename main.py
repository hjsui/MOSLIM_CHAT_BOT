import os
import logging
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

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و OPENROUTER_API_KEY في متغيرات البيئة")

# إعداد عميل OpenRouter
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# -------------------- الذاكرة المؤقتة --------------------
user_histories = defaultdict(list)
MAX_HISTORY = 10  # آخر 10 رسائل

# -------------------- شخصية البوت (محسّنة) --------------------
SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، صديق ذكي ومتوازن. "
    "شخصيتك ودودة، لطيفة، ومتوازنة. تحب مساعدة الناس وتقديم إجابات دقيقة ومفيدة بأسلوب مباشر وواضح. "
    "تستخدم الإيموجي المناسب للسياق (😊، 🤲، ✨، 🕌) بشكل طبيعي وخفيف جداً دون مبالغة. "
    "تخاطب المستخدم باسمه الأول أحياناً لتجعل المحادثة شخصية ودافئة. "
    "مرجعيتك إسلامية وأنت معتدل ومتوازن، بعيد عن التشدد. إذا سُئلت عن فتوى، قل بلطف: 'هذه مسألة دينية دقيقة، يُفضل سؤال أهل العلم.' "
    "أنت لست روبوتاً بارداً، بل صديق حكيم ومتواضع. لا تبالغ في العاطفة ولا تستخدم كلمات غريبة مثل 'حبيبي' أو 'يا قلبي'. "
    "تتحدث العربية بطلاقة تامة. ترد دائماً بصياغة واضحة ولطيفة ومختصرة نسبياً. "
    "ممنوع منعاً باتاً أن تبدأ أي رد بـ 'مسلم العماري:' أو أي صيغة مشابهة. تحدث بشكل طبيعي كصديق."
)

# -------------------- قائمة النماذج المجانية على OpenRouter --------------------
FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "google/gemma-3-27b-it:free",
    "openrouter/free"  # توجيه تلقائي لأفضل نموذج متاح
]

# -------------------- توليد صورة واحدة --------------------
async def generate_single_image(prompt: str) -> bytes | None:
    """توليد صورة واحدة باستخدام Pollinations.ai"""
    try:
        seed = random.randint(1, 99999)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=768&height=768&seed={seed}&nologo=true"
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.content
        else:
            logger.error(f"فشل تحميل الصورة: {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"استثناء في توليد الصورة: {e}")
        return None

def detect_draw_intent(text: str) -> str | None:
    """كشف نية الرسم في النص"""
    triggers = ["ارسم", "اصنع صورة", "صور لي", "تخيل", "اعمل صورة", "رسم", "خلق صورة", "تخيل صورة"]
    for t in triggers:
        if t in text:
            parts = text.split(t, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

# -------------------- دالة الذكاء العامة (مع ذاكرة واحتياطي) --------------------
async def ask_ai(user_id: int, user_name: str, user_message: str) -> str:
    """إرسال المحادثة إلى OpenRouter مع سجل المحادثة"""
    # بناء الرسائل: system prompt + التاريخ + الرسالة الجديدة
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # إضافة تاريخ المحادثة
    if user_id in user_histories:
        messages.extend(user_histories[user_id])
    
    # إضافة رسالة المستخدم الجديدة
    messages.append({"role": "user", "content": user_message})

    # تجربة النماذج بالترتيب
    last_error = ""
    for model in FREE_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.85,
                max_tokens=2000
            )
            reply = response.choices[0].message.content.strip()
            
            # تحديث الذاكرة: إضافة سؤال المستخدم ورد البوت
            history = user_histories[user_id]
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": reply})
            # الاحتفاظ بآخر 10 رسائل فقط
            if len(history) > MAX_HISTORY * 2:
                user_histories[user_id] = history[-(MAX_HISTORY * 2):]
            
            logger.info(f"نجح النموذج {model}")
            return reply
        except Exception as e:
            last_error = str(e)
            logger.warning(f"فشل النموذج {model}: {e}")
    
    logger.error(f"فشلت كل النماذج. آخر خطأ: {last_error}")
    return "⚠️ عذراً، جميع خدمات الذكاء الاصطناعي مشغولة حالياً. حاول مرة أخرى بعد قليل."

# -------------------- خادم FastAPI --------------------
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
        text = update.message.text or ""

        logger.info(f"رسالة من {user_name} ({user_id}): {text}")

        # ============ الأوامر الثابتة ============
        if text.startswith("/start"):
            welcome_msg = (
                f"✨ أهلاً وسهلاً بك يا {user_name}!\n\n"
                "أنا **مسلم العماري**، رفيقك الذكي. ✨\n"
                "أنا هنا عشان أساعدك في أي شيء تحتاجه، من النصيحة للمعلومة، ومن القرآن للرسم.\n\n"
                "🎯 **وش تقدر تسألني عنه؟**\n"
                "• أسئلة دينية وثقافية واجتماعية.\n"
                "• آيات قرآنية وأحاديث وأدعية.\n"
                "• نصايح يومية وتفسير.\n"
                "• مواقيت الصلاة التقريبية.\n"
                "• رسم صورة من خيالك (أرسل 'ارسم وصف').\n\n"
                "📜 اكتب /help عشان تشوف كل الأوامر المتاحة.\n"
                "يا هلا فيك، ابدأ بسؤالك الأول! 🤲"
            )
            await bot.send_message(chat_id, welcome_msg)
            return {"status": "ok"}

        if text.startswith("/help"):
            help_msg = (
                "🕌 **قائمة المساعدة** 🕌\n\n"
                "⚡️ **أوامر المحتوى الإسلامي:**\n"
                "/quran - آية قرآنية عشوائية مع تفسيرها.\n"
                "/hadith - حديث شريف مع شرح مختصر.\n"
                "/dua - دعاء مبارك من القرآن أو السنة.\n"
                "/naseeha - نصيحة حياتية أو دينية ملهمة.\n"
                "/azkar - ذكر من الأذكار مع فضله.\n"
                "/seerah - موقف من السيرة النبوية.\n"
                "/tafsir - تفسير ميسر لآية.\n"
                "/iqra - اقتراح كتاب إسلامي أو ثقافي.\n"
                "/random - خليط إيماني مميز (آية + حديث + دعاء + نصيحة).\n"
                "/prayer_times - تذكير بأهمية الصلاة ومواقيتها التقريبية.\n\n"
                "🎨 **الرسم:**\n"
                "/draw وصف - أرسم لك صورة من وصفك.\n"
                "أو ببساطة اكتب 'ارسم لي ...' وأنا أفهمك.\n\n"
                "ℹ️ **معلومات:**\n"
                "/info - معلومات عن البوت.\n"
                "/start - رسالة ترحيبية.\n\n"
                "💬 **الدردشة:**\n"
                "تقدر تسألني أي سؤال بشكل طبيعي، وأنا أجاوبك بذكاء.\n\n"
                "أنا هنا لخدمتك! 😊"
            )
            await bot.send_message(chat_id, help_msg)
            return {"status": "ok"}

        if text.startswith("/info"):
            await bot.send_message(chat_id, 
                "🛡️ **عن البوت**\n\n"
                "الاسم: مسلم العماري\n"
                "التخصص: مرجعية عربية مغربية إسلامية\n"
                "المطور: مسلم العماري 👑\n"
                "أنا بوت ذكي يهدف لمساعدتك وتقديم المعلومة المفيدة."
            )
            return {"status": "ok"}

        # ============ الرسم ============
        if text.startswith("/draw"):
            prompt = text.replace("/draw", "", 1).strip()
            if not prompt:
                await bot.send_message(chat_id, "🎨 أرسل الأمر هكذا: /draw وصف الصورة")
                return {"status": "ok"}
            img_data = await generate_single_image(prompt)
            if img_data:
                await bot.send_photo(chat_id, photo=img_data, caption=f"🎨 صورة لك يا {user_name}")
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصورة. حاول مرة أخرى.")
            return {"status": "ok"}

        draw_prompt = detect_draw_intent(text)
        if draw_prompt:
            img_data = await generate_single_image(draw_prompt)
            if img_data:
                await bot.send_photo(chat_id, photo=img_data, caption=f"🎨 صورة لك يا {user_name}")
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصورة.")
            return {"status": "ok"}

        # ============ الأوامر الديناميكية (تستخدم الذكاء الاصطناعي) ============
        cmd = text.split()[0].lower()
        prompts_map = {
            "/quran": "أعطني آية قرآنية عشوائية مع تفسيرها. ابدأ بـ '📖'.",
            "/hadith": "أعطني حديثاً شريفاً مع شرحه. ابدأ بـ '🌟'.",
            "/dua": "أعطني دعاءً جميلاً. ابدأ بـ '🤲'.",
            "/naseeha": "أعطني نصيحة حياتية ملهمة. ابدأ بـ '📿'.",
            "/azkar": "أعطني ذكراً مع فضله. ابدأ بـ '📿'.",
            "/seerah": "احك لي موقفاً من السيرة. ابدأ بـ '🌿'.",
            "/tafsir": "أعطني آية مع تفسيرها. ابدأ بـ '📖'.",
            "/iqra": "اقترح علي كتاباً مفيداً. ابدأ بـ '📚'.",
            "/random": "أرسل خليطاً: آية، حديث، دعاء، نصيحة. ابدأ بـ '🎲'.",
            "/prayer_times": "اذكر أهمية الصلاة ومواقيتها التقريبية. ابدأ بـ '🕌'."
        }
        if cmd in prompts_map:
            # نستخدم صيغة الأمر مباشرة دون إظهار اسم البوت
            reply = await ask_ai(user_id, user_name, prompts_map[cmd])
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # ============ دردشة عامة ============
        reply = await ask_ai(user_id, user_name, text)
        await bot.send_message(chat_id, reply)
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري يعمل بقوة وذكاء ✨"}
