"""Tests for in-process RFC 6238 TOTP computation engine."""

import unittest

from authy_local.enrollment import generate_totp_from_uri
from authy_local.errors import AppError


class TestInProcessTotp(unittest.TestCase):
    # RFC 6238 Appendix B test secret: "12345678901234567890" (Base32: GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ)
    RFC_SECRET_B32 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_rfc6238_sha1_vectors(self):
        # RFC 6238 Appendix B test vectors for SHA1, 8 digits
        vectors = [
            (59, "94287082"),
            (1111111109, "07081804"),
            (1111111111, "14050471"),
            (1234567890, "89005924"),
            (2000000000, "69279037"),
        ]
        for timestamp, expected_code in vectors:
            with self.subTest(timestamp=timestamp):
                code, remaining = generate_totp_from_uri(
                    self.RFC_SECRET_B32,
                    timestamp=float(timestamp),
                    digits=8,
                    period=30,
                    algorithm="SHA1",
                )
                self.assertEqual(code, expected_code)
                self.assertAlmostEqual(remaining, float(30 - (timestamp % 30)))

    def test_totp_from_otpauth_uri(self):
        uri = (
            f"otpauth://totp/Example:alice@google.com"
            f"?secret={self.RFC_SECRET_B32}&issuer=Example&algorithm=SHA1&digits=6&period=30"
        )
        code, remaining = generate_totp_from_uri(uri, timestamp=59.0)
        # Last 6 digits of 94287082 is 287082
        self.assertEqual(code, "287082")
        self.assertAlmostEqual(remaining, 1.0)

    def test_totp_sha256_algorithm(self):
        secret_256 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZA"
        uri = f"otpauth://totp/Test:user?secret={secret_256}&algorithm=SHA256&digits=8&period=30"
        # RFC 6238 Appendix B test vector for SHA256 at T=59: "46119246"
        code, _ = generate_totp_from_uri(uri, timestamp=59.0)
        self.assertEqual(code, "46119246")

    def test_totp_sha512_algorithm(self):
        secret_512 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNA"
        uri = f"otpauth://totp/Test:user?secret={secret_512}&algorithm=SHA512&digits=8&period=30"
        # RFC 6238 Appendix B test vector for SHA512 at T=59: "90693936"
        code, _ = generate_totp_from_uri(uri, timestamp=59.0)
        self.assertEqual(code, "90693936")

    def test_totp_steam_guard(self):
        # Steam secret test vector at T=1500000000 -> "K23BY"
        uri = f"otpauth://totp/Steam:testuser?secret={self.RFC_SECRET_B32}&algorithm=STEAM&digits=5"
        code, remaining = generate_totp_from_uri(uri, timestamp=1500000000.0)
        self.assertEqual(code, "K23BY")
        self.assertEqual(len(code), 5)
        self.assertAlmostEqual(remaining, 30.0)

        # Also via steam:// scheme
        steam_uri = f"steam://testuser?secret={self.RFC_SECRET_B32}"
        code2, _ = generate_totp_from_uri(steam_uri, timestamp=1500000000.0)
        self.assertEqual(code2, "K23BY")

    def test_totp_invalid_uri_or_secret(self):
        with self.assertRaises(AppError) as ctx:
            generate_totp_from_uri("invalid secret!#$")
        self.assertEqual(ctx.exception.exit_code, 2)

        with self.assertRaises(AppError) as ctx:
            generate_totp_from_uri("otpauth://hotp/foo?secret=" + self.RFC_SECRET_B32)
        # parse_uri accepts hotp scheme but generate_totp operates on period
        # Let's check malformed uri
        with self.assertRaises(AppError) as ctx:
            generate_totp_from_uri("http://example.com")
        self.assertEqual(ctx.exception.exit_code, 2)
