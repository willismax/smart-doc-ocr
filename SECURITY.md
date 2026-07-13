# 安全政策

本專案的核心價值是「文件與個資不離開本機」。任何違反此承諾的行為都視為安全漏洞。

## 屬於安全漏洞的情況

- 任何未經使用者同意的**對外網路連線**（模型下載腳本除外，且僅限安裝階段）
- PII 遮蔽可被繞過（遮蔽後的輸出可反推原始個資）
- 稽核日誌（`logs/audit.jsonl`）的雜湊鏈可在不被 `verify-audit` 偵測的情況下竄改
- 惡意構造的文件（PDF/Office/圖片）造成任意程式碼執行

## 回報方式

請**不要**開公開 Issue 揭露漏洞細節。請使用 GitHub 的
[Private Vulnerability Reporting](https://github.com/willismax/smart-doc-ocr/security/advisories/new)
回報，我們會盡快回應。

## 部署端的安全建議

1. 執行 `scripts\setup_firewall.ps1` 封鎖 Python 出站連線，
   並用 `scripts\verify_offline.py` 驗證
2. 不要把專案放在雲端同步資料夾（Google Drive / OneDrive / Dropbox），
   `output/` 與 `logs/` 含個資會被自動上傳
3. `output/` 目錄建議設定 Windows ACL，僅授權帳號可讀
4. 定期執行 `python cli.py verify-audit` 確認稽核日誌完整
