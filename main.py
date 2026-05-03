import os
import json
import logging
import random
import requests
from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update, Bot, InputMediaPhoto
from telegram.ext import ApplicationBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("يجب تعيين BOT_TOKEN و GROQ_API_KEY في متغيرات البيئة")

groq_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot: Bot = telegram_app.bot

# ==================== شخصية المساعد (مثلي تمامًا – صارمة وواضحة) ====================
MAIN_SYSTEM_PROMPT = (
    "أنت 'مسلم العماري'، مساعد ذكي ومفيد تماماً مثل DeepSeek.\n"
    "شخصيتك ودودة، لطيفة، ومتوازنة. تحب مساعدة الناس وتقديم إجابات دقيقة ومفيدة بأسلوب مباشر وواضح.\n"
    "تستخدم الإيموجي المناسب للسياق (مثل 😊، 🤲، ✨، 🕌، 💚) بشكل طبيعي وخفيف جداً دون مبالغة.\n"
    "تخاطب المستخدم باسمه الأول أحياناً لتجعل المحادثة شخصية ودافئة.\n"
    "مرجعيتك إسلامية وأنت معتدل ومتوازن، بعيد عن التشدد. إذا سُئلت عن فتوى، قل بلطف: 'هذه مسألة دينية دقيقة، يُفضل سؤال أهل العلم.'\n"
    "أنت لست روبوتاً بارداً، بل صديق حكيم ومتواضع. لكنك لا تبالغ في العاطفة أو تستخدم كلمات غريبة. لا تقل 'حبيبي' أو 'يا قلبي'.\n"
    "تتحدث العربية بطلاقة تامة. ترد دائماً بصياغة واضحة ولطيفة ومختصرة نسبياً. لا تثرثر."
)

# ==================== ذاكرة مؤقتة (آخر 6 رسائل فقط) ====================
user_histories = {}
MAX_HISTORY = 6

# ==================== دوال الرسم (مُبسطة ومضمونة) ====================
async def fetch_image_bytes(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=25)
        return resp.content if resp.status_code == 200 else None
    except:
        return None

async def draw_images(prompt: str) -> list[bytes]:
    images = []
    for _ in range(3):
        seed = random.randint(1, 99999)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=768&height=768&seed={seed}&nologo=true"
        data = await fetch_image_bytes(url)
        if data:
            images.append(data)
    return images

def detect_draw_intent(text: str) -> str | None:
    triggers = ["ارسم", "اصنع صورة", "صور لي", "تخيل", "اعمل صورة", "رسم", "خلق صورة", "تخيل صورة"]
    for t in triggers:
        if t in text:
            parts = text.split(t, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

# ==================== دالة الذكاء العام ====================
async def ask_ai(user_id: int, user_name: str, prompt: str = None) -> str:
    messages = [{"role": "system", "content": MAIN_SYSTEM_PROMPT}]
    if user_id in user_histories:
        messages.extend(user_histories[user_id])
    if prompt:
        messages.append({"role": "user", "content": prompt})
    else:
        messages.append({"role": "user", "content": "أعطني الرد مباشرة."})

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.85,
            max_tokens=2000
        )
        reply = resp.choices[0].message.content
        if prompt:
            if user_id not in user_histories:
                user_histories[user_id] = []
            user_histories[user_id].extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": reply}
            ])
            if len(user_histories[user_id]) > MAX_HISTORY:
                user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]
        return reply
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
        if not update.message: return {"status": "ok"}

        chat_id = update.message.chat_id
        user_id = update.effective_user.id
        user_name = update.message.from_user.first_name or "صديقي"
        text = update.message.text or ""

        logger.info(f"رسالة من {user_name}: {text}")

        # --- معالجة الرسم (/draw) ---
        if text.startswith("/draw"):
            prompt = text.replace("/draw", "", 1).strip()
            if not prompt:
                await bot.send_message(chat_id, "🎨 أرسل: /draw وصف الصورة")
                return {"status": "ok"}
            imgs = await draw_images(prompt)
            if imgs:
                media = [InputMediaPhoto(img) for img in imgs]
                await bot.send_media_group(chat_id, media)
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
            return {"status": "ok"}

        # --- معالجة الرسم (نية) ---
        draw_prompt = detect_draw_intent(text)
        if draw_prompt:
            imgs = await draw_images(draw_prompt)
            if imgs:
                media = [InputMediaPhoto(img) for img in imgs]
                await bot.send_media_group(chat_id, media)
            else:
                await bot.send_message(chat_id, "⚠️ فشل توليد الصور.")
            return {"status": "ok"}

        # --- الأوامر الثابتة ---
        if text.startswith("/start"):
            await bot.send_message(chat_id, f"🕋 أهلاً بك يا {user_name}!\n\nأنا مسلم، مساعدك الشخصي. جرب /help")
            return {"status": "ok"}
        if text.startswith("/info"):
            await bot.send_message(chat_id, f"🛡️ عن البوت\n\nالاسم: مسلم العماري\nالتخصص: مرجعية عربية مغربية إسلامية\nالمطور: مسلم العماري! 👑\n\nاسألني ما شئت 🤲✨")
            return {"status": "ok"}
        if text.startswith("/help"):
            await bot.send_message(chat_id, "🕌 /quran /hadith /dua /naseeha /tafsir /azkar /seerah /iqra /prayer_times /random /draw وصف")
            return {"status": "ok"}

        # --- الأوامر الديناميكية (تستخدم AI) ---
        cmd = text.split()[0].lower()
        prompts = {
            "/quran": "أعطني آية قرآنية عشوائية مع تفسيرها. ابدأ بـ '📖 آية من الذكر الحكيم'.",
            "/hadith": "أعطني حديثاً شريفاً مع شرحه. ابدأ بـ '🌟 حديث شريف'.",
            "/dua": "أعطني دعاءً جميلاً. ابدأ بـ '🤲 دعاء'.",
            "/naseeha": "أعطني نصيحة حياتية ملهمة. ابدأ بـ '📿 نصيحة'.",
            "/azkar": "أعطني ذكراً مع فضله. ابدأ بـ '📿 ذكر وفضله'.",
            "/seerah": "احك لي موقفاً من السيرة. ابدأ بـ '🌿 من السيرة'.",
            "/tafsir": "أعطني آية مع تفسيرها. ابدأ بـ '📖 تفسير'.",
            "/iqra": "اقترح علي كتاباً مفيداً. ابدأ بـ '📚 كتاب'.",
            "/random": "أرسل خليطاً: آية، حديث، دعاء، نصيحة. ابدأ بـ '🎲 خليط إيماني'.",
            "/prayer_times": "اذكر أهمية الصلاة ومواقيتها التقريبية. ابدأ بـ '🕌 تنبيه الصلاة'."
        }
        if cmd in prompts:
            reply = await ask_ai(user_id, user_name, prompts[cmd])
            await bot.send_message(chat_id, reply)
            return {"status": "ok"}

        # --- محادثة عامة ---
        reply = await ask_ai(user_id, user_name, text)
        await bot.send_message(chat_id, reply)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/")
def index():
    return {"message": "مسلم العماري مستقر وذكي!"}
