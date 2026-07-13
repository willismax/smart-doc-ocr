"""smartdoc — 離線 OCR 智慧文件辨識與比對系統。

六層 Pipeline：
    router → preprocessor → recognizer → structurer → pii → comparator
每層獨立、可單獨替換；重依賴全部 lazy import，缺少時優雅降級。
"""

__version__ = "1.0.0"
