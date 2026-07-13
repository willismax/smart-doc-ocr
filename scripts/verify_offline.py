"""安全驗收：確認本系統的 Python 已無法對外連線。

在「已設定防火牆」或「離線機」上執行：
    python scripts\\verify_offline.py
預期輸出：所有測試目標都連不上 → ✅ 通過。
若任何一個連得上 → ❌ 表示防火牆規則沒生效。
"""
from __future__ import annotations

import socket
import sys

TARGETS = [
    ("8.8.8.8", 53),          # Google DNS
    ("1.1.1.1", 443),         # Cloudflare
    ("huggingface.co", 443),  # 模型下載站（PII 外洩最常見出口）
    ("paddlepaddle.org.cn", 443),
]

def can_connect(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

if __name__ == "__main__":
    leaked = []
    for host, port in TARGETS:
        ok = can_connect(host, port)
        mark = "❌ 連得上（外洩風險）" if ok else "✅ 連不上"
        print(f"  {mark}  {host}:{port}")
        if ok:
            leaked.append(host)
    print()
    if leaked:
        print("❌ 未通過：此環境仍可對外連線，請執行 scripts\\setup_firewall.ps1")
        sys.exit(1)
    print("✅ 通過：本系統無法對外連線，個資不會經網路離開這台電腦。")
    sys.exit(0)
