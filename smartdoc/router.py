"""Layer 1 — 文件路由器。

用檔案開頭的 magic bytes 判斷真實格式，完全不信任副檔名。
純 Python 實作（直接讀檔頭 + zipfile 內容檢查），不依賴 libmagic DLL，
在 Windows 上少一個會壞的外部依賴。
"""
from __future__ import annotations

import zipfile
from enum import Enum
from pathlib import Path

from .errors import CorruptedFileError, EmptyFileError, PasswordProtectedError


class DocType(Enum):
    PDF_DIGITAL = "pdf_digital"   # PDF 有文字層
    PDF_SCANNED = "pdf_scanned"   # PDF 掃描檔，無文字層
    PDF_MIXED = "pdf_mixed"       # 部分頁面有文字
    WORD = "word"
    EXCEL = "excel"
    PPT = "ppt"
    IMAGE = "image"
    EMAIL = "email"
    TEXT = "text"                 # 純文字 / Markdown / CSV
    LEGACY_OFFICE = "legacy_office"  # 舊版 .doc/.xls/.ppt（OLE 容器）
    UNKNOWN = "unknown"


# 圖片格式 magic bytes
_IMAGE_MAGICS: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"BM", "bmp"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "webp"),  # 需再確認 offset 8 為 WEBP
]


class DocumentRouter:
    """判斷文件真實類型。PDF 另做文字覆蓋率分析決定是否需要 OCR。"""

    def __init__(self, settings: dict | None = None):
        from .config import SETTINGS
        cfg = (settings or SETTINGS)["ocr"]
        self.min_text_len = cfg["min_text_len_per_page"]
        self.digital_coverage = cfg["digital_coverage"]
        self.scanned_coverage = cfg["scanned_coverage"]

    # ── 主入口 ────────────────────────────────────────────────
    def detect(self, file_path: Path) -> DocType:
        file_path = Path(file_path)
        if not file_path.exists():
            raise CorruptedFileError(detail=f"檔案不存在：{file_path}")
        if file_path.stat().st_size == 0:
            raise EmptyFileError(detail=str(file_path.name))

        header = self._read_header(file_path)

        # PDF（開頭 1KB 內出現 %PDF- 皆算，容忍前置垃圾位元組）
        if b"%PDF-" in header[:1024]:
            return self._classify_pdf(file_path)

        # ZIP 容器 → OOXML (docx/xlsx/pptx) 或其他 zip
        if header.startswith(b"PK\x03\x04"):
            return self._classify_zip(file_path)

        # OLE 容器 → 舊版 Office 或 Outlook .msg
        if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            if file_path.suffix.lower() == ".msg":
                return DocType.EMAIL
            return DocType.LEGACY_OFFICE

        # 圖片
        for magic, kind in _IMAGE_MAGICS:
            if header.startswith(magic):
                if kind == "webp" and header[8:12] != b"WEBP":
                    continue
                return DocType.IMAGE

        # Email (.eml 是純文字，用標頭關鍵字判斷)
        if self._looks_like_eml(header):
            return DocType.EMAIL

        # 純文字（UTF-8/BIG5 可解碼且不含 NUL）
        if self._looks_like_text(header):
            return DocType.TEXT

        return DocType.UNKNOWN

    # ── PDF 分類：數位 / 掃描 / 混合 ─────────────────────────
    def _classify_pdf(self, file_path: Path) -> DocType:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            # PyMuPDF 未安裝時無法細分，先當數位 PDF 交給後續層報錯
            return DocType.PDF_DIGITAL

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            raise CorruptedFileError(detail=f"{file_path.name}: {e}") from e

        try:
            if doc.needs_pass:
                raise PasswordProtectedError(detail=file_path.name)
            total = len(doc)
            if total == 0:
                raise CorruptedFileError(detail=f"{file_path.name}: PDF 無任何頁面")
            # 大 PDF 只取樣前 30 頁做分類，避免路由階段就吃滿記憶體
            sample = min(total, 30)
            text_pages = 0
            for i in range(sample):
                text = doc[i].get_text().strip()
                if len(text) >= self.min_text_len:
                    text_pages += 1
            coverage = text_pages / sample
        finally:
            doc.close()

        if coverage >= self.digital_coverage:
            return DocType.PDF_DIGITAL
        if coverage <= self.scanned_coverage:
            return DocType.PDF_SCANNED
        return DocType.PDF_MIXED

    # ── ZIP 容器分類 ──────────────────────────────────────────
    def _classify_zip(self, file_path: Path) -> DocType:
        try:
            with zipfile.ZipFile(file_path) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile as e:
            raise CorruptedFileError(detail=f"{file_path.name}: {e}") from e

        if any(n.startswith("word/") for n in names):
            return DocType.WORD
        if any(n.startswith("xl/") for n in names):
            return DocType.EXCEL
        if any(n.startswith("ppt/") for n in names):
            return DocType.PPT
        return DocType.UNKNOWN

    # ── 輔助 ─────────────────────────────────────────────────
    @staticmethod
    def _read_header(file_path: Path, size: int = 2048) -> bytes:
        with open(file_path, "rb") as f:
            return f.read(size)

    @staticmethod
    def _looks_like_eml(header: bytes) -> bool:
        try:
            text = header.decode("utf-8", errors="ignore")
        except Exception:
            return False
        head_lines = text.splitlines()[:20]
        markers = ("Received:", "From:", "To:", "Subject:",
                   "Return-Path:", "MIME-Version:", "Date:")
        hits = sum(1 for line in head_lines
                   if any(line.startswith(m) for m in markers))
        return hits >= 3

    @staticmethod
    def _looks_like_text(header: bytes) -> bool:
        if b"\x00" in header:
            return False
        for enc in ("utf-8", "big5", "cp950"):
            try:
                header.decode(enc)
                return True
            except (UnicodeDecodeError, LookupError):
                continue
        return False
