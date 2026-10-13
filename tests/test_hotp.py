"""Unit tests for RFC 4226 HOTP code generation and URI handling."""

import unittest

from authy_local.enrollment import (
    generate_hotp_code,
    generate_hotp_from_uri,
    parse_secret_or_uri,
)
from authy_local.errors import AppError


class TestHotp(unittest.TestCase):
    # RFC 4226 Appendix D Test Vectors
    # Key: "12345678901234567890" in Base32 is "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    RFC_VECTORS = [
        (0, "755224"),
        (1, "287082"),
        (2, "359152"),
        (3, "969429"),
        (4, "338314"),
        (5, "254676"),
        (6, "287922"),
        (7, "162583"),
        (8, "399871"),
        (9, "520489"),
    ]

    def test_rfc4226_appendix_d_vectors(self):
        for counter, expected in self.RFC_VECTORS:
            with self.subTest(counter=counter):
                code = generate_hotp_code(self.RFC_SECRET, counter, digits=6, algorithm="SHA1")
                self.assertEqual(code, expected)

    def test_hotp_8_digits(self):
        code = generate_hotp_code(self.RFC_SECRET, 0, digits=8, algorithm="SHA1")
        self.assertEqual(code, "84755224")

    def test_hotp_sha256_and_sha512(self):
        code256 = generate_hotp_code(self.RFC_SECRET, 0, digits=6, algorithm="SHA256")
        self.assertEqual(len(code256), 6)
        self.assertTrue(code256.isdigit())

        code512 = generate_hotp_code(self.RFC_SECRET, 0, digits=6, algorithm="SHA512")
        self.assertEqual(len(code512), 6)
        self.assertTrue(code512.isdigit())

    def test_hotp_invalid_counter_fails_closed(self):
        with self.assertRaises(AppError):
            generate_hotp_code(self.RFC_SECRET, -1)

    def test_hotp_uri_parsing_and_serialization(self):
        uri = f"otpauth://hotp/Example:alice?secret={self.RFC_SECRET}&counter=5&issuer=Example"
        params = parse_secret_or_uri(uri)
        self.assertEqual(params.token_type, "hotp")
        self.assertEqual(params.counter, 5)
        self.assertEqual(params.issuer, "Example")
        self.assertEqual(params.account, "alice")

        serialized = params.to_uri()
        self.assertIn("otpauth://hotp/", serialized)
        self.assertIn("counter=5", serialized)

        # Generate directly from URI
        code = generate_hotp_from_uri(uri)
        self.assertEqual(code, "254676")

    def test_generate_hotp_from_totp_uri_fails(self):
        totp_uri = f"otpauth://totp/Example:alice?secret={self.RFC_SECRET}"
        with self.assertRaises(AppError):
            generate_hotp_from_uri(totp_uri)


if __name__ == "__main__":
    unittest.main()
