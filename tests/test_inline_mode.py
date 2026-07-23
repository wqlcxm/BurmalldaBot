import unittest

from handlers import user_handlers
from services.captions import BOT_WATERMARK


class InlineModeTests(unittest.TestCase):
    def test_build_inline_query_results_uses_meme_ids(self) -> None:
        memes = [
            {
                "id": 7,
                "title": "Тестовый мем",
                "file_id": "video_file_id",
                "views": 12,
            }
        ]

        results = user_handlers.build_inline_query_results(memes)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "meme:7")
        self.assertEqual(results[0].title, "Тестовый мем")
        self.assertEqual(results[0].video_file_id, "video_file_id")
        self.assertIn("👁️ 12", results[0].description)
        self.assertIn("Тестовый мем", results[0].caption)
        self.assertIn("Просмотров: 12", results[0].caption)
        self.assertTrue(results[0].caption.endswith(BOT_WATERMARK))

    def test_build_inline_query_results_can_hide_description(self) -> None:
        memes = [{"id": 8, "title": "Скрытый мем", "file_id": "video_file_id_2", "views": 3}]

        results = user_handlers.build_inline_query_results(memes, show_description=False)

        self.assertEqual(results[0].description, "")
        self.assertEqual(results[0].caption, BOT_WATERMARK)


if __name__ == "__main__":
    unittest.main()
