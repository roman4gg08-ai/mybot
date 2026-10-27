import asyncio, json, os, time
from datetime import datetime
from zoneinfo import ZoneInfo
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

load_dotenv()
TOKEN = os.environ["BOT_TOKEN"]
OWNER_IDS = {
    int(x) for x in os.getenv("OWNER_ID", "0").replace(" ", "").split(",") if x
}
API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("AI_MODEL", "gemini-1.5-flash")
COOLDOWN = 6 * 3600
AI_LIMIT_PER_HOUR = 8
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
FILE = os.path.join(DATA_DIR, "settings.json")
DEFAULTS = {
    "enabled": True,
    "notify": True,
    "ai": False,
    "start": 0,
    "end": 24,
    "tz": "Europe/Moscow",
    "text": "Привет! Это помощник rgm, он сейчас не может ответить",
    "prompt": (
        "Ты — ИИ-помощник владельца этого аккаунта (rgm). Он сейчас недоступен. "
        "В первом ответе представься помощником. Отвечай коротко, вежливо и на "
        "языке собеседника. Ты не можешь ничего обещать, назначать встречи, "
        "обсуждать деньги и переводы, сообщать личные данные, адреса и пароли: "
        "в таких случаях скажи, что передашь сообщение и владелец ответит сам. "
        "Не выдавай себя за человека."
    ),
}
TYPES = {
    "photo": "фото", "voice": "голосовое", "video_note": "кружок",
    "video": "видео", "sticker": "стикер", "animation": "GIF",
    "document": "файл", "audio": "аудио", "location": "геолокация",
    "venue": "место", "contact": "контакт", "poll": "опрос",
    "dice": "кубик", "story": "история",
}

def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except Exception:
        return dict(DEFAULTS)

def save():
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False)

S = load()
bot = Bot(TOKEN)
dp = Dispatcher()
owners, last_reply, history, ai_times = {}, {}, {}, {}

def is_owner(m: Message):
    return bool(m.from_user) and m.from_user.id in OWNER_IDS

def is_away():
    h = datetime.now(ZoneInfo(S["tz"])).hour
    a, b = S["start"], S["end"]
    if a < b:
        return a <= h < b
    return h >= a or h < b

async def owner_id(conn_id):
    if conn_id not in owners:
        c = await bot.get_business_connection(conn_id)
        owners[conn_id] = c.user.id
    return owners[conn_id]

def describe(m: Message):
    ctype = str(getattr(m.content_type, "value", m.content_type))
    body = m.text or m.caption or ""
    if len(body) > 300:
        body = body[:300] + "…"
    if ctype == "text":
        return body
    return f"[{TYPES.get(ctype, ctype)}] {body}".strip()

async def ask_ai(key, text):
    h = history.setdefault(key, [])
    if h and h[-1]["role"] == "user":
        h[-1]["parts"][0]["text"] += "\n" + text
    else:
        h.append({"role": "user", "parts": [{"text": text}]})
    del h[:-10]
    while h and h[0]["role"] != "user":
        h.pop(0)
    payload = {
        "systemInstruction": {"parts": [{"text": S["prompt"]}]},
        "contents": h,
        "generationConfig": {"maxOutputTokens": 1000},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent"
    )
    headers = {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload, headers=headers) as r:
            data = await r.json()
            if r.status != 200:
                raise RuntimeError(str(data)[:300])
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    reply = "".join(p.get("text", "") for p in parts).strip()
    if not reply:
        raise RuntimeError("empty reply: " + str(data)[:300])
    h.append({"role": "model", "parts": [{"text": reply}]})
    return reply

@dp.message(Command("myid"))
async def cmd_myid(m: Message):
    await m.answer(f"Твой ID: {m.from_user.id}")

@dp.message(Command("start", "help"))
async def cmd_help(m: Message):
    if not is_owner(m):
        await m.answer("Узнай свой ID командой /myid")
        return
    await m.answer(
        "/time 0 7 — часы ответа\n"
        "/text Текст — фиксированное сообщение\n"
        "/ai on, /ai off — умные ответы через ИИ\n"
        "/prompt Текст — инструкции для ИИ\n"
        "/on, /off — включить, выключить ответы\n"
        "/notify on, /notify off — уведомления мне\n"
        "/tz Europe/Moscow — часовой пояс\n"
        "/status — настройки"
    )

@dp.message(Command("status"))
async def cmd_status(m: Message):
    if not is_owner(m):
        return
    ai = "включён" if S["ai"] else "выключен"
    if S["ai"] and not API_KEY:
        ai += " (нет GEMINI_API_KEY!)"
    await m.answer(
        f"Автоответ: {'включён' if S['enabled'] else 'выключен'}\n"
        f"ИИ ({MODEL}): {ai}\n"
        f"Уведомления: {'включены' if S['notify'] else 'выключены'}\n"
        f"Часы: {S['start']}:00 — {S['end']}:00 ({S['tz']})\n"
        f"Сейчас {'отвечаю' if is_away() else 'не отвечаю'}\n"
        f"Текст: {S['text']}"
    )

@dp.message(Command("time"))
async def cmd_time(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    try:
        a, b = map(int, command.args.split())
        assert 0 <= a <= 23 and 0 <= b <= 24 and a != b
    except Exception:
        await m.answer("Формат: /time 0 7 (часы 0-23, конец 0-24, начало не равно концу)")
        return
    S["start"], S["end"] = a, b
    save()
    await m.answer(f"Готово: отвечаю с {a}:00 до {b}:00")

@dp.message(Command("text"))
async def cmd_text(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    if not command.args:
        await m.answer("Формат: /text Привет! Я скоро отвечу")
        return
    S["text"] = command.args.strip()
    save()
    await m.answer("Текст обновлён")

@dp.message(Command("prompt"))
async def cmd_prompt(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    if not command.args:
        await m.answer(f"Текущие инструкции для ИИ:\n\n{S['prompt']}")
        return
    S["prompt"] = command.args.strip()
    save()
    await m.answer("Инструкции для ИИ обновлены")

@dp.message(Command("ai"))
async def cmd_ai(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    arg = (command.args or "").strip().lower()
    if arg not in ("on", "off"):
        await m.answer("Формат: /ai on или /ai off")
        return
    if arg == "on" and not API_KEY:
        await m.answer("Сначала добавь переменную GEMINI_API_KEY на хостинге")
        return
    S["ai"] = arg == "on"
    save()
    await m.answer("ИИ " + ("включён" if S["ai"] else "выключен"))

@dp.message(Command("on"))
async def cmd_on(m: Message):
    if is_owner(m):
        S["enabled"] = True
        save()
        await m.answer("Автоответ включён")

@dp.message(Command("off"))
async def cmd_off(m: Message):
    if is_owner(m):
        S["enabled"] = False
        save()
        await m.answer("Автоответ выключен")

@dp.message(Command("notify"))
async def cmd_notify(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    arg = (command.args or "").strip().lower()
    if arg not in ("on", "off"):
        await m.answer("Формат: /notify on или /notify off")
        return
    S["notify"] = arg == "on"
    save()
    await m.answer("Уведомления " + ("включены" if S["notify"] else "выключены"))

@dp.message(Command("tz"))
async def cmd_tz(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    try:
        ZoneInfo(command.args.strip())
    except Exception:
        await m.answer("Формат: /tz Europe/Moscow")
        return
    S["tz"] = command.args.strip()
    save()
    await m.answer(f"Часовой пояс: {S['tz']}")

@dp.business_message()
async def auto_reply(m: Message):
    if not m.from_user:
        return
    acc = await owner_id(m.business_connection_id)
    if m.from_user.id == acc:
        return
    if not S["enabled"] or not is_away():
        return

    key = (m.business_connection_id, m.chat.id)
    now = time.time()
    user_text = m.text or m.caption
    reply, used_ai = None, False

    if S["ai"] and API_KEY and user_text:
        times = [t for t in ai_times.get(key, []) if now - t < 3600]
        if len(times) < AI_LIMIT_PER_HOUR:
            try:
                reply = await ask_ai(key, user_text)
                used_ai = True
                times.append(now)
            except Exception as e:
                print("ai error:", e)
        ai_times[key] = times
        if reply is None and len(times) >= AI_LIMIT_PER_HOUR:
            return

    if reply is None:
        if now - last_reply.get(key, 0) < COOLDOWN:
            return
        last_reply[key] = now
        reply = S["text"]

    await bot.send_message(
        chat_id=m.chat.id,
        text=reply,
        business_connection_id=m.business_connection_id,
    )

    if S["notify"]:
        try:
            u = m.from_user
            who = u.full_name + (f" (@{u.username})" if u.username else "")
            note = (
                f"Тебе написал {who}.\n\n"
                f"Сообщение: {describe(m)}\n\n"
                f"Ответ{' ИИ' if used_ai else ''}: {reply}"
            )
            await bot.send_message(acc, note[:4000])
        except Exception as e:
                print("ai error:", e)

async def main():
    print("Bot is running...")
    await dp.start_polling(bot)

asyncio.run(main())
