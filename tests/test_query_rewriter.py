import unittest


class QueryRewriterTests(unittest.TestCase):
    def test_contains_cjk_detects_chinese_text(self) -> None:
        from utils.query_rewriter import contains_cjk

        self.assertTrue(contains_cjk("日落海边"))
        self.assertFalse(contains_cjk("sunset beach"))

    def test_rewrite_query_for_clip_maps_known_visual_terms(self) -> None:
        from utils.query_rewriter import rewrite_query_for_clip

        rewritten = rewrite_query_for_clip("日落 海边 狗")

        self.assertEqual(rewritten.original_query, "日落 海边 狗")
        self.assertEqual(rewritten.rewritten_query, "sunset beach dog")
        self.assertTrue(rewritten.was_rewritten)

    def test_rewrite_query_for_clip_leaves_english_query_unchanged(self) -> None:
        from utils.query_rewriter import rewrite_query_for_clip

        rewritten = rewrite_query_for_clip("forest cat")

        self.assertEqual(rewritten.rewritten_query, "forest cat")
        self.assertFalse(rewritten.was_rewritten)


if __name__ == "__main__":
    unittest.main()
