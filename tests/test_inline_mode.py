import unittest

from handlers import user_handlers


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
        self.assertIn("Просмотров: 12", results[0].description)


if __name__ == "__main__":
    unittest.main()
