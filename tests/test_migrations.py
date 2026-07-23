import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import db_core
from database.migrations import MIGRATIONS


class MigrationsAndAuthorPrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, 'memes.db')
        self.original_db_path = db_core.DB_PATH
        db_core.DB_PATH = self.db_path
        asyncio.run(db_core.init_db(self.db_path))

    def tearDown(self) -> None:
        db_core.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_init_db_is_idempotent(self) -> None:
        asyncio.run(db_core.init_db(self.db_path))
        asyncio.run(db_core.add_meme('file_1', 'Мем 1', sender_id=1, sender_username='@alice'))
        asyncio.run(db_core.init_db(self.db_path))

        meme = asyncio.run(db_core.get_meme_by_id(1))
        self.assertEqual(meme['title'], 'Мем 1')
        self.assertEqual(meme['views'], 0)

    def test_migrations_are_recorded(self) -> None:
        async def read_applied() -> set[str]:
            import aiosqlite

            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT id FROM schema_migrations') as cursor:
                    rows = await cursor.fetchall()
                    return {row[0] for row in rows}

        applied = asyncio.run(read_applied())
        expected = {migration_id for migration_id, _ in MIGRATIONS}
        self.assertEqual(applied, expected)

    def test_show_username_privacy(self) -> None:
        asyncio.run(db_core.add_meme('file_1', 'Мем 1', sender_id=10, sender_username='@alice'))
        meme = asyncio.run(db_core.get_meme_by_id(1))

        author = asyncio.run(db_core.get_visible_meme_author(meme))
        self.assertEqual(author, '@alice')

        asyncio.run(db_core.set_show_username_enabled(10, False))
        author_hidden = asyncio.run(db_core.get_visible_meme_author(meme))
        self.assertIsNone(author_hidden)

        asyncio.run(db_core.set_show_username_enabled(10, True))
        author_visible = asyncio.run(db_core.get_visible_meme_author(meme))
        self.assertEqual(author_visible, '@alice')

    def test_show_in_top_privacy(self) -> None:
        asyncio.run(db_core.add_meme('file_1', 'Мем 1', sender_id=10, sender_username='@alice'))
        asyncio.run(db_core.add_meme('file_2', 'Мем 2', sender_id=11, sender_username='@bob'))

        top = asyncio.run(db_core.get_top_contributors())
        self.assertEqual([user['sender_username'] for user in top], ['@alice', '@bob'])

        asyncio.run(db_core.set_show_in_top_enabled(10, False))
        top_hidden = asyncio.run(db_core.get_top_contributors())
        self.assertEqual([user['sender_username'] for user in top_hidden], ['@bob'])

        asyncio.run(db_core.set_show_in_top_enabled(10, True))
        top_visible = asyncio.run(db_core.get_top_contributors())
        self.assertEqual([user['sender_username'] for user in top_visible], ['@alice', '@bob'])


class LiveDbResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _make_db_with_memes(self, path: Path, titles: list[str]) -> None:
        conn = sqlite3.connect(path)
        conn.execute(
            '''CREATE TABLE memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                sender_id INTEGER DEFAULT 0,
                sender_username TEXT DEFAULT '@anon',
                views INTEGER NOT NULL DEFAULT 0
            )'''
        )
        for index, title in enumerate(titles, start=1):
            conn.execute(
                'INSERT INTO memes (title, file_id, sender_id, sender_username, views) VALUES (?, ?, ?, ?, ?)',
                (title, f'file_{index}', 1, '@alice', 0),
            )
        conn.commit()
        conn.close()

    def test_seeds_live_db_from_original_when_missing(self) -> None:
        seed = self.base / 'original_memes_old.db'
        self._make_db_with_memes(seed, ['A', 'B', 'C'])

        live = Path(db_core.resolve_db_path(self.base))
        self.assertEqual(live.name, 'memes_old.db')
        self.assertTrue(live.exists())
        # original_* файлы: таблицы memes и users не копируются
        self.assertEqual(db_core._count_memes(live), 0)

    def test_does_not_overwrite_live_db_even_if_seed_has_more_memes(self) -> None:
        live = self.base / 'memes_old.db'
        seed = self.base / 'original_memes_old.db'
        self._make_db_with_memes(live, ['only-one'])
        self._make_db_with_memes(seed, ['A', 'B', 'C', 'D'])

        resolved = Path(db_core.resolve_db_path(self.base))
        self.assertEqual(resolved, live)
        self.assertEqual(db_core._count_memes(live), 1)

    def test_keeps_live_db_when_it_already_has_more_memes(self) -> None:
        live = self.base / 'memes_old.db'
        seed = self.base / 'original_memes_old.db'
        self._make_db_with_memes(live, ['A', 'B', 'C', 'D', 'E'])
        self._make_db_with_memes(seed, ['A', 'B'])

        db_core.resolve_db_path(self.base)
        self.assertEqual(db_core._count_memes(live), 5)


if __name__ == '__main__':
    unittest.main()
