"""Версионные миграции схемы SQLite.

Миграции только добавляют таблицы/колонки и правят данные точечно.
Они никогда не удаляют и не пересоздают пользовательские данные.
При деплое обновляйте код бота, а файл БД на хосте оставляйте прежним.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import aiosqlite

MigrationFunc = Callable[[aiosqlite.Connection], Awaitable[None]]


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f'PRAGMA table_info({table})') as cursor:
        rows = await cursor.fetchall()
        return {row[1] for row in rows}


async def _ensure_column(
    db: aiosqlite.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = await _table_columns(db, table)
    if column not in columns:
        await db.execute(f'ALTER TABLE {table} ADD COLUMN {definition}')


async def migration_001_base_tables(db: aiosqlite.Connection) -> None:
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
            score INTEGER NOT NULL DEFAULT 0
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


async def migration_002_meme_columns(db: aiosqlite.Connection) -> None:
    await _ensure_column(db, 'memes', 'sender_id', 'sender_id INTEGER DEFAULT 0')
    await _ensure_column(db, 'memes', 'sender_username', "sender_username TEXT DEFAULT '@anon'")
    await _ensure_column(db, 'memes', 'views', 'views INTEGER NOT NULL DEFAULT 0')


async def migration_003_normalize_usernames(db: aiosqlite.Connection) -> None:
    await db.execute("""
        UPDATE memes
        SET sender_username = CASE
            WHEN sender_username IS NULL OR TRIM(sender_username) = '' THEN '@anon'
            WHEN sender_username LIKE '@%' THEN sender_username
            ELSE '@' || TRIM(sender_username)
        END
    """)
    await db.execute("""
        UPDATE users
        SET username = CASE
            WHEN username IS NULL OR TRIM(username) = '' THEN '@anon'
            WHEN username LIKE '@%' THEN username
            ELSE '@' || TRIM(username)
        END
    """)


async def migration_004_users_show_username(db: aiosqlite.Connection) -> None:
    await _ensure_column(
        db,
        'users',
        'show_username',
        'show_username INTEGER NOT NULL DEFAULT 1',
    )


MIGRATIONS: list[tuple[str, MigrationFunc]] = [
    ('001_base_tables', migration_001_base_tables),
    ('002_meme_columns', migration_002_meme_columns),
    ('003_normalize_usernames', migration_003_normalize_usernames),
    ('004_users_show_username', migration_004_users_show_username),
]


async def run_migrations(db: aiosqlite.Connection) -> list[str]:
    """Применяет неприменённые миграции. Возвращает список применённых id."""
    await db.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    ''')

    async with db.execute('SELECT id FROM schema_migrations') as cursor:
        applied = {row[0] for row in await cursor.fetchall()}

    newly_applied: list[str] = []
    for migration_id, migrate in MIGRATIONS:
        if migration_id in applied:
            continue
        await migrate(db)
        await db.execute(
            'INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)',
            (migration_id, datetime.now(timezone.utc).isoformat()),
        )
        newly_applied.append(migration_id)

    await db.commit()
    return newly_applied
