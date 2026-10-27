import asyncio, json, os, time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

load_dotenv()
TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
COOLDOWN = 6 * 3600
FILE = "settings.json"
DEFAULTS = {
    "enabled": True,
    "start": 0,
    "end": 7,
    "tz": "Europe/Moscow",
    "text": "Привет! Это помощник rgm, он сейчас не может ответить",
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
    return OWNER_ID != 0 and m.from_user and m.from_user.id == OWNER_ID

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
        "/on, /off — включить, выключить\n"
        "/tz Europe/Moscow — часовой пояс\n"
        "/status — настройки"
    )

@dp.message(Command("status"))
async def cmd_status(m: Message):
    if not is_owner(m):
        return
    await m.answer(
        f"Автоответ: {'включён' if S['enabled'] else 'выключен'}\n"
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

@dp.business_message(F.text)
async def auto_reply(m: Message):
    if m.from_user.id == await owner_id(m.business_connection_id):
        return
    if not S["enabled"] or not is_away():
        return
    now = time.time()
    if now - last_reply.get(m.chat.id, 0) < COOLDOWN:
        return
    last_reply[m.chat.id] = now
    await bot.send_message(
        chat_id=m.chat.id,
        text=S["text"],
        business_connection_id=m.business_connection_id,
    )

async def main():
    print("Bot is running...")
    await dp.start_polling(bot)

asyncio.run(main())
