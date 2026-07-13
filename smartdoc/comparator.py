"""Layer 6 — 比對引擎。

三種模式：
① 逐行文字差異（difflib，零依賴）
② 語意相似度（sentence-transformers 離線模型；未安裝時自動降級為
   字元 bigram 餘弦相似度 — 純 Python，對中文效果尚可）
③ 欄位比對（exact / numeric / fuzzy）
"""
from __future__ import annotations

import difflib
import logging
import math
import re
from collections import Counter
from pathlib import Path

from .config import SETTINGS

logger = logging.getLogger(__name__)


class DocumentComparator:
    def __init__(self, settings: dict | None = None):
        self.cfg = (settings or SETTINGS)["compare"]
        self._model = None
        self._model_checked = False

    # ── 模式一：逐行文字差異 ─────────────────────────────────
    def diff_text(self, text_a: str, text_b: str) -> dict:
        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()
        diff = list(difflib.unified_diff(
            lines_a, lines_b,
            fromfile="文件 A", tofile="文件 B", lineterm=""))
        similarity = difflib.SequenceMatcher(None, text_a, text_b).ratio()
        return {
            "similarity_ratio": round(similarity, 4),
            "similarity_pct": f"{similarity * 100:.1f}%",
            "diff_lines": diff,
            "added": sum(1 for l in diff
                         if l.startswith("+") and not l.startswith("+++")),
            "removed": sum(1 for l in diff
                           if l.startswith("-") and not l.startswith("---")),
        }

    # ── 模式二：語意相似度 ───────────────────────────────────
    def semantic_similarity(self, text_a: str, text_b: str) -> dict:
        """回傳 {score, method}。method 說明實際用了哪種演算法。"""
        model = self._get_model()
        if model is not None:
            try:
                return {
                    "score": self._embed_similarity(model, text_a, text_b),
                    "method": "sentence-transformers（語意向量）",
                }
            except Exception as e:
                logger.warning("語意模型推論失敗（%s），降級為 n-gram", e)
        return {
            "score": self._ngram_similarity(text_a, text_b),
            "method": "字元 bigram 餘弦（降級模式，未載入語意模型）",
        }

    def _get_model(self):
        if self._model_checked:
            return self._model
        self._model_checked = True
        model_dir = Path(self.cfg["semantic_model_dir"])
        if not model_dir.is_dir():
            logger.info("語意模型目錄不存在（%s），使用降級比對", model_dir)
            return None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(str(model_dir), device="cpu")
        except Exception as e:
            logger.warning("語意模型載入失敗（%s），使用降級比對", e)
        return self._model

    def _embed_similarity(self, model, text_a: str, text_b: str) -> float:
        import numpy as np
        chunks_a = self._chunk(text_a) or [""]
        chunks_b = self._chunk(text_b) or [""]
        emb_a = model.encode(chunks_a, show_progress_bar=False)
        emb_b = model.encode(chunks_b, show_progress_bar=False)
        vec_a = np.mean(emb_a, axis=0)
        vec_b = np.mean(emb_b, axis=0)
        denom = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if denom == 0:
            return 0.0
        return round(float(np.dot(vec_a, vec_b) / denom), 4)

    def _chunk(self, text: str) -> list[str]:
        """中文沒有空白分詞，直接按字元數切段。"""
        size = self.cfg["chunk_chars"]
        text = text.strip()
        return [text[i:i + size] for i in range(0, len(text), size)]

    @staticmethod
    def _ngram_similarity(text_a: str, text_b: str, n: int = 2) -> float:
        """字元 n-gram 餘弦相似度（純 Python 降級方案）。"""
        def grams(t: str) -> Counter:
            t = re.sub(r"\s+", "", t)
            return Counter(t[i:i + n] for i in range(max(len(t) - n + 1, 0)))
        ga, gb = grams(text_a), grams(text_b)
        if not ga or not gb:
            return 0.0
        common = set(ga) & set(gb)
        dot = sum(ga[g] * gb[g] for g in common)
        norm = math.sqrt(sum(v * v for v in ga.values())) * \
            math.sqrt(sum(v * v for v in gb.values()))
        return round(dot / norm, 4) if norm else 0.0

    # ── 模式三：欄位比對 ─────────────────────────────────────
    def field_compare(self, doc_a: dict, doc_b: dict,
                      field_map: dict) -> list[dict]:
        """field_map 例：
        {"姓名": {"type": "exact"},
         "金額": {"type": "numeric"},
         "地址": {"type": "fuzzy", "threshold": 0.8}}
        """
        results = []
        for field_name, config in field_map.items():
            val_a = str(doc_a.get(field_name, "") or "")
            val_b = str(doc_b.get(field_name, "") or "")
            ftype = config.get("type", "exact")
            if ftype == "numeric":
                num_a = self._extract_number(val_a)
                num_b = self._extract_number(val_b)
                match = (num_a is not None and num_a == num_b)
                score = 1.0 if match else 0.0
            elif ftype == "fuzzy":
                score = difflib.SequenceMatcher(None, val_a, val_b).ratio()
                match = score >= config.get("threshold", 0.8)
            else:  # exact
                match = val_a.strip() == val_b.strip()
                score = 1.0 if match else 0.0
            results.append({
                "field": field_name,
                "value_a": val_a, "value_b": val_b,
                "match": match, "score": round(score, 3),
            })
        return results

    @staticmethod
    def _extract_number(text: str) -> float | None:
        cleaned = str(text).replace(",", "").replace("，", "")
        m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        return float(m.group()) if m else None
