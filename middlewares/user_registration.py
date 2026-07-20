from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from database.db_core import register_user


class UserRegistrationMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            if event.from_user and not event.from_user.is_bot:
                await register_user(event.from_user.id, event.from_user.username)
        elif isinstance(event, CallbackQuery):
            if event.from_user and not event.from_user.is_bot:
                await register_user(event.from_user.id, event.from_user.username)
        return await handler(event, data)
