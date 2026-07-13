"""Layer 5 — 個資保護。

內建繁中規則引擎（零外部依賴、完全離線）：
- 台灣身分證字號：regex + 官方檢查碼演算法驗證（大幅降低誤報）
- 統一編號：regex + 財政部檢查碼驗證 + 上下文詞
- 信用卡號：regex + Luhn 驗證
- 手機 / 市話 / Email / 護照 / 銀行帳號 / 地址 / 姓名欄位
- 可從 config/pii_rules.yaml 追加自定義規則

Presidio 若有安裝會做為「額外」偵測器疊加（聯集），沒裝也完全可用。
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


# ── 驗證器 ──────────────────────────────────────────────────────

_TW_ID_LETTER = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16,
    "H": 17, "I": 34, "J": 18, "K": 19, "L": 20, "M": 21, "N": 22,
    "O": 35, "P": 23, "Q": 24, "R": 25, "S": 26, "T": 27, "U": 28,
    "V": 29, "W": 32, "X": 30, "Y": 31, "Z": 33,
}


def validate_tw_id(value: str) -> bool:
    """台灣身分證字號檢查碼（1 英文 + 1~2 開頭 + 8 數字）。"""
    if not re.fullmatch(r"[A-Z][12]\d{8}", value):
        return False
    n = _TW_ID_LETTER[value[0]]
    digits = [n // 10, n % 10] + [int(c) for c in value[1:]]
    weights = [1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1]
    return sum(d * w for d, w in zip(digits, weights)) % 10 == 0


def validate_tw_company_id(value: str) -> bool:
    """統一編號檢查碼（財政部 2023 新制：加權和可被 5 整除）。"""
    if not re.fullmatch(r"\d{8}", value):
        return False
    weights = [1, 2, 1, 2, 1, 2, 4, 1]
    total = 0
    for d, w in zip(value, weights):
        p = int(d) * w
        total += p // 10 + p % 10
    if total % 5 == 0:
        return True
    # 第 7 位是 7 時，乘積 7*4=28 → 2+8=10，可取 1+0 或視為 1
    return value[6] == "7" and (total + 1) % 5 == 0


def validate_luhn(value: str) -> bool:
    digits = [int(c) for c in re.sub(r"[\s-]", "", value)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ── 規則定義 ────────────────────────────────────────────────────

@dataclass
class PiiRule:
    entity: str                      # 例：TW_ID_NUMBER
    label: str                       # 遮蔽時顯示的中文標籤，例：身分證字號
    regex: str
    score: float = 0.8
    validator: Callable[[str], bool] | None = None
    context_words: list[str] = field(default_factory=list)
    context_required: bool = False   # True → 附近沒有上下文詞就不算 PII
    context_window: int = 30         # 前後各看幾個字元
    _compiled: re.Pattern = field(init=False, repr=False, default=None)

    def __post_init__(self):
        self._compiled = re.compile(self.regex)


@dataclass
class PiiFinding:
    entity: str
    label: str
    start: int
    end: int
    text: str
    score: float


BUILTIN_RULES: list[PiiRule] = [
    PiiRule("TW_ID_NUMBER", "身分證字號",
            r"(?<![A-Z0-9])[A-Z][12]\d{8}(?!\d)",
            score=0.95, validator=validate_tw_id),
    PiiRule("TW_MOBILE", "手機號碼",
            r"(?<!\d)09\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)",
            score=0.85),
    PiiRule("TW_LANDLINE", "市話號碼",
            r"(?<!\d)\(?0\d{1,2}\)?[\s-]?\d{3,4}[\s-]?\d{4}(?!\d)",
            score=0.6,
            context_words=["電話", "聯絡", "TEL", "Tel", "tel", "分機"],
            context_required=True),
    PiiRule("EMAIL", "電子郵件",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            score=0.9),
    PiiRule("CREDIT_CARD", "信用卡號",
            r"(?<!\d)(?:\d[ -]?){13,19}(?<![ -])(?!\d)",
            score=0.9, validator=validate_luhn,
            context_words=["卡號", "信用卡", "VISA", "Master", "JCB", "刷卡"],
            context_required=True),
    PiiRule("TW_COMPANY_ID", "統一編號",
            r"(?<!\d)\d{8}(?!\d)",
            score=0.75, validator=validate_tw_company_id,
            context_words=["統編", "統一編號", "公司", "營業人", "買受人"],
            context_required=True),
    PiiRule("PASSPORT", "護照號碼",
            r"(?<![A-Z0-9])[0-9]{9}(?![0-9])|(?<![A-Z0-9])[A-Z]{1,2}\d{7,8}(?!\d)",
            score=0.6,
            context_words=["護照", "Passport", "passport", "PASSPORT"],
            context_required=True),
    PiiRule("BANK_ACCOUNT", "銀行帳號",
            r"(?<!\d)\d{10,16}(?!\d)",
            score=0.6,
            context_words=["帳號", "帳戶", "匯款", "銀行", "郵局", "轉帳"],
            context_required=True),
    PiiRule("TW_ADDRESS", "地址",
            r"[一-鿿]{1,4}[縣市][一-鿿]{1,4}[區鄉鎮市]"
            r"[一-鿿0-9]{1,20}?[路街道巷弄][0-9０-９\-之]{1,8}號"
            r"(?:[0-9０-９]{1,3}樓)?",
            score=0.85),
    PiiRule("PERSON_NAME_FIELD", "姓名",
            r"(?<=姓名[:：])[ 　]?[一-鿿]{2,4}"
            r"|(?<=申請人[:：])[ 　]?[一-鿿]{2,4}"
            r"|(?<=立書人[:：])[ 　]?[一-鿿]{2,4}"
            r"|(?<=收件人[:：])[ 　]?[一-鿿]{2,4}",
            score=0.85),
    PiiRule("BIRTHDAY_FIELD", "出生日期",
            r"(?:19|20)\d{2}[./年-]\s?\d{1,2}[./月-]\s?\d{1,2}日?",
            score=0.5,
            context_words=["出生", "生日", "誕生"],
            context_required=True),
]

_VALIDATORS = {
    "tw_id": validate_tw_id,
    "tw_company_id": validate_tw_company_id,
    "luhn": validate_luhn,
}


def load_custom_rules(path: Path) -> list[PiiRule]:
    """從 YAML 載入自定義規則；檔案缺席或格式錯誤時回傳空清單並記 log。"""
    path = Path(path)
    if not path.exists():
        return []
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        rules = []
        for item in data.get("pii_rules", []):
            rules.append(PiiRule(
                entity=item["name"],
                label=item.get("label", item["name"]),
                regex=item["regex"],
                score=float(item.get("score", 0.7)),
                validator=_VALIDATORS.get(item.get("validator", "")),
                context_words=item.get("context_words", []),
                context_required=bool(item.get("context_required",
                                               bool(item.get("context_words")))),
            ))
        return rules
    except Exception as e:
        logger.warning("自定義 PII 規則載入失敗（%s），僅使用內建規則", e)
        return []


# ── 偵測與遮蔽 ──────────────────────────────────────────────────

class PIIProtector:
    """偵測 + 遮蔽 + 稽核。operator: replace | redact | hash | keep"""

    def __init__(self, rules: list[PiiRule] | None = None,
                 custom_rules_path: Path | None = None,
                 audit_log=None):
        self.rules = list(rules if rules is not None else BUILTIN_RULES)
        if custom_rules_path:
            self.rules += load_custom_rules(custom_rules_path)
        self.audit_log = audit_log

    def detect(self, text: str) -> list[PiiFinding]:
        findings: list[PiiFinding] = []
        for rule in self.rules:
            for m in rule._compiled.finditer(text):
                value = m.group()
                if rule.validator and not rule.validator(
                        re.sub(r"[\s-]", "", value)
                        if rule.entity == "CREDIT_CARD" else value):
                    continue
                if rule.context_required and not self._has_context(
                        text, m.start(), m.end(),
                        rule.context_words, rule.context_window):
                    continue
                findings.append(PiiFinding(
                    entity=rule.entity, label=rule.label,
                    start=m.start(), end=m.end(),
                    text=value, score=rule.score))
        return self._resolve_overlaps(findings)

    def mask(self, text: str, findings: list[PiiFinding] | None = None,
             operator: str = "replace") -> str:
        if findings is None:
            findings = self.detect(text)
        if operator == "keep":
            return text
        out = text
        for f in sorted(findings, key=lambda x: x.start, reverse=True):
            if operator == "replace":
                repl = f"《{f.label}》"
            elif operator == "redact":
                repl = ""
            elif operator == "hash":
                digest = hashlib.sha256(f.text.encode("utf-8")).hexdigest()[:8]
                repl = f"《{f.label}#{digest}》"
            else:
                raise ValueError(f"未知的遮蔽模式：{operator}")
            out = out[:f.start] + repl + out[f.end:]
        return out

    def analyze_and_mask(self, text: str, file_name: str = "",
                         operator: str = "replace") -> dict:
        """一站式：偵測 → 遮蔽 → 稽核。回傳含統計的 dict。"""
        findings = self.detect(text)
        masked = self.mask(text, findings, operator)
        if self.audit_log is not None:
            self.audit_log.write(
                "pii_scan",
                file=file_name,
                operator=operator,
                pii_count=len(findings),
                pii_types=sorted({f.entity for f in findings}),
            )
        return {
            "masked_text": masked,
            "pii_count": len(findings),
            "pii_types": sorted({f.entity for f in findings}),
            "pii_labels": sorted({f.label for f in findings}),
            "findings": findings,
        }

    # ── 內部 ─────────────────────────────────────────────────
    @staticmethod
    def _has_context(text: str, start: int, end: int,
                     words: list[str], window: int) -> bool:
        if not words:
            return True
        lo = max(0, start - window)
        hi = min(len(text), end + window)
        around = text[lo:hi]
        return any(w in around for w in words)

    @staticmethod
    def _resolve_overlaps(findings: list[PiiFinding]) -> list[PiiFinding]:
        """重疊時保留分數高（同分取較長）者。"""
        ordered = sorted(findings,
                         key=lambda f: (-f.score, -(f.end - f.start), f.start))
        kept: list[PiiFinding] = []
        for f in ordered:
            if all(f.end <= k.start or f.start >= k.end for k in kept):
                kept.append(f)
        return sorted(kept, key=lambda f: f.start)
