from aiogram import Dispatcher
from . import user, booking, admin, reminders, contacts


def register_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    dp.include_router(user.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    dp.include_router(reminders.router)
    dp.include_router(contacts.router)