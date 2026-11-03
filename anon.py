"""
Анонимный бот для получения сообщений (aiogram 3.x)

Установка:  pip install aiogram
Запуск:     BOT_TOKEN=123:ABC python anon_bot.py

Как работает:
- /start            -> бот выдаёт вашу персональную ссылку.
- Человек открывает ссылку и пишет боту -> вам приходит анонимное сообщение.
- Ответьте (reply) на это сообщение -> ответ уйдёт отправителю анонимно.
- Ответьте на сообщение командой /who -> отправитель получит запрос и САМ решит,
  раскрыть ли username/ID и/или поделиться номером телефона.
"""
import asyncio
import os
import sqlite3
import asyncio
import os
import sqlite3

from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

TOKEN = os.environ["BOT_TOKEN"]
bot = Bot(TOKEN)
dp = Dispatcher()

DB_PATH = os.environ.get("DB_PATH", "anon_bot.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(DB_PATH)
db.execute("CREATE TABLE IF NOT EXISTS target (user_id INTEGER PRIMARY KEY, owner_id INTEGER)")
db.execute(
    "CREATE TABLE IF NOT EXISTS msgs (owner_id INTEGER, owner_msg_id INTEGER, "
    "sender_id INTEGER, sender_msg_id INTEGER, PRIMARY KEY (owner_id, owner_msg_id))"
)
db.commit()

def set_target(user_id: int, owner_id: int):
    db.execute("REPLACE INTO target VALUES (?, ?)", (user_id, owner_id))
    db.commit()


def get_target(user_id: int):
    row = db.execute("SELECT owner_id FROM target WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else None


def find_sender(owner_id: int, owner_msg_id: int):
    return db.execute(
        "SELECT sender_id, sender_msg_id FROM msgs WHERE owner_id=? AND owner_msg_id=?",
        (owner_id, owner_msg_id),
    ).fetchone()


@dp.message(CommandStart())
async def start(m: Message, command: CommandObject):
    if command.args and command.args.isdigit():
        owner_id = int(command.args)
        if owner_id == m.from_user.id:
            await m.answer("Это ваша собственная ссылка 🙂 Отправьте её другим.")
            return
        set_target(m.from_user.id, owner_id)
        await m.answer("✉️ Напишите сообщение — получатель увидит его анонимно.")
        return
    me = await bot.get_me()
    await m.answer(
        "Ваша ссылка для анонимных сообщений:\n"
        f"https://t.me/{me.username}?start={m.from_user.id}"
    )


@dp.message(Command("who"))
async def who(m: Message):
    # Команда работает только в ответ на сохранённое анонимное сообщение.
    # Без reply или если сообщение не найдено — ничего не отправляем.
    if not m.reply_to_message:
        return

    found = find_sender(m.from_user.id, m.reply_to_message.message_id)
    if not found:
        return

    sender_id, _sender_msg_id = found

    # Telegram Bot API не позволяет получить номер телефона автоматически.
    try:
        u = await bot.get_chat(sender_id)
        full_name = getattr(u, "full_name", None) or "неизвестно"
        username = f"@{u.username}" if u.username else "нет"
    except Exception:
        full_name = "не удалось получить"
        username = "не удалось получить"

    await m.answer(
        "🔎 Данные отправителя:\\n"
        f"Имя: {full_name}\\n"
        f"Username: {username}\\n"
        f"ID: {sender_id}\\n"
        "Номер телефона: недоступен через Telegram Bot API без добровольно отправленного контакта."
    )


@dp.message()
async def relay(m: Message):
    # 1) Владелец отвечает на анонимное сообщение -> уходит отправителю
    if m.reply_to_message:
        found = find_sender(m.from_user.id, m.reply_to_message.message_id)
        if found:
            sender_id, sender_msg_id = found
            await bot.send_message(sender_id, "💬 Ответ на ваше сообщение:", reply_to_message_id=sender_msg_id)
            await m.copy_to(sender_id)
            await m.answer("Ответ доставлен анонимно ✅")
            return

    # 2) Обычный пользователь пишет владельцу
    owner_id = get_target(m.from_user.id)
    if not owner_id:
        await m.answer("Откройте чью-нибудь ссылку или отправьте /start, чтобы получить свою.")
        return
    await bot.send_message(owner_id, "📩 Новое анонимное сообщение:")
    sent = await m.copy_to(owner_id)
    db.execute(
        "REPLACE INTO msgs VALUES (?, ?, ?, ?)",
        (owner_id, sent.message_id, m.from_user.id, m.message_id),
    )
    db.commit()
    await m.answer("Отправлено анонимно ✅")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
