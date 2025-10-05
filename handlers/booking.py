import logging
import aiosqlite
from datetime import datetime, timedelta
from typing import Dict, Set, List
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
    """Начало процесса записи - СНАЧАЛА выбор услуг"""
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

    # Инициализируем состояние
    pending[message.from_user.id] = {"services": set()}
    
    # Показываем выбор услуг
    text, kb, _, _ = await render_services_keyboard(set())
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


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

    text, kb, _, _ = await render_services_keyboard(selected)
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "services_done")
async def finalize_services(call: CallbackQuery):
    """Завершение выбора услуг и переход к выбору времени"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return

    selected: Set[int] = state["services"]
    if not selected:
        await call.answer("Выбери хотя бы одну услугу 🙏", show_alert=True)
        return

    # Получаем информацию об услугах
    async with aiosqlite.connect(DB_PATH) as db:
        q_marks = ",".join("?" * len(selected))
        cur = await db.execute(
            f"SELECT name, price, duration_minutes FROM services WHERE id IN ({q_marks})",
            tuple(selected)
        )
        services_data = await cur.fetchall()

    # Считаем общее время и стоимость
    total_price = sum(price for _, price, _ in services_data)
    total_minutes = sum((duration or 60) for _, _, duration in services_data)
    
    # Сохраняем в состояние
    state["total_price"] = total_price
    state["total_minutes"] = total_minutes
    state["services_data"] = services_data
    
    # Показываем календарь
    today = datetime.now()
    
    hours = total_minutes // 60
    mins = total_minutes % 60
    time_str = f"{hours}ч {mins}мин" if hours else f"{mins}мин"
    
    await call.message.edit_text(
        f"✅ Услуги выбраны!\n\n"
        f"💰 Сумма: *{total_price} ₽*\n"
        f"⏱ Время: *{time_str}*\n\n"
        f"Теперь выбери удобную дату:",
        parse_mode="Markdown",
        reply_markup=await build_calendar(today.year, today.month)
    )
    await call.answer()


async def find_available_slots_for_duration(date_obj, duration_minutes: int) -> List[tuple]:
    """Найти все слоты на дату, где есть достаточно свободного времени подряд
    
    Returns:
        List of (start_slot_id, start_dt, slot_ids_needed)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем ВСЕ слоты на эту дату отсортированные по времени
        cur = await db.execute(
            """SELECT id, dt, is_booked FROM timeslots 
               WHERE date(dt)=? 
               ORDER BY dt""",
            (date_obj.isoformat(),)
        )
        all_slots = await cur.fetchall()
    
    if not all_slots:
        return []
    
    # Сколько слотов подряд нужно (слоты по 60 минут)
    slots_needed = (duration_minutes + 59) // 60  # округление вверх
    
    available_sequences = []
    
    # Проходим по каждому свободному слоту
    for i, (slot_id, dt_str, is_booked) in enumerate(all_slots):
        # Если слот занят - пропускаем
        if is_booked:
            continue
        
        # Проверяем что после этого слота есть достаточно слотов (или времени)
        # Например: если нужно 2 часа, а это последний слот дня - нельзя
        remaining_slots = len(all_slots) - i
        if remaining_slots < slots_needed:
            # Недостаточно слотов до конца дня
            continue
        
        # Начинаем с этого слота
        start_dt = datetime.fromisoformat(dt_str)
        sequence = [slot_id]
        current_dt = start_dt
        
        # Пытаемся найти достаточно последовательных СВОБОДНЫХ слотов
        for j in range(i + 1, len(all_slots)):
            next_slot_id, next_dt_str, next_is_booked = all_slots[j]
            next_dt = datetime.fromisoformat(next_dt_str)
            
            # Проверяем что слот ровно через 1 час
            expected_dt = current_dt + timedelta(hours=1)
            
            if next_dt != expected_dt:
                # Есть пропуск в слотах - не можем использовать этот старт
                break
            
            if next_is_booked:
                # Следующий слот занят - не можем использовать этот старт
                break
            
            # Слот подходит
            sequence.append(next_slot_id)
            current_dt = next_dt
            
            # Если собрали достаточно слотов - всё, нашли подходящее окно
            if len(sequence) >= slots_needed:
                break
        
        # Проверяем что собрали достаточно слотов
        if len(sequence) >= slots_needed:
            # Берём только нужное количество слотов
            final_sequence = sequence[:slots_needed]
            available_sequences.append((slot_id, dt_str, final_sequence))
    
    return available_sequences


@router.callback_query(F.data.startswith("pick_date:"))
async def pick_date(call: CallbackQuery):
    """Обработка выбора даты - показываем только подходящие слоты"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    
    if not state or "total_minutes" not in state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return
    
    date_str = call.data.split(":")[1]
    date_obj = datetime.fromisoformat(date_str).date()
    
    # Находим подходящие слоты
    duration_minutes = state["total_minutes"]
    available_slots = await find_available_slots_for_duration(date_obj, duration_minutes)
    
    if not available_slots:
        await call.answer(
            f"😔 На этот день нет окон с достаточным временем ({duration_minutes}мин).\n"
            f"Выбери другой день.",
            show_alert=True
        )
        return
    
    # Формируем кнопки
    kb_rows = []
    for start_slot_id, start_dt, slot_ids in available_slots:
        dt = datetime.fromisoformat(start_dt)
        
        # Показываем диапазон времени
        end_dt = dt + timedelta(minutes=duration_minutes)
        time_range = f"{dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
        
        kb_rows.append([
            InlineKeyboardButton(
                text=time_range,
                callback_data=f"slotrange:{start_slot_id}:{','.join(map(str, slot_ids))}"
            )
        ])
    
    kb_rows.append([
        InlineKeyboardButton(text="⬅️ Назад к календарю", callback_data="back_to_calendar"),
        InlineKeyboardButton(text="⬅️ Изменить услуги", callback_data="back_to_services_choice")
    ])
    
    await call.message.edit_text(
        f"📅 *{date_obj.strftime('%d.%m.%Y')}*\n"
        f"⏱ Длительность: *{duration_minutes}мин*\n\n"
        f"Доступные окна:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("slotrange:"))
async def confirm_slot_range(call: CallbackQuery):
    """Подтверждение выбора диапазона слотов"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return
    
    # Парсим данные
    parts = call.data.split(":", 2)
    start_slot_id = int(parts[1])
    slot_ids = list(map(int, parts[2].split(",")))
    
    # Сохраняем в состояние
    state["start_slot_id"] = start_slot_id
    state["slot_ids"] = slot_ids
    
    # Получаем время для отображения
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT dt FROM timeslots WHERE id=?", (start_slot_id,))
        row = await cur.fetchone()
        start_dt = datetime.fromisoformat(row[0])
    
    end_dt = start_dt + timedelta(minutes=state["total_minutes"])
    
    # Формируем список услуг
    services_list = "\n".join([f"• {name}" for name, _, _ in state["services_data"]])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pick_date:{start_dt.date().isoformat()}"),
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    ]])
    
    await call.message.edit_text(
        f"*Проверь запись:*\n\n"
        f"📅 {start_dt.strftime('%d.%m.%Y')}\n"
        f"⏰ {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}\n\n"
        f"*Услуги:*\n{services_list}\n\n"
        f"💰 Итого: *{state['total_price']} ₽*\n\n"
        f"Всё верно?",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "confirm_booking")
async def confirm_booking(call: CallbackQuery):
    """Подтверждение и создание записи"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    
    if not state or "slot_ids" not in state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return

    slot_ids = state["slot_ids"]
    total_price = state["total_price"]
    
    async with aiosqlite.connect(DB_PATH) as db:
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

        # 🔒 АТОМАРНАЯ ПРОВЕРКА И БРОНИРОВАНИЕ ВСЕХ СЛОТОВ
        try:
            await db.execute("BEGIN IMMEDIATE")
            
            # Проверяем все слоты ЕЩЁ РАЗ
            placeholders = ",".join("?" * len(slot_ids))
            cur = await db.execute(
                f"SELECT id, dt, is_booked FROM timeslots WHERE id IN ({placeholders})",
                slot_ids
            )
            slots = await cur.fetchall()
            
            if len(slots) != len(slot_ids):
                await db.rollback()
                await call.answer("Некоторые слоты не найдены 😕", show_alert=True)
                return
            
            # Проверяем что ВСЕ слоты свободны
            for slot_id, dt_str, is_booked in slots:
                if is_booked:
                    await db.rollback()
                    await call.answer(
                        "😔 К сожалению, один из слотов уже занят.\n"
                        "Попробуй выбрать другое время.",
                        show_alert=True
                    )
                    return
            
            # Всё ок, занимаем ВСЕ слоты атомарно
            for slot_id in slot_ids:
                await db.execute(
                    "UPDATE timeslots SET is_booked=1, booked_by_user_id=? WHERE id=?",
                    (uid, slot_id)
                )
            
            # Создаём бронь (привязываем к первому слоту)
            start_slot_id = slot_ids[0]
            await db.execute(
                "INSERT INTO bookings(user_id, timeslot_id, total_price, created_at) VALUES (?, ?, ?, ?)",
                (uid, start_slot_id, total_price, datetime.utcnow().isoformat())
            )
            
            await db.commit()
            
            # Получаем время для сообщения
            first_dt_str = slots[0][1]
            
        except Exception as e:
            await db.rollback()
            logging.error(f"Booking error: {e}")
            await call.answer("❌ Ошибка при бронировании. Попробуй ещё раз.", show_alert=True)
            return

    pending.pop(user_id, None)

    start_dt = datetime.fromisoformat(first_dt_str)
    end_dt = start_dt + timedelta(minutes=state["total_minutes"])
    when = f"{start_dt.strftime('%d.%m %H:%M')} - {end_dt.strftime('%H:%M')}"
    
    await call.message.edit_text(
        f"✅ *Отлично!*\n\n"
        f"Ты записан(а) на:\n"
        f"📅 {start_dt.strftime('%d.%m.%Y')}\n"
        f"⏰ {when}\n"
        f"💰 {total_price} ₽\n\n"
        f"Жду тебя! 💅",
        parse_mode="Markdown"
    )

    # Уведомить мастера
    try:
        services_list = "\n".join([f"• {name}" for name, _, _ in state["services_data"]])
        await call.bot.send_message(
            ADMIN_ID,
            f"🆕 *Новая запись!*\n\n"
            f"👤 {call.from_user.full_name}\n"
            f"📅 {start_dt.strftime('%d.%m.%Y')}\n"
            f"⏰ {when}\n\n"
            f"Услуги:\n{services_list}\n\n"
            f"💰 {total_price} ₽",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"Cannot notify admin: {e}")

    await call.answer("✅ Запись создана!")


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
    """Отмена записи - освобождаем ВСЕ связанные слоты"""
    booking_id = int(call.data.split(":")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN IMMEDIATE")
            
            # Находим основной слот
            cur = await db.execute("SELECT timeslot_id FROM bookings WHERE id=?", (booking_id,))
            row = await cur.fetchone()
            if not row:
                await db.rollback()
                return await call.answer("Запись не найдена ❌", show_alert=True)
            main_slot_id = row[0]
            
            # Находим все слоты этого пользователя, связанные с этой записью
            # (все подряд идущие слоты от начала записи)
            cur = await db.execute("""
                SELECT u.id FROM users WHERE tg_id=?
            """, (call.from_user.id,))
            user_row = await cur.fetchone()
            if not user_row:
                await db.rollback()
                return await call.answer("Пользователь не найден", show_alert=True)
            user_db_id = user_row[0]
            
            # Получаем время основного слота
            cur = await db.execute("SELECT dt FROM timeslots WHERE id=?", (main_slot_id,))
            main_dt_str = (await cur.fetchone())[0]
            main_dt = datetime.fromisoformat(main_dt_str)
            
            # Находим все слоты этого пользователя начиная с этого времени
            cur = await db.execute("""
                SELECT id, dt FROM timeslots 
                WHERE booked_by_user_id=? AND dt >= ?
                ORDER BY dt
            """, (user_db_id, main_dt_str))
            user_slots = await cur.fetchall()
            
            # Освобождаем последовательные слоты
            slots_to_free = [main_slot_id]
            for i, (slot_id, dt_str) in enumerate(user_slots):
                if slot_id == main_slot_id:
                    continue
                dt = datetime.fromisoformat(dt_str)
                expected_dt = main_dt + timedelta(hours=len(slots_to_free))
                if dt == expected_dt:
                    slots_to_free.append(slot_id)
                else:
                    break
            
            # Освобождаем все найденные слоты
            placeholders = ",".join("?" * len(slots_to_free))
            await db.execute(
                f"UPDATE timeslots SET is_booked=0, booked_by_user_id=NULL WHERE id IN ({placeholders})",
                slots_to_free
            )
            
            # Удаляем бронь
            await db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
            
            await db.commit()
            
        except Exception as e:
            await db.rollback()
            logging.error(f"Cancel booking error: {e}")
            return await call.answer("Ошибка отмены", show_alert=True)

    await call.message.edit_text("✅ Запись успешно отменена!")
    await call.answer()

    # Уведомить мастера
    try:
        await call.bot.send_message(
            ADMIN_ID,
            f"❌ Пользователь {call.from_user.full_name} отменил запись #{booking_id}"
        )
    except Exception as e:
        logging.warning(f"Cannot notify admin: {e}")


@router.callback_query(F.data.startswith("reschedule:"))
async def reschedule_booking(call: CallbackQuery):
    """Перенос записи"""
    booking_id = int(call.data.split(":")[1])
    
    await call.message.edit_text(
        "Для переноса записи:\n"
        "1. Отмени текущую запись\n"
        "2. Создай новую запись: /book\n\n"
        "Это гарантирует что новое время подходит для всех твоих услуг 😊"
    )
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
    user_id = call.from_user.id  # ✅ ИСПРАВЛЕНО
    state = pending.get(user_id)
    
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return
    
    today = datetime.now()
    await call.message.edit_text(
        "Выбери дату:",
        reply_markup=await build_calendar(today.year, today.month)
    )
    await call.answer()


@router.callback_query(F.data == "back_to_services_choice")
async def back_to_services_choice(call: CallbackQuery):
    """Возврат к выбору услуг"""
    user_id = call.from_user.id
    state = pending.get(user_id)
    
    if not state:
        await call.answer("Начни сначала: /book", show_alert=True)
        return
    
    selected: Set[int] = state.get("services", set())
    text, kb, _, _ = await render_services_keyboard(selected)
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
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


@router.callback_query(F.data == "back_to_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """Возврат из календаря в главное меню"""
    await callback.message.edit_text(
        "Главное меню 🏠"
    )
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def ignore_callback(call: CallbackQuery):
    """Игнорирование callback (для заголовков и т.д.)"""
    await call.answer()