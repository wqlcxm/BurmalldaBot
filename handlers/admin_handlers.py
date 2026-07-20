import aiosqlite
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from database import db_core
from database.db_core import (
    add_allowed_user,
    add_meme,
    ban_user,
    format_username,
    get_all_user_ids,
    get_allowed_users,
    is_maintenance_enabled,
    remove_allowed_user,
    set_maintenance_mode,
)
from config_data.config import load_config
from lexicons.lexicon import LEXICON

router = Router()
config = load_config()
DB_PATH = db_core.DB_PATH


def get_db_path() -> str:
    return db_core.DB_PATH


def build_maintenance_menu_text(enabled: bool, allowed_users: list[int]) -> str:
    status_text = "ВКЛЮЧЕНЫ" if enabled else "ВЫКЛЮЧЕНЫ"
    users_text = ", ".join(str(user_id) for user_id in allowed_users) if allowed_users else "пока нет"
    return (
        f"🚧 <b>Техработы: {status_text}</b>\n\n"
        f"👤 Исключений: {len(allowed_users)}\n"
        f"🧾 Кто может пользоваться ботом: {users_text}"
    )


def build_allowed_users_text(allowed_users: list[int]) -> str:
    if allowed_users:
        users_text = "\n".join(str(user_id) for user_id in allowed_users)
        return f"👤 <b>Исключения:</b>\n\n{users_text}"
    return "👤 <b>Исключения:</b>\n\nПока пусто"


class RenameMemeState(StatesGroup):
    waiting_for_new_title = State()


class RejectMemeState(StatesGroup):
    waiting_for_reason = State()


class BroadcastState(StatesGroup):
    waiting_for_broadcast_text = State()


class MaintenanceState(StatesGroup):
    waiting_for_user_id = State()


@router.callback_query(F.data.startswith("admin_accept"))
async def process_moderation_choice(callback: CallbackQuery, bot: Bot):
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

    try:
        if sender_id and sender_id != config.tg_bot.admin_id:
            await bot.send_message(
                chat_id=sender_id,
                text=LEXICON['meme_approved_notification'].format(title=title)
            )
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {sender_id}: {e}")
    
    await callback.message.edit_caption(
        caption=f"💚 <b>МЕМ ОДОБРЕН И ДОБАВЛЕН!</b>\n\n<b>Название:</b> {title}\n<b>Автор:</b> {format_username(sender_username)}"
    )

@router.callback_query(F.data.startswith("admin_reject"))
async def process_reject_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    try:
        await callback.answer()
    except Exception:
        pass

    data_parts = callback.data.split(":")
    if len(data_parts) >= 3:
        sender_id = int(data_parts[1])
        sender_username = data_parts[2]
    else:
        sender_id = config.tg_bot.admin_id
        sender_username = "anon"

    caption = callback.message.caption or ""
    try:
        title = caption.split("Название для кнопки:")[1].split("\n")[0].strip()
    except Exception:
        title = "Без названия"

    await state.set_state(RejectMemeState.waiting_for_reason)
    await state.update_data(
        sender_id=sender_id,
        sender_username=sender_username,
        title=title,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        callback_data=callback.data
    )

    try:
        await callback.message.edit_caption(
            caption=f"{caption}\n\n⏳ Ожидаю причину отказа..."
        )
    except Exception:
        pass

    await callback.message.answer(
        "❌ Напиши причину отказа для этого мема.\n\n"
        "Отправь текст, и я передам его автору.\n"
        "Для отмены отправь /cancel"
    )


@router.message(RejectMemeState.waiting_for_reason, F.text)
async def process_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != config.tg_bot.admin_id:
        return

    if message.text and message.text.strip().startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Отказ отменён.")
        return

    reason = message.text.strip()
    if not reason:
        await message.answer("Введите причину отказа текстом или отправьте /cancel для отмены.")
        return

    state_data = await state.get_data()
    sender_id = state_data.get("sender_id")
    sender_username = state_data.get("sender_username")
    title = state_data.get("title")
    chat_id = state_data.get("chat_id")
    message_id = state_data.get("message_id")
    callback_data = state_data.get("callback_data") or ""

    if sender_id is None and callback_data:
        try:
            sender_id = int(callback_data.split(":")[1])
        except Exception:
            sender_id = None

    await state.clear()

    notification_sent = False
    try:
        if sender_id and sender_id != config.tg_bot.admin_id:
            await bot.send_message(
                chat_id=sender_id,
                text=LEXICON['meme_rejected_notification'].format(title=title, reason=reason)
            )
            notification_sent = True
    except Exception as e:
        print(f"Не удалось отправить уведомление об отказе пользователю {sender_id}: {e}")

    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"❌ <b>МЕМ ОТКЛОНЕН</b>\n\n<b>Название:</b> {title}\n<b>Причина:</b> {reason}\n<b>Автор:</b> {format_username(sender_username)}"
        )
    except Exception as e:
        print(f"Не удалось обновить сообщение модерации: {e}")

    if notification_sent:
        await message.answer(f"✅ Причина отказа сохранена и отправлена автору.\n\n<b>Причина:</b> {reason}")
    else:
        await message.answer(f"⚠️ Причина отказа сохранена, но не удалось отправить уведомление автору.\n\n<b>Причина:</b> {reason}")


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

@router.callback_query(F.data == "admin_maintenance_menu")
async def open_maintenance_menu(callback: CallbackQuery):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    maintenance_enabled = await is_maintenance_enabled()
    allowed_users = await get_allowed_users()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить техработы", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton(text="🔐 Управление исключениями", callback_data="admin_manage_allowed_users")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_open_main")],
    ])
    await callback.message.edit_text(
        build_maintenance_menu_text(maintenance_enabled, allowed_users),
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "admin_toggle_maintenance")
async def toggle_maintenance(callback: CallbackQuery):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    current_state = await is_maintenance_enabled()
    new_state = not current_state
    await set_maintenance_mode(new_state)
    await callback.answer(
        f"Режим техработ {'включён' if new_state else 'выключен'}",
        show_alert=True
    )

    allowed_users = await get_allowed_users()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить техработы", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton(text="🔐 Управление исключениями", callback_data="admin_manage_allowed_users")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_open_main")],
    ])
    await callback.message.edit_text(
        build_maintenance_menu_text(new_state, allowed_users),
        reply_markup=kb
    )


@router.callback_query(F.data == "admin_manage_allowed_users")
async def manage_allowed_users(callback: CallbackQuery):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить исключение", callback_data="admin_add_allowed_user")],
        [InlineKeyboardButton(text="➖ Удалить исключение", callback_data="admin_remove_allowed_user")],
        [InlineKeyboardButton(text="👀 Показать исключения", callback_data="admin_show_allowed_users")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_open_main")],
    ])
    await callback.message.edit_text(
        "🔐 <b>Управление исключениями</b>\n\n"
        "Выберите действие для доступа в режиме техработ:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_allowed_user")
async def start_add_allowed_user(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    await state.set_state(MaintenanceState.waiting_for_user_id)
    await state.update_data(action="add")
    await callback.message.edit_text(
        "➕ <b>Введите ID пользователя</b>, которому разрешить доступ при техработах.\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_remove_allowed_user")
async def start_remove_allowed_user(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    await state.set_state(MaintenanceState.waiting_for_user_id)
    await state.update_data(action="remove")
    await callback.message.edit_text(
        "➖ <b>Введите ID пользователя</b>, которого нужно удалить из исключений.\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_show_allowed_users")
async def show_allowed_users(callback: CallbackQuery):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    users = await get_allowed_users()
    text = build_allowed_users_text(users)

    await callback.message.edit_text(text)
    await callback.answer()


@router.callback_query(F.data == "admin_open_main")
async def open_main_admin_menu(callback: CallbackQuery):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚧 Тех. работы", callback_data="admin_maintenance_menu")],
        [InlineKeyboardButton(text="🔐 Исключения", callback_data="admin_manage_allowed_users")],
        [InlineKeyboardButton(text="📂 Управление мемами", callback_data="admin_manage_memes")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")]
    ])
    await callback.message.edit_text(
        "🛠 <b>ДОБРО ПОЖАЛОВАТЬ В АДМИН-ПАНЕЛЬ Бурмалды!</b>\n\n"
        "Выберите действие:",
        reply_markup=kb
    )
    await callback.answer()


@router.message(MaintenanceState.waiting_for_user_id, F.text)
async def process_allowed_user_id(message: Message, state: FSMContext):
    if message.from_user.id != config.tg_bot.admin_id:
        return

    if message.text and message.text.strip().startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Ввод исключения отменён.")
        return

    state_data = await state.get_data()
    action = state_data.get("action", "add")

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный numeric ID пользователя.")
        return

    if action == "add":
        await add_allowed_user(user_id)
        await message.answer(f"✅ Пользователь {user_id} добавлен в исключения.")
    else:
        await remove_allowed_user(user_id)
        await message.answer(f"✅ Пользователь {user_id} удалён из исключений.")

    await state.clear()
    await process_admin_menu(message)


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
        [InlineKeyboardButton(text="🚧 Тех. работы", callback_data="admin_maintenance_menu")],
        [InlineKeyboardButton(text="🔐 Исключения", callback_data="admin_manage_allowed_users")],
        [InlineKeyboardButton(text="📂 Управление мемами", callback_data="admin_manage_memes")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")]
    ])
    await message.answer("🛠 <b>ДОБРО ПОЖАЛОВАТЬ В АДМИН-ПАНЕЛЬ Бурмалды!</b>\n Выберите действие:", reply_markup=kb)

# Закрыть админку
@router.callback_query(F.data == "admin_close")
async def close_admin(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.tg_bot.admin_id:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    await callback.answer()
    await state.set_state(BroadcastState.waiting_for_broadcast_text)
    await callback.message.edit_text(
        "📢 <b>Введите текст для рассылки</b>\n\n"
        "Отправьте сообщение, и я разошлю его всем пользователям.\n"
        "Для отмены отправьте /cancel"
    )


@router.message(BroadcastState.waiting_for_broadcast_text)
async def process_broadcast_text(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != config.tg_bot.admin_id:
        return

    if message.text and message.text.strip().startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        await process_admin_menu(message)
        return

    text_to_send = message.text or message.caption or ""
    if not text_to_send.strip():
        await message.answer("❌ Отправьте текст сообщения или /cancel для отмены.")
        return

    await state.clear()
    await message.answer("⏳ Рассылка запущена...")

    user_ids = await get_all_user_ids()
    sent_count = 0
    failed_count = 0

    for user_id in user_ids:
        try:
            await bot.send_message(chat_id=user_id, text=text_to_send, parse_mode="HTML")
            sent_count += 1
        except Exception:
            failed_count += 1

    await message.answer(
        f"✅ Рассылка завершена.\n"
        f"Отправлено: <b>{sent_count}</b>\n"
        f"Не доставлено: <b>{failed_count}</b>"
    )
    await process_admin_menu(message)


# Вывод списка мемов для редактирования/удаления
@router.callback_query(F.data == "admin_manage_memes")
@router.callback_query(F.data.startswith("admin_page_"))
async def admin_manage_memes(callback: CallbackQuery):
    await callback.answer()
    
    # Пагинация (постраничный вывод), если мемов много
    page = int(callback.data.split("_")[2]) if callback.data.startswith("admin_page_") else 0
    limit = 5
    offset = page * limit

    async with aiosqlite.connect(get_db_path()) as db:
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
    
    async with aiosqlite.connect(get_db_path()) as db:
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
    
    async with aiosqlite.connect(get_db_path()) as db:
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
    async with aiosqlite.connect(get_db_path()) as db:
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