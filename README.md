# smart-doc-ocr — 智慧文件辨識與比對系統（離線版）

[![CI](https://github.com/willismax/smart-doc-ocr/actions/workflows/ci.yml/badge.svg)](https://github.com/willismax/smart-doc-ocr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10--3.12-blue.svg)](requirements.txt)
[![Platform: Windows 11](https://img.shields.io/badge/platform-Windows%2011-0078d4.svg)](#部署位置先讀這個)

Windows 11 離線部署的 OCR 文件辨識＋比對系統。給一般文書人員使用（純網頁介面），
所有運算在本機執行，文件與個資不經網路離開電腦。

> **Fully-offline OCR document recognition & comparison system for Windows 11.**
> Traditional Chinese-first PII detection with checksum validation (Taiwan ID /
> tax ID / Luhn), tamper-evident audit log (SHA-256 hash chain), batch processing
> with per-file error isolation, and a clerk-friendly Streamlit UI. No document
> ever leaves the machine.

## 功能

- **單檔辨識**：PDF（數位/掃描/混合）、Word、Excel、PPT、圖片（JPG/PNG/TIFF/BMP）、
  Email（.eml/.msg）、純文字 → 輸出乾淨的 Markdown
- **文件比對**：逐行文字差異 / 語意相似度 / 欄位比對（姓名、金額…）
- **批量處理**：一次丟 100+ 份，逐份獨立處理，一份壞檔不影響整批，輸出 Markdown＋Excel 報告
- **個資保護**：預設自動遮蔽（身分證、手機、Email、地址、信用卡、統編…），
  含台灣身分證/統編**檢查碼驗證**降低誤報；append-only 稽核日誌（雜湊鏈防竄改）

## ⚠️ 部署位置（先讀這個）

**請把本資料夾放在本機磁碟（例如 `C:\smart-doc-ocr`），不要放在
Google Drive / OneDrive / Dropbox 等雲端同步資料夾內**，原因有二：

1. **穩定性**：同步軟體會損毀 `.venv` 內的套件檔案（實測會發生）
2. **個資外洩**：`output\` 的辨識結果與 `logs\` 稽核日誌含個資，
   放在同步資料夾等於自動上傳雲端，直接違反離線個資保護的初衷

`install.ps1` 會自動偵測並警告。

## 快速開始（有網路的機器）

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1        # 用 uv 自動安裝 Python 3.12 + 所有套件 + AI 模型 + 跑測試
```

之後雙擊 `start.bat`，瀏覽器開 <http://localhost:8501>。

> 安裝使用 [uv](https://docs.astral.sh/uv/)：自動下載相容的 Python 3.12
> （PaddleOCR 不支援 3.13+），套件安裝比 pip 快一個數量級。

## 離線機部署

1. 在有網路的機器跑完 `install.ps1`
2. 執行 `scripts\make_offline_bundle.ps1` → 產出 `offline_packages\`（wheels）＋ `python-3.12\`（可攜式 Python）
3. 整個資料夾複製到離線機：
   ```powershell
   .\python-3.12\python.exe -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --no-index --find-links offline_packages -r requirements.txt
   .\.venv\Scripts\python.exe cli.py doctor   # 健康檢查
   ```
4. **個資防護（建議）**：以系統管理員執行 `scripts\setup_firewall.ps1`
   封鎖本系統 Python 的所有出站連線，再用 `python scripts\verify_offline.py` 驗證。

## 架構（六層 Pipeline）

```
上傳 → 路由器(magic bytes) → 影像前處理 → 辨識(OCR/萃取) → 結構化 → 個資保護 → 比對/輸出
```

| 層 | 模組 | 職責 |
|---|---|---|
| 1 路由 | `smartdoc/router.py` | magic bytes 判型（不信副檔名）＋PDF 文字覆蓋率分類 |
| 2 前處理 | `smartdoc/preprocessor.py` | 歪斜校正、去雜訊、CLAHE、條件式二值化 |
| 3 辨識 | `smartdoc/recognizer.py` | PaddleOCR（單例）＋PyMuPDF＋MarkItDown（三段降級） |
| 4 結構化 | `smartdoc/structurer.py` | OCR 雜訊清洗、表格→Markdown、欄位抽取 |
| 5 個資 | `smartdoc/pii.py` | 繁中規則引擎（檢查碼驗證＋上下文詞）、四種遮蔽模式 |
| 6 比對 | `smartdoc/comparator.py` | difflib / 語意向量（無模型自動降級 n-gram）/ 欄位比對 |

橫向支撐：`pipeline.py`（編排）、`batch.py`（重試＋錯誤隔離）、
`audit.py`（雜湊鏈稽核日誌）、`errors.py`（中文錯誤訊息）、`config.py`（設定）。

### 關鍵穩定性決策

- **路由靠 magic bytes**：副檔名改錯照樣正確處理；壞 zip/空檔/加密 PDF 在入口就擋下並給中文訊息
- **每份文件獨立 try/except**：可預期錯誤（損壞、不支援）不重試直接報告；
  未預期錯誤指數退避重試 2 次；`MemoryError` 直接跳過該檔
- **PDF 轉圖用 PyMuPDF 內建 rasterizer**：不需要 poppler（少一個 Windows 常見環境地雷）
- **重依賴全部 lazy import**：PaddleOCR / OpenCV / sentence-transformers 缺席時系統照常啟動，
  對應功能降級並在介面明確提示
- **遮蔽版一律產生**：畫面顯示原文與否只是開關，稽核與報告永遠有遮蔽版

## 常用指令

```powershell
.\.venv\Scripts\python.exe cli.py doctor                 # 依賴健康檢查
.\.venv\Scripts\python.exe cli.py process 資料夾 --out output  # 批量辨識（排程可用）
.\.venv\Scripts\python.exe cli.py compare a.pdf b.pdf    # 快速比對
.\.venv\Scripts\python.exe cli.py verify-audit           # 驗證稽核日誌未被竄改
.\.venv\Scripts\python.exe -m unittest discover -s tests # 跑驗收測試（67 項）
```

## 設定

- `config/settings.yaml`：檔案大小上限、OCR 語言/DPI、遮蔽模式、並行數
- `config/pii_rules.yaml`：自定義 PII 規則（regex＋上下文詞＋內建檢查碼驗證器）

## 貢獻與授權

- 貢獻方式見 [CONTRIBUTING.md](CONTRIBUTING.md)（含 Windows 相容性守則——三個實測踩過的地雷）
- 安全漏洞回報見 [SECURITY.md](SECURITY.md)
- 版本紀錄見 [CHANGELOG.md](CHANGELOG.md)
- 授權：[MIT](LICENSE)

## 目錄結構

```
smart-doc-ocr/
├── app.py            Streamlit 網頁介面（文書人員入口）
├── cli.py            命令列（資訊人員/排程）
├── start.bat         雙擊啟動
├── install.ps1       一鍵安裝（uv）
├── smartdoc/         六層 pipeline 模組
├── config/           settings.yaml、pii_rules.yaml
├── scripts/          模型下載、離線打包、防火牆、離線驗證
├── models/           AI 模型（det/rec/cls/multilingual-MiniLM）
├── tests/            67 項單元＋端對端測試
├── logs/             app.log＋audit.jsonl（稽核，勿手動編輯）
└── output/           辨識結果與報告
```
