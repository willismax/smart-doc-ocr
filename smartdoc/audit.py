"""稽核日誌 — append-only JSONL + 雜湊鏈（tamper-evident）。

每筆記錄含前一筆的 SHA-256，形成鏈：竄改或刪除任何一筆，
後續所有 entry_hash 都對不上，verify_chain() 立即發現。
比「唯讀屬性」更實際：Windows 上管理員永遠能改檔案，
但改了會被驗證抓到。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return _GENESIS
        last = None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
        except OSError:
            return _GENESIS
        if not last:
            return _GENESIS
        try:
            return json.loads(last).get("entry_hash", _GENESIS)
        except json.JSONDecodeError:
            return _GENESIS

    @staticmethod
    def _hash_entry(prev_hash: str, payload: dict) -> str:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()

    def write(self, event: str, **fields) -> dict:
        """寫入一筆稽核記錄，回傳完整 entry。"""
        payload = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "event": event,
            **fields,
        }
        with self._lock:
            entry_hash = self._hash_entry(self._last_hash, payload)
            entry = {**payload,
                     "prev_hash": self._last_hash,
                     "entry_hash": entry_hash}
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._last_hash = entry_hash
        return entry

    def verify_chain(self) -> tuple[bool, str]:
        """驗證整條鏈。回傳 (是否完整, 說明)。"""
        if not self.path.exists():
            return True, "尚無稽核記錄"
        prev = _GENESIS
        with open(self.path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return False, f"第 {lineno} 行不是合法 JSON（可能被竄改）"
                claimed = entry.pop("entry_hash", None)
                stated_prev = entry.pop("prev_hash", None)
                if stated_prev != prev:
                    return False, f"第 {lineno} 行 prev_hash 斷鏈（前面有記錄被刪除或修改）"
                if self._hash_entry(prev, entry) != claimed:
                    return False, f"第 {lineno} 行內容與雜湊不符（該行被竄改）"
                prev = claimed
        return True, "稽核日誌完整無竄改"
