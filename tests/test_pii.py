import unittest

from smartdoc.pii import (PIIProtector, validate_luhn, validate_tw_company_id,
                          validate_tw_id)


class TestValidators(unittest.TestCase):
    def test_tw_id_valid(self):
        # A123456789 是教科書範例（檢查碼正確）
        self.assertTrue(validate_tw_id("A123456789"))

    def test_tw_id_invalid_checksum(self):
        self.assertFalse(validate_tw_id("A123456780"))

    def test_tw_id_bad_format(self):
        self.assertFalse(validate_tw_id("A323456789"))  # 性別碼只能 1/2
        self.assertFalse(validate_tw_id("1123456789"))

    def test_luhn(self):
        self.assertTrue(validate_luhn("4111111111111111"))   # 測試卡號
        self.assertFalse(validate_luhn("4111111111111112"))

    def test_company_id(self):
        self.assertTrue(validate_tw_company_id("04595257"))  # 台積電統編
        self.assertFalse(validate_tw_company_id("12345678"))


class TestDetection(unittest.TestCase):
    def setUp(self):
        self.p = PIIProtector()

    def test_detect_tw_id(self):
        findings = self.p.detect("申請人身分證字號：A123456789，請查收。")
        entities = {f.entity for f in findings}
        self.assertIn("TW_ID_NUMBER", entities)

    def test_invalid_id_not_detected(self):
        findings = self.p.detect("編號 A123456780 為訂單流水號")
        self.assertNotIn("TW_ID_NUMBER", {f.entity for f in findings})

    def test_detect_mobile(self):
        findings = self.p.detect("聯絡電話 0912-345-678")
        self.assertIn("TW_MOBILE", {f.entity for f in findings})

    def test_detect_email(self):
        findings = self.p.detect("信箱 test@example.com.tw")
        self.assertIn("EMAIL", {f.entity for f in findings})

    def test_context_required(self):
        # 8 位數字（統編檢查碼正確）但附近沒有上下文詞 → 不算
        no_ctx = self.p.detect("流水號 04595257 已入庫")
        self.assertNotIn("TW_COMPANY_ID", {f.entity for f in no_ctx})
        with_ctx = self.p.detect("公司統一編號：04595257")
        self.assertIn("TW_COMPANY_ID", {f.entity for f in with_ctx})

    def test_detect_address(self):
        findings = self.p.detect("寄送地址：台北市大安區和平東路100號3樓")
        self.assertIn("TW_ADDRESS", {f.entity for f in findings})

    def test_detect_name_field(self):
        findings = self.p.detect("姓名：王小明\n電話：0912345678")
        self.assertIn("PERSON_NAME_FIELD", {f.entity for f in findings})


class TestMasking(unittest.TestCase):
    def setUp(self):
        self.p = PIIProtector()

    def test_replace(self):
        out = self.p.mask("身分證：A123456789 END")
        self.assertNotIn("A123456789", out)
        self.assertIn("《身分證字號》", out)
        self.assertIn("END", out)  # 其餘文字不受影響

    def test_redact(self):
        out = self.p.mask("身分證：A123456789", operator="redact")
        self.assertNotIn("A123456789", out)

    def test_hash_is_stable(self):
        a = self.p.mask("A123456789", operator="hash")
        b = self.p.mask("A123456789", operator="hash")
        self.assertEqual(a, b)
        self.assertNotIn("A123456789", a)

    def test_keep(self):
        text = "身分證：A123456789"
        self.assertEqual(self.p.mask(text, operator="keep"), text)

    def test_analyze_and_mask_report(self):
        r = self.p.analyze_and_mask(
            "姓名：王小明，手機 0912345678，身分證 A123456789")
        self.assertGreaterEqual(r["pii_count"], 3)
        self.assertNotIn("A123456789", r["masked_text"])
        self.assertNotIn("0912345678", r["masked_text"])

    def test_overlap_resolution(self):
        # 手機號同時可能被銀行帳號規則匹配，遮蔽後不應重複或殘留
        out = self.p.mask("帳號轉帳用手機 0912345678 認證")
        self.assertNotIn("0912345678", out)


if __name__ == "__main__":
    unittest.main()
