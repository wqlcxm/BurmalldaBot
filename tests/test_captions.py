import unittest

from services.captions import BOT_WATERMARK, build_video_caption


class CaptionBuilderTests(unittest.TestCase):
    def test_watermark_always_present_without_details(self) -> None:
        caption = build_video_caption(show_details=False)
        self.assertEqual(caption, BOT_WATERMARK)

    def test_details_and_author_before_watermark(self) -> None:
        caption = build_video_caption(
            title='Тест',
            views=5,
            author_username='alice',
            header='Случайный мем:',
        )
        self.assertIn('Случайный мем:', caption)
        self.assertIn('Тест', caption)
        self.assertIn('Просмотров: 5', caption)
        self.assertIn('@alice', caption)
        self.assertTrue(caption.endswith(BOT_WATERMARK))


if __name__ == '__main__':
    unittest.main()
