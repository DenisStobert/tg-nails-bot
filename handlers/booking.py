import logging
import aiosqlite
from datetime import datetime
from typing import Dict, Set
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import DB_PATH, ADMIN_ID
from keyboards.main_menu import main_menu_kb
from keyboards.services import render_services_keyboard
from utils.calendar import build_calendar

router = Router()

# Память для выбора услуг до подтверждения
pending: Dict[int, dict] = {}


@router.message(Command("book"))
@router.message(F.text.startswith("📅"))
async def start_booking(message: Message):
    """Начало процесса записи"""
    # Проверим, есть ли телефон у пользователя
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT phone FROM users WHERE tg_id=?", (message.from_user.id,))
        row = await cur.fetchone()

    if not row or not row[0]:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True
        )
        return await message.answer("Для записи нужен твой номер телефона:", reply_markup=kb)

    # Показываем календарь
    await show_calendar(message)


async def show_calendar(message: Message):
    """Показать календарь для выбора даты"""
    today = datetime.now()
    await message.answer(
        "Выбери дату:",
        reply_markup=await build_calendar(today.year, today.month)
    )


@router.callback_query(F.data.startswith("pick_date:"))
async def pick_date(call: CallbackQuery):
    """Обработка выбора даты"""
    date_str = call.data.split(":")[1]
    date_obj = datetime.fromisoformat(date_str).date()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, dt FROM timeslots WHERE is_booked=0 AND date(dt)=? ORDER BY dt",
            (date_obj.isoformat(),)
        )
        rows = await cur.fetchall()

    if not rows:
        await call.answer("На этот день нет свободных окон 😔", show_alert=True)
        return

    kb_rows = []
    for sid, dt in rows:
        t = datetime.fromisoformat(dt).strftime("%H:%M")
        kb_rows.append([
            InlineKeyboardButton(
                text=t,
                callback_data=f"slot:{sid}"
            )
        ])

    kb_rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_calendar")
    ])

    await call.message.edit_text(
        f"📅 {date_obj.strftime('%d.%m.%Y')}\nВыбери время:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("slot:"))
async def choose_slot(call: CallbackQuery):
    """Выбор временного слота"""
    slot_id = int(call.data.split(":")[1])
    user_id = call.from_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT dt FROM timeslots WHERE id=?", (slot_id,))
        row = await cur.fetchone()
        slot_dt = datetime.fromisoformat(row[0])
    
    pending[user_id] = {
        "slot_id": slot_id,
        "services": set(),
        "date": slot_dt.date().isoformat()
    }

    # Показать услуги
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, name, price FROM services ORDER BY id")
        services = await cur.fetchall()

    kb_rows = []
    for sid, name, price in services:
        kb_rows.append([
            InlineKeyboardButton(
                text=f"▫️ {name} ({price} ₽)",
                callback_data=f"toggle:{sid}"
            )
        ])
    kb_rows.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="done"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    
    await call.message.edit_text(
        "Отметь нужные услуги (нажимай по пунктам), затем жми «Готово».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_service(call: CallbackQuery):
    """Переключение выбора услуги"""
    user_id = call.from_user.id
    svc_id = int(call.data.split(":")[1])

    state = pending.get(user_id)
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return

    selected: Set[int] = state["services"]
    if svc_id in selected:
        selected.remove(svc_id)
    else:
        selected.add(svc_id)

    text, kb, _ = await render_services_keyboard(selected)
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "done")
async def finalize_services(call: CallbackQuery):
    """Финализация выбора услуг и показ подтверждения"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return

    selected: Set[int] = state["services"]
    if not selected:
        await call.answer("Выбери хотя бы одну услугу 🙏", show_alert=True)
        return

    # Посчитать сумму
    async with aiosqlite.connect(DB_PATH) as db:
        q_marks = ",".join("?" * len(selected))
        cur = await db.execute(f"SELECT name, price FROM services WHERE id IN ({q_marks})", tuple(selected))
        rows = await cur.fetchall()

    total = sum(price for _, price in rows)
    services_list = "\n".join([f"• {name}" for name, _ in rows])

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_services"),
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    ]])
    
    await call.message.edit_text(
        f"*Проверка заказа:*\n{services_list}\n\nИтого: *{total} ₽*\nПодтверждаешь?",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "confirm")
async def confirm_booking(call: CallbackQuery):
    """Подтверждение и создание записи"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return

    slot_id = state["slot_id"]
    selected: Set[int] = state["services"]

    async with aiosqlite.connect(DB_PATH) as db:
        # Сумма
        q_marks = ",".join("?" * len(selected))
        cur = await db.execute(f"SELECT price FROM services WHERE id IN ({q_marks})", tuple(selected))
        total = sum(r[0] for r in await cur.fetchall())

        # Получить/создать пользователя
        cur = await db.execute("SELECT id FROM users WHERE tg_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            uid = row[0]
        else:
            await db.execute("INSERT INTO users(tg_id) VALUES (?)", (user_id,))
            await db.commit()
            cur = await db.execute("SELECT id FROM users WHERE tg_id=?", (user_id,))
            uid = (await cur.fetchone())[0]

        # Проверить свободность слота
        cur = await db.execute("SELECT dt, is_booked FROM timeslots WHERE id=?", (slot_id,))
        slot = await cur.fetchone()
        if not slot:
            await call.answer("Слот не найден 😕", show_alert=True)
            return
        dt_str, is_booked = slot
        if is_booked:
            await call.answer("Увы, слот уже занят. Выбери другой.", show_alert=True)
            return

        # Занять слот и создать бронь
        await db.execute("UPDATE timeslots SET is_booked=1, booked_by_user_id=? WHERE id=?", (uid, slot_id))
        await db.execute(
            "INSERT INTO bookings(user_id, timeslot_id, total_price, created_at) VALUES (?, ?, ?, ?)",
            (uid, slot_id, total, datetime.utcnow().isoformat())
        )
        await db.commit()

    pending.pop(user_id, None)

    when = datetime.fromisoformat(dt_str).strftime("%d.%m %H:%M")
    await call.message.edit_text(
        f"Готово! Ты записан(а) на *{when}*.\nСумма: *{total} ₽*",
        parse_mode="Markdown"
    )

    # Уведомить мастера
    try:
        bot = call.bot
        await bot.send_message(
            ADMIN_ID,
            f"Новая запись: {call.from_user.full_name} на {when}, сумма {total} ₽"
        )
    except Exception as e:
        logging.warning(f"Cannot notify admin: {e}")

    await call.answer()


@router.message(Command("my"))
@router.message(F.text.startswith("👀"))
async def my_bookings(message: Message):
    """Показать мои записи"""
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM users WHERE tg_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return await message.answer("Пока записей нет.")

        uid = row[0]
        cur = await db.execute("""
            SELECT b.id, t.dt, b.total_price
            FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE b.user_id=?
            ORDER BY t.dt DESC
        """, (uid,))
        rows = await cur.fetchall()

    if not rows:
        return await message.answer("Пока записей нет.")

    for bid, dt_str, total in rows:
        dt = datetime.fromisoformat(dt_str).strftime("%d.%m %H:%M")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_booking:{bid}")]
        ])
        await message.answer(
            f"*Запись:* {dt}\n💰 {total} ₽",
            parse_mode="Markdown",
            reply_markup=kb
        )


@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking(call: CallbackQuery):
    """Отмена записи"""
    booking_id = int(call.data.split(":")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT timeslot_id FROM bookings WHERE id=?", (booking_id,))
        row = await cur.fetchone()
        if not row:
            return await call.answer("Запись не найдена ❌", show_alert=True)
        slot_id = row[0]

        await db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        await db.execute(
            "UPDATE timeslots SET is_booked=0, booked_by_user_id=NULL WHERE id=?",
            (slot_id,)
        )
        await db.commit()

    await call.message.edit_text("✅ Запись успешно отменена!")
    await call.answer()

    # Уведомить мастера
    try:
        bot = call.bot
        await bot.send_message(
            ADMIN_ID,
            f"Пользователь {call.from_user.full_name} отменил запись #{booking_id}"
        )
    except Exception as e:
        logging.warning(f"Cannot notify admin: {e}")


@router.callback_query(F.data.startswith("reschedule:"))
async def reschedule_booking(call: CallbackQuery):
    """Перенос записи"""
    booking_id = int(call.data.split(":")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT b.user_id, b.timeslot_id
            FROM bookings b
            WHERE b.id = ?
        """, (booking_id,))
        row = await cur.fetchone()

        if not row:
            return await call.answer("Запись не найдена ❌", show_alert=True)

        user_id, old_slot_id = row

        cur = await db.execute("""
            SELECT id, dt FROM timeslots
            WHERE is_booked = 0
            ORDER BY dt ASC
            LIMIT 10
        """)
        slots = await cur.fetchall()

    if not slots:
        return await call.message.edit_text("😕 Нет свободных слотов для переноса. Попробуй позже.")

    kb_rows = []
    for sid, dt_str in slots:
        dt = datetime.fromisoformat(dt_str)
        kb_rows.append([
            InlineKeyboardButton(
                text=dt.strftime("%d.%m %H:%M"),
                callback_data=f"confirm_reschedule:{booking_id}:{sid}"
            )
        ])
    kb_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reschedule")])

    await call.message.edit_text(
        "Выбери новый слот для переноса:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_reschedule:"))
async def confirm_reschedule(call: CallbackQuery):
    """Подтверждение переноса"""
    _, booking_id_str, new_slot_id_str = call.data.split(":")
    booking_id = int(booking_id_str)
    new_slot_id = int(new_slot_id_str)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT timeslot_id FROM bookings WHERE id=?", (booking_id,))
        row = await cur.fetchone()
        if not row:
            return await call.answer("Бронь не найдена ❌", show_alert=True)
        old_slot_id = row[0]

        cur = await db.execute("SELECT dt, is_booked FROM timeslots WHERE id=?", (new_slot_id,))
        slot = await cur.fetchone()
        if not slot or slot[1]:
            return await call.answer("Выбранный слот уже занят 😕", show_alert=True)

        await db.execute("UPDATE timeslots SET is_booked=0, booked_by_user_id=NULL WHERE id=?", (old_slot_id,))
        await db.execute(
            "UPDATE timeslots SET is_booked=1, booked_by_user_id=(SELECT user_id FROM bookings WHERE id=?) WHERE id=?",
            (booking_id, new_slot_id)
        )
        await db.execute("UPDATE bookings SET timeslot_id=?, reminded12=0 WHERE id=?", (new_slot_id, booking_id))
        await db.commit()

        cur = await db.execute("SELECT dt FROM timeslots WHERE id=?", (new_slot_id,))
        new_dt = datetime.fromisoformat((await cur.fetchone())[0])

    await call.message.edit_text(f"✅ Запись успешно перенесена на {new_dt.strftime('%d.%m %H:%M')}!")

    try:
        bot = call.bot
        await bot.send_message(
            ADMIN_ID,
            f"Пользователь {call.from_user.full_name} перенёс запись #{booking_id} на {new_dt.strftime('%d.%m %H:%M')}"
        )
    except Exception as e:
        logging.warning(f"Не удалось уведомить мастера: {e}")

    await call.answer()


@router.callback_query(F.data == "cancel_reschedule")
async def cancel_reschedule(call: CallbackQuery):
    """Отмена переноса"""
    await call.message.edit_text("Перенос отменён ✅")
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cancel_flow(call: CallbackQuery):
    """Отмена процесса бронирования"""
    pending.pop(call.from_user.id, None)
    await call.message.edit_text("Запись отменена. Можешь начать заново: /book")
    await call.answer()


@router.callback_query(F.data == "back_to_calendar")
async def back_to_calendar(call: CallbackQuery):
    """Возврат к календарю"""
    today = datetime.now()
    await call.message.edit_text(
        "Выбери дату:",
        reply_markup=await build_calendar(today.year, today.month)
    )
    await call.answer()


@router.callback_query(F.data == "back_to_slots")
async def back_to_slots(call: CallbackQuery):
    """Возврат к выбору слотов"""
    state = pending.get(call.from_user.id)
    if not state or "date" not in state:
        return await call.answer("Начни сначала: /book", show_alert=True)

    date_str = state["date"]

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, dt FROM timeslots WHERE is_booked=0 AND date(dt)=? ORDER BY dt",
            (date_str,)
        )
        rows = await cur.fetchall()

    if not rows:
        await call.message.edit_text("На этот день нет свободных окон 😔")
        return

    kb_rows = []
    for sid, dt in rows:
        t = datetime.fromisoformat(dt).strftime("%H:%M")
        kb_rows.append([InlineKeyboardButton(text=t, callback_data=f"slot:{sid}")])

    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_calendar")])

    await call.message.edit_text(
        f"📅 {date_str}\nВыбери время:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await call.answer()


@router.callback_query(F.data == "back_to_services")
async def back_to_services(call: CallbackQuery):
    """Возврат к выбору услуг"""
    state = pending.get(call.from_user.id)
    if not state:
        return await call.answer("Начни сначала: /book", show_alert=True)

    selected: Set[int] = state["services"]
    text, kb, _ = await render_services_keyboard(selected)
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    """Возврат в главное меню"""
    await call.message.delete()
    await call.message.answer(
        "Главное меню:",
        reply_markup=main_menu_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("prev_month:"))
async def prev_month(call: CallbackQuery):
    """Предыдущий месяц в календаре"""
    year, month = map(int, call.data.split(":")[1].split("-"))
    if month == 1:
        year -= 1
        month = 12
    else:
        month -= 1

    await call.message.edit_text(
        "Выбери дату:",
        reply_markup=await build_calendar(year, month)
    )
    await call.answer()


@router.callback_query(F.data.startswith("next_month:"))
async def next_month(call: CallbackQuery):
    """Следующий месяц в календаре"""
    year, month = map(int, call.data.split(":")[1].split("-"))
    if month == 12:
        year += 1
        month = 1
    else:
        month += 1

    await call.message.edit_text(
        "Выбери дату:",
        reply_markup=await build_calendar(year, month)
    )
    await call.answer()


@router.callback_query(F.data == "ignore")
async def ignore_callback(call: CallbackQuery):
    """Игнорирование callback (для заголовков и т.д.)"""
    await call.answer()