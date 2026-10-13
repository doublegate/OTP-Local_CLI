"""Tests for core enrollment engine, Base32 normalization, QR decoding, and RFC 6238 TOTP."""

import unittest
from unittest.mock import MagicMock, patch

from authy_local.enrollment import (
    OtpParameters,
    clean_base32,
    decode_qr_image_bytes,
    generate_totp_code,
    get_clipboard_image,
    get_clipboard_text,
    parse_secret_or_uri,
)
from authy_local.errors import AppError


class TestEnrollmentEngine(unittest.TestCase):
    """Unit test suite for enrollment.py."""

    def test_clean_base32_normalization(self) -> None:
        """Verify clean_base32 strips spaces, dashes, converts uppercase, and validates bounds."""
        # Standard 16-char secret
        self.assertEqual(clean_base32("JBSWY3DPEHPK3PXP"), "JBSWY3DPEHPK3PXP")
        # Lowercase with whitespace and hyphens
        self.assertEqual(clean_base32("  jbsw-y3dp ehpk 3pxp  "), "JBSWY3DPEHPK3PXP")
        # With trailing padding
        self.assertEqual(clean_base32("JBSWY3DPEHPK3PXP==="), "JBSWY3DPEHPK3PXP")

        # Invalid lengths (< 16 characters or > 256)
        with self.assertRaises(AppError) as ctx:
            clean_base32("ABCDEF")
        self.assertEqual(ctx.exception.exit_code, 2)

        # Invalid Base32 characters (0, 1, 8, 9)
        with self.assertRaises(AppError) as ctx:
            clean_base32("JBSWY3DPEHPK3PX8")
        self.assertEqual(ctx.exception.exit_code, 2)

        # Non-string input
        with self.assertRaises(AppError) as ctx:
            clean_base32(12345)  # type: ignore
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_parse_raw_secret(self) -> None:
        """Verify parse_secret_or_uri handles raw Base32 secret string with defaults and bounds."""
        params = parse_secret_or_uri(
            "jbsw y3dp ehpk 3pxp", fallback_label="Personal", fallback_issuer="GitHub"
        )
        self.assertEqual(params.secret, "JBSWY3DPEHPK3PXP")
        self.assertEqual(params.account, "Personal")
        self.assertEqual(params.issuer, "GitHub")
        self.assertEqual(params.digits, 6)
        self.assertEqual(params.period, 30)
        self.assertEqual(params.algorithm, "SHA1")

        # Custom options
        params_custom = parse_secret_or_uri(
            "JBSWY3DPEHPK3PXP",
            fallback_label="AWS",
            digits=8,
            period=60,
            algorithm="sha256",
        )
        self.assertEqual(params_custom.digits, 8)
        self.assertEqual(params_custom.period, 60)
        self.assertEqual(params_custom.algorithm, "SHA256")

        # Rejects invalid digits
        with self.assertRaises(AppError):
            parse_secret_or_uri("JBSWY3DPEHPK3PXP", digits=7)

        # Rejects invalid period
        with self.assertRaises(AppError):
            parse_secret_or_uri("JBSWY3DPEHPK3PXP", period=2)

        # Rejects invalid algorithm
        with self.assertRaises(AppError):
            parse_secret_or_uri("JBSWY3DPEHPK3PXP", algorithm="MD5")

    def test_parse_otpauth_uri(self) -> None:
        """Verify parse_secret_or_uri strictly validates and parses otpauth://totp/... URIs."""
        uri = "otpauth://totp/Acme:alice@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Acme&algorithm=SHA256&digits=8&period=45"
        params = parse_secret_or_uri(uri)
        self.assertEqual(params.secret, "JBSWY3DPEHPK3PXP")
        self.assertEqual(params.issuer, "Acme")
        self.assertEqual(params.account, "alice@example.com")
        self.assertEqual(params.algorithm, "SHA256")
        self.assertEqual(params.digits, 8)
        self.assertEqual(params.period, 45)
        self.assertEqual(params.token_type, "totp")

        # Verify serialization roundtrip
        serialized = params.to_uri()
        self.assertTrue(serialized.startswith("otpauth://totp/Acme:alice@example.com?"))
        self.assertIn("secret=JBSWY3DPEHPK3PXP", serialized)
        self.assertIn("issuer=Acme", serialized)
        self.assertIn("digits=8", serialized)

        # Rejects duplicate query keys
        with self.assertRaises(AppError):
            parse_secret_or_uri(
                "otpauth://totp/test?secret=JBSWY3DPEHPK3PXP&secret=JBSWY3DPEHPK3PXQ"
            )

        # Rejects invalid scheme or netloc
        with self.assertRaises(AppError):
            parse_secret_or_uri("https://example.com/totp?secret=JBSWY3DPEHPK3PXP")
        with self.assertRaises(AppError):
            parse_secret_or_uri("otpauth://unknown/test?secret=JBSWY3DPEHPK3PXP")

        # Rejects missing secret
        with self.assertRaises(AppError):
            parse_secret_or_uri("otpauth://totp/test?issuer=Test")

        # Rejects forbidden unknown query params
        with self.assertRaises(AppError):
            parse_secret_or_uri("otpauth://totp/test?secret=JBSWY3DPEHPK3PXP&evil=true")

    def test_rfc6238_standard_test_vectors(self) -> None:
        """Verify generate_totp_code matches canonical RFC 6238 test vectors."""
        # RFC 6238 test seed for SHA1: ASCII "12345678901234567890" in Base32 is GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
        seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        params_sha1 = OtpParameters(secret=seed, digits=8, period=30, algorithm="SHA1")

        # RFC 6238 reference vectors:
        # Time = 59s -> TOTP = 94287082
        code, rem = generate_totp_code(params_sha1, timestamp=59)
        self.assertEqual(code, "94287082")
        self.assertEqual(rem, 1.0)

        # Time = 1111111109s -> TOTP = 07081804
        code, rem = generate_totp_code(params_sha1, timestamp=1111111109)
        self.assertEqual(code, "07081804")

        # Time = 1111111111s -> TOTP = 14050471
        code, rem = generate_totp_code(params_sha1, timestamp=1111111111)
        self.assertEqual(code, "14050471")

        # Time = 2000000000s -> TOTP = 69279037
        code, rem = generate_totp_code(params_sha1, timestamp=2000000000)
        self.assertEqual(code, "69279037")

        # 6-digit standard test
        params_6 = OtpParameters(secret=seed, digits=6, period=30, algorithm="SHA1")
        code_6, _ = generate_totp_code(params_6, timestamp=59)
        self.assertEqual(code_6, "287082")

    def test_qr_decode_from_bytes_and_file(self) -> None:
        """Verify decode_qr_image_bytes and decode_qr_image_file invoke zbarimg with safety controls."""
        fake_env = {"PATH": "/usr/bin"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"otpauth://totp/Mock:user?secret=JBSWY3DPEHPK3PXP\n"

        with (
            patch("shutil.which", return_value="/usr/bin/zbarimg"),
            patch("authy_local.enrollment.run", return_value=mock_result) as mock_run,
        ):
            decoded = decode_qr_image_bytes(b"FAKE_PNG_BYTES", fake_env)
            self.assertEqual(decoded, "otpauth://totp/Mock:user?secret=JBSWY3DPEHPK3PXP")
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertEqual(args[0], ["/usr/bin/zbarimg", "-q", "--raw", "-"])
            self.assertEqual(kwargs["input_data"], b"FAKE_PNG_BYTES")

        # Missing zbarimg tool raises AppError(3)
        with patch("shutil.which", return_value=None):
            with self.assertRaises(AppError) as ctx:
                decode_qr_image_bytes(b"data", fake_env)
            self.assertEqual(ctx.exception.exit_code, 3)

        # Nonzero exit code or empty stdout raises AppError(2)
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = b""
        with (
            patch("shutil.which", return_value="/usr/bin/zbarimg"),
            patch("authy_local.enrollment.run", return_value=mock_fail),
        ):
            with self.assertRaises(AppError) as ctx:
                decode_qr_image_bytes(b"bad_image", fake_env)
            self.assertEqual(ctx.exception.exit_code, 2)

    def test_clipboard_retrieval_wayland(self) -> None:
        """Verify get_clipboard_image and get_clipboard_text query wl-paste safely."""
        env_wayland = {"WAYLAND_DISPLAY": "wayland-0", "PATH": "/usr/bin"}
        mock_img = MagicMock()
        mock_img.returncode = 0
        mock_img.stdout = b"\x89PNG\r\n\x1a\nfakeimage"

        with (
            patch("shutil.which", return_value="/usr/bin/wl-paste"),
            patch("authy_local.enrollment.run", return_value=mock_img),
        ):
            data = get_clipboard_image(env_wayland)
            self.assertEqual(data, b"\x89PNG\r\n\x1a\nfakeimage")

        mock_txt = MagicMock()
        mock_txt.returncode = 0
        mock_txt.stdout = b"JBSWY3DPEHPK3PXP\n"

        with (
            patch("shutil.which", return_value="/usr/bin/wl-paste"),
            patch("authy_local.enrollment.run", return_value=mock_txt),
        ):
            txt = get_clipboard_text(env_wayland)
            self.assertEqual(txt, "JBSWY3DPEHPK3PXP")

        # Refusal without WAYLAND_DISPLAY
        with self.assertRaises(AppError) as ctx:
            get_clipboard_image({"PATH": "/usr/bin"})
        self.assertEqual(ctx.exception.exit_code, 3)


if __name__ == "__main__":
    unittest.main()
