from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def create_moderation_keyboard(user_id: int, username: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки для админа с передачей авторских данных в callback_data."""
    if not username:
        callback_accept = "admin_accept"
        callback_reject = "admin_reject"
    else:
        callback_accept = f"admin_accept:{user_id}:{username}"
        callback_reject = f"admin_reject:{user_id}:{username}"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=callback_accept),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=callback_reject)
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Забанить автора", callback_data=f"admin_ban_{user_id}")
    )
    return builder.as_markup()

