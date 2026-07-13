import tempfile
import unittest
import zipfile
from pathlib import Path

from smartdoc.errors import CorruptedFileError, EmptyFileError
from smartdoc.router import DocType, DocumentRouter


def _has_fitz() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = DocumentRouter()
        self.tmp = Path(tempfile.mkdtemp())

    def _write(self, name: str, data: bytes) -> Path:
        p = self.tmp / name
        p.write_bytes(data)
        return p

    def test_empty_file(self):
        p = self._write("empty.pdf", b"")
        with self.assertRaises(EmptyFileError):
            self.router.detect(p)

    def test_png_with_wrong_extension(self):
        """副檔名亂改也要認得真實格式（magic bytes 路由）。"""
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        p = self._write("photo.pdf", png)  # 副檔名故意寫 .pdf
        self.assertEqual(self.router.detect(p), DocType.IMAGE)

    def test_jpeg(self):
        p = self._write("scan.docx", b"\xff\xd8\xff\xe0" + b"\x00" * 64)
        self.assertEqual(self.router.detect(p), DocType.IMAGE)

    def test_docx(self):
        p = self.tmp / "real.bin"  # 副檔名不對也要認出 Word
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("word/document.xml", "<w:document/>")
        self.assertEqual(self.router.detect(p), DocType.WORD)

    def test_xlsx(self):
        p = self.tmp / "book.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("xl/workbook.xml", "<workbook/>")
        self.assertEqual(self.router.detect(p), DocType.EXCEL)

    def test_pptx(self):
        p = self.tmp / "deck.pptx"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("ppt/presentation.xml", "<p/>")
        self.assertEqual(self.router.detect(p), DocType.PPT)

    def test_corrupted_zip(self):
        p = self._write("broken.docx", b"PK\x03\x04" + b"garbage" * 10)
        with self.assertRaises(CorruptedFileError):
            self.router.detect(p)

    def test_eml(self):
        eml = (b"From: a@b.com\r\nTo: c@d.com\r\nSubject: hi\r\n"
               b"Date: Mon, 1 Jan 2026 00:00:00 +0800\r\n\r\nbody")
        p = self._write("mail.eml", eml)
        self.assertEqual(self.router.detect(p), DocType.EMAIL)

    def test_plain_text(self):
        p = self._write("note.txt", "純文字測試內容".encode("utf-8"))
        self.assertEqual(self.router.detect(p), DocType.TEXT)

    def test_big5_text(self):
        p = self._write("old.txt", "繁體中文測試".encode("big5"))
        self.assertEqual(self.router.detect(p), DocType.TEXT)

    def test_unknown_binary(self):
        p = self._write("data.bin", b"\x00\x01\x02\x03" * 32)
        self.assertEqual(self.router.detect(p), DocType.UNKNOWN)

    def test_ole_msg(self):
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
        p = self._write("mail.msg", ole)
        self.assertEqual(self.router.detect(p), DocType.EMAIL)
        p2 = self._write("legacy.doc", ole)
        self.assertEqual(self.router.detect(p2), DocType.LEGACY_OFFICE)

    @unittest.skipUnless(_has_fitz(), "需要 PyMuPDF")
    def test_real_pdf_digital(self):
        import fitz
        p = self.tmp / "digital.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello World " * 20)
        doc.save(str(p))
        doc.close()
        self.assertEqual(self.router.detect(p), DocType.PDF_DIGITAL)

    @unittest.skipUnless(_has_fitz(), "需要 PyMuPDF")
    def test_real_pdf_scanned(self):
        import fitz
        p = self.tmp / "scanned.pdf"
        doc = fitz.open()
        doc.new_page()  # 無文字 → 視為掃描
        doc.save(str(p))
        doc.close()
        self.assertEqual(self.router.detect(p), DocType.PDF_SCANNED)


if __name__ == "__main__":
    unittest.main()
