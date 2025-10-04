import aiosqlite
from typing import Set, Tuple
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DB_PATH


async def render_services_keyboard(selected: Set[int]) -> Tuple[str, InlineKeyboardMarkup, int]:
    """Рендер клавиатуры выбора услуг с чекбоксами"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, name, price FROM services ORDER BY id")
        services = await cur.fetchall()

    kb_rows = []
    total = 0
    for sid, name, price in services:
        checked = sid in selected
        prefix = "☑️" if checked else "▫️"
        if checked:
            total += price
        kb_rows.append([
            InlineKeyboardButton(
                text=f"{prefix} {name} ({price} ₽)",
                callback_data=f"toggle:{sid}"
            )
        ])
    
    kb_rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_slots"),
        InlineKeyboardButton(text="✅ Готово", callback_data="done"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    
    text = f"Выбор услуг. Текущая сумма: *{total} ₽*"
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows), total