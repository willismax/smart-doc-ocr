"""命令列介面 — 給資訊人員驗證/排程用；文書人員請用 start.bat（網頁介面）。

用法：
    python cli.py process 檔案或資料夾 [--no-mask] [--out 輸出目錄]
    python cli.py compare 檔案A 檔案B [--mode diff|semantic]
    python cli.py verify-audit          # 驗證稽核日誌未被竄改
    python cli.py doctor                # 檢查各依賴安裝狀態
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_process(args) -> int:
    from smartdoc.batch import BatchProcessor, Status
    from smartdoc.config import SETTINGS
    from smartdoc.pipeline import DocumentPipeline

    target = Path(args.path)
    if target.is_dir():
        exts = {".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".doc", ".xls",
                ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
                ".eml", ".msg", ".txt", ".md", ".csv"}
        files = sorted(p for p in target.rglob("*")
                       if p.is_file() and p.suffix.lower() in exts)
    else:
        files = [target]
    if not files:
        print("找不到可處理的檔案")
        return 1

    out_dir = Path(args.out or SETTINGS["paths"]["output"])
    out_dir.mkdir(parents=True, exist_ok=True)

    pipeline = DocumentPipeline(mask_pii=not args.no_mask)
    processor = BatchProcessor(pipeline)

    def on_progress(done, total, result):
        icon = "OK " if result.status == Status.SUCCESS else "ERR"
        print(f"[{done}/{total}] {icon} {Path(result.file_path).name}"
              f" ({result.duration_sec}s) {result.error}")

    results = processor.run(files, on_progress=on_progress)
    for r in results:
        if r.status == Status.SUCCESS:
            stem = Path(r.file_path).stem
            (out_dir / f"{stem}.md").write_text(
                r.output.get("display_text", ""), encoding="utf-8")

    (out_dir / "batch_report.md").write_text(
        processor.report_markdown(), encoding="utf-8")
    processor.report_xlsx(out_dir / "batch_report.xlsx")
    s = processor.summary()
    print(f"\n完成：成功 {s['success']}/{s['total']}，"
          f"報告在 {out_dir}")
    return 0 if s["failed"] + s["skipped"] == 0 else 2


def cmd_compare(args) -> int:
    from smartdoc.comparator import DocumentComparator
    from smartdoc.pipeline import DocumentPipeline

    pipeline = DocumentPipeline()
    ra = pipeline.process(Path(args.file_a))
    rb = pipeline.process(Path(args.file_b))
    comparator = DocumentComparator()
    if args.mode == "semantic":
        r = comparator.semantic_similarity(
            ra["structured_text"], rb["structured_text"])
        print(f"語意相似度：{r['score'] * 100:.1f}%（{r['method']}）")
    else:
        d = comparator.diff_text(ra["display_text"], rb["display_text"])
        print(f"文字相似度：{d['similarity_pct']}  "
              f"新增 {d['added']} 行 / 刪除 {d['removed']} 行")
        print("\n".join(d["diff_lines"][:200]))
    return 0


def cmd_verify_audit(_args) -> int:
    from smartdoc.audit import AuditLog
    from smartdoc.config import SETTINGS
    log = AuditLog(Path(SETTINGS["paths"]["logs"]) / "audit.jsonl")
    ok, msg = log.verify_chain()
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


def cmd_doctor(_args) -> int:
    # torch 必須先於 paddle 載入（Windows DLL 衝突，WinError 127）
    try:
        import torch  # noqa: F401
    except Exception:
        pass
    checks = [
        ("PyMuPDF（PDF 讀取）", "fitz", True),
        ("Pillow（圖片讀取）", "PIL", True),
        ("PyYAML（設定檔）", "yaml", False),
        ("OpenCV（影像前處理）", "cv2", False),
        ("NumPy", "numpy", True),
        ("PaddleOCR（掃描辨識）", "paddleocr", False),
        ("MarkItDown（Office 轉換）", "markitdown", False),
        ("python-docx（Word 降級）", "docx", False),
        ("openpyxl（Excel）", "openpyxl", False),
        ("python-pptx（PPT 降級）", "pptx", False),
        ("sentence-transformers（語意比對）", "sentence_transformers", False),
        ("Streamlit（網頁介面）", "streamlit", True),
        ("extract-msg（Outlook 郵件）", "extract_msg", False),
    ]
    print(f"Python {sys.version}\n")
    missing_required = 0
    for label, module, required in checks:
        try:
            __import__(module)
            print(f"  ✅ {label}")
        except ImportError:
            mark = "❌ 必要" if required else "⚠️ 選用"
            print(f"  {mark} {label} — 未安裝")
            if required:
                missing_required += 1
        except Exception as e:  # 已安裝但載入失敗（如 torch DLL 錯誤）
            mark = "❌ 必要" if required else "⚠️ 選用"
            print(f"  {mark} {label} — 已安裝但載入失敗：{e}")
            if required:
                missing_required += 1
    from smartdoc.recognizer import OcrEngine
    engine = OcrEngine.get()
    print("\nOCR 引擎：" + ("✅ 可用" if engine.available
                          else f"⚠️ 不可用（{engine.load_error}）"))
    from smartdoc.config import SETTINGS
    model_dir = Path(SETTINGS["compare"]["semantic_model_dir"])
    print("語意模型：" + ("✅ 已就位" if model_dir.is_dir()
                        else "⚠️ 未下載（比對將用降級演算法）"))
    return 0 if missing_required == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="辨識檔案或整個資料夾")
    p.add_argument("path")
    p.add_argument("--no-mask", action="store_true", help="不遮蔽個資")
    p.add_argument("--out", default=None, help="輸出目錄")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("compare", help="比對兩份文件")
    p.add_argument("file_a")
    p.add_argument("file_b")
    p.add_argument("--mode", choices=["diff", "semantic"], default="diff")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("verify-audit", help="驗證稽核日誌完整性")
    p.set_defaults(func=cmd_verify_audit)

    p = sub.add_parser("doctor", help="檢查依賴安裝狀態")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
