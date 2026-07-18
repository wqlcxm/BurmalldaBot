from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def create_moderation_keyboard() -> InlineKeyboardMarkup:
    """Кнопки для админа: одобрить или отклонить мем."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data="admin_accept"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="admin_reject")
    )
    return builder.as_markup()

def create_moderation_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Кнопки для админа с возможностью забанить автора предложки."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data="admin_accept"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="admin_reject")
    )
    # Кнопка бана во второй ряд
    builder.row(
        InlineKeyboardButton(text="🚫 Забанить автора", callback_data=f"admin_ban_{user_id}")
    )
    return builder.as_markup()

