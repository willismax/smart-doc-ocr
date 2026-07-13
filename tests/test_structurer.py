import unittest

from smartdoc.structurer import TextStructurer, extract_fields


class TestStructurer(unittest.TestCase):
    def setUp(self):
        self.s = TextStructurer()

    def test_clean_fullwidth_digits(self):
        self.assertEqual(self.s.clean_text("金額：１２３４５"), "金額：12345")

    def test_clean_blank_lines(self):
        out = self.s.clean_text("a\n\n\n\n\nb")
        self.assertEqual(out, "a\n\nb")

    def test_table_from_rows(self):
        md = self.s.table_to_markdown([["姓名", "金額"], ["王小明", "100"]])
        self.assertIn("| 姓名 | 金額 |", md)
        self.assertIn("| 王小明 | 100 |", md)

    def test_table_escapes_pipe(self):
        md = self.s.table_to_markdown([["a|b"], ["c"]])
        self.assertIn("a\\|b", md)

    def test_table_ragged_rows(self):
        md = self.s.table_to_markdown([["A", "B", "C"], ["1"]])
        self.assertIn("| 1 |  |  |", md)

    def test_table_from_html(self):
        html = "<table><tr><td>甲</td><td>乙</td></tr><tr><td>1</td><td>2</td></tr></table>"
        md = self.s.table_to_markdown(html)
        self.assertIn("| 甲 | 乙 |", md)

    def test_structure_pages(self):
        raw = {"type": "pdf_digital", "pages": [
            {"page": 1, "text": "第一頁內容", "tables": []},
            {"page": 2, "text": "第二頁內容",
             "tables": [[["h1"], ["v1"]]]},
        ]}
        out = self.s.structure(raw)
        self.assertIn("## 第 1 頁", out)
        self.assertIn("### 表格 1", out)

    def test_single_page_no_header(self):
        raw = {"type": "image", "pages": [
            {"page": 1, "text": "只有一頁", "tables": []}]}
        out = self.s.structure(raw)
        self.assertNotIn("## 第 1 頁", out)

    def test_extract_fields(self):
        text = "姓名：王小明\n金額: 3,500 元\n備註：無"
        fields = extract_fields(text, ["姓名", "金額", "不存在的欄位"])
        self.assertEqual(fields["姓名"], "王小明")
        self.assertEqual(fields["金額"], "3,500 元")
        self.assertNotIn("不存在的欄位", fields)


if __name__ == "__main__":
    unittest.main()
