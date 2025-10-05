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
            created_at TEXT NOT NULL
        )""")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        
        # Добавляем колонку duration_minutes если её нет
        try:
            await db.execute("ALTER TABLE services ADD COLUMN duration_minutes INTEGER DEFAULT 60")
            await db.commit()
            print("✅ Добавлена колонка duration_minutes")
        except Exception:
            pass
        
        # Добавляем колонки для напоминаний если их нет
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminded24 INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass
        
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminded12 INTEGER DEFAULT 0")
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
        
        # Обновляем существующие услуги - устанавливаем дефолтные 60 минут
        await db.execute("UPDATE services SET duration_minutes = 60 WHERE duration_minutes IS NULL OR duration_minutes = 0")
        await db.commit()
        
        # Засеем базовые услуги, если пусто
        cur = await db.execute("SELECT COUNT(*) FROM services")
        count = (await cur.fetchone())[0]
        if count == 0:
            await db.executemany(
                "INSERT INTO services(name, price, duration_minutes) VALUES (?, ?, ?)",
                [
                    ("Покрытие", 1000, 60),
                    ("Дизайн", 500, 30),
                    ("Снятие", 300, 30),
                ],
            )
            await db.commit()
            print("✅ Добавлены базовые услуги")