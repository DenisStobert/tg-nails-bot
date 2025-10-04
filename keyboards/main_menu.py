from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Главное меню бота"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записаться"), KeyboardButton(text="👀 Мои записи")],
            [KeyboardButton(text="💰 Услуги и цены")],
        ],
        resize_keyboard=True
    )