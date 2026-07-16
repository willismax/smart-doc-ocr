# 貢獻指南

感謝你有興趣改進本專案！

## 開發環境

```powershell
git clone https://github.com/willismax/smart-doc-ocr.git
cd smart-doc-ocr
.\install.ps1          # uv 自動安裝 Python 3.12 + 依賴 + 模型
```

只改核心邏輯（不碰 OCR / 語意模型）的話，輕量環境就夠：

```powershell
python -m uv venv .venv --python 3.12
python -m uv pip install --python .venv -r requirements-core.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 送 PR 前

1. **跑測試**：`python -m unittest discover -s tests`（67+ 項，必須全綠）
2. **新功能附測試**：測試放 `tests/`，用 stdlib `unittest`（離線機也要能跑驗收）
3. **維持降級原則**：重依賴（PaddleOCR、torch、OpenCV…）一律 lazy import，
   缺席時功能降級並提示，不能讓系統啟動失敗
4. **錯誤訊息雙軌**：給使用者的訊息用繁中（`SmartDocError.user_message`），
   技術細節進 log

## Windows 相容性守則（血淚教訓，違反必炸）

- `.ps1` 檔案必須存成 **UTF-8 with BOM**（PowerShell 5.1 會把無 BOM 檔當 Big5 解析，
  中文註解會吞掉換行讓指令消失）
- `.bat` 檔案必須**全 ASCII**（cmd 以 OEM 代碼頁逐行解析，中文位元組會吞換行；
  cmd 對 UTF-8 BOM 支援又很差，所以連 BOM 這條路都沒有）
- **torch 必須先於 paddle import**（DLL 衝突 → WinError 127），
  新增會 import 兩者之一的進入點時，記得先預載 torch
- PaddlePaddle 打不開含非 ASCII 字元的路徑，模型路徑處理請走
  `OcrEngine._ascii_safe_models()`
- 呼叫 Python 子程序時設 `PYTHONUTF8=1`
- PowerShell 腳本內**不要對原生指令用 `2>$null` / `2>&1`**：
  PS 5.1 在 `$ErrorActionPreference = "Stop"` 下會把 stderr 包成終止錯誤，
  連「檢查指令是否存在」都會直接炸。需要靜音偵測時走
  `cmd /c "指令 >nul 2>nul"` 再看 `$LASTEXITCODE`

## 架構速覽

```
router → preprocessor → recognizer → structurer → pii → comparator
```

每層一個模組、各自可獨立替換，詳見 [README.md](README.md#架構六層-pipeline)。

## 回報問題

開 Issue 時請附上：
- `python cli.py doctor` 的輸出
- `logs/app.log` 相關段落（**請先確認不含個資**）
- 可重現的步驟（測試檔請自行去識別化）

## 授權

送出 PR 即表示同意你的貢獻以 [MIT License](LICENSE) 釋出。
