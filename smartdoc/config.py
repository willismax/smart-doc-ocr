"""全域設定載入。

config/settings.yaml 存在時覆蓋預設值；不存在或 PyYAML 缺席時用內建預設，
確保系統在最小依賴下仍可啟動。
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

# 專案根目錄（smartdoc/ 的上一層）
ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "paths": {
        "models": str(ROOT / "models"),
        "logs": str(ROOT / "logs"),
        "output": str(ROOT / "output"),
        "pii_rules": str(ROOT / "config" / "pii_rules.yaml"),
    },
    "limits": {
        "max_file_size_mb": 200,
        "max_pdf_pages": 1000,
        "pdf_chunk_pages": 10,       # 大 PDF 分批頁數
        "max_retries": 2,            # 每份文件失敗重試次數
        "retry_backoff_sec": 2.0,
    },
    "ocr": {
        "engine": "paddle",          # paddle | none
        "lang": "chinese_cht",       # PaddleOCR 語言：繁中
        "use_gpu": "auto",           # auto | true | false
        "dpi": 300,                  # 掃描 PDF 轉圖解析度
        "min_text_len_per_page": 50, # 判斷「頁面有文字層」的門檻
        "digital_coverage": 0.8,     # 文字頁占比 > 此值 → 數位 PDF
        "scanned_coverage": 0.1,     # 文字頁占比 < 此值 → 掃描 PDF
    },
    "pii": {
        "default_mask": True,        # 預設遮蔽；要看原文需主動關閉
        "operator": "replace",       # replace | redact | hash | keep
        "audit_enabled": True,
    },
    "compare": {
        "semantic_model_dir": str(ROOT / "models" / "multilingual-MiniLM"),
        "chunk_chars": 400,
    },
    "batch": {
        "max_workers": 2,            # OCR 為 CPU 密集，預設保守
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """讀取 settings.yaml 併入預設值；任何讀取失敗都回退到預設。"""
    path = path or (ROOT / "config" / "settings.yaml")
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        import yaml  # lazy：沒裝 PyYAML 也能跑
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        if not isinstance(user_cfg, dict):
            return copy.deepcopy(DEFAULTS)
        return _deep_merge(DEFAULTS, user_cfg)
    except Exception:
        return copy.deepcopy(DEFAULTS)


# 模組層單例（app 內共用）
SETTINGS = load_settings()
