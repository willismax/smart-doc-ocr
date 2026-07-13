# make_offline_bundle.ps1 — 在有網路的機器上打包，供「完全離線」的機器安裝。
# 產出：
#   offline_packages\   所有 wheel（對應 Python 3.12 / Windows x64）
#   python-3.12\        可攜式 Python（免安裝，直接複製）
#   models\             已由 download_models.py 下載的 AI 模型
#
# 離線機安裝（把整個專案資料夾複製過去後）：
#   .\python-3.12\python.exe -m venv .venv
#   .\.venv\Scripts\python.exe -m pip install --no-index --find-links offline_packages -r requirements.txt
#   .\.venv\Scripts\python.exe cli.py doctor

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "❌ 請先執行 install.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "=== 1/2 下載所有 wheel（以 venv 的 Python 3.12 為準）===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force offline_packages | Out-Null
& .\.venv\Scripts\python.exe -m pip download -r requirements.txt -d offline_packages
& .\.venv\Scripts\python.exe -m pip download pip setuptools wheel -d offline_packages

Write-Host "=== 2/2 複製可攜式 Python 3.12 ===" -ForegroundColor Cyan
# uv 管理的 Python 是可攜式的，直接複製即可在離線機使用
$uvPython = & .\.venv\Scripts\python.exe -c "import sys; print(sys.base_prefix)"
if (Test-Path $uvPython) {
    robocopy $uvPython "python-3.12" /E /NFL /NDL /NJH /NJS | Out-Null
    Write-Host "✅ 已複製 $uvPython → python-3.12\"
} else {
    Write-Host "⚠️ 找不到基底 Python（$uvPython），離線機請自行安裝 Python 3.12" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Green
Write-Host "把整個專案資料夾（含 offline_packages\、python-3.12\、models\）"
Write-Host "複製到離線機，然後在離線機執行："
Write-Host "  .\python-3.12\python.exe -m venv .venv"
Write-Host "  .\.venv\Scripts\python.exe -m pip install --no-index --find-links offline_packages -r requirements.txt"
Write-Host "  .\.venv\Scripts\python.exe cli.py doctor"
Write-Host "  （之後雙擊 start.bat 即可使用）"
