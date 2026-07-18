from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config_data.config import load_config

config = load_config()

class CheckSubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Работаем только с сообщениями и колбэками
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)
            
        user_id = event.from_user.id
        
        # Админу проверку подписки отключаем, чтобы не заблочить самого себя
        if user_id == config.tg_bot.admin_id:
            return await handler(event, data)

        try:
            # Укажи ID своего канала в .env как CHANNEL_ID (например, -100xxxxxxxxx)
            # Или замени config.tg_bot.channel_id на строковую ссылку типа "@my_channel"
            member = await event.bot.get_chat_member(chat_id="@burmalldatgk", user_id=user_id)
            
            # Если статус пользователя не состоит в канале
            if member.status in ['left', 'kicked']:
                text = "❌ <b>Доступ ограничен!</b>\n\nЧтобы пользоваться ботом и смотреть мемы, подпишись на наш официальный канал!"
                # Ссылку на канал тоже можно вынести в конфиг или лексикон
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/burmalldatgk")]
                ])
                
                if isinstance(event, Message):
                    await event.answer(text, reply_markup=kb)
                else:
                    await event.answer(text, show_alert=True)
                return # Дропаем апдейт
        except Exception as e:
            print(f"Ошибка проверки подписки: {e}")
            # Если канал не найден или бот не админ в нем, пропускаем юзера, чтобы бот не лег
            return await handler(event, data)

        return await handler(event, data)