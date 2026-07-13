"""Pipeline 總編排：驗證 → 路由 → 萃取 → 結構化 → 個資保護。

單份文件的完整處理入口。批量邏輯在 batch.py。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .audit import AuditLog
from .config import SETTINGS
from .errors import EmptyFileError, FileTooLargeError
from .pii import PIIProtector
from .recognizer import DocumentRecognizer
from .router import DocType, DocumentRouter
from .structurer import TextStructurer

logger = logging.getLogger(__name__)


def validate_file(path: Path, settings: dict | None = None) -> None:
    """處理前防衛性檢查，不通過直接丟 SmartDocError。"""
    cfg = (settings or SETTINGS)["limits"]
    path = Path(path)
    size = path.stat().st_size
    if size == 0:
        raise EmptyFileError(detail=path.name)
    size_mb = size / (1024 * 1024)
    if size_mb > cfg["max_file_size_mb"]:
        raise FileTooLargeError(
            f"檔案過大（{size_mb:.1f} MB，上限 {cfg['max_file_size_mb']} MB）。",
            detail=path.name)


class DocumentPipeline:
    """一份文件從進到出的完整流程。執行緒安全（各層皆無共享可變狀態，
    audit log 內部有鎖）。"""

    def __init__(self, settings: dict | None = None,
                 mask_pii: bool | None = None,
                 pii_operator: str | None = None):
        self.settings = settings or SETTINGS
        pii_cfg = self.settings["pii"]
        self.mask_pii = pii_cfg["default_mask"] if mask_pii is None else mask_pii
        self.pii_operator = pii_operator or pii_cfg["operator"]

        self.router = DocumentRouter(self.settings)
        self.recognizer = DocumentRecognizer(self.settings)
        self.structurer = TextStructurer()
        audit = None
        if pii_cfg["audit_enabled"]:
            audit = AuditLog(Path(self.settings["paths"]["logs"]) / "audit.jsonl")
        self.audit = audit
        self.pii = PIIProtector(
            custom_rules_path=Path(self.settings["paths"]["pii_rules"]),
            audit_log=audit)

    def process(self, path: Path) -> dict:
        """回傳：
        {
          file, doc_type, structured_text（依設定可能已遮蔽）,
          display_text（給 UI 顯示、預設遮蔽版）,
          pii_report {pii_count, pii_types, pii_labels, masked_text},
          pages（頁數）, used_ocr（是否動用 OCR）
        }
        """
        path = Path(path)
        validate_file(path, self.settings)
        doc_type = self.router.detect(path)
        raw = self.recognizer.extract(path, doc_type)
        structured = self.structurer.structure(raw)

        # 遮蔽版一律產生（供報告/稽核使用）；mask_pii 只決定畫面顯示哪個版本
        pii_report = self.pii.analyze_and_mask(
            structured, file_name=path.name, operator=self.pii_operator)
        display = (pii_report["masked_text"]
                   if self.mask_pii else structured)

        if self.audit is not None:
            self.audit.write(
                "process",
                file=path.name,
                doc_type=doc_type.value,
                chars=len(structured),
                masked=self.mask_pii)

        pages = raw.get("pages", [])
        return {
            "file": str(path),
            "file_name": path.name,
            "doc_type": doc_type.value,
            "structured_text": structured,
            "display_text": display,
            "pii_report": {
                "pii_count": pii_report["pii_count"],
                "pii_types": pii_report["pii_types"],
                "pii_labels": pii_report["pii_labels"],
                "masked_text": pii_report["masked_text"],
            },
            "pages": len(pages) if pages else 1,
            "used_ocr": doc_type in (DocType.PDF_SCANNED, DocType.PDF_MIXED,
                                     DocType.IMAGE)
                        or any(p.get("ocr") for p in pages),
        }
