import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from database.db_core import add_meme, ban_user
from config_data.config import load_config

router = Router()
config = load_config()
DB_PATH = 'database/memes.db'

class RenameMemeState(StatesGroup):
    waiting_for_new_title = State()

@router.callback_query(F.data.startswith("admin_accept"))
async def process_moderation_choice(callback: CallbackQuery):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    await callback.answer("Мем одобрен!")
    
    # Безопасно парсим callback_data (формат: admin_accept:ID:username)
    data_parts = callback.data.split(":")
    
    # Если кнопка новая — берём ID и ник автора. Если старая — ставим дефолтные
    if len(data_parts) >= 3:
        sender_id = int(data_parts[1])
        sender_username = data_parts[2]
    else:
        # Для старых кнопок, отправленных до обновления
        sender_id = config.tg_bot.admin_id  # или 0
        sender_username = "anon"

    caption = callback.message.caption or ""
    try:
        title = caption.split("Название для кнопки:")[1].split("\n")[0].strip()
    except Exception:
        title = "Без названия"

    file_id = callback.message.video.file_id
    
    # Сохраняем в базу данных
    from database.db_core import add_meme
    await add_meme(title=title, file_id=file_id, sender_id=sender_id, sender_username=sender_username)
    
    await callback.message.edit_caption(
        caption=f"💚 <b>МЕМ ОДОБРЕН И ДОБАВЛЕН!</b>\n\n<b>Название:</b> {title}\n<b>Автор:</b> @{sender_username}"
    )

@router.callback_query(F.data.startswith("admin_ban_"))
async def process_admin_ban(callback: CallbackQuery):
    print(f" Нажата кнопка бана! Callback data: {callback.data}") # Это выведется в консоль
    
    # Проверка: админ ли нажал?
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    # Сразу отвечаем на колбэк, чтобы убрать вечную загрузку
    await callback.answer("Пользователь заблокирован!", show_alert=True)
    
    # Вытаскиваем ID
    try:
        user_to_ban = int(callback.data.split("_")[2])
        print(f"ID для бана определен: {user_to_ban}")
        
        # Добавляем в базу данных
        await ban_user(user_to_ban)
        print("Юзер успешно добавлен в таблицу banned_users")
    except Exception as e:
        print(f"Ошибка при парсинге ID или записи в БД: {e}")
        return
    
    # Обновляем текст сообщения
    try:
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=callback.message.caption + f"\n\n🛑 <b>АВТОР ЗАБАНЕН ФОРЕВЕР!</b>"
            )
        else:
            await callback.message.edit_text(
                text=callback.message.text + f"\n\n🛑 <b>АВТОР ЗАБАНЕН ФОРЕВЕР!</b>"
            )
    except Exception as e:
        print(f"Не удалось обновить текст сообщения: {e}")

@router.message(Command("admin"))
async def process_admin_menu(message: Message):
    # Жесткий фейсконтроль!
    if message.from_user.id != config.tg_bot.admin_id:
        SHOO_VIDEO_FILE_ID = "BAACAgUAAxkBAAIBWWpbeXx8cMUzRRM3zav3hF0Vr6dQAALzHAAC4BPgVn4X2nhyIlIhPQQ"
        await message.answer_video(
            video=SHOO_VIDEO_FILE_ID,
            caption="Ыы не админ!"
        )
        # Подсказка: вместо текста можешь отправить видео/стикер: await message.answer_sticker("file_id_стикера")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Управление мемами", callback_data="admin_manage_memes")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")]
    ])
    await message.answer("🛠 <b>ДОБРО ПОЖАЛОВАТЬ В АДМИН-ПАНЕЛЬ Бурмалды!</b>\n Выберите действие:", reply_markup=kb)

# Закрыть админку
@router.callback_query(F.data == "admin_close")
async def close_admin(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

# Вывод списка мемов для редактирования/удаления
@router.callback_query(F.data == "admin_manage_memes")
@router.callback_query(F.data.startswith("admin_page_"))
async def admin_manage_memes(callback: CallbackQuery):
    await callback.answer()
    
    # Пагинация (постраничный вывод), если мемов много
    page = int(callback.data.split("_")[2]) if callback.data.startswith("admin_page_") else 0
    limit = 5
    offset = page * limit

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Берем порцию мемов
        async with db.execute('SELECT id, title FROM memes LIMIT ? OFFSET ?', (limit, offset)) as cursor:
            memes = await cursor.fetchall()
        # Считаем общее количество
        async with db.execute('SELECT COUNT(id) FROM memes') as cursor:
            total_memes = (await cursor.fetchone())[0]

    if not memes:
        await callback.message.edit_text("📦 В базе данных пока нет меums.", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_close")]]))
        return

    text = f"📝 <b>Управление мемами (Страница {page + 1}):</b>\n\n Выберите мем для редактирования или удаления:"
    kb = []
    
    # Кнопка для каждого мема
    for meme in memes:
        kb.append([InlineKeyboardButton(text=f"🎬 {meme['title']}", callback_data=f"medit_{meme['id']}")])

    # Кнопки Назад / Вперед для страниц
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_page_{page - 1}"))
    if offset + limit < total_memes:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin_page_{page + 1}"))
    if nav_buttons:
        kb.append(nav_buttons)
        
    kb.append([InlineKeyboardButton(text="🔙 В главное меню админки", callback_data="admin_menu_back")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Возврат в корень админки
@router.callback_query(F.data == "admin_menu_back")
async def back_to_admin_root(callback: CallbackQuery):
    await callback.message.delete()
    # Просто вызываем команду меню заново, сымитировав сообщение
    await process_admin_menu(callback.message)
    await callback.answer()

# Карточка конкретного мема (Удалить / Переименовать)
@router.callback_query(F.data.startswith("medit_"))
async def edit_meme_card(callback: CallbackQuery):
    await callback.answer()
    meme_id = int(callback.data.split("_")[1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT title, file_id FROM memes WHERE id = ?', (meme_id,)) as cursor:
            meme = await cursor.fetchone()

    if not meme:
        await callback.message.edit_text("Мем не найден.")
        return

    text = f"⚙️ <b>Редактирование мема:</b>\n\n<b>Название:</b> {meme['title']}\n<b>ID в базе:</b> {meme_id}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"mrename_{meme_id}")],
        [InlineKeyboardButton(text="🗑 Удалить мем", callback_data=f"mdel_{meme_id}")],
        [InlineKeyboardButton(text="🔙 К списку мемов", callback_data="admin_manage_memes")]
    ])
    
    # Админу также шлется само видео, чтобы он вспомнил что это, но в данном случае просто редактируем текст меню
    await callback.message.edit_text(text, reply_markup=kb)

# ДЕЙСТВИЕ: УДАЛЕНИЕ МЕМА
@router.callback_query(F.data.startswith("mdel_"))
async def delete_meme_action(callback: CallbackQuery):
    meme_id = int(callback.data.split("_")[1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM memes WHERE id = ?', (meme_id,))
        await db.commit()
        
    await callback.answer("🗑 Мем успешно удален!", show_alert=True)
    # Возвращаем админа к списку мемов
    await admin_manage_memes(callback)

# ДЕЙСТВИЕ: ЗАПУСК ПЕРЕИМЕНОВАНИЯ (Вход в FSM)
@router.callback_query(F.data.startswith("mrename_"))
async def rename_meme_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    meme_id = int(callback.data.split("_")[1])
    
    await state.set_state(RenameMemeState.waiting_for_new_title)
    await state.update_data(meme_id=meme_id, menu_msg_id=callback.message.message_id)
    
    await callback.message.edit_text("✏️ <b>Введите новое название для этого мема:</b>\n\n<i>Качество (типа 720p) применится автоматически, если оно было в названии, или напишите как надо.</i>")

# ЛОВИМ НОВОЕ НАЗВАНИЕ
@router.message(RenameMemeState.waiting_for_new_title)
async def rename_meme_finish(message: Message, state: FSMContext):
    new_title = message.text.strip()
    state_data = await state.get_data()
    meme_id = state_data['meme_id']
    menu_msg_id = state_data['menu_msg_id']
    
    await state.clear()
    
    # Обновляем в базе
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE memes SET title = ? WHERE id = ?', (new_title, meme_id))
        await db.commit()
        
    await message.answer(f"✅ Мем успешно переименован в: <b>{new_title}</b>")
    
    # Удаляем старое меню админки, чтобы не плодить сообщения, и вызываем новое
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=menu_msg_id)
    except Exception:
        pass
        
    # Выводим админку заново
    await process_admin_menu(message)