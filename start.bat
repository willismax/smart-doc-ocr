@echo off
rem Keep this file ASCII-only: cmd.exe parses batch files with the OEM
rem codepage (Big5 on zh-TW systems) and multi-byte characters corrupt
rem line breaks, turning comments into broken commands.
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Not installed yet. Run install.ps1 first.
    echo         PowerShell:  Set-ExecutionPolicy -Scope Process Bypass
    echo                      .\install.ps1
    pause
    exit /b 1
)

echo ============================================
echo   Smart Doc OCR - starting...
echo   Open your browser at:  http://localhost:8501
echo   (Close this window to stop the system)
echo ============================================
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false --server.address 127.0.0.1
pause
