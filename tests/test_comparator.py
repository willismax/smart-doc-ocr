import unittest

from smartdoc.comparator import DocumentComparator


class TestComparator(unittest.TestCase):
    def setUp(self):
        self.c = DocumentComparator()

    def test_diff_identical(self):
        d = self.c.diff_text("甲乙丙\n丁戊己", "甲乙丙\n丁戊己")
        self.assertEqual(d["similarity_ratio"], 1.0)
        self.assertEqual(d["added"], 0)
        self.assertEqual(d["removed"], 0)

    def test_diff_changed(self):
        d = self.c.diff_text("合約金額 100 元", "合約金額 200 元")
        self.assertLess(d["similarity_ratio"], 1.0)
        self.assertGreaterEqual(d["added"], 1)
        self.assertGreaterEqual(d["removed"], 1)

    def test_ngram_similar_chinese(self):
        a = "本合約自簽訂日起生效，有效期間為一年。"
        b = "本合約自簽訂日起生效，有效期間為兩年。"
        score = self.c._ngram_similarity(a, b)
        self.assertGreater(score, 0.7)

    def test_ngram_different(self):
        score = self.c._ngram_similarity("今天天氣很好", "採購合約書附件三")
        self.assertLess(score, 0.3)

    def test_ngram_empty(self):
        self.assertEqual(self.c._ngram_similarity("", "abc"), 0.0)

    def test_semantic_falls_back(self):
        """models/ 沒有語意模型時應自動降級，不噴例外。"""
        r = self.c.semantic_similarity("測試文件內容", "測試文件內容")
        self.assertGreaterEqual(r["score"], 0.99)
        self.assertIn("method", r)

    def test_field_compare(self):
        rows = self.c.field_compare(
            {"姓名": "王小明", "金額": "3,500 元", "地址": "台北市大安區"},
            {"姓名": "王小明", "金額": "3500", "地址": "臺北市大安區"},
            {"姓名": {"type": "exact"},
             "金額": {"type": "numeric"},
             "地址": {"type": "fuzzy", "threshold": 0.7}})
        by_field = {r["field"]: r for r in rows}
        self.assertTrue(by_field["姓名"]["match"])
        self.assertTrue(by_field["金額"]["match"])   # 3,500 == 3500
        self.assertTrue(by_field["地址"]["match"])   # 台/臺 一字之差

    def test_field_compare_missing(self):
        rows = self.c.field_compare({"金額": "100"}, {}, {"金額": {"type": "numeric"}})
        self.assertFalse(rows[0]["match"])

    def test_extract_number(self):
        self.assertEqual(self.c._extract_number("NT$ 1,234.5 元"), 1234.5)
        self.assertIsNone(self.c._extract_number("無數字"))


if __name__ == "__main__":
    unittest.main()
