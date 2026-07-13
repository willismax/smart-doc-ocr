"""端對端測試：不需要 OCR 引擎的路徑（純文字 / Email / 空檔 / 超大檔）。"""
import copy
import tempfile
import unittest
from pathlib import Path

from smartdoc.config import DEFAULTS
from smartdoc.errors import EmptyFileError, FileTooLargeError
from smartdoc.pipeline import DocumentPipeline, validate_file


def make_settings(tmp: Path) -> dict:
    s = copy.deepcopy(DEFAULTS)
    s["paths"]["logs"] = str(tmp / "logs")
    s["paths"]["output"] = str(tmp / "output")
    s["paths"]["pii_rules"] = str(tmp / "no_rules.yaml")  # 不存在 → 只用內建
    return s


class TestPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.settings = make_settings(self.tmp)

    def test_text_file_with_pii_masked(self):
        p = self.tmp / "doc.txt"
        p.write_text("申請人姓名：王小明\n身分證字號：A123456789\n"
                     "聯絡手機：0912345678\n內容：年度報告",
                     encoding="utf-8")
        pipeline = DocumentPipeline(settings=self.settings, mask_pii=True)
        result = pipeline.process(p)
        self.assertEqual(result["doc_type"], "text")
        self.assertNotIn("A123456789", result["display_text"])
        self.assertNotIn("0912345678", result["display_text"])
        self.assertIn("年度報告", result["display_text"])
        self.assertGreaterEqual(result["pii_report"]["pii_count"], 3)
        # 稽核日誌已寫入且完整
        from smartdoc.audit import AuditLog
        log = AuditLog(Path(self.settings["paths"]["logs"]) / "audit.jsonl")
        ok, msg = log.verify_chain()
        self.assertTrue(ok, msg)

    def test_mask_off_keeps_original(self):
        p = self.tmp / "doc.txt"
        p.write_text("身分證字號：A123456789", encoding="utf-8")
        pipeline = DocumentPipeline(settings=self.settings, mask_pii=False)
        result = pipeline.process(p)
        self.assertIn("A123456789", result["display_text"])
        # 但 pii_report 裡仍有遮蔽版可用
        self.assertNotIn("A123456789",
                         result["pii_report"]["masked_text"])

    def test_eml(self):
        p = self.tmp / "mail.eml"
        p.write_bytes(b"From: boss@corp.tw\r\nTo: me@corp.tw\r\n"
                      b"Subject: Salary\r\nDate: Mon, 1 Jan 2026 00:00:00 +0800\r\n"
                      b"MIME-Version: 1.0\r\nContent-Type: text/plain\r\n\r\n"
                      b"body text here")
        pipeline = DocumentPipeline(settings=self.settings)
        result = pipeline.process(p)
        self.assertEqual(result["doc_type"], "email")
        self.assertIn("Salary", result["structured_text"])

    def test_empty_file_rejected(self):
        p = self.tmp / "empty.txt"
        p.write_bytes(b"")
        with self.assertRaises(EmptyFileError):
            validate_file(p, self.settings)

    def test_oversize_rejected(self):
        self.settings["limits"]["max_file_size_mb"] = 0.0001
        p = self.tmp / "big.txt"
        p.write_bytes(b"x" * 10_000)
        with self.assertRaises(FileTooLargeError):
            validate_file(p, self.settings)


if __name__ == "__main__":
    unittest.main()
