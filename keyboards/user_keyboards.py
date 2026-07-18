from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from lexicons.lexicon import LEXICON

def create_main_menu() -> ReplyKeyboardMarkup:
    """Генерирует нижнюю обычную клавиатуру с главной кнопкой."""
    button_meme = KeyboardButton(text=LEXICON['meme_button'])
    button_top = KeyboardButton(text=LEXICON['top_button'])
    button_add_meme = KeyboardButton(text=LEXICON['add_meme_button'])

    return ReplyKeyboardMarkup(
        keyboard=[
        [button_meme, button_top],
        [button_add_meme]
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
        # В callback_data зашиваем ID мема
        builder.row(InlineKeyboardButton(
            text=meme['title'],
            callback_data=f"show_meme_{meme['id']}"
        ))
        
    return builder.as_markup()