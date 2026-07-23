import asyncio
import os
import tempfile
import unittest

from database import db_core


class MemeLikesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self.temp_dir.name, 'memes.db')
        self.original_db_path = db_core.DB_PATH
        db_core.DB_PATH = self.db_path
        asyncio.run(db_core.init_db(self.db_path))

    def tearDown(self) -> None:
        db_core.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_toggle_like_and_sort(self) -> None:
        asyncio.run(db_core.add_meme('f1', 'Low', sender_id=1, sender_username='@a'))
        asyncio.run(db_core.add_meme('f2', 'High', sender_id=1, sender_username='@a'))
        asyncio.run(db_core.add_meme('f3', 'LikedLow', sender_id=1, sender_username='@a'))

        asyncio.run(db_core.increment_meme_views(1))
        asyncio.run(db_core.increment_meme_views(2))
        asyncio.run(db_core.increment_meme_views(2))
        asyncio.run(db_core.increment_meme_views(2))

        liked, count = asyncio.run(db_core.toggle_meme_like(99, 3))
        self.assertTrue(liked)
        self.assertEqual(count, 1)

        memes = asyncio.run(db_core.get_all_memes())
        liked_ids = asyncio.run(db_core.get_user_liked_meme_ids(99))
        ordered = db_core.sort_memes_for_inline(memes, liked_ids)
        self.assertEqual([m['title'] for m in ordered], ['LikedLow', 'High', 'Low'])

        liked, count = asyncio.run(db_core.toggle_meme_like(99, 3))
        self.assertFalse(liked)
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
