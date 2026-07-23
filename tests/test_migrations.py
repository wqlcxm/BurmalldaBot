import asyncio
import os
import tempfile
import unittest

from database import db_core
from database.migrations import MIGRATIONS


class MigrationsAndAuthorPrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, 'memes.db')
        self.original_db_path = db_core.DB_PATH
        db_core.DB_PATH = self.db_path
        asyncio.run(db_core.init_db())

    def tearDown(self) -> None:
        db_core.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_init_db_is_idempotent(self) -> None:
        asyncio.run(db_core.init_db())
        asyncio.run(db_core.add_meme('file_1', 'Мем 1', sender_id=1, sender_username='@alice'))
        asyncio.run(db_core.init_db())

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


if __name__ == '__main__':
    unittest.main()
