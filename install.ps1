# install.ps1 — 在「有網路」的機器上執行一次，完成安裝＋模型下載。
# 使用 uv（比 pip 快 10 倍以上），並自動安裝相容的 Python 3.12，
# 不受機器上原有 Python 版本影響（PaddleOCR 需要 3.10~3.12）。
#
# 用法（PowerShell）：
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\install.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
# 中文與符號輸出需要 UTF-8（否則 Big5 主控台會亂碼甚至讓 Python 崩潰）
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "=== OCR 智慧文件辨識系統 安裝程式（uv）===" -ForegroundColor Cyan

# ⚠️ 雲端同步資料夾檢查：venv 會被同步機制損毀，且辨識結果（含個資）會被同步上雲
$syncMarkers = @("我的雲端硬碟", "My Drive", "OneDrive", "Dropbox", "iCloudDrive")
$here = (Get-Location).Path
foreach ($m in $syncMarkers) {
    if ($here -like "*$m*") {
        Write-Host ""
        Write-Host "❌ 偵測到本資料夾位於雲端同步路徑（$m）！" -ForegroundColor Red
        Write-Host "   1. venv 檔案會被同步軟體損毀，系統將不穩定" -ForegroundColor Red
        Write-Host "   2. output\ 的辨識結果（含個資）會被自動上傳雲端 → 個資外洩" -ForegroundColor Red
        Write-Host "   請先把整個資料夾複製到本機磁碟（例如 C:\smart-doc-ocr）再安裝。" -ForegroundColor Yellow
        $answer = Read-Host "仍要繼續嗎？(y/N)"
        if ($answer -ne 'y') { exit 1 }
        break
    }
}

# 0. 確保 uv 可用（優先用已安裝的；沒有就先透過 pip 裝）
function Invoke-Uv { param([string[]]$UvArgs)
    if (Get-Command uv -ErrorAction SilentlyContinue) { & uv @UvArgs }
    else { & python -m uv @UvArgs }
    if ($LASTEXITCODE -ne 0) { throw "uv 指令失敗：uv $($UvArgs -join ' ')" }
}
$hasUv = (Get-Command uv -ErrorAction SilentlyContinue) -or
         ((& python -m uv --version 2>$null) -ne $null)
if (-not $hasUv) {
    Write-Host "安裝 uv 中…"
    python -m pip install --quiet uv
}
Invoke-Uv @("--version")

# 1. 安裝相容的 Python 3.12 並建立虛擬環境
Invoke-Uv @("python", "install", "3.12")
if (-not (Test-Path ".venv")) {
    Invoke-Uv @("venv", ".venv", "--python", "3.12")
    Write-Host "✅ 虛擬環境建立完成（Python 3.12）"
}

# 2. 安裝套件（uv 平行下載 + 快取，遠快於 pip）
Invoke-Uv @("pip", "install", "--python", ".venv", "-r", "requirements.txt")
Write-Host "✅ 套件安裝完成"

# 3. 下載 AI 模型（PaddleOCR + 語意比對模型）
& .\.venv\Scripts\python.exe scripts\download_models.py

# 4. 健康檢查
& .\.venv\Scripts\python.exe cli.py doctor

# 5. 跑驗收測試
& .\.venv\Scripts\python.exe -m unittest discover -s tests -q

Write-Host ""
Write-Host "=== 安裝完成 ===" -ForegroundColor Green
Write-Host "雙擊 start.bat 啟動系統（瀏覽器開 http://localhost:8501）"
Write-Host ""
Write-Host "下一步（個資防護，建議執行）：" -ForegroundColor Yellow
Write-Host "  1. 離線打包部署：scripts\make_offline_bundle.ps1"
Write-Host "  2. 封鎖對外連線：scripts\setup_firewall.ps1（需系統管理員）"
