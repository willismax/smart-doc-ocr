import json
import tempfile
import unittest
from pathlib import Path

from smartdoc.audit import AuditLog


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "audit.jsonl"

    def test_write_and_verify(self):
        log = AuditLog(self.path)
        log.write("process", file="a.pdf", pii_count=3)
        log.write("process", file="b.pdf", pii_count=0)
        ok, msg = log.verify_chain()
        self.assertTrue(ok, msg)

    def test_chain_across_restarts(self):
        AuditLog(self.path).write("e1", file="a.pdf")
        AuditLog(self.path).write("e2", file="b.pdf")  # 重新開啟續鏈
        ok, msg = AuditLog(self.path).verify_chain()
        self.assertTrue(ok, msg)

    def test_tamper_content_detected(self):
        log = AuditLog(self.path)
        log.write("process", file="secret.pdf", pii_count=5)
        log.write("process", file="other.pdf", pii_count=1)
        # 竄改第一筆的 pii_count
        lines = self.path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["pii_count"] = 0
        lines[0] = json.dumps(entry, ensure_ascii=False)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, msg = AuditLog(self.path).verify_chain()
        self.assertFalse(ok)

    def test_delete_line_detected(self):
        log = AuditLog(self.path)
        for i in range(3):
            log.write("process", file=f"f{i}.pdf")
        lines = self.path.read_text(encoding="utf-8").splitlines()
        del lines[1]  # 刪掉中間一筆
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, msg = AuditLog(self.path).verify_chain()
        self.assertFalse(ok)

    def test_empty_log_verifies(self):
        ok, _ = AuditLog(self.path).verify_chain()
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
