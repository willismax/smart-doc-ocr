import tempfile
import unittest
from pathlib import Path

from smartdoc.batch import BatchProcessor, Status, process_with_retry
from smartdoc.errors import CorruptedFileError


class FakePipeline:
    """模擬 pipeline：檔名含 bad 直接失敗、含 flaky 第一次失敗第二次成功。"""

    def __init__(self):
        self.attempts = {}

    def process(self, path):
        name = Path(path).name
        n = self.attempts.get(name, 0) + 1
        self.attempts[name] = n
        if "corrupt" in name:
            raise CorruptedFileError(detail=name)
        if "flaky" in name and n == 1:
            raise RuntimeError("暫時性錯誤")
        if "oom" in name:
            raise MemoryError()
        return {"file_name": name, "doc_type": "text", "pages": 1,
                "display_text": "ok",
                "pii_report": {"pii_count": 0}}


class TestRetry(unittest.TestCase):
    def _paths(self, *names):
        tmp = Path(tempfile.mkdtemp())
        out = []
        for n in names:
            p = tmp / n
            p.write_text("x", encoding="utf-8")
            out.append(p)
        return out

    def test_success(self):
        (p,) = self._paths("good.txt")
        r = process_with_retry(p, FakePipeline(), max_retries=2, backoff=0)
        self.assertEqual(r.status, Status.SUCCESS)

    def test_flaky_retries_then_succeeds(self):
        (p,) = self._paths("flaky.txt")
        r = process_with_retry(p, FakePipeline(), max_retries=2, backoff=0)
        self.assertEqual(r.status, Status.SUCCESS)
        self.assertEqual(r.retries, 1)

    def test_expected_error_no_retry(self):
        (p,) = self._paths("corrupt.pdf")
        pipe = FakePipeline()
        r = process_with_retry(p, pipe, max_retries=3, backoff=0)
        self.assertEqual(r.status, Status.FAILED)
        self.assertEqual(pipe.attempts["corrupt.pdf"], 1)  # 不浪費時間重試
        self.assertIn("損壞", r.error)  # 錯誤訊息是中文

    def test_memory_error_skips(self):
        (p,) = self._paths("oom.pdf")
        r = process_with_retry(p, FakePipeline(), max_retries=3, backoff=0)
        self.assertEqual(r.status, Status.SKIPPED)


class TestBatch(unittest.TestCase):
    def test_one_bad_file_does_not_kill_batch(self):
        tmp = Path(tempfile.mkdtemp())
        paths = []
        for name in ["a.txt", "corrupt.pdf", "b.txt", "oom.pdf", "c.txt"]:
            p = tmp / name
            p.write_text("x", encoding="utf-8")
            paths.append(p)
        bp = BatchProcessor(FakePipeline(), max_workers=2)
        results = bp.run(paths)
        self.assertEqual(len(results), 5)
        s = bp.summary()
        self.assertEqual(s["success"], 3)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["skipped"], 1)
        # 結果依原始順序
        self.assertEqual([Path(r.file_path).name for r in results],
                         ["a.txt", "corrupt.pdf", "b.txt", "oom.pdf", "c.txt"])

    def test_report_markdown(self):
        tmp = Path(tempfile.mkdtemp())
        p = tmp / "good.txt"
        p.write_text("x", encoding="utf-8")
        bp = BatchProcessor(FakePipeline(), max_workers=1)
        bp.run([p])
        report = bp.report_markdown()
        self.assertIn("批量處理報告", report)
        self.assertIn("good.txt", report)

    def test_progress_callback_error_ignored(self):
        tmp = Path(tempfile.mkdtemp())
        p = tmp / "good.txt"
        p.write_text("x", encoding="utf-8")
        bp = BatchProcessor(FakePipeline(), max_workers=1)

        def bad_callback(done, total, result):
            raise RuntimeError("UI 壞了")

        results = bp.run([p], on_progress=bad_callback)
        self.assertEqual(results[0].status, Status.SUCCESS)


if __name__ == "__main__":
    unittest.main()
