import asyncio
import aiocron
import logging

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from database import db_init
from handlers import register_handlers
from handlers.reminders import remind_24h_before, remind_12h_before, remind_1h_before

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


async def main():
    """Главная функция запуска бота"""
    # Инициализация базы данных
    await db_init()
    logging.info("✅ Database initialized")
    
    # Регистрация всех обработчиков
    register_handlers(dp)
    logging.info("✅ Handlers registered")
    
    # Запуск крон-задач для напоминаний
    # В продакшене измените на реальное расписание:
    # '0 */1 * * *' - каждый час
    # '*/30 * * * *' - каждые 30 минут
    
    # Для теста: каждую минуту
    cron_24h = aiocron.crontab('*/30 * * * *', func=lambda: remind_24h_before(bot), start=True)
    cron_12h = aiocron.crontab('*/30 * * * *', func=lambda: remind_12h_before(bot), start=True)
    cron_1h = aiocron.crontab('*/15 * * * *', func=lambda: remind_1h_before(bot), start=True)
    
    logging.info("⏰ Reminder crons started:")
    logging.info("   • 24h reminder - every minute (test mode)")
    logging.info("   • 12h reminder - every minute (test mode)")
    logging.info("   • 1h reminder - every minute (test mode)")
    logging.info("")
    logging.info("📝 Change cron schedule in main.py for production!")
    logging.info("   Recommended: '*/30 * * * *' (every 30 minutes)")
    
    # Запуск бота
    logging.info("🚀 Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())