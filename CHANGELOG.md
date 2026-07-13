# Changelog

本專案遵循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [1.0.0] - 2026-07-13

### 新增
- 六層 Pipeline：magic bytes 路由 → 影像前處理 → 辨識 → 結構化 → 個資保護 → 比對
- 支援格式：PDF（數位/掃描/混合）、Word、Excel、PPT、圖片、Email（.eml/.msg）、純文字
- PaddleOCR 繁中辨識（CPU/GPU 自動切換）＋ OpenCV 前處理（歪斜校正/去雜訊/CLAHE）
- 內建繁中 PII 引擎：台灣身分證/統編**檢查碼驗證**、信用卡 Luhn、
  上下文詞過濾、四種遮蔽模式（replace/redact/hash/keep）
- 三種比對：逐行差異（difflib）、語意相似度（multilingual-MiniLM，
  無模型自動降級 n-gram）、欄位比對
- 批量處理：逐檔錯誤隔離＋指數退避重試＋Markdown/Excel 報告
- 稽核日誌：append-only JSONL＋SHA-256 雜湊鏈（防竄改），`verify-audit` 驗證
- Streamlit 網頁介面（文書人員）＋ CLI（資訊人員/排程）
- 離線部署工具鏈：uv 一鍵安裝、離線打包（wheels＋可攜式 Python）、
  防火牆封鎖腳本、離線驗證腳本
- 67 項單元＋端對端測試（stdlib unittest，離線可跑）

### Windows 相容性修復
- `.ps1` 全部改為 UTF-8 with BOM（PowerShell 5.1 Big5 解析問題）
- torch 鎖定 2.5.1 並強制先於 paddle 載入（DLL 衝突 WinError 127）
- 模型路徑含非 ASCII 字元時自動鏡像至 `%LOCALAPPDATA%`（PaddlePaddle 路徑限制）
