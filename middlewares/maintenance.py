from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from config_data.config import load_config
from database.db_core import is_maintenance_enabled, is_user_allowed

config = load_config()


class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user = getattr(event, 'from_user', None)
        if not user or user.is_bot:
            return await handler(event, data)

        user_id = user.id
        if user_id == config.tg_bot.admin_id:
            return await handler(event, data)

        if await is_user_allowed(user_id):
            return await handler(event, data)

        if await is_maintenance_enabled():
            text = (
                "⚠️ Бот временно закрыт на технические работы.\n\n"
                "Администратор уже работает над запуском."
            )
            if isinstance(event, Message):
                await event.answer(text)
            else:
                await event.answer(text, show_alert=True)
            return None

        return await handler(event, data)
