import aiosqlite
from typing import Set, Tuple
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DB_PATH


async def render_services_keyboard(selected: Set[int]) -> Tuple[str, InlineKeyboardMarkup, int, int]:
    """Рендер клавиатуры выбора услуг с чекбоксами
    
    Returns:
        text: Текст сообщения
        keyboard: Клавиатура
        total_price: Общая стоимость
        total_minutes: Общее время в минутах
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, name, price, duration_minutes FROM services ORDER BY id")
        services = await cur.fetchall()

    kb_rows = []
    total_price = 0
    total_minutes = 0
    
    for sid, name, price, duration in services:
        checked = sid in selected
        prefix = "☑️" if checked else "▫️"
        
        if checked:
            total_price += price
            total_minutes += (duration or 60)
        
        # Показываем длительность
        duration_str = f"{duration}мин" if duration else "60мин"
        
        kb_rows.append([
            InlineKeyboardButton(
                text=f"{prefix} {name} ({price}₽, {duration_str})",
                callback_data=f"toggle:{sid}"
            )
        ])
    
    kb_rows.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="services_done"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    
    # Форматируем время
    hours = total_minutes // 60
    mins = total_minutes % 60
    time_str = ""
    if hours > 0:
        time_str += f"{hours}ч "
    if mins > 0:
        time_str += f"{mins}мин"
    if not time_str:
        time_str = "0мин"
    
    text = (
        f"*Выбор услуг*\n\n"
        f"💰 Сумма: *{total_price} ₽*\n"
        f"⏱ Время: *{time_str.strip()}*\n\n"
        f"Выбери нужные услуги:"
    )
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows), total_price, total_minutes