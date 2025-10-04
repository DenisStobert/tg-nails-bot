import logging
import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from config import DB_PATH
from keyboards.main_menu import main_menu_kb

router = Router()


@router.message(CommandStart())
async def on_start(message: Message):
    """Обработка команды /start"""
    # Регистрация пользователя (если ещё не в БД)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(tg_id, name) VALUES (?, ?)",
            (message.from_user.id, message.from_user.full_name or "")
        )
        await db.commit()

    logging.info(f"User started: tg_id={message.from_user.id}")

    await message.answer(
        "Привет! Я бот для записи к мастеру 💅\nВыбери действие:",
        reply_markup=main_menu_kb()
    )


@router.message(Command("services"))
@router.message(F.text.lower().contains("услу") | F.text.lower().contains("цены"))
async def list_services(message: Message):
    """Показать список услуг и цен"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, name, price FROM services ORDER BY id")
        rows = await cur.fetchall()

    text = "💅 *Услуги и цены:*\n"
    for _, name, price in rows:
        text += f"• {name} — {price} ₽\n"
    await message.answer(text, parse_mode="Markdown")


@router.message(F.contact)
async def on_contact(message: Message):
    """Обработка контакта (номера телефона)"""
    phone = message.contact.phone_number
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET phone=? WHERE tg_id=?", (phone, message.from_user.id))
        await db.commit()
    await message.answer("Спасибо 👍 Телефон сохранён!", reply_markup=main_menu_kb())