import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties  # Добавили этот импорт
from middlewares.shadow_ban import BanMiddleware
from config_data.config import load_config
from handlers import user_handlers, admin_handlers
from database.db_core import init_db

async def main():
    # Инициализируем базу данных
    await init_db()
    
    # Загружаем конфиг
    config = load_config()
    
    # Инициализируем бот по новым правилам aiogram 3.7+
    bot = Bot(
        token=config.tg_bot.token, 
        default=DefaultBotProperties(parse_mode="HTML")
    ) 
    
    dp = Dispatcher()

    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())
    
    dp.include_router(user_handlers.router)
    dp.include_router(admin_handlers.router)

    
    print("Бот успешно запущен и база данных готова!")
    
    # Пропускаем накопившиеся апдейты и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())