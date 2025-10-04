import aiosqlite
from config import DB_PATH


async def db_init():
    """Инициализация базы данных и создание таблиц"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE,
            name TEXT,
            phone TEXT
        )""")
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL
        )""")
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS timeslots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt TEXT NOT NULL,
            is_booked INTEGER DEFAULT 0,
            booked_by_user_id INTEGER
        )""")
        
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timeslot_id INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            reminded24 INTEGER DEFAULT 0,
            reminded12 INTEGER DEFAULT 0,
            reminded1h INTEGER DEFAULT 0,
            confirmed INTEGER DEFAULT 0
        )""")
        
        # Добавляем новые колонки если их нет (для существующих БД)
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminded24 INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass
        
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminded1h INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass
        
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN confirmed INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass
        
        # Засеем базовые услуги, если пусто
        cur = await db.execute("SELECT COUNT(*) FROM services")
        count = (await cur.fetchone())[0]
        if count == 0:
            await db.executemany(
                "INSERT INTO services(name, price) VALUES (?, ?)",
                [
                    ("Покрытие", 1000),
                    ("Дизайн", 500),
                    ("Снятие", 300),
                ],
            )
        await db.commit()