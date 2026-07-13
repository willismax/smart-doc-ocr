"""Layer 4 — 結構化層：OCR / 萃取原始輸出 → 乾淨 Markdown。"""
from __future__ import annotations

import html as _html
import re

# 全形數字與常見 OCR 誤字對照
_OCR_CORRECTIONS = {
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "—": "-", "‒": "-", "–": "-",
}


class TextStructurer:
    """把各 handler 的原始輸出統一整理成 Markdown 字串。"""

    def structure(self, raw: dict) -> str:
        doc_type = raw.get("type", "")
        if "pages" in raw:
            return self._structure_pages(raw["pages"])
        return self.clean_text(raw.get("text", ""))

    def _structure_pages(self, pages: list[dict]) -> str:
        parts = []
        multi = len(pages) > 1
        for p in pages:
            if multi:
                parts.append(f"\n## 第 {p['page']} 頁\n")
            text = p.get("text", "")
            if text:
                parts.append(self.clean_text(text))
            for i, table in enumerate(p.get("tables", []), 1):
                md = self.table_to_markdown(table)
                if md:
                    parts.append(f"\n### 表格 {i}\n\n{md}")
        return "\n".join(x for x in parts if x).strip()

    def clean_text(self, text: str) -> str:
        for wrong, right in _OCR_CORRECTIONS.items():
            text = text.replace(wrong, right)
        # 移除行尾空白、壓縮 3+ 連續空行
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def table_to_markdown(self, table) -> str:
        """支援兩種輸入：二維陣列（PyMuPDF find_tables）或 HTML 字串（PP-Structure）。"""
        if isinstance(table, str):
            rows = self._html_table_to_rows(table)
        else:
            rows = table
        if not rows or not rows[0]:
            return ""
        def cell(c):
            s = "" if c is None else str(c)
            return s.replace("|", "\\|").replace("\n", " ").strip()
        width = max(len(r) for r in rows)
        norm = [list(r) + [""] * (width - len(r)) for r in rows]
        header, body = norm[0], norm[1:]
        md = "| " + " | ".join(cell(h) for h in header) + " |\n"
        md += "|" + "---|" * width + "\n"
        for row in body:
            md += "| " + " | ".join(cell(c) for c in row) + " |\n"
        return md

    @staticmethod
    def _html_table_to_rows(html_str: str) -> list[list[str]]:
        """極簡 HTML 表格解析（PP-Structure 輸出的 table html）。"""
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_str,
                             re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr,
                               re.DOTALL | re.IGNORECASE)
            rows.append([_html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                         for c in cells])
        return [r for r in rows if any(r)]


def extract_fields(text: str, labels: list[str]) -> dict[str, str]:
    """從文件文字抽取「標籤：值」欄位，供欄位比對模式使用。

    支援全形/半形冒號與等號；值取到行尾。
    """
    fields: dict[str, str] = {}
    for label in labels:
        m = re.search(
            rf"{re.escape(label)}\s*[:：=]\s*([^\n\r|]{{1,80}})", text)
        if m:
            fields[label] = m.group(1).strip()
    return fields
