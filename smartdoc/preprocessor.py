"""Layer 2 — 影像前處理。

歪斜校正 + 去雜訊 + CLAHE 對比增強 + Otsu 二值化。
OpenCV 為 lazy import：未安裝時 process() 原樣回傳，OCR 仍可跑，
只是低品質掃描件準確率下降（並記 log 提示）。

相對設計稿的修正：
- minAreaRect 的角度在直排/表格文件上可能給出離譜值，
  校正角度限制在 ±15 度內，超過視為誤判、不旋轉。
- 二值化對照片類圖片反而有害，僅對「近雙峰」灰階分布套用。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_cv2 = None
_cv2_checked = False


def _get_cv2():
    """lazy 載入 OpenCV；只嘗試一次。"""
    global _cv2, _cv2_checked
    if not _cv2_checked:
        _cv2_checked = True
        try:
            import cv2
            _cv2 = cv2
        except ImportError:
            logger.warning("OpenCV 未安裝，影像前處理停用（OCR 準確率會下降）")
    return _cv2


class ImagePreprocessor:
    """OCR 前影像增強。輸入/輸出皆為 numpy ndarray（BGR 或灰階）。"""

    MAX_DESKEW_DEG = 15.0   # 校正角度上限，超過視為偵測誤判
    MIN_DESKEW_DEG = 0.3    # 低於此角度不值得旋轉

    def process(self, image):
        cv2 = _get_cv2()
        if cv2 is None:
            return image
        img = self._to_gray(image)
        img = self._deskew(img)
        img = self._denoise(img)
        img = self._enhance_contrast(img)
        img = self._maybe_binarize(img)
        return img

    # ── 個別步驟 ─────────────────────────────────────────────
    def _to_gray(self, img):
        cv2 = _get_cv2()
        if img.ndim == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def _deskew(self, img):
        cv2 = _get_cv2()
        import numpy as np
        # 用暗色像素（文字）的最小外接矩形估計傾斜角
        dark = np.column_stack(np.where(img < 128))
        if len(dark) < 100:  # 幾乎空白頁
            return img
        angle = cv2.minAreaRect(dark)[-1]
        if angle > 45:
            angle -= 90
        elif angle < -45:
            angle += 90
        if abs(angle) < self.MIN_DESKEW_DEG or abs(angle) > self.MAX_DESKEW_DEG:
            return img
        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _denoise(self, img):
        cv2 = _get_cv2()
        # fastNlMeans 很慢；大圖改用較快的 median blur
        h, w = img.shape[:2]
        if h * w > 4_000_000:
            return cv2.medianBlur(img, 3)
        return cv2.fastNlMeansDenoising(img, h=10)

    def _enhance_contrast(self, img):
        cv2 = _get_cv2()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(img)

    def _maybe_binarize(self, img):
        """僅在灰階分布接近雙峰（典型文件掃描）時二值化。"""
        cv2 = _get_cv2()
        import numpy as np
        hist = cv2.calcHist([img], [0], None, [256], [0, 256]).ravel()
        hist = hist / max(hist.sum(), 1)
        # 中間調占比高 → 照片/漸層圖，跳過二值化
        mid_ratio = hist[64:192].sum()
        if mid_ratio > 0.5:
            return img
        _, binary = cv2.threshold(
            img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    def scale_for_ocr(self, img, min_side: int = 960):
        """短邊不足 min_side 時放大，確保小字可辨識。"""
        cv2 = _get_cv2()
        if cv2 is None:
            return img
        h, w = img.shape[:2]
        short = min(h, w)
        if short >= min_side:
            return img
        scale = min_side / short
        return cv2.resize(
            img, (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
