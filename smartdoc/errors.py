"""統一錯誤定義。

原則：
- 給文書人員看的訊息（user_message）一律繁體中文、不含 traceback。
- 技術細節（原始例外）進 log，不進 UI。
"""
from __future__ import annotations


class SmartDocError(Exception):
    """本系統所有可預期錯誤的基底類別。"""

    #: 給一般使用者看的說明（繁中、可直接顯示在 UI）
    user_message: str = "處理時發生錯誤，請聯絡系統管理員。"

    def __init__(self, user_message: str | None = None, *, detail: str = ""):
        if user_message:
            self.user_message = user_message
        self.detail = detail
        super().__init__(self.user_message + (f" ({detail})" if detail else ""))


class UnsupportedFormatError(SmartDocError):
    user_message = "不支援的檔案格式。"


class CorruptedFileError(SmartDocError):
    user_message = "檔案已損壞或無法開啟。"


class FileTooLargeError(SmartDocError):
    user_message = "檔案超過大小上限。"


class EmptyFileError(SmartDocError):
    user_message = "檔案是空的（0 KB）。"


class OcrEngineUnavailableError(SmartDocError):
    user_message = (
        "OCR 引擎尚未安裝或載入失敗，掃描文件與圖片暫時無法辨識。"
        "數位 PDF 與 Office 文件仍可正常處理。"
    )


class ModelMissingError(SmartDocError):
    user_message = "找不到離線模型檔，請確認 models/ 目錄已放入模型。"


class PasswordProtectedError(SmartDocError):
    user_message = "檔案有密碼保護，請先解除密碼後再上傳。"
