import asyncio, json, os, time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

load_dotenv()
TOKEN = os.environ["BOT_TOKEN"]
OWNER_IDS = {
    int(x) for x in os.getenv("OWNER_ID", "0").replace(" ", "").split(",") if x
}
COOLDOWN = 6 * 3600  # не чаще раза в 6 часов на один чат
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULTS = {
    "enabled": True,
    "notify": True,
    "start": 0,
    "end": 7,
    "tz": "Europe/Moscow",
    "text": "Привет! Это помощник rgm, он сейчас не может ответить",
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
owners, last_reply = {}, {}

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
        "/text Текст — сообщение\n"
        "/on, /off — включить, выключить ответы\n"
        "/notify on, /notify off — уведомления мне\n"
        "/tz Europe/Moscow — часовой пояс\n"
        "/status — настройки"
    )

@dp.message(Command("status"))
async def cmd_status(m: Message):
    if not is_owner(m):
        return
    await m.answer(
        f"Автоответ: {'включён' if S['enabled'] else 'выключен'}\n"
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
        assert 0 <= a <= 23 and 0 <= b
