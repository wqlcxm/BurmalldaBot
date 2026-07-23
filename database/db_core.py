from pathlib import Path
import random
import shutil
import sqlite3

from aiogram.types import User
import aiosqlite

from database.migrations import run_migrations

DB_DIR = Path(__file__).resolve().parent

# Рабочая БД для чтения и записи: сюда бот пишет новые мемы и юзеров.
LIVE_DB_NAME = 'memes.db'

# Дополнительная read-only БД: бот читает отсюда старые мемы.
READONLY_DB_NAME = 'memes_old.db'

# Сиды только для первичного восстановления / первого запуска.
# В них бот никогда не пишет во время работы.
SEED_DB_NAMES = (
    'original_memes_old.db',
    'original_memes.db',
)


SEED_EXCLUDE_TABLES = ('memes', 'users')


def _copy_db_excluding_tables(src: Path, dst: Path, exclude_tables: tuple[str, ...]) -> None:
    """Копирует SQLite-базу, пропуская указанные таблицы."""
    shutil.copy2(src, dst)
    with sqlite3.connect(dst) as conn:
        for table in exclude_tables:
            conn.execute(f'DROP TABLE IF EXISTS {table}')
        conn.commit()


def _count_memes(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memes'"
            ).fetchone()
            if not row:
                return 0
            return int(conn.execute('SELECT COUNT(*) FROM memes').fetchone()[0])
    except sqlite3.Error:
        return 0


def resolve_db_path(db_dir: Path | None = None) -> str:
    """Возвращает путь к рабочей БД.

    Сид из original_* копируется ТОЛЬКО если рабочей БД ещё нет.
    Никогда не перезаписывает существующую live-базу — иначе удаление
    мемов и новые загрузки откатываются при каждом перезапуске.

    Для original_* файлов таблицы memes и users не копируются,
    чтобы удалённые мемы не возвращались при пересоздании БД.
    """
    base_dir = db_dir or DB_DIR
    live_path = base_dir / LIVE_DB_NAME

    if live_path.exists():
        return str(live_path)

    for seed_name in SEED_DB_NAMES:
        seed_path = base_dir / seed_name
        if seed_path.exists():
            if seed_name.startswith('original_'):
                _copy_db_excluding_tables(seed_path, live_path, SEED_EXCLUDE_TABLES)
                print(
                    f'Рабочая БД создана из {seed_path.name} '
                    f'(без таблиц {", ".join(SEED_EXCLUDE_TABLES)}): -> {live_path.name}'
                )
            else:
                shutil.copy2(seed_path, live_path)
                print(
                    f'Рабочая БД создана из {seed_path.name}: '
                    f'{_count_memes(live_path)} мемов -> {live_path.name}'
                )
            break

    return str(live_path)


def resolve_readonly_db_path(db_dir: Path | None = None) -> str | None:
    """Возвращает путь к read-only БД (memes_old.db), или None если файла нет."""
    base_dir = db_dir or DB_DIR
    readonly_path = base_dir / READONLY_DB_NAME
    if readonly_path.exists():
        return str(readonly_path)
    return None


DB_PATH = resolve_db_path()
READ_DB_PATH: str | None = None


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


async def init_db(db_path: str | None = None):
    """Готовит рабочую БД и применяет миграции, не трогая пользовательские данные зря."""
    global DB_PATH, READ_DB_PATH
    DB_PATH = db_path if db_path is not None else resolve_db_path()
    if db_path is not None:
        READ_DB_PATH = None
    else:
        READ_DB_PATH = resolve_readonly_db_path()
    print(f'Используется база данных (write): {DB_PATH}')
    if READ_DB_PATH:
        print(f'Используется база данных (read-only): {READ_DB_PATH}')
    async with aiosqlite.connect(DB_PATH) as db:
        applied = await run_migrations(db)
        for migration_id in applied:
            print(f'Применена миграция: {migration_id}')


# ---------------------------------------------------------------------------
# Внутренние хелперы для работы с двумя БД
# ---------------------------------------------------------------------------

async def _fetch_memes_from_db(db_path: str) -> list[dict]:
    """Читает все мемы из одной конкретной БД."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM memes ORDER BY id ASC') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def _has_meme_in_db(db_path: str, file_id: str) -> bool:
    """Проверяет, есть ли мем с таким file_id в указанной БД."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            'SELECT 1 FROM memes WHERE file_id = ? LIMIT 1', (file_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def _migrate_meme_to_live(meme: dict) -> int:
    """Копирует мем из read-only БД в рабочую. Возвращает новый ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'INSERT INTO memes (file_id, title, sender_id, sender_username, views) '
            'VALUES (?, ?, ?, ?, ?)',
            (
                meme['file_id'],
                meme['title'],
                meme.get('sender_id', 0),
                meme.get('sender_username', '@anon'),
                meme.get('views', 0),
            ),
        )
        new_id = cursor.lastrowid
        await db.commit()
    return new_id


async def _delete_meme_from_readonly(file_id: str) -> None:
    """Удаляет мем из read-only БД после миграции (чтобы не дублировать)."""
    if not READ_DB_PATH:
        return
    async with aiosqlite.connect(READ_DB_PATH) as db:
        await db.execute('DELETE FROM memes WHERE file_id = ?', (file_id,))
        await db.commit()


async def _maybe_migrate_meme(meme: dict) -> dict:
    """Если мем есть только в read-only БД — мигрирует в рабочую.

    Возвращает мем с обновлённым id (из рабочей БД).
    Если мем уже в рабочей БД — возвращает как есть.
    """
    file_id = meme['file_id']

    if not READ_DB_PATH:
        return meme

    in_live = await _has_meme_in_db(DB_PATH, file_id)
    if in_live:
        return meme

    in_readonly = await _has_meme_in_db(READ_DB_PATH, file_id)
    if not in_readonly:
        return meme

    new_id = await _migrate_meme_to_live(meme)
    await _delete_meme_from_readonly(file_id)

    migrated = dict(meme)
    migrated['id'] = new_id
    return migrated


# ---------------------------------------------------------------------------
# Бан-лист (только рабочая БД)
# ---------------------------------------------------------------------------

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


async def is_inline_description_enabled() -> bool:
    """Проверяет, включено ли описание под результатами inline-запроса."""
    value = await get_bot_setting('inline_description_enabled', '1')
    return value != '0'


async def set_inline_description_enabled(enabled: bool) -> None:
    """Включает или отключает описание под результатами inline-запроса."""
    await set_bot_setting('inline_description_enabled', '1' if enabled else '0')


async def is_show_username_enabled(user_id: int) -> bool:
    """Проверяет, разрешил ли пользователь показывать свой username на мемах."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT show_username FROM users WHERE user_id = ?',
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return True
            return row[0] != 0


async def set_show_username_enabled(user_id: int, enabled: bool) -> None:
    """Включает или отключает показ username пользователя на его мемах."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO users (user_id, username, score, show_username) VALUES (?, '@anon', 0, ?)
               ON CONFLICT(user_id) DO UPDATE SET show_username = excluded.show_username''',
            (user_id, 1 if enabled else 0),
        )
        await db.commit()


async def is_show_in_top_enabled(user_id: int) -> bool:
    """Проверяет, разрешил ли пользователь отображаться в топе статистики."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT show_in_top FROM users WHERE user_id = ?',
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return True
            return row[0] != 0


async def set_show_in_top_enabled(user_id: int, enabled: bool) -> None:
    """Включает или отключает отображение пользователя в топе статистики."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO users (user_id, username, score, show_in_top) VALUES (?, '@anon', 0, ?)
               ON CONFLICT(user_id) DO UPDATE SET show_in_top = excluded.show_in_top''',
            (user_id, 1 if enabled else 0),
        )
        await db.commit()


async def get_visible_meme_author(meme: dict) -> str | None:
    """Возвращает username автора мема, если он разрешил показ, иначе None."""
    sender_username = meme.get('sender_username')
    sender_id = meme.get('sender_id') or 0
    if not sender_username or normalize_username(sender_username) == '@anon':
        return None
    if sender_id and not await is_show_username_enabled(sender_id):
        return None
    return sender_username


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
    """Возвращает уникальные user_id из обеих БД."""
    ids: set[int] = set()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            rows = await cursor.fetchall()
            ids.update(row[0] for row in rows)
    if READ_DB_PATH:
        try:
            async with aiosqlite.connect(READ_DB_PATH) as db:
                async with db.execute('SELECT user_id FROM users') as cursor:
                    rows = await cursor.fetchall()
                    ids.update(row[0] for row in rows)
        except Exception:
            pass
    return list(ids)


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
    """Увеличивает счётчик просмотров для выбранного мема.

    Если мем в read-only БД — сначала мигрирует его в рабочую.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM memes WHERE id = ?', (meme_id,)) as cursor:
            in_live = await cursor.fetchone() is not None

    if not in_live and READ_DB_PATH:
        meme = await get_meme_by_id(meme_id)
        if meme and meme['id'] != meme_id:
            meme_id = meme['id']

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE memes SET views = views + 1 WHERE id = ?', (meme_id,))
        await db.commit()


async def get_all_memes() -> list[dict]:
    """Возвращает список всех мемов из обеих БД, дедуплицированных по file_id."""
    seen: set[str] = set()
    result: list[dict] = []

    memes_live = await _fetch_memes_from_db(DB_PATH)
    for m in memes_live:
        fid = m['file_id']
        if fid not in seen:
            seen.add(fid)
            result.append(m)

    if READ_DB_PATH:
        try:
            memes_old = await _fetch_memes_from_db(READ_DB_PATH)
            for m in memes_old:
                fid = m['file_id']
                if fid not in seen:
                    seen.add(fid)
                    result.append(m)
        except Exception:
            pass

    result.sort(key=lambda m: m.get('id', 0))
    return result


async def get_meme_by_id(meme_id: int) -> dict | None:
    """Возвращает конкретный мем по его ID. Ищет в обеих БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

    if READ_DB_PATH:
        try:
            async with aiosqlite.connect(READ_DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        meme = dict(row)
                        migrated = await _maybe_migrate_meme(meme)
                        return migrated
        except Exception:
            pass

    return None


async def reset_top_contributors() -> None:
    """Очищает рейтинг пользователей и начинает считать заново."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM users')
        await db.commit()


async def get_top_contributors() -> list[dict]:
    """Топ-10 пользователей по score из обеих БД (суммирует score при совпадении).

    Не включает пользователей с show_in_top = 0.
    """
    scores: dict[str, int] = {}
    hidden: set[str] = set()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT username, score, show_in_top FROM users WHERE score > 0'
        ) as cursor:
            rows = await cursor.fetchall()
            for username, score, show_in_top in rows:
                key = normalize_username(username)
                scores[key] = scores.get(key, 0) + score
                if show_in_top == 0:
                    hidden.add(key)

    if READ_DB_PATH:
        try:
            async with aiosqlite.connect(READ_DB_PATH) as db:
                async with db.execute(
                    'SELECT username, score FROM users WHERE score > 0'
                ) as cursor:
                    rows = await cursor.fetchall()
                    for username, score in rows:
                        key = normalize_username(username)
                        scores[key] = scores.get(key, 0) + score
        except Exception:
            pass

    filtered = [(u, s) for u, s in scores.items() if u not in hidden]
    sorted_users = sorted(filtered, key=lambda x: (-x[1], x[0]))[:10]
    return [
        {'sender_username': username, 'meme_count': score}
        for username, score in sorted_users
    ]


async def get_top_memes(limit: int = 3) -> list[dict]:
    """Возвращает самые популярные мемы по числу просмотров из обеих БД."""
    all_memes = await get_all_memes()
    all_memes.sort(key=lambda m: (-int(m.get('views', 0)), m.get('id', 0)))
    return all_memes[:limit]


async def get_random_meme() -> dict | None:
    """Возвращает случайный мем из объединённых БД."""
    memes = await get_all_memes()
    if not memes:
        return None
    return random.choice(memes)


async def delete_meme(meme_id: int) -> bool:
    """Полностью удаляет мем и его лайки из рабочей БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM memes WHERE id = ?', (meme_id,)) as cursor:
            exists = await cursor.fetchone() is not None
        if not exists:
            return False
        await db.execute('DELETE FROM meme_likes WHERE meme_id = ?', (meme_id,))
        await db.execute('DELETE FROM memes WHERE id = ?', (meme_id,))
        await db.commit()
        return True


async def get_meme_likes_count(meme_id: int) -> int:
    """Возвращает число лайков у мема."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT COUNT(*) FROM meme_likes WHERE meme_id = ?',
            (meme_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row else 0


async def has_user_liked_meme(user_id: int, meme_id: int) -> bool:
    """Проверяет, лайкнул ли пользователь мем."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT 1 FROM meme_likes WHERE user_id = ? AND meme_id = ?',
            (user_id, meme_id),
        ) as cursor:
            return await cursor.fetchone() is not None


async def get_user_liked_meme_ids(user_id: int) -> set[int]:
    """Возвращает id мемов, которые лайкнул пользователь."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT meme_id FROM meme_likes WHERE user_id = ?',
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return {int(row[0]) for row in rows}


async def toggle_meme_like(user_id: int, meme_id: int) -> tuple[bool, int]:
    """Ставит или снимает лайк. Возвращает (сейчас_лайкнут, число_лайков).

    Если мем в read-only БД — сначала мигрирует его в рабочую.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM memes WHERE id = ?', (meme_id,)) as cursor:
            in_live = await cursor.fetchone() is not None

    if not in_live and READ_DB_PATH:
        meme = await get_meme_by_id(meme_id)
        if meme and meme['id'] != meme_id:
            meme_id = meme['id']

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT 1 FROM meme_likes WHERE user_id = ? AND meme_id = ?',
            (user_id, meme_id),
        ) as cursor:
            already_liked = await cursor.fetchone() is not None

        if already_liked:
            await db.execute(
                'DELETE FROM meme_likes WHERE user_id = ? AND meme_id = ?',
                (user_id, meme_id),
            )
            liked = False
        else:
            await db.execute(
                'INSERT OR IGNORE INTO meme_likes (user_id, meme_id) VALUES (?, ?)',
                (user_id, meme_id),
            )
            liked = True

        await db.commit()
        async with db.execute(
            'SELECT COUNT(*) FROM meme_likes WHERE meme_id = ?',
            (meme_id,),
        ) as cursor:
            row = await cursor.fetchone()
            count = int(row[0]) if row else 0

    return liked, count


async def get_all_meme_likes_counts() -> dict[int, int]:
    """Возвращает словарь {meme_id: количество_лайков} для всех мемов."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT meme_id, COUNT(*) FROM meme_likes GROUP BY meme_id'
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


def sort_memes_for_inline(
    memes: list[dict],
    liked_ids: set[int] | None = None,
    likes_counts: dict[int, int] | None = None,
    top_mode: bool = False,
) -> list[dict]:
    """Сортировка мемов для инлайн-запроса.

    top_mode=True  → сначала по убыванию лайков, затем просмотров.
    top_mode=False → лайкнутые пользователем сверху, внутри — по лайкам,
                      затем по просмотрам.
    """
    liked = liked_ids or set()
    counts = likes_counts or {}

    def _sort_key(meme: dict):
        meme_id = meme.get('id') or 0
        meme_likes = counts.get(meme_id, 0)
        meme_views = int(meme.get('views') or 0)
        if top_mode:
            return (-meme_likes, -meme_views, meme_id)
        return (
            0 if meme_id in liked else 1,
            -meme_likes,
            -meme_views,
            meme_id,
        )

    return sorted(memes, key=_sort_key)

