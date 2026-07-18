import re
# import random
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from lexicons.lexicon import LEXICON
from keyboards.user_keyboards import create_main_menu, create_memes_inline_keyboard, create_cancel_menu
from keyboards.admin_keyboards import create_moderation_keyboard
from database.db_core import get_all_memes, get_meme_by_id, ban_user, unban_user, get_top_contributors
from config_data.config import load_config

router = Router()
config = load_config()

# Состояния FSM для добавления мема
class AddMemeState(StatesGroup):
    upload_video = State()  # Ожидание видеоролика
    type_title = State()    # Ожидание названия кнопки

@router.message(CommandStart())
@router.message(F.text == LEXICON['back_button'])
async def process_start_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        text=LEXICON['/start'],
        reply_markup=create_main_menu()
    )

@router.message(F.text == LEXICON['meme_button'])
async def process_meme_menu_request(message: Message):
    memes = await get_all_memes()
    if not memes:
        await message.answer(text=LEXICON['no_memes'])
        return
    inline_kb = create_memes_inline_keyboard(memes)
    await message.answer(text="Выбери мем из списка ниже", reply_markup=inline_kb)

@router.callback_query(F.data.startswith("show_meme_"))
async def process_meme_click(callback: CallbackQuery):
    meme_id = int(callback.data.split("_")[2])
    meme = await get_meme_by_id(meme_id)
    if not meme:
        await callback.answer(LEXICON['not_found'], show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.answer_video(video=meme['file_id'], caption=f"🎬 <b>{meme['title']}</b>")
    except Exception as e:
        await callback.message.answer(text=LEXICON['error'])

# --- ПОШАГОВОЕ ДОБАВЛЕНИЕ МЕМА НА МОДЕРАЦИЮ ---

# Шаг 1: Юзер пишет команду /addmeme
@router.message(Command("addmeme"))
@router.message(F.text == LEXICON['add_meme_button'])
async def start_add_meme(message: Message, state: FSMContext):
    await message.answer(
        LEXICON['add_meme_instruction'],
        reply_markup=create_cancel_menu()
    )
    await state.set_state(AddMemeState.upload_video)

@router.message(AddMemeState.upload_video, F.video)
async def process_add_meme_video(message: Message, state: FSMContext):
    # Проверяем разрешение видео встроенными средствами Telegram API
    height = message.video.height
    
    if height >= 1080:
        quality = "1080p"
    elif height >= 720:
        quality = "720p"
    elif height >= 480:
        quality = "480p"
    else:
        quality = "360p"
        
    # Сохраняем и ID видео, и автоматически определенное качество
    await state.update_data(file_id=message.video.file_id, video_quality=quality) 
    await message.answer(f"определил качество видео как <b>{quality}</b>.\nА теперь напиши название для кнопки **(качество я добавлю сам в конец!)**:")
    await state.set_state(AddMemeState.type_title)

@router.message(AddMemeState.type_title, F.text)
async def process_add_meme_title(message: Message, state: FSMContext, bot: Bot):
    user_title = message.text.strip()
    user_data = await state.get_data()
    file_id = user_data['file_id']
    quality = user_data['video_quality']  # Например, "720p"
    
    # Регулярка, которая ищет конструкции типа 720p, 1080p, 480p, 360p на конце (игнорируя регистр)
    # Она также срежет пробелы перед ними
    cleaned_title = re.sub(r'\s*\d{3,4}p\b', '', user_title, flags=re.IGNORECASE).strip()
    
    # Теперь склеиваем очищенное название с автоматически определенным качеством
    full_title = f"{cleaned_title} {quality}"
    
    await state.clear()
    await message.answer(LEXICON['check_meme'])
    
    # Отправляем видео тебе в ЛС на модерацию
    await bot.send_video(
        chat_id=config.tg_bot.admin_id,
        video=file_id,
        caption=f"<b>📢 Предложен новый мем!</b>\n\n<b>Название для кнопки:</b> {full_title}\n<b>Отправил:</b> @{message.from_user.username or 'без_юзернейма'} (ID: {message.from_user.id})",
        reply_markup=create_moderation_keyboard(user_id=message.from_user.id)
    )

# Если вместо видео юзер отправил текст или что-то не то
@router.message(AddMemeState.upload_video)
async def process_add_meme_video_invalid(message: Message):
    await message.answer("отправь именно **видеоролик**!")

# Шаг 3: Юзер написал название. Отправляем админу
@router.message(AddMemeState.type_title, F.text)
async def process_add_meme_title(message: Message, state: FSMContext, bot: Bot):
    user_title = message.text.strip()
    user_data = await state.get_data()
    file_id = user_data['file_id']
    quality = user_data['video_quality']
    
    cleaned_title = re.sub(r'\s*\d{3,4}p\b', '', user_title, flags=re.IGNORECASE).strip()
    full_title = f"{cleaned_title} {quality}"
    
    await state.clear()
    await message.answer("🚀 Твой мем отправлен на проверку админу!")
    
    # Собираем данные юзера для админки
    username = message.from_user.username or f"id{message.from_user.id}"
    
    # Изменим клавиатуру модерации: передадим в кнопки ID автора предложки
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    moderation_kb = InlineKeyboardBuilder()
    # Зашиваем ID автора и юзернейм прямо в callback_data кнопок через разделитель :
    moderation_kb.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_accept:{message.from_user.id}:{username}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="admin_reject")
    )
    moderation_kb.row(
        InlineKeyboardButton(text="🚫 Забанить автора", callback_data=f"admin_ban_{message.from_user.id}")
    )

    await bot.send_video(
        chat_id=config.tg_bot.admin_id,
        video=file_id,
        caption=f"<b>📢 Предложен новый мем!</b>\n\n<b>Название для кнопки:</b> {full_title}\n<b>Отправил:</b> @{username} (ID: {message.from_user.id})",
        reply_markup=moderation_kb.as_markup()
    )

# Если вместо названия кнопки юзер шлет стикеры/фото
@router.message(AddMemeState.type_title)
async def process_add_meme_title_invalid(message: Message):
    await message.answer("напиши название для кнопки обычным текстом")    

@router.callback_query(F.data.startswith("admin_ban_"))
async def process_admin_ban(callback: CallbackQuery):
    print(f" Нажата кнопка бана! Callback data: {callback.data}")
    
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    await callback.answer("Пользователь заблокирован!", show_alert=True)
    
    try:
        user_to_ban = int(callback.data.split("_")[2])
        await ban_user(user_to_ban)
        print(f"Юзер {user_to_ban} успешно добавлен в бан-лист.")
    except Exception as e:
        print(f"Ошибка бана: {e}")
        return
    
    # Обновляем описание видео
    if callback.message.caption:
        await callback.message.edit_caption(
            caption=callback.message.caption + f"\n\n🛑 <b>АВТОР ЗАБАНЕН ФОРЕВЕР!</b>"
        )

@router.message(Command("unban"))
async def process_unban_command(message: Message):
    # Проверяем, админ ли пишет
    if message.from_user.id != config.tg_bot.admin_id:
        return

    # Разбираем текст команды. Ожидаем формат: /unban 123456789
    command_parts = message.text.split()
    
    if len(command_parts) < 2:
        await message.reply("❌ Не указан ID пользователя! Пример: <code>/unban 123456789</code>")
        return
        
    user_id_str = command_parts[1]
    
    # Проверяем, что админ ввёл именно число, а не текст или юзернейм
    if not user_id_str.isdigit():
        await message.reply("❌ ID пользователя должен состоять только из цифр! Скопируй его из сообщения предложки.")
        return
        
    user_to_unban = int(user_id_str)
    
    try:
        # Удаляем из базы данных
        await unban_user(user_to_unban)
        await message.reply(f"✅ Пользователь с ID <code>{user_to_unban}</code> успешно разбанен и снова может предлагать мемы!")
    except Exception as e:
        await message.reply(f"❌ Ошибка при разбане: {e}")

@router.message(Command("top"))
@router.message(F.text == LEXICON['top_button'])
async def process_top_command(message: Message):
    top_users = await get_top_contributors()
    
    if not top_users:
        await message.answer("🏆 Таблица лидеров пуста. Будь первым, кто предложит одобренный мем! Используй /addmeme")
        return
        
    text = "🏆 <b>ТОП-10 ОТПРАВИТЕЛЕЙ МЕМОВ:</b>\nЕсли написано @anon то у отправителя нету username\n\n"
    
    # Красивые медальки для первых трех мест
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    for index, user in enumerate(top_users, start=1):
        medal = medals.get(index, f"{index}.")
        text += f"{medal} @{user['sender_username']} — <b>{user['meme_count']}</b> мемов\n"
        
    await message.answer(text)