import aiosqlite
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import DB_PATH, ADMIN_ID

router = Router()


@router.message(Command("admin"))
async def admin_menu(message: Message):
    """Меню администратора"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    await message.answer(
        "🔧 *Меню мастера:*\n\n"
        "*Управление слотами:*\n"
        "• /addslot YYYY-MM-DD HH:MM — добавить окно\n"
        "• /generate\\_slots — генератор расписания\n"
        "• /clear\\_old\\_slots — удалить старые слоты\n"
        "• /slots — список окон\n"
        "• /del\\_slot <id> — удалить окно\n"
        "• /free\\_slot <id> — освободить окно\n\n"
        "*Управление услугами:*\n"
        "• /addservice <название> <цена> <минуты> — добавить\n"
        "• /delservice <название> — удалить\n"
        "• /setprice <название> <цена> — цена\n"
        "• /set\\_duration <название> <минуты> — время\n\n"
        "*Записи и статистика:*\n"
        "• /bookings — все записи\n"
        "• /export — экспорт в CSV\n"
        "• /stats — статистика\n\n"
        "*Информация:*\n"
        "• /set\\_contacts — настроить контакты",
        parse_mode="Markdown"
    )


@router.message(Command("addslot"))
async def add_slot(message: Message):
    """Добавить временной слот"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split()
    if len(parts) < 3:
        return await message.answer("Формат: /addslot 2025-10-10 14:00")

    dt_str = f"{parts[1]} {parts[2]}"
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return await message.answer("Дата/время не распознаны. Пример: 2025-10-10 14:00")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO timeslots(dt) VALUES (?)", (dt.isoformat(),))
        await db.commit()

    await message.answer(f"✅ Окно добавлено: {dt.strftime('%d.%m %H:%M')}")


@router.message(Command("generate_slots"))
async def generate_slots_start(message: Message):
    """Начало генерации слотов"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 На одну неделю", callback_data="gen_week")],
        [InlineKeyboardButton(text="📅 На две недели", callback_data="gen_2weeks")],
        [InlineKeyboardButton(text="📅 На месяц", callback_data="gen_month")],
        [InlineKeyboardButton(text="⚙️ Настроить свой период", callback_data="gen_custom")],
    ])
    
    await message.answer(
        "🕐 *Генератор расписания*\n\n"
        "Выбери период для создания слотов:",
        parse_mode="Markdown",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("gen_"))
async def generate_slots_period(call: CallbackQuery):
    """Выбор периода генерации"""
    period = call.data.split("_")[1]
    
    if period == "custom":
        await call.message.edit_text(
            "⚙️ Используй команду:\n"
            "/make\\_slots <дней> <часы>\n\n"
            "Пример:\n"
            "`/make_slots 7 10:00,12:00,14:00,16:00,18:00`\n\n"
            "Это создаст слоты на 7 дней с указанными часами",
            parse_mode="Markdown"
        )
        await call.answer()
        return
    
    # Определяем количество дней
    days = {"week": 7, "2weeks": 14, "month": 30}[period]
    
    # Показываем выбор времени
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕐 9:00 - 18:00 (каждый час)", callback_data=f"gentime_{days}_work")],
        [InlineKeyboardButton(text="🕐 10:00 - 20:00 (каждые 2 часа)", callback_data=f"gentime_{days}_long")],
        [InlineKeyboardButton(text="⚙️ Свои часы", callback_data=f"gentime_{days}_custom")],
    ])
    
    await call.message.edit_text(
        f"📅 Период: *{days} дней*\n\n"
        "Выбери рабочие часы:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data.startswith("gentime_"))
async def generate_slots_time(call: CallbackQuery):
    """Генерация слотов"""
    parts = call.data.split("_")
    days = int(parts[1])
    time_type = parts[2]
    
    if time_type == "custom":
        await call.message.edit_text(
            "⚙️ Используй команду:\n"
            f"`/make_slots {days} 10:00,12:00,14:00,16:00,18:00`\n\n"
            "Укажи свои часы через запятую",
            parse_mode="Markdown"
        )
        await call.answer()
        return
    
    # Определяем часы
    if time_type == "work":
        hours = list(range(9, 19))  # 9:00 - 18:00
    else:  # long
        hours = list(range(10, 21, 2))  # 10:00 - 20:00 каждые 2 часа
    
    # Генерируем слоты
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    created_count = 0
    
    async with aiosqlite.connect(DB_PATH) as db:
        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            
            # Пропускаем выходные (опционально)
            # if current_date.weekday() >= 5:  # 5=суббота, 6=воскресенье
            #     continue
            
            for hour in hours:
                slot_time = current_date.replace(hour=hour, minute=0)
                
                # Проверяем, не существует ли уже такой слот
                cur = await db.execute(
                    "SELECT id FROM timeslots WHERE dt=?",
                    (slot_time.isoformat(),)
                )
                if await cur.fetchone():
                    continue
                
                await db.execute(
                    "INSERT INTO timeslots(dt) VALUES (?)",
                    (slot_time.isoformat(),)
                )
                created_count += 1
        
        await db.commit()
    
    await call.message.edit_text(
        f"✅ *Готово!*\n\n"
        f"Создано слотов: *{created_count}*\n"
        f"Период: {days} дней\n"
        f"Рабочие часы: {', '.join([f'{h}:00' for h in hours])}",
        parse_mode="Markdown"
    )
    await call.answer()


@router.message(Command("make_slots"))
async def make_slots_custom(message: Message):
    """Создание слотов с кастомными параметрами"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer(
            "Формат: /make\\_slots <дней> <часы>\n"
            "Пример: `/make_slots 7 10:00,12:00,14:00,16:00`",
            parse_mode="Markdown"
        )
    
    try:
        days = int(parts[1])
        hours_str = parts[2].split(",")
        hours = []
        
        for h in hours_str:
            h = h.strip()
            hour, minute = map(int, h.split(":"))
            hours.append((hour, minute))
    except Exception:
        return await message.answer("❌ Ошибка формата. Проверь команду.")
    
    # Генерируем слоты
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    created_count = 0
    
    async with aiosqlite.connect(DB_PATH) as db:
        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            
            for hour, minute in hours:
                slot_time = current_date.replace(hour=hour, minute=minute)
                
                cur = await db.execute(
                    "SELECT id FROM timeslots WHERE dt=?",
                    (slot_time.isoformat(),)
                )
                if await cur.fetchone():
                    continue
                
                await db.execute(
                    "INSERT INTO timeslots(dt) VALUES (?)",
                    (slot_time.isoformat(),)
                )
                created_count += 1
        
        await db.commit()
    
    await message.answer(
        f"✅ *Готово!*\n\n"
        f"Создано слотов: *{created_count}*\n"
        f"Период: {days} дней",
        parse_mode="Markdown"
    )


@router.message(Command("slots"))
async def list_slots(message: Message):
    """Список всех слотов"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, dt, is_booked FROM timeslots ORDER BY dt LIMIT 30"
        )
        rows = await cur.fetchall()

    if not rows:
        return await message.answer("Окон пока нет.")

    text = "*Окна (первые 30):*\n"
    for sid, dt_str, is_booked in rows:
        mark = "🔴 занято" if is_booked else "🟢 свободно"
        text += f"• #{sid} {datetime.fromisoformat(dt_str).strftime('%d.%m %H:%M')} — {mark}\n"
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("del_slot"))
async def delete_slot(message: Message):
    """Удалить слот"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.answer("Используй: /del_slot <id>")

    slot_id = parts[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM timeslots WHERE id=?", (slot_id,))
        await db.commit()
    await message.answer(f"✅ Окно #{slot_id} удалено")


@router.message(Command("free_slot"))
async def free_slot(message: Message):
    """Освободить занятый слот"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.answer("Используй: /free_slot <id>")

    slot_id = parts[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE timeslots SET is_booked=0, booked_by_user_id=NULL WHERE id=?",
            (slot_id,)
        )
        await db.commit()
    await message.answer(f"✅ Окно #{slot_id} теперь свободно")


@router.message(Command("setprice"))
async def set_price(message: Message):
    """Изменить цену услуги"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Используй: /setprice <название> <цена>")

    name = parts[1]
    try:
        price = int(parts[2])
    except ValueError:
        return await message.answer("Цена должна быть числом")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE services SET price=? WHERE LOWER(name)=LOWER(?)",
            (price, name)
        )
        await db.commit()

        if cur.rowcount == 0:
            return await message.answer(f"Услуга '{name}' не найдена ❌")

    await message.answer(f"✅ Цена для «{name}» обновлена: {price} ₽")


@router.message(Command("bookings"))
async def list_bookings(message: Message):
    """Список всех записей"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT b.id, t.dt, u.name, u.phone, b.total_price
            FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            JOIN users u ON u.id = b.user_id
            ORDER BY t.dt DESC
            LIMIT 20
        """)
        rows = await cur.fetchall()

    if not rows:
        return await message.answer("Пока записей нет.")

    text = "*Последние записи:*\n\n"
    for bid, dt_str, name, phone, price in rows:
        dt = datetime.fromisoformat(dt_str).strftime("%d.%m %H:%M")
        phone_str = f" | {phone}" if phone else ""
        text += f"• {dt} — {name}{phone_str}\n  💰 {price} ₽ (#{bid})\n\n"

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("addservice"))
async def add_service(message: Message):
    """Добавить новую услугу"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Используй: /addservice <название> <цена>")

    name = parts[1]
    try:
        price = int(parts[2])
    except ValueError:
        return await message.answer("Цена должна быть числом")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM services WHERE LOWER(name)=LOWER(?)", (name,))
        row = await cur.fetchone()
        if row:
            return await message.answer(f"Услуга '{name}' уже существует ❌")

        await db.execute("INSERT INTO services(name, price) VALUES (?, ?)", (name, price))
        await db.commit()

    await message.answer(f"✅ Услуга '{name}' добавлена. Цена: {price} ₽")


@router.message(Command("delservice"))
async def delete_service(message: Message):
    """Удалить услугу"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Используй: /delservice <название>")

    name = parts[1]

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM services WHERE LOWER(name)=LOWER(?)", (name,))
        await db.commit()

        if cur.rowcount == 0:
            return await message.answer(f"Услуга '{name}' не найдена ❌")

    await message.answer(f"✅ Услуга '{name}' удалена")


@router.message(Command("stats"))
async def show_statistics(message: Message):
    """Показать статистику"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="stats_general")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="stats_finance")],
        [InlineKeyboardButton(text="🔥 Популярные услуги", callback_data="stats_services")],
        [InlineKeyboardButton(text="📅 По дням недели", callback_data="stats_weekdays")],
        [InlineKeyboardButton(text="👥 Клиенты", callback_data="stats_clients")],
    ])
    
    await message.answer(
        "📊 *Статистика и аналитика*\n\n"
        "Выбери раздел:",
        parse_mode="Markdown",
        reply_markup=kb
    )


@router.callback_query(F.data == "stats_general")
async def stats_general(call: CallbackQuery):
    """Общая статистика"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Всего записей
        cur = await db.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = (await cur.fetchone())[0]
        
        # Записи за последние 30 дней
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cur = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE created_at >= ?",
            (thirty_days_ago,)
        )
        bookings_30d = (await cur.fetchone())[0]
        
        # Предстоящие записи
        now = datetime.now().isoformat()
        cur = await db.execute("""
            SELECT COUNT(*) FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE t.dt > ?
        """, (now,))
        upcoming = (await cur.fetchone())[0]
        
        # Всего клиентов
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL")
        total_clients = (await cur.fetchone())[0]
        
        # Свободные слоты
        cur = await db.execute("SELECT COUNT(*) FROM timeslots WHERE is_booked=0 AND dt > ?", (now,))
        free_slots = (await cur.fetchone())[0]
    
    text = (
        "📊 *Общая статистика*\n\n"
        f"📝 Всего записей: *{total_bookings}*\n"
        f"📅 За последние 30 дней: *{bookings_30d}*\n"
        f"⏭ Предстоящих: *{upcoming}*\n\n"
        f"👥 Всего клиентов: *{total_clients}*\n"
        f"🟢 Свободных слотов: *{free_slots}*\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_back")
    ]])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "stats_finance")
async def stats_finance(call: CallbackQuery):
    """Финансовая статистика"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Общая выручка
        cur = await db.execute("SELECT SUM(total_price) FROM bookings")
        total_revenue = (await cur.fetchone())[0] or 0
        
        # Выручка за 30 дней
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cur = await db.execute(
            "SELECT SUM(total_price) FROM bookings WHERE created_at >= ?",
            (thirty_days_ago,)
        )
        revenue_30d = (await cur.fetchone())[0] or 0
        
        # Выручка за 7 дней
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cur = await db.execute(
            "SELECT SUM(total_price) FROM bookings WHERE created_at >= ?",
            (seven_days_ago,)
        )
        revenue_7d = (await cur.fetchone())[0] or 0
        
        # Средний чек
        cur = await db.execute("SELECT AVG(total_price) FROM bookings")
        avg_check = (await cur.fetchone())[0] or 0
        
        # Предстоящая выручка
        now = datetime.now().isoformat()
        cur = await db.execute("""
            SELECT SUM(b.total_price) FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE t.dt > ?
        """, (now,))
        upcoming_revenue = (await cur.fetchone())[0] or 0
    
    text = (
        "💰 *Финансовая статистика*\n\n"
        f"💵 Общая выручка: *{total_revenue:,.0f} ₽*\n"
        f"📊 За 30 дней: *{revenue_30d:,.0f} ₽*\n"
        f"📊 За 7 дней: *{revenue_7d:,.0f} ₽*\n\n"
        f"💳 Средний чек: *{avg_check:,.0f} ₽*\n"
        f"⏭ Предстоящая: *{upcoming_revenue:,.0f} ₽*\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_back")
    ]])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "stats_services")
async def stats_services(call: CallbackQuery):
    """Статистика по услугам"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Это требует связи многие-ко-многим между bookings и services
        # Для простоты используем существующую структуру
        cur = await db.execute("""
            SELECT s.name, s.price, COUNT(*) as cnt
            FROM services s
            GROUP BY s.id
            ORDER BY s.price DESC
            LIMIT 10
        """)
        services = await cur.fetchall()
    
    text = "🔥 *Популярные услуги*\n\n"
    
    if not services:
        text += "Пока нет данных"
    else:
        for name, price, _ in services:
            text += f"• {name} — {price} ₽\n"
    
    text += "\n_Полная аналитика по услугам будет доступна после добавления связи bookings↔services_"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_back")
    ]])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "stats_weekdays")
async def stats_weekdays(call: CallbackQuery):
    """Статистика по дням недели"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT 
                CAST(strftime('%w', t.dt) AS INTEGER) as dow,
                COUNT(*) as cnt,
                SUM(b.total_price) as revenue
            FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            GROUP BY dow
            ORDER BY dow
        """)
        days_data = await cur.fetchall()
    
    weekdays = {
        0: "Воскресенье",
        1: "Понедельник",
        2: "Вторник",
        3: "Среда",
        4: "Четверг",
        5: "Пятница",
        6: "Суббота"
    }
    
    text = "📅 *Загруженность по дням недели*\n\n"
    
    if not days_data:
        text += "Пока нет данных"
    else:
        for dow, cnt, revenue in days_data:
            day_name = weekdays.get(dow, "Неизвестно")
            text += f"*{day_name}:* {cnt} записей, {revenue or 0:,.0f} ₽\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_back")
    ]])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "stats_clients")
async def stats_clients(call: CallbackQuery):
    """Статистика по клиентам"""
    async with aiosqlite.connect(DB_PATH) as db:
        # ТОП клиентов по количеству записей
        cur = await db.execute("""
            SELECT u.name, COUNT(*) as visits, SUM(b.total_price) as spent
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            GROUP BY u.id
            ORDER BY visits DESC
            LIMIT 10
        """)
        top_clients = await cur.fetchall()
    
    text = "👥 *ТОП-10 клиентов*\n\n"
    
    if not top_clients:
        text += "Пока нет данных"
    else:
        for i, (name, visits, spent) in enumerate(top_clients, 1):
            text += f"{i}. {name}: {visits} визитов, {spent:,.0f} ₽\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Назад", callback_data="stats_back")
    ]])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "stats_back")
async def stats_back(call: CallbackQuery):
    """Возврат к меню статистики"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="stats_general")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="stats_finance")],
        [InlineKeyboardButton(text="🔥 Популярные услуги", callback_data="stats_services")],
        [InlineKeyboardButton(text="📅 По дням недели", callback_data="stats_weekdays")],
        [InlineKeyboardButton(text="👥 Клиенты", callback_data="stats_clients")],
    ])
    
    await call.message.edit_text(
        "📊 *Статистика и аналитика*\n\n"
        "Выбери раздел:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await call.answer()


@router.message(Command("debug_slots"))
async def debug_slots(message: Message):
    """Отладка слотов (только админ)"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    # Проверяем какая дата
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.answer("Используй: /debug_slots 2025-10-05")
    
    date_str = parts[1]
    
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT id, dt, is_booked FROM timeslots 
               WHERE date(dt)=? 
               ORDER BY dt""",
            (date_str,)
        )
        slots = await cur.fetchall()
    
    if not slots:
        return await message.answer(f"❌ На дату {date_str} нет слотов вообще!")
    
    text = f"*Слоты на {date_str}:*\n\n"
    for sid, dt, is_booked in slots:
        status = "🔴 ЗАНЯТ" if is_booked else "🟢 СВОБОДЕН"
        text += f"#{sid} {datetime.fromisoformat(dt).strftime('%H:%M')} {status}\n"
    
    await message.answer(text, parse_mode="Markdown")


# ===== ЭКСПОРТ ДАННЫХ =====

@router.message(Command("export"))
async def export_bookings(message: Message):
    """Экспорт всех записей в CSV"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT 
                b.id,
                t.dt,
                u.name,
                u.phone,
                b.total_price,
                b.created_at,
                COALESCE(b.confirmed, 0) as confirmed
            FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            JOIN users u ON u.id = b.user_id
            ORDER BY t.dt DESC
        """)
        rows = await cur.fetchall()
    
    if not rows:
        return await message.answer("Нет записей для экспорта")
    
    # Создаём CSV
    import io
    output = io.StringIO()
    output.write("ID,Дата,Время,Клиент,Телефон,Сумма,Создано,Подтверждено\n")
    
    for bid, dt_str, name, phone, price, created, confirmed in rows:
        dt = datetime.fromisoformat(dt_str)
        date = dt.strftime("%d.%m.%Y")
        time = dt.strftime("%H:%M")
        phone_clean = phone or "нет"
        conf_str = "Да" if confirmed else "Нет"
        created_date = datetime.fromisoformat(created).strftime("%d.%m.%Y")
        
        output.write(f"{bid},{date},{time},{name},{phone_clean},{price},{created_date},{conf_str}\n")
    
    # Отправляем файл
    from aiogram.types import BufferedInputFile
    
    file_content = output.getvalue().encode('utf-8-sig')  # BOM для Excel
    file = BufferedInputFile(file_content, filename=f"bookings_{datetime.now().strftime('%Y%m%d')}.csv")
    
    await message.answer_document(
        document=file,
        caption=f"📊 Экспорт записей\nВсего: {len(rows)} записей"
    )


# ===== УПРАВЛЕНИЕ СЛОТАМИ =====

@router.message(Command("clear_old_slots"))
async def clear_old_slots(message: Message):
    """Удалить все старые (прошедшие) слоты"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить старые свободные", callback_data="clear_old_free")],
        [InlineKeyboardButton(text="🗑 Удалить ВСЕ старые", callback_data="clear_old_all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clear")],
    ])
    
    await message.answer(
        "Какие старые слоты удалить?\n\n"
        "• *Свободные* - только пустые слоты\n"
        "• *Все* - включая с завершёнными записями",
        parse_mode="Markdown",
        reply_markup=kb
    )


@router.callback_query(F.data == "clear_old_free")
async def clear_old_free_slots(call: CallbackQuery):
    """Удалить старые свободные слоты"""
    now = datetime.now().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM timeslots WHERE dt < ? AND is_booked = 0",
            (now,)
        )
        deleted = cur.rowcount
        await db.commit()
    
    await call.message.edit_text(f"✅ Удалено старых свободных слотов: {deleted}")
    await call.answer()


@router.callback_query(F.data == "clear_old_all")
async def clear_old_all_slots(call: CallbackQuery):
    """Удалить ВСЕ старые слоты"""
    now = datetime.now().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем старые записи
        cur = await db.execute("""
            DELETE FROM bookings 
            WHERE timeslot_id IN (
                SELECT id FROM timeslots WHERE dt < ?
            )
        """, (now,))
        deleted_bookings = cur.rowcount
        
        # Удаляем старые слоты
        cur = await db.execute("DELETE FROM timeslots WHERE dt < ?", (now,))
        deleted_slots = cur.rowcount
        
        await db.commit()
    
    await call.message.edit_text(
        f"✅ Очищено:\n"
        f"• Записей: {deleted_bookings}\n"
        f"• Слотов: {deleted_slots}"
    )
    await call.answer()


@router.callback_query(F.data == "cancel_clear")
async def cancel_clear(call: CallbackQuery):
    """Отмена очистки"""
    await call.message.edit_text("Отменено")
    await call.answer()


# ===== УПРАВЛЕНИЕ УСЛУГАМИ =====

@router.message(Command("set_duration"))
async def set_duration(message: Message):
    """Установить длительность услуги"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Используй: /set_duration <название> <минуты>")
    
    name = parts[1]
    try:
        duration = int(parts[2])
    except ValueError:
        return await message.answer("Длительность должна быть числом")
    
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE services SET duration_minutes=? WHERE LOWER(name)=LOWER(?)",
            (duration, name)
        )
        await db.commit()
        
        if cur.rowcount == 0:
            return await message.answer(f"Услуга '{name}' не найдена ❌")
    
    await message.answer(f"✅ Длительность «{name}» обновлена: {duration} минут")


@router.message(Command("addservice"))
async def add_service(message: Message):
    """Добавить новую услугу"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    parts = message.text.strip().split(maxsplit=3)
    if len(parts) < 3:
        return await message.answer("Используй: /addservice <название> <цена> [минуты]")

    name = parts[1]
    try:
        price = int(parts[2])
        duration = int(parts[3]) if len(parts) > 3 else 60
    except ValueError:
        return await message.answer("Цена и длительность должны быть числами")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM services WHERE LOWER(name)=LOWER(?)", (name,))
        row = await cur.fetchone()
        if row:
            return await message.answer(f"Услуга '{name}' уже существует ❌")

        await db.execute(
            "INSERT INTO services(name, price, duration_minutes) VALUES (?, ?, ?)", 
            (name, price, duration)
        )
        await db.commit()

    await message.answer(f"✅ Услуга '{name}' добавлена\n💰 Цена: {price} ₽\n⏱ Длительность: {duration} мин")