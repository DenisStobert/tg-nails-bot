import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import DB_PATH, ADMIN_ID
from utils.misc import iso_format

router = Router()


async def remind_24h_before(bot: Bot):
    """Отправка напоминаний за 24 часа до записи"""
    now = datetime.now()
    start = now + timedelta(hours=24)
    end = start + timedelta(minutes=10)

    logging.info(f"[24h] now={iso_format(now)}  window=[{iso_format(start)} .. {iso_format(end)})")

    async with aiosqlite.connect(DB_PATH) as db:
        # Добавляем колонку если её нет
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminded24 INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        cur = await db.execute("""
            SELECT b.id, u.tg_id, u.name, t.dt
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE COALESCE(b.reminded24,0) = 0
              AND t.dt >= ?
              AND t.dt <  ?
        """, (iso_format(start), iso_format(end)))
        rows = await cur.fetchall()

    logging.info(f"[24h] candidates found: {len(rows)}")
    if not rows:
        return

    for bid, tg_id, name, dt_str in rows:
        try:
            when = datetime.fromisoformat(dt_str)
            time_str = when.strftime("%d.%m %H:%M")

            text = (
                f"💅 Привет, {name or 'клиент'}!\n\n"
                f"📅 Напоминаем: завтра у тебя запись на {time_str}\n\n"
                f"Если планы изменились — можешь перенести или отменить запись 👇"
            )

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📅 Перенести запись", callback_data=f"reschedule:{bid}")],
                [InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_booking:{bid}")],
                [InlineKeyboardButton(text="💬 Написать мастеру", url=f"tg://user?id={ADMIN_ID}")]
            ])

            await bot.send_message(tg_id, text, reply_markup=kb)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE bookings SET reminded24=1 WHERE id=?", (bid,))
                await db.commit()

            logging.info(f"[24h] ✅ reminder sent for booking #{bid} to user={tg_id}")

        except Exception as e:
            logging.warning(f"[24h] ⚠️ failed to send reminder for #{bid}: {e}")


async def remind_12h_before(bot: Bot):
    """Отправка напоминаний за 12 часов до записи"""
    now = datetime.now()
    start = now + timedelta(hours=12)
    end = start + timedelta(minutes=10)

    logging.info(f"[12h] now={iso_format(now)}  window=[{iso_format(start)} .. {iso_format(end)})")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT b.id, u.tg_id, u.name, t.dt
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE COALESCE(b.reminded12,0) = 0
              AND t.dt >= ?
              AND t.dt <  ?
        """, (iso_format(start), iso_format(end)))
        rows = await cur.fetchall()

    logging.info(f"[12h] candidates found: {len(rows)}")
    if not rows:
        return

    for bid, tg_id, name, dt_str in rows:
        try:
            when = datetime.fromisoformat(dt_str)
            time_str = when.strftime("%d.%m %H:%M")

            text = (
                f"💅 {name or 'Клиент'}, это важно!\n\n"
                f"⏰ Через 12 часов у тебя запись на {time_str}\n\n"
                f"❗️ Пожалуйста, подтверди что придёшь, или перенеси/отмени запись"
            )

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтверждаю, приду!", callback_data=f"confirm_attendance:{bid}")],
                [InlineKeyboardButton(text="📅 Перенести", callback_data=f"reschedule:{bid}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_booking:{bid}")],
            ])

            await bot.send_message(tg_id, text, reply_markup=kb)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE bookings SET reminded12=1 WHERE id=?", (bid,))
                await db.commit()

            logging.info(f"[12h] ✅ reminder sent for booking #{bid} to user={tg_id}")

        except Exception as e:
            logging.warning(f"[12h] ⚠️ failed to send reminder for #{bid}: {e}")


async def remind_1h_before(bot: Bot):
    """Отправка напоминаний за 1 час до записи"""
    now = datetime.now()
    start = now + timedelta(hours=1)
    end = start + timedelta(minutes=10)

    logging.info(f"[1h] now={iso_format(now)}  window=[{iso_format(start)} .. {iso_format(end)})")

    async with aiosqlite.connect(DB_PATH) as db:
        # Добавляем колонку если её нет
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminded1h INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        cur = await db.execute("""
            SELECT b.id, u.tg_id, u.name, t.dt
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE COALESCE(b.reminded1h,0) = 0
              AND t.dt >= ?
              AND t.dt <  ?
        """, (iso_format(start), iso_format(end)))
        rows = await cur.fetchall()

    logging.info(f"[1h] candidates found: {len(rows)}")
    if not rows:
        return

    for bid, tg_id, name, dt_str in rows:
        try:
            when = datetime.fromisoformat(dt_str)
            time_str = when.strftime("%H:%M")

            text = (
                f"💅 {name or 'Клиент'}!\n\n"
                f"⏰ Через час тебя жду на {time_str}!\n\n"
                f"📍 Не забудь адрес и возьми хорошее настроение 😊\n"
                f"До встречи! ✨"
            )

            await bot.send_message(tg_id, text)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE bookings SET reminded1h=1 WHERE id=?", (bid,))
                await db.commit()

            logging.info(f"[1h] ✅ reminder sent for booking #{bid} to user={tg_id}")

        except Exception as e:
            logging.warning(f"[1h] ⚠️ failed to send reminder for #{bid}: {e}")


@router.callback_query(F.data.startswith("confirm_attendance:"))
async def confirm_attendance(call: CallbackQuery):
    """Подтверждение посещения клиентом"""
    booking_id = int(call.data.split(":")[1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Добавляем колонку если её нет
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN confirmed INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass
        
        # Подтверждаем запись
        await db.execute("UPDATE bookings SET confirmed=1 WHERE id=?", (booking_id,))
        await db.commit()
        
        # Получаем информацию о записи
        cur = await db.execute("""
            SELECT t.dt, b.total_price
            FROM bookings b
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE b.id = ?
        """, (booking_id,))
        row = await cur.fetchone()
    
    if row:
        dt_str, price = row
        when = datetime.fromisoformat(dt_str).strftime("%d.%m %H:%M")
        
        await call.message.edit_text(
            f"✅ *Отлично!*\n\n"
            f"Твоя запись подтверждена:\n"
            f"📅 {when}\n"
            f"💰 {price} ₽\n\n"
            f"Жду тебя! 💅",
            parse_mode="Markdown"
        )
        
        # Уведомляем мастера
        try:
            await call.bot.send_message(
                ADMIN_ID,
                f"✅ Клиент {call.from_user.full_name} подтвердил запись #{booking_id} на {when}"
            )
        except Exception as e:
            logging.warning(f"Cannot notify admin: {e}")
    
    await call.answer("✅ Запись подтверждена!")


@router.message(Command("debug_reminders"))
async def debug_reminders(message: Message):
    """Отладочная информация о напоминаниях (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")

    now = datetime.now()
    
    # Окна для разных напоминаний
    windows = {
        "24h": (now + timedelta(hours=24), now + timedelta(hours=24, minutes=10)),
        "12h": (now + timedelta(hours=12), now + timedelta(hours=12, minutes=10)),
        "1h": (now + timedelta(hours=1), now + timedelta(hours=1, minutes=10)),
    }
    
    text = "🔍 *Отладка напоминаний*\n\n"
    text += f"Текущее время: {iso_format(now)}\n\n"
    
    async with aiosqlite.connect(DB_PATH) as db:
        for label, (start, end) in windows.items():
            cur = await db.execute("""
                SELECT b.id, u.name, t.dt, 
                       COALESCE(b.reminded24, 0) as r24,
                       COALESCE(b.reminded12, 0) as r12,
                       COALESCE(b.reminded1h, 0) as r1h,
                       COALESCE(b.confirmed, 0) as conf
                FROM bookings b
                JOIN users u ON u.id = b.user_id
                JOIN timeslots t ON t.id = b.timeslot_id
                WHERE t.dt >= ? AND t.dt < ?
            """, (iso_format(start), iso_format(end)))
            rows = await cur.fetchall()
            
            text += f"*Окно {label}:* [{iso_format(start)} - {iso_format(end)}]\n"
            text += f"Кандидатов: {len(rows)}\n"
            
            for bid, name, dt_str, r24, r12, r1h, conf in rows[:3]:
                flags = []
                if r24: flags.append("24h✓")
                if r12: flags.append("12h✓")
                if r1h: flags.append("1h✓")
                if conf: flags.append("CONF✓")
                flags_str = " ".join(flags) if flags else "новая"
                
                text += f"  • #{bid} {name} {dt_str} [{flags_str}]\n"
            
            text += "\n"
    
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("test_reminder"))
async def test_reminder(message: Message):
    """Тестовая отправка напоминания (только админ)"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.answer(
            "Использование: /test\\_reminder <booking\\_id>\n"
            "Например: `/test_reminder 5`",
            parse_mode="Markdown"
        )
    
    booking_id = int(parts[1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT u.tg_id, u.name, t.dt
            FROM bookings b
            JOIN users u ON u.id = b.user_id
            JOIN timeslots t ON t.id = b.timeslot_id
            WHERE b.id = ?
        """, (booking_id,))
        row = await cur.fetchone()
    
    if not row:
        return await message.answer("❌ Запись не найдена")
    
    tg_id, name, dt_str = row
    when = datetime.fromisoformat(dt_str)
    time_str = when.strftime("%d.%m %H:%M")
    
    text = (
        f"🧪 *ТЕСТОВОЕ НАПОМИНАНИЕ*\n\n"
        f"💅 Привет, {name or 'клиент'}!\n"
        f"📅 У тебя запись на {time_str}\n\n"
        f"Это тестовое сообщение от мастера"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data=f"confirm_attendance:{booking_id}")],
        [InlineKeyboardButton(text="📅 Перенести", callback_data=f"reschedule:{booking_id}")],
    ])
    
    try:
        await message.bot.send_message(tg_id, text, parse_mode="Markdown", reply_markup=kb)
        await message.answer("✅ Тестовое напоминание отправлено!")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")