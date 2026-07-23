import asyncio
import os
import tempfile
import unittest

from database import db_core


class MemeStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "memes.db")
        self.original_db_path = db_core.DB_PATH
        db_core.DB_PATH = self.db_path
        asyncio.run(db_core.init_db(self.db_path))

    def tearDown(self) -> None:
        db_core.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_views_and_top_memes(self) -> None:
        asyncio.run(db_core.add_meme("file_1", "Мем 1", sender_id=1, sender_username="@alice"))
        asyncio.run(db_core.add_meme("file_2", "Мем 2", sender_id=2, sender_username="@bob"))
        asyncio.run(db_core.add_meme("file_3", "Мем 3", sender_id=3, sender_username="@carol"))

        asyncio.run(db_core.increment_meme_views(1))
        asyncio.run(db_core.increment_meme_views(1))
        asyncio.run(db_core.increment_meme_views(2))

        meme_1 = asyncio.run(db_core.get_meme_by_id(1))
        meme_2 = asyncio.run(db_core.get_meme_by_id(2))
        meme_3 = asyncio.run(db_core.get_meme_by_id(3))

        self.assertEqual(meme_1["views"], 2)
        self.assertEqual(meme_2["views"], 1)
        self.assertEqual(meme_3["views"], 0)

        top_memes = asyncio.run(db_core.get_top_memes(limit=3))
        self.assertEqual([meme["title"] for meme in top_memes], ["Мем 1", "Мем 2", "Мем 3"])


if __name__ == "__main__":
    unittest.main()
