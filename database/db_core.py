from pathlib import Path

from aiogram.types import User
import aiosqlite

DB_DIR = Path(__file__).resolve().parent
DEFAULT_DB = 'memes_old.db'
LEGACY_DB = 'memes.db'

if (DB_DIR / DEFAULT_DB).exists():
    DB_PATH = str(DB_DIR / DEFAULT_DB)
else:
    DB_PATH = str(DB_DIR / LEGACY_DB)


def normalize_username(username: str | None) -> str:
    if username is None:
        return '@anon'

    clean_username = str(username).strip()
    if not clean_username:
        return '@anon'

    if clean_username.startswith('@'):
        return clean_username

    return f'@{clean_username}'


def format_username(username: str | None) -> str:
    return normalize_username(username)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                sender_id INTEGER DEFAULT 0,
                sender_username TEXT DEFAULT '@anon',
                views INTEGER NOT NULL DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                inline_description_enabled INTEGER DEFAULT 1,
                caption_enabled INTEGER DEFAULT 1
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS maintenance_allowed_users (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await db.commit()

        await db.execute("""
            UPDATE memes
            SET sender_username = CASE
                WHEN sender_username IS NULL OR TRIM(sender_username) = '' THEN '@anon'
                WHEN sender_username LIKE '@%' THEN sender_username
                ELSE '@' || TRIM(sender_username)
            END
            WHERE sender_username IS NOT NULL OR sender_username IS NULL
        """)
        await db.execute("""
            UPDATE users
            SET username = CASE
                WHEN username IS NULL OR TRIM(username) = '' THEN '@anon'
                WHEN username LIKE '@%' THEN username
                ELSE '@' || TRIM(username)
            END
            WHERE username IS NOT NULL OR username IS NULL
        """)
        await db.commit()

        try:
            await db.execute('ALTER TABLE memes ADD COLUMN sender_id INTEGER DEFAULT 0')
            await db.commit()
            print('Колонка sender_id успешно добавлена в старую БД.')
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE memes ADD COLUMN sender_username TEXT DEFAULT '@anon'")
            await db.commit()
            print('Колонка sender_username успешно добавлена в старую БД.')
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE users ADD COLUMN inline_description_enabled INTEGER DEFAULT 1")
            await db.commit()
            print('Колонка inline_description_enabled успешно добавлена в таблицу users.')
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE users ADD COLUMN caption_enabled INTEGER DEFAULT 1")
            await db.commit()
            print('Колонка caption_enabled успешно добавлена в таблицу users.')
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE memes ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
            await db.commit()
            print('Колонка views успешно добавлена в старую БД.')
        except aiosqlite.OperationalError:
            pass


async def ban_user(user_id: int):
    """Добавляет юзера в бан-лист."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)', (user_id,))
        await db.commit()


async def unban_user(user_id: int):
    """Удаляет юзера из бан-листа."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
        await db.commit()


async def is_user_banned(user_id: int) -> bool:
    """Проверяет, находится ли юзер в бане."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None


async def set_maintenance_mode(enabled: bool) -> None:
    """Включает или выключает режим техработ."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            ('maintenance_mode', '1' if enabled else '0')
        )
        await db.commit()


async def get_bot_setting(key: str, default: str = '') -> str:
    """Возвращает значение настройки из таблицы bot_settings."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM bot_settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default


async def set_bot_setting(key: str, value: str) -> None:
    """Сохраняет значение настройки в таблице bot_settings."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value)
        )
        await db.commit()


async def is_maintenance_enabled() -> bool:
    """Проверяет, включён ли режим техработ."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM bot_settings WHERE key = ?', ('maintenance_mode',)) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0] == '1')


async def add_allowed_user(user_id: int) -> None:
    """Добавляет пользователя в список исключений для режима техработ."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO maintenance_allowed_users (user_id) VALUES (?)', (user_id,))
        await db.commit()


async def remove_allowed_user(user_id: int) -> None:
    """Удаляет пользователя из списка исключений для режима техработ."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM maintenance_allowed_users WHERE user_id = ?', (user_id,))
        await db.commit()


async def is_user_allowed(user_id: int) -> bool:
    """Проверяет, разрешён ли пользователю доступ в режиме техработ."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM maintenance_allowed_users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None


async def is_inline_description_enabled(user_id: int) -> bool:
    """Проверяет, включено ли описание под результатами inline-запроса для конкретного пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT inline_description_enabled FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            # По умолчанию включено (1)
            return row[0] != 0 if row else True


async def set_inline_description_enabled(user_id: int, enabled: bool) -> None:
    """Включает или отключает описание под результатами inline-запроса для конкретного пользователя."""
    async with aiosqlite.


async def is_caption_enabled(user_id: int) -> bool:
    """Проверяет, включена ли подпись под видео для конкретного пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT caption_enabled FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            # По умолчанию включено (1)
            return row[0] != 0 if row else True


async def set_caption_enabled(user_id: int, enabled: bool) -> None:
    """Включает или отключает подпись под видео для конкретного пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO users (user_id, username, caption_enabled) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               caption_enabled = excluded.caption_enabled''',
            (user_id, '@anon', 1 if enabled else 0)
        )
        await db.commit()connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO users (user_id, username, inline_description_enabled) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               inline_description_enabled = excluded.inline_description_enabled''',
            (user_id, '@anon', 1 if enabled else 0)
        )
        await db.commit()


async def get_allowed_users() -> list[int]:
    """Возвращает список пользователей, которым разрешён доступ в режиме техработ."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM maintenance_allowed_users ORDER BY user_id') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def register_user(user_id: int, username: str | None = None) -> None:
    """Сохраняет или обновляет пользователя в базе для последующей рассылки."""
    normalized_username = normalize_username(username)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO users (user_id, username, score) VALUES (?, ?, 0)
               ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username''',
            (user_id, normalized_username)
        )
        await db.commit()


async def get_all_user_ids() -> list[int]:
    """Возвращает список идентификаторов зарегистрированных пользователей."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def add_meme(
    file_id: str,
    title: str,
    user: User | None = None,
    sender_id: int | None = None,
    sender_username: str | None = None,
):
    if sender_id is None:
        sender_id = user.id if user else 0

    if sender_username is None:
        if user and user.username:
            sender_username = user.username
        elif user:
            sender_username = f"{user.first_name or ''} {user.last_name or ''}".strip() or 'Аноним'
        else:
            sender_username = 'anon'

    sender_username = normalize_username(sender_username)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO memes (file_id, title, sender_id, sender_username, views) VALUES (?, ?, ?, ?, 0)',
            (file_id, title, sender_id, sender_username)
        )
        await db.execute(
            '''INSERT INTO users (user_id, username, score) VALUES (?, ?, 1)
               ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               score = score + 1''',
            (sender_id, sender_username)
        )
        await db.commit()


async def increment_meme_views(meme_id: int) -> None:
    """Увеличивает счётчик просмотров для выбранного мема."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE memes SET views = views + 1 WHERE id = ?', (meme_id,))
        await db.commit()


async def get_all_memes() -> list[dict]:
    """Возвращает список всех мемов из базе в порядке добавления."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM memes ORDER BY id ASC') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_meme_by_id(meme_id: int) -> dict | None:
    """Возвращает конкретный мем по его ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def reset_top_contributors() -> None:
    """Очищает рейтинг пользователей и начинает считать заново."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM users')
        await db.commit()


async def get_top_contributors() -> list[dict]:
    """Возвращает топ-10 пользователей по количеству одобренных мемов."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT username AS sender_username, score AS meme_count
            FROM users
            WHERE score > 0
            ORDER BY score DESC, username ASC
            LIMIT 10
        ''') as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                row_data = dict(row)
                row_data['sender_username'] = normalize_username(row_data['sender_username'])
                result.append(row_data)
            return result


async def get_top_memes(limit: int = 3) -> list[dict]:
    """Возвращает самые популярные мемы по числу просмотров."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT id, title, views FROM memes ORDER BY views DESC, id ASC LIMIT ?',
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_random_meme() -> dict | None:
    """Возвращает случайный мем из базы данных."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT id, title, file_id, views FROM memes ORDER BY RANDOM() LIMIT 1') as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None