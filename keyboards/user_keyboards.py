from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from lexicons.lexicon import LEXICON

def create_main_menu() -> ReplyKeyboardMarkup:
    """Генерирует нижнюю обычную клавиатуру с главной кнопкой."""
    button_meme = KeyboardButton(text=LEXICON['meme_button'])
    button_top = KeyboardButton(text=LEXICON['top_button'])
    button_add_meme = KeyboardButton(text=LEXICON['add_meme_button'])
    button_random_meme = KeyboardButton(text=LEXICON['random_meme_button'])
    button_about = KeyboardButton(text=LEXICON['about_button'])
    button_settings = KeyboardButton(text=LEXICON['settings_button'])

    return ReplyKeyboardMarkup(
        keyboard=[
        [button_meme, button_top],
        [button_add_meme, button_random_meme],
        [button_settings, button_about]
        ],
        resize_keyboard=True
    )

def create_cancel_menu() -> ReplyKeyboardMarkup:
    """Генерирует клавиатуру отмены для режима FSM."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=LEXICON['back_button'])]
        ],
        resize_keyboard=True
    )

def create_memes_inline_keyboard(memes_list: list[dict]) -> InlineKeyboardMarkup:
    """Генерирует инлайн-кнопки со списком названий мемов из базы данных."""
    builder = InlineKeyboardBuilder()
    
    for meme in memes_list:
        views = meme.get('views', 0)
        # В callback_data зашиваем ID мема
        builder.row(InlineKeyboardButton(
            text=f"{meme['title']} 👁 {views}",
            callback_data=f"show_meme_{meme['id']}"
        ))
        
    return builder.as_markup()


def create_settings_keyboard(
    caption_enabled: bool,
    show_username_enabled: bool,
    show_in_top_enabled: bool,
) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру персональных и inline-настроек."""
    builder = InlineKeyboardBuilder()
    caption_text = '✅ Отключить подпись' if caption_enabled else '🔄 Включить подпись'
    username_text = (
        '✅ Скрыть мой username'
        if show_username_enabled
        else '🔄 Показывать мой username'
    )
    top_text = (
        '✅ Скрыть меня из топа'
        if show_in_top_enabled
        else '🔄 Показывать меня в топе'
    )
    builder.row(InlineKeyboardButton(
        text=caption_text,
        callback_data='toggle_inline_description'
    ))
    builder.row(InlineKeyboardButton(
        text=username_text,
        callback_data='toggle_show_username'
    ))
    builder.row(InlineKeyboardButton(
        text=top_text,
        callback_data='toggle_show_in_top'
    ))
    return builder.as_markup()


def create_meme_like_keyboard(meme_id: int, likes_count: int = 0, liked: bool = False) -> InlineKeyboardMarkup:
    """Кнопка лайка под мемом, отправленным в боте."""
    heart = '❤️' if liked else '🤍'
    count_text = f' {likes_count}' if likes_count else ''
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f'{heart}{count_text}',
        callback_data=f'like_meme_{meme_id}',
    ))
    return builder.as_markup()
