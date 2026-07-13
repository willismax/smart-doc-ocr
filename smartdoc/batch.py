"""批量處理：每份文件獨立 try/except + 重試 + 退避，一份壞檔不影響整批。"""
from __future__ import annotations

import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from .config import SETTINGS
from .errors import SmartDocError

logger = logging.getLogger(__name__)


class Status(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ProcessingResult:
    file_path: str
    status: Status
    output: dict = field(default_factory=dict)
    error: str = ""            # 給使用者看的繁中訊息
    error_detail: str = ""     # 技術細節（進 log / 報告附錄）
    duration_sec: float = 0.0
    retries: int = 0


def process_with_retry(file_path: Path, pipeline,
                       max_retries: int | None = None,
                       backoff: float | None = None) -> ProcessingResult:
    """單份文件處理，帶重試與指數退避。任何例外都被吞掉轉成結果物件。"""
    limits = SETTINGS["limits"]
    max_retries = limits["max_retries"] if max_retries is None else max_retries
    backoff = limits["retry_backoff_sec"] if backoff is None else backoff
    start = time.time()
    last_error = ""
    last_detail = ""

    for attempt in range(max_retries + 1):
        try:
            output = pipeline.process(file_path)
            return ProcessingResult(
                file_path=str(file_path), status=Status.SUCCESS,
                output=output,
                duration_sec=round(time.time() - start, 2),
                retries=attempt)
        except MemoryError:
            return ProcessingResult(
                file_path=str(file_path), status=Status.SKIPPED,
                error="記憶體不足，此檔案已跳過。請關閉其他程式或分批處理。",
                duration_sec=round(time.time() - start, 2),
                retries=attempt)
        except SmartDocError as e:
            # 可預期錯誤（格式不支援、檔案損壞…）：重試沒有意義，直接失敗
            return ProcessingResult(
                file_path=str(file_path), status=Status.FAILED,
                error=e.user_message, error_detail=e.detail,
                duration_sec=round(time.time() - start, 2),
                retries=attempt)
        except Exception as e:
            last_error = "處理時發生未預期錯誤，已記錄技術細節。"
            last_detail = traceback.format_exc()
            logger.error("處理 %s 失敗（第 %d 次）：%s",
                         file_path, attempt + 1, e)
            if attempt < max_retries:
                time.sleep(backoff * (2 ** attempt))

    return ProcessingResult(
        file_path=str(file_path), status=Status.FAILED,
        error=last_error, error_detail=last_detail,
        duration_sec=round(time.time() - start, 2),
        retries=max_retries + 1)


class BatchProcessor:
    def __init__(self, pipeline, max_workers: int | None = None):
        self.pipeline = pipeline
        self.max_workers = max_workers or SETTINGS["batch"]["max_workers"]
        self.results: list[ProcessingResult] = []

    def run(self, file_paths: list[Path],
            on_progress: Callable[[int, int, ProcessingResult], None] | None = None,
            ) -> list[ProcessingResult]:
        """批量執行。on_progress(done, total, result) 供 UI 更新進度。"""
        self.results = []
        total = len(file_paths)
        if total == 0:
            return []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(process_with_retry, fp, self.pipeline): fp
                       for fp in file_paths}
            done = 0
            for future in as_completed(futures):
                result = future.result()  # process_with_retry 不會丟例外
                self.results.append(result)
                done += 1
                if on_progress:
                    try:
                        on_progress(done, total, result)
                    except Exception:
                        pass  # 進度回呼壞掉不影響批次
        # 依原始順序排列
        order = {str(p): i for i, p in enumerate(file_paths)}
        self.results.sort(key=lambda r: order.get(r.file_path, 1 << 30))
        return self.results

    # ── 報告 ─────────────────────────────────────────────────
    def summary(self) -> dict:
        total = len(self.results)
        success = sum(1 for r in self.results if r.status == Status.SUCCESS)
        failed = sum(1 for r in self.results if r.status == Status.FAILED)
        skipped = sum(1 for r in self.results if r.status == Status.SKIPPED)
        avg = (sum(r.duration_sec for r in self.results) / total) if total else 0
        return {"total": total, "success": success, "failed": failed,
                "skipped": skipped, "avg_sec": round(avg, 1)}

    def report_markdown(self) -> str:
        s = self.summary()
        if s["total"] == 0:
            return "# 批量處理報告\n\n（無檔案）"
        lines = [
            "# 批量處理報告", "",
            "## 摘要",
            f"- 總計：{s['total']} 份",
            f"- 成功：{s['success']} 份"
            f"（{s['success'] / s['total'] * 100:.1f}%）",
            f"- 失敗：{s['failed']} 份",
            f"- 跳過：{s['skipped']} 份",
            f"- 平均耗時：{s['avg_sec']} 秒/份", "",
            "## 明細",
            "| 檔案 | 狀態 | 耗時(秒) | 個資數 | 說明 |",
            "|---|---|---|---|---|",
        ]
        icon = {Status.SUCCESS: "✅ 成功", Status.FAILED: "❌ 失敗",
                Status.SKIPPED: "⏭️ 跳過"}
        for r in self.results:
            name = Path(r.file_path).name
            pii = r.output.get("pii_report", {}).get("pii_count", "")
            note = r.error or ""
            lines.append(f"| {name} | {icon[r.status]} | {r.duration_sec} "
                         f"| {pii} | {note} |")
        failures = [r for r in self.results if r.status == Status.FAILED
                    and r.error_detail]
        if failures:
            lines += ["", "## 失敗技術細節（給資訊人員）", ""]
            for r in failures:
                lines += [f"### {Path(r.file_path).name}", "```",
                          r.error_detail[:2000], "```", ""]
        return "\n".join(lines)

    def report_xlsx(self, out_path: Path) -> Path | None:
        """輸出 Excel 差異表；openpyxl 未安裝時回傳 None。"""
        try:
            import openpyxl
        except ImportError:
            logger.warning("openpyxl 未安裝，略過 Excel 報告")
            return None
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "批量處理結果"
        ws.append(["檔案", "狀態", "類型", "頁數", "個資數",
                   "耗時(秒)", "重試", "說明"])
        for r in self.results:
            ws.append([
                Path(r.file_path).name, r.status.value,
                r.output.get("doc_type", ""), r.output.get("pages", ""),
                r.output.get("pii_report", {}).get("pii_count", ""),
                r.duration_sec, r.retries, r.error])
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out_path))
        return out_path
