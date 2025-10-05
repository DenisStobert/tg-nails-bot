import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import DB_PATH, ADMIN_ID

router = Router()


@router.message(Command("contacts"))
@router.message(Command("about"))
async def show_contacts(message: Message):
    """Показать контакты и информацию"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT key, value FROM settings WHERE key LIKE 'contact_%'")
        settings = {row[0]: row[1] for row in await cur.fetchall()}
    
    address = settings.get('contact_address', 'Не указан')
    phone = settings.get('contact_phone', 'Не указан')
    instagram = settings.get('contact_instagram', '')
    hours = settings.get('contact_hours', 'Не указаны')
    map_url = settings.get('contact_map_url', '')
    
    text = (
        "📍 *Контакты и информация*\n\n"
        f"🏠 Адрес: {address}\n"
        f"📞 Телефон: {phone}\n"
        f"🕐 Часы работы: {hours}\n"
    )
    
    kb_rows = []
    if map_url:
        kb_rows.append([InlineKeyboardButton(text="🗺 Как добраться", url=map_url)])
    if instagram:
        kb_rows.append([InlineKeyboardButton(text="📸 Instagram", url=instagram)])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@router.message(Command("set_contacts"))
async def set_contacts_start(message: Message):
    """Настройка контактов (только админ)"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    await message.answer(
        "⚙️ *Настройка контактов*\n\n"
        "Используй команды:\n"
        "• `/set_address <адрес>`\n"
        "• `/set_phone <телефон>`\n"
        "• `/set_hours <часы работы>`\n"
        "• `/set_instagram <ссылка>`\n"
        "• `/set_map <ссылка на карты>`\n\n"
        "Пример:\n"
        "`/set_address Москва, ул. Ленина 15`",
        parse_mode="Markdown"
    )


async def save_setting(key: str, value: str):
    """Сохранить настройку"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        """, (key, value))
        await db.commit()


@router.message(Command("set_address"))
async def set_address(message: Message):
    """Установить адрес"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    value = message.text.replace("/set_address", "").strip()
    if not value:
        return await message.answer("Укажи адрес после команды")
    
    await save_setting('contact_address', value)
    await message.answer(f"✅ Адрес сохранён: {value}")


@router.message(Command("set_phone"))
async def set_phone(message: Message):
    """Установить телефон"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    value = message.text.replace("/set_phone", "").strip()
    if not value:
        return await message.answer("Укажи телефон после команды")
    
    await save_setting('contact_phone', value)
    await message.answer(f"✅ Телефон сохранён: {value}")


@router.message(Command("set_hours"))
async def set_hours(message: Message):
    """Установить часы работы"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    value = message.text.replace("/set_hours", "").strip()
    if not value:
        return await message.answer("Укажи часы работы")
    
    await save_setting('contact_hours', value)
    await message.answer(f"✅ Часы работы сохранены: {value}")


@router.message(Command("set_instagram"))
async def set_instagram(message: Message):
    """Установить Instagram"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    value = message.text.replace("/set_instagram", "").strip()
    if not value:
        return await message.answer("Укажи ссылку на Instagram")
    
    await save_setting('contact_instagram', value)
    await message.answer(f"✅ Instagram сохранён: {value}")


@router.message(Command("set_map"))
async def set_map(message: Message):
    """Установить ссылку на карту"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("Недостаточно прав.")
    
    value = message.text.replace("/set_map", "").strip()
    if not value:
        return await message.answer("Укажи ссылку на карту")
    
    await save_setting('contact_map_url', value)
    await message.answer(f"✅ Ссылка на карту сохранена")