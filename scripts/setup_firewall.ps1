# setup_firewall.ps1 — 個資防護第一道：封鎖本系統 Python 的所有出站連線。
# 就算未來某個套件想偷偷連網，作業系統層直接擋掉。
# 需以「系統管理員」執行。

#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$pythonExe  = Join-Path $root ".venv\Scripts\python.exe"
$streamlit  = Join-Path $root ".venv\Scripts\streamlit.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "❌ 找不到 $pythonExe，請先執行 install.ps1" -ForegroundColor Red
    exit 1
}

foreach ($exe in @($pythonExe, $streamlit)) {
    if (-not (Test-Path $exe)) { continue }
    $name = "SmartDocOCR 封鎖出站 - $(Split-Path $exe -Leaf)"
    # 先移除舊規則避免重複
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $name `
        -Direction Outbound -Program $exe -Action Block `
        -Profile Any -Enabled True | Out-Null
    Write-Host "✅ 已封鎖出站：$exe"
}

Write-Host ""
Write-Host "注意：localhost（127.0.0.1）不經過防火牆，" -ForegroundColor Yellow
Write-Host "Streamlit 網頁介面照常運作，只有『對外』連線被封鎖。" -ForegroundColor Yellow
Write-Host "驗證：啟動系統後執行 scripts\verify_offline.py 應顯示全部連線失敗。"
