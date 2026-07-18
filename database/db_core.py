import aiosqlite

DB_PATH = 'database/memes.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Создаем базовые таблицы, если их вообще не было
        await db.execute('''
            CREATE TABLE IF NOT EXISTS memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await db.commit()

        # --- ХАК ДЛЯ СТАРОЙ БАЗЫ: Добавляем новые колонки вручную ---
        try:
            await db.execute('ALTER TABLE memes ADD COLUMN sender_id INTEGER DEFAULT 0')
            await db.commit()
            print("Колонка sender_id успешно добавлена в старую БД.")
        except aiosqlite.OperationalError:
            # Если колонка уже есть, SQLite выдаст ошибку, просто игнорируем её
            pass

        try:
            await db.execute("ALTER TABLE memes ADD COLUMN sender_username TEXT DEFAULT 'anon'")
            await db.commit()
            print("Колонка sender_username успешно добавлена в старую БД.")
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

async def add_meme(title: str, file_id: str, sender_id: int, sender_username: str):
    """Добавляет мем вместе с данными автора."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO memes (title, file_id, sender_id, sender_username) VALUES (?, ?, ?, ?)',
            (title, file_id, sender_id, sender_username)
        )
        await db.commit()

async def get_all_memes() -> list[dict]:
    """Возвращает список всех мемов из базы."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM memes') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_meme_by_id(meme_id: int) -> dict | None:
    """Возвращает конкретный мем по его ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
        
async def get_top_contributors() -> list[dict]:
    """Возвращает топ-10 пользователей по количеству одобренных мемов."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Считаем мемы, группируя по sender_id
        async with db.execute('''
            SELECT sender_username, COUNT(id) as meme_count 
            FROM memes 
            WHERE sender_id != 0
            GROUP BY sender_id 
            ORDER BY meme_count DESC 
            LIMIT 10
        ''') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        
async def get_random_meme() -> dict | None:
    """Возвращает случайный мем из базы данных."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Сортируем по RANDOM() и берем 1 строчку
        async with db.execute('SELECT title, file_id FROM memes ORDER BY RANDOM() LIMIT 1') as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None