import calendar
import aiosqlite
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DB_PATH


async def build_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    """Построение календаря для выбора даты"""
    kb = []

    # Заголовок
    month_name = calendar.month_name[month]
    header = [InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore")]
    kb.append(header)

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb.append([InlineKeyboardButton(text=d, callback_data="ignore") for d in week_days])

    # Соберём инфу о доступных слотах
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT date(dt) as d, COUNT(*) 
            FROM timeslots 
            WHERE is_booked=0 AND strftime('%Y-%m', dt)=?
            GROUP BY d
            """,
            (f"{year:04d}-{month:02d}",)
        )
        available_days = {row[0]: row[1] for row in await cur.fetchall()}

    # Календарная сетка
    month_days = calendar.monthcalendar(year, month)
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                day_str = f"{year:04d}-{month:02d}-{day:02d}"
                # если есть доступные слоты
                if day_str in available_days:
                    txt = f"[{day}]"
                else:
                    txt = str(day)
                row.append(InlineKeyboardButton(
                    text=txt,
                    callback_data=f"pick_date:{day_str}"
                ))
        kb.append(row)

    # Навигация
    kb.append([
        InlineKeyboardButton(text="⬅️", callback_data=f"prev_month:{year}-{month}"),
        InlineKeyboardButton(text="➡️", callback_data=f"next_month:{year}-{month}")
    ])

    kb.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")])

    return InlineKeyboardMarkup(inline_keyboard=kb)