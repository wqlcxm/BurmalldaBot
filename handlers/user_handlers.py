import re
# import random
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineQuery,
    ChosenInlineResult,
    InlineQueryResultArticle,
    InlineQueryResultCachedVideo,
    InputTextMessageContent,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from lexicons.lexicon import LEXICON
from keyboards.user_keyboards import (
    create_main_menu,
    create_memes_inline_keyboard,
    create_cancel_menu,
    create_settings_keyboard,
)
from keyboards.admin_keyboards import create_moderation_keyboard
from database.db_core import (
    get_all_memes,
    get_meme_by_id,
    ban_user,
    get_random_meme,
    unban_user,
    get_top_contributors,
    reset_top_contributors,
    format_username,
    register_user,
    increment_meme_views,
    get_top_memes,
    is_inline_description_enabled,
    set_inline_description_enabled,
    is_caption_enabled,
    set_caption_enabled,
)
from config_data.config import load_config

router = Router()
config = load_config()


def build_inline_query_results(
    memes: list[dict],
    show_description: bool = True,
    show_caption: bool = True,
) -> list[InlineQueryResultCachedVideo]:
    results: list[InlineQueryResultCachedVideo] = []
    for meme in memes:
        title = meme.get('title') or 'Без названия'
        views = meme.get('views', 0)
        file_id = meme.get('file_id', '')
        
        # Пропускаем мемы с невалидным file_id
        if not file_id or len(file_id) < 20:
            continue
            
        description = f"👁️ Просмотров: {views}" if show_description else ''
        caption = f"🎬 <b>{title}</b>\n\n👁️ Просмотров: {views}" if show_caption else ''
        
        results.append(
            InlineQueryResultCachedVideo(
                id=f"meme:{meme['id']}",
                video_file_id=file_id,
                title=title,
                description=description,
                caption=caption,
                parse_mode='HTML',
            )
        )
    return results


# Состояния FSM для добавления мема
class AddMemeState(StatesGroup):
    upload_video = State()  # Ожидание видеоролика
    type_title = State()    # Ожидание названия кнопки

@router.inline_query()
async def process_inline_query(query: InlineQuery):
    search_text = (query.query or '').strip().lower()
    memes = await get_all_memes()
    user_id = query.from_user.id

    if search_text:
        filtered_memes = [
            meme for meme in memes
            if search_text in (meme.get('title') or '').lower()
        ]
    else:
        filtered_memes = sorted(memes, key=lambda meme: meme.get('views', 0), reverse=True)
show_caption = await is_caption_enabled(user_id)
        results = build_inline_query_results(filtered_memes[:20], show_description=show_description, show_caption=show_caption)
    else:
        results = [
            InlineQueryResultArticle(
                id='empty-results',
                title='Пока нет подходящих мемов',
                input_message_content=InputTextMessageContent(
                    message_text='📦 В базе пока нет мемов, подходящих под этот запрос.'
                ),
            )
        ]

    if results:
                )
        ]

    await query.answer(results=results, cache_time=0, is_personal=False)


@router.chosen_inline_result()
async def process_chosen_inline_result(result: ChosenInlineResult):
    if not result.result_id.startswith('meme:'):
        return

    try:
        meme_id = int(result.result_id.split(':', 1)[1])
    except ValueError:
        return

    await increment_meme_views(meme_id)


@router.callback_query(F.data == 'toggle_inline_description')
async def process_toggle_inline_description(callback: CallbackQuery):
    user_id = callback.from_user.id
    enabled = await is_inline_description_enabled(user_id)
    await set_inline_description_enabled(user_id, not enabled)

    new_enabled = await is_inline_description_enabled(user_id)
    caption_enabled = await is_caption_enabled(user_id)
    await callback.message.edit_text(
        text=LEXICON['settings_text'].format(
            description_status='включено' if new_enabled else 'выключено',
            caption_status='включено' if caption_enabled else 'выключено'
        ),
        reply_markup=create_settings_keyboard(new_enabled, caption_enabled)
    )
    await callback.answer('Настройки обновлены')


@router.callback_query(F.data == 'toggle_caption')
async def process_toggle_caption(callback: CallbackQuery):
    user_id = callback.from_user.id
    enabled = await is_caption_enabled(user_id)
    await set_caption_enabled(user_id, not enabled)

    new_enabled = await is_caption_enabled(user_id)
    description_enabled = await is_inline_description_enabled(user_id)
    await callback.message.edit_text(
        text=LEXICON['settings_text'].format(
            description_status='включено' if description_enabled else 'выключено',
            caption_status='включено' if new_enabled else 'выключено'
        ),
        reply_markup=create_settings_keyboard(description_enabled, new_enabled)
    )
    await callback.answer('Настройки обновлены')


@router.message(F.text == LEXICON['settings_button'])
async def process_settings_request(message: Message):
    user_id = message.from_user.id
    description_enabled = await is_inline_description_enabled(user_id)
    caption_enabled = await is_caption_enabled(user_id)
    await message.answer(
        text=LEXICON['settings_text'].format(
            description_status='включено' if description_enabled else 'выключено',
            caption_status='включено' if caption_enabled else 'выключено'
        ),
        reply_markup=create_settings_keyboard(description_enabled, caption_enabled)
    )


@router.message(CommandStart())
@router.message(F.text == LEXICON['back_button'])
async def process_start_command(message: Message, state: FSMContext):
    await state.clear()
    await register_user(message.from_user.id, message.from_user.username)
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
    await increment_meme_views(meme_id)
    updated_meme = await get_meme_by_id(meme_id)
    await callback.answer()
    try:
        chat_id = callback.message.chat.id if callback.message else callback.from_user.id
        await callback.bot.send_video(
            chat_id=chat_id,
            video=updated_meme['file_id'],
            caption=f"🎬 <b>{updated_meme['title']}</b>\n\n👁️ Просмотров: {updated_meme.get('views', 0)}"
        )
    except TelegramBadRequest as exc:
        if "wrong file_id" in str(exc).lower() or "temporarily unavailable" in str(exc).lower():
            await callback.bot.send_message(
                chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
                text=LEXICON['meme_unavailable'].format(title=updated_meme['title'])
            )
        else:
            await callback.bot.send_message(
                chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
                text=LEXICON['error']
            )
    except Exception:
        if callback.message:
            await callback.message.answer(text=LEXICON['error'])
        else:
            await callback.bot.send_message(chat_id=callback.from_user.id, text=LEXICON['error'])

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

    username = message.from_user.username or f"id{message.from_user.id}"
    # Отправляем видео тебе в ЛС на модерацию
    await bot.send_video(
        chat_id=config.tg_bot.admin_id,
        video=file_id,
        caption=f"<b>📢 Предложен новый мем!</b>\n\n<b>Название для кнопки:</b> {full_title}\n<b>Отправил:</b> {format_username(username)} (ID: {message.from_user.id})",
        reply_markup=create_moderation_keyboard(user_id=message.from_user.id, username=username)
    )

# Если вместо видео юзер отправил текст или что-то не то
@router.message(AddMemeState.upload_video)
async def process_add_meme_video_invalid(message: Message):
    await message.answer("отправь именно **видеоролик**!")

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

@router.message(Command("reset_top"))
async def process_reset_top_command(message: Message):
    if message.from_user.id != config.tg_bot.admin_id:
        return

    await reset_top_contributors()
    await message.reply("✅ Рейтинг пользователей очищен. Топ начнёт набираться заново.")


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
    top_memes = await get_top_memes(limit=3)
    top_users = await get_top_contributors()

    if not top_memes and not top_users:
        await message.answer("📦 В базе пока нет мемов — стань первым, кто добавит их через /addmeme")
        return

    text = LEXICON['top_response']
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for index, meme in enumerate(top_memes, start=1):
        medal = medals.get(index, f"{index}.")
        text += f"{medal} <b>{meme['title']}</b> — <b>{meme.get('views', 0)}</b> просмотров\n"

    if top_users:
        text += f"\n{LEXICON['top_contributors_response']}"
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for index, user in enumerate(top_users, start=1):
            medal = medals.get(index, f"{index}.")
            text += f"{medal} {format_username(user['sender_username'])} — <b>{user['meme_count']}</b> мемов\n"

    await message.answer(text)

@router.message(Command("random"))
@router.message(F.text == LEXICON['random_meme_button'])
async def process_random_meme_command(message: Message):
    # Получаем случайный мем из базы данных
    meme = await get_random_meme()
    
    if not meme:
        await message.answer("📦 В базе пока нет мемов. Будь первым, кто предложит годноту через /addmeme !")
        return
        
    await increment_meme_views(meme['id'])
    updated_meme = await get_meme_by_id(meme['id'])

    try:
        await message.answer_video(
            video=updated_meme['file_id'],
            caption=f"🎲 Твой случайный мем дня:\n<b>{updated_meme['title']}</b>\n\n👁️ Просмотров: {updated_meme.get('views', 0)}"
        )
    except TelegramBadRequest as exc:
        if "wrong file_id" in str(exc).lower() or "temporarily unavailable" in str(exc).lower():
            await message.answer(LEXICON['meme_unavailable'].format(title=updated_meme['title']))
        else:
            await message.answer(LEXICON['error'])
    except Exception:
        await message.answer(LEXICON['error'])


@router.message(F.text == LEXICON['about_button'])
async def process_about_request(message: Message):
    await message.answer(text=LEXICON['about_text'])