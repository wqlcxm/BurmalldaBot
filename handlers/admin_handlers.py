from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.db_core import add_meme, ban_user
from config_data.config import load_config

router = Router()
config = load_config()

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