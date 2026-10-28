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
    "muted": [],
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
owners, last_reply, warned = {}, {}, {}

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

async def delete_msg(conn_id, msg_id):
    await bot.delete_business_messages(
        business_connection_id=conn_id, message_ids=[msg_id]
    )

async def warn_owner(acc, text):
    now = time.time()
    if now - warned.get(acc, 0) < 3600:
        return
    warned[acc] = now
    try:
        await bot.send_message(acc, text)
    except Exception as e:
        print("warn error:", e)

async def drop_if_muted(m: Message, acc: int) -> bool:
    if m.chat.id not in S["muted"]:
        return False
    try:
        await delete_msg(m.business_connection_id, m.message_id)
    except Exception as e:
        print("delete error:", e)
        await warn_owner(
            acc,
            "Не удалось удалить сообщение заглушённого собеседника. "
            "Проверь, что у бота включено право на удаление сообщений "
            "(Настройки → Telegram для бизнеса → Чат-боты).\n"
            f"Ошибка: {str(e)[:200]}",
        )
    return True

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
        "/mute ID, /unmute ID, /mutelist — заглушить, вернуть, список\n"
        "(в чате с человеком можно написать просто /mute или /unmute)\n"
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
        f"Заглушено собеседников: {len(S['muted'])}\n"
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

@dp.message(Command("mute"))
async def cmd_mute(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    try:
        uid = int((command.args or "").strip())
    except Exception:
        await m.answer("Формат: /mute 123456789 (ID человека из уведомления)")
        return
    if uid not in S["muted"]:
        S["muted"].append(uid)
        save()
    await m.answer(f"Заглушен: {uid}")

@dp.message(Command("unmute"))
async def cmd_unmute(m: Message, command: CommandObject):
    if not is_owner(m):
        return
    try:
        uid = int((command.args or "").strip())
    except Exception:
        await m.answer("Формат: /unmute 123456789")
        return
    if uid in S["muted"]:
        S["muted"].remove(uid)
        save()
    await m.answer(f"Больше не заглушён: {uid}")

@dp.message(Command("mutelist"))
async def cmd_mutelist(m: Message):
    if not is_owner(m):
        return
    if not S["muted"]:
        await m.answer("Список заглушённых пуст")
        return
    await m.answer("Заглушены:\n" + "\n".join(str(x) for x in S["muted"]))

@dp.edited_business_message()
async def on_edited(m: Message):
    if not m.from_user:
        return
    acc = await owner_id(m.business_connection_id)
    if m.from_user.id != acc:
        await drop_if_muted(m, acc)

@dp.business_message()
async def on_business_message(m: Message):
    if not m.from_user:
        return
    acc = await owner_id(m.business_connection_id)

    # сообщения самого владельца: команды /mute и /unmute прямо в чате
    if m.from_user.id == acc:
        cmd = (m.text or "").strip().lower()
        if cmd in ("/mute", "/unmute"):
            cid = m.chat.id
            if cmd == "/mute":
                if cid not in S["muted"]:
                    S["muted"].append(cid)
                    save()
                info = f"Собеседник {cid} заглушён: его сообщения будут удаляться."
            else:
                if cid in S["muted"]:
                    S["muted"].remove(cid)
                    save()
                info = f"Собеседник {cid} больше не заглушён."
            try:
                await delete_msg(m.business_connection_id, m.message_id)
            except Exception as e:
                print("delete cmd error:", e)
            try:
                await bot.send_message(acc, info)
            except Exception as e:
                print("info error:", e)
        return

    # заглушённые: удаляем сразу, ответа нет
    if await drop_if_muted(m, acc):
        return

    if not S["enabled"] or not is_away():
        return

    key = (m.business_connection_id, m.chat.id)
    now = time.time()
    if now - last_reply.get(key, 0) < COOLDOWN:
        return
    last_reply[key] = now

    await bot.send_message(
        chat_id=m.chat.id,
        text=S["text"],
        business_connection_id=m.business_connection_id,
    )

    if S["notify"]:
        try:
            u = m.from_user
            who = u.full_name + (f" (@{u.username})" if u.username else "")
            await bot.send_message(
                acc,
                f"Тебе написал {who}, ID {u.id}.\n"
                f"Я ответил за тебя.\n\n"
                f"Сообщение: {describe(m)}",
            )
        except Exception as e:
            print("notify error:", e)

async def main():
    print("Bot is running...")
    await dp.start_polling(bot)

asyncio.run(main())
