@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [錯誤] 尚未安裝。請先以系統管理員執行 install.ps1
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
echo ============================================
echo   智慧文件辨識系統 啟動中...
echo   請在瀏覽器開啟  http://localhost:8501
echo   （關閉此視窗即停止系統）
echo ============================================
streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false --server.address 127.0.0.1
pause
