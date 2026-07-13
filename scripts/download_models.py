"""在有網路的機器上執行一次：下載所有離線模型到 models/。

- PaddleOCR 偵測/辨識/角度模型（繁中）
- sentence-transformers 語意比對模型（可選）

之後把整個專案資料夾（含 models/）複製到離線機即可。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


def download_paddleocr() -> bool:
    print("── 下載 PaddleOCR 模型（繁體中文）──")
    try:
        from paddleocr import PaddleOCR
    except ImportError as e:
        print(f"⚠️ PaddleOCR 未安裝，略過（{e}）")
        return False
    try:
        # 觸發下載到使用者快取，再複製進專案 models/
        try:
            ocr = PaddleOCR(use_angle_cls=True, lang="chinese_cht",
                            show_log=False)
        except TypeError:  # PaddleOCR 3.x
            ocr = PaddleOCR(lang="chinese_cht")
        cache = Path.home() / ".paddleocr"
        if cache.is_dir():
            found = {"det": None, "rec": None, "cls": None}
            for p in cache.rglob("*"):
                if not p.is_dir():
                    continue
                name = p.name.lower()
                for key in found:
                    if key in name and found[key] is None and \
                            any(f.suffix in (".pdmodel", ".pdiparams", ".json")
                                for f in p.iterdir() if f.is_file()):
                        found[key] = p
            for key, src in found.items():
                if src:
                    dst = MODELS / key
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    print(f"  ✅ {key}: {src.name} → models/{key}")
                else:
                    print(f"  ⚠️ 找不到 {key} 模型（PaddleOCR 仍可用自身快取）")
        print("✅ PaddleOCR 模型完成")
        return True
    except Exception as e:
        print(f"❌ PaddleOCR 模型下載失敗：{e}")
        return False


def download_semantic_model() -> bool:
    print("── 下載語意比對模型（paraphrase-multilingual-MiniLM-L12-v2）──")
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:  # ImportError 之外，torch DLL 載入失敗會丟 OSError
        print(f"⚠️ sentence-transformers 無法載入，略過（{e}）；"
              "比對功能會用降級演算法")
        return False
    try:
        model = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        target = MODELS / "multilingual-MiniLM"
        model.save(str(target))
        print(f"✅ 語意模型已存到 {target}")
        return True
    except Exception as e:
        print(f"❌ 語意模型下載失敗：{e}")
        return False


if __name__ == "__main__":
    MODELS.mkdir(exist_ok=True)
    # torch 必須先於 paddle 載入（Windows DLL 衝突，WinError 127）
    try:
        import torch  # noqa: F401
    except Exception:
        pass
    ok1 = download_paddleocr()
    ok2 = download_semantic_model()
    print()
    if ok1 or ok2:
        print("模型下載結束。把整個專案資料夾複製到離線機即可使用。")
    sys.exit(0)
