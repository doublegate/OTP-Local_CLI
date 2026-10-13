"""Preview optional setup; explicitly install only reviewed native runtime bytes."""

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

TOTPM_REVISION = "6789ed7f8616e4d90e8d6670f04fe815bd34462b"
TOTPM_LOCK_SHA256 = "f75f384ee838304e85d1592b6060644dc32e0f9a8d7c8bb63f9b3d103d7c088b"
TOTPM_BINARY_SHA256 = "5c166307a1441fa028bc676afadea8e364aa57248b2d6658b03c63a498b3f547"
TOTPM_LICENSE_SHA256 = "94a10fc212f0c58a58cef3f8914cb43a20cce7c98a689016c94090bd39f5c55b"
# Exact MIT license from TOTPM_REVISION; supplied with the reviewed binary.
TOTPM_LICENSE = """Copyright 2024 Koditoriet AB

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
""".encode("utf-8")
PASS_OTP_REVISION = "7bb50dbc4b6073f12f40be66a5ee371b9652a646"
PASS_OTP_SHA256 = "8b7533e02dc37816dd8ed472a5b852ea7bdaf878ec32a233350c444ec7a33460"
PASS_OTP_HARDENED_SHA256 = "4a700b3fa54ffb12c134d202b1f23fe74b4e1b4b942670fb54a766857d6c9b68"
PASS_OTP_LICENSE_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def hardened_extension(upstream: bytes) -> bytes:
    """Apply exact reviewed stdin-only/TOTP-only changes to pinned GPLv3 source."""
    if hashlib.sha256(upstream).hexdigest() != PASS_OTP_SHA256:
        raise ValueError("Upstream extension fingerprint mismatch")
    replacements = (
        (
            b"  # Check oathtool for stdin secrets feature\n",
            b'  [[ "$otp_type" == "totp" ]] || die "This private extension supports TOTP only."\n'
            b'  [[ -n "$OATH" ]] || die "oathtool is required for stdin-only generation."\n'
            b"  unset OATH_SAFE\n"
            b"  # Private companion hardening: version-sort and fail closed on unsafe generation.\n"
            b"  # Check oathtool for stdin secrets feature\n",
            1,
        ),
        (b'$(sort -n <<< "$OATH_VERSIONS")', b'$(sort -V <<< "$OATH_VERSIONS")', 1),
        (
            b'  [[ "$OATH_VERSIONS" = "$(sort -V <<< "$OATH_VERSIONS")" ]] && OATH_SAFE=1\n',
            b'  [[ "$OATH_VERSIONS" = "$(sort -V <<< "$OATH_VERSIONS")" ]] && OATH_SAFE=1\n'
            b'  [[ -n "$OATH_SAFE" ]] || die "oathtool 2.6.5 or newer is required."\n',
            1,
        ),
        (
            b'        cmd+=("$otp_secret")\n',
            b'        die "Secret input through argv is disabled."\n',
            2,
        ),
        (
            b'      [[ -n "$OTPTOOL" ]] && cmd=("$OTPTOOL" "$uri")\n',
            b"      unset OTPTOOL\n",
            2,
        ),
    )
    result = upstream
    for old, new, expected_count in replacements:
        if result.count(old) != expected_count:
            raise ValueError("Reviewed extension patch does not apply exactly")
        result = result.replace(old, new)
    if hashlib.sha256(result).hexdigest() != PASS_OTP_HARDENED_SHA256:
        raise ValueError("Hardened extension fingerprint mismatch")
    return result


def _read(path: Path, limit: int = 16 * 1024 * 1024) -> bytes:
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Invalid runtime input")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Invalid runtime input")
    return data


def _directory(path: Path, home: Path, *, create: bool) -> None:
    """Validate every ancestor; enforce private modes only on dedicated trees."""
    if not path.is_relative_to(home):
        raise ValueError("Runtime path escapes home")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if not current.exists() and not current.is_symlink():
            if not create:
                continue
            current.mkdir(mode=0o700)
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("Runtime directory is unsafe")
            if current == home or current.is_relative_to(home):
                if info.st_uid != os.getuid() or info.st_mode & 0o022:
                    raise ValueError("Runtime directory has foreign ownership")
            private_roots = (
                home / ".local/share/authy-local/optional",
                home / ".local/state/authy-local",
            )
            if any(current.is_relative_to(root) for root in private_roots):
                if info.st_mode & 0o077:
                    raise ValueError("Runtime directory is not private")


def _atomic(path: Path, data: bytes, mode: int) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".optional-runtime-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_runtime(home: Path, pass_source: Path, totpm_binary: Path) -> str:
    """Install only exact reviewed native bytes; never execute them or touch keys."""
    if not home.is_absolute() or home == Path("/") or ".." in home.parts:
        raise ValueError("Invalid runtime home")
    extension = _read(pass_source / "otp.bash", 1024 * 1024)
    license_text = _read(pass_source / "LICENSE", 1024 * 1024)
    binary = _read(totpm_binary)
    if (
        hashlib.sha256(extension).hexdigest() != PASS_OTP_SHA256
        or hashlib.sha256(license_text).hexdigest() != PASS_OTP_LICENSE_SHA256
        or hashlib.sha256(binary).hexdigest() != TOTPM_BINARY_SHA256
        or hashlib.sha256(TOTPM_LICENSE).hexdigest() != TOTPM_LICENSE_SHA256
    ):
        raise ValueError("Runtime fingerprint mismatch")
    extension = hardened_extension(extension)
    root = home / ".local/share/authy-local/optional"
    targets = {
        root / "bin/totpm": (binary, 0o700),
        root / "bin/totpm-LICENSE": (TOTPM_LICENSE, 0o600),
        root / "pass-store/.extensions/otp.bash": (extension, 0o700),
        root / "pass-store/.extensions/pass-otp-LICENSE": (license_text, 0o600),
    }
    state = home / ".local/state/authy-local/optional-runtime.json"
    entries = {str(path): hashlib.sha256(data).hexdigest() for path, (data, _) in targets.items()}
    for parent in (state.parent, *(path.parent for path in targets)):
        _directory(parent, home, create=False)
    previous = None
    if state.exists() or state.is_symlink():
        info = state.lstat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Runtime ownership manifest is unsafe")
        try:
            previous = json.loads(_read(state, 65536))
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ValueError("Runtime ownership manifest is invalid") from error
        if not isinstance(previous, dict) or previous.get("entries") != entries:
            raise ValueError("Runtime ownership manifest does not match")
        if previous.get("status") not in ("pending", "complete"):
            raise ValueError("Runtime ownership manifest is invalid")
    before = {}
    for path, (data, mode) in targets.items():
        exists = path.exists() or path.is_symlink()
        if exists:
            info = path.lstat()
            if (
                previous is None
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != mode
                or _read(path) != data
            ):
                raise ValueError("Unowned or modified runtime target")
        before[path] = exists
    if previous and previous["status"] == "complete" and all(before.values()):
        return "unchanged"
    for parent in (state.parent, *(path.parent for path in targets)):
        _directory(parent, home, create=True)
    document = {"version": 1, "status": "pending", "entries": entries}
    _atomic(state, json.dumps(document, indent=2).encode() + b"\n", 0o600)
    for path, (data, mode) in targets.items():
        _directory(path.parent, home, create=False)
        exists = path.exists() or path.is_symlink()
        if exists != before[path] or (exists and _read(path) != data):
            raise ValueError("Runtime target changed during installation")
        if not exists:
            _atomic(path, data, mode)
    document["status"] = "complete"
    _atomic(state, json.dumps(document, indent=2).encode() + b"\n", 0o600)
    return "installed"


def verify_source(kind: str, source: Path) -> bool:
    """Verify the reviewed extension or Cargo lock; never execute source."""
    filename, expected = (
        ("otp.bash", PASS_OTP_SHA256) if kind == "pass-otp" else ("Cargo.lock", TOTPM_LOCK_SHA256)
    )
    try:
        target = source / filename
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(target, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                return False
            data = stream.read(1024 * 1024 + 1)
        return hashlib.sha256(data).hexdigest() == expected
    except OSError:
        return False


def manifest(home: Path) -> dict:
    """Describe dedicated paths and exact build choices; do not inspect them."""
    optional = home / ".local/share/authy-local/optional"
    state = home / ".local/state/authy-local/totpm"
    config = home / ".config/authy-local/totpm.conf"
    directories = (
        optional,
        optional / "bin",
        optional / "pass-store",
        optional / "pass-store/.extensions",
        optional / "gnupg",
        state,
        state / "system",
        state / "user",
        config.parent,
    )
    return {
        "mode": "preview-only",
        "packages": ["pass", "oath-toolkit", "gnupg", "tpm2-tss", "pkgconf", "dbus", "sqlite"],
        "directories": [{"path": str(path), "mode": "0700"} for path in directories],
        "pass_otp": {
            "repository": "https://github.com/pass-extension/pass-otp.git",
            "revision": PASS_OTP_REVISION,
            "file": "otp.bash",
            "sha256": PASS_OTP_SHA256,
            "installed_sha256": PASS_OTP_HARDENED_SHA256,
            "license_sha256": PASS_OTP_LICENSE_SHA256,
            "license_destination": str(optional / "pass-store/.extensions/pass-otp-LICENSE"),
            "license_mode": "0600",
            "destination": str(optional / "pass-store/.extensions/otp.bash"),
            "mode": "0700",
            "oathtool_minimum": "2.6.5",
            "key_creation": "operator-only interactive dedicated key; backup and restore required",
        },
        "totpm": {
            "repository": "https://github.com/koditoriet/totpm.git",
            "revision": TOTPM_REVISION,
            "version": "0.1.2",
            "binary_sha256": TOTPM_BINARY_SHA256,
            "license_sha256": TOTPM_LICENSE_SHA256,
            "license_destination": str(optional / "bin/totpm-LICENSE"),
            "license_mode": "0600",
            "cargo_lock_sha256": TOTPM_LOCK_SHA256,
            "build_argv": [
                "cargo",
                "build",
                "--release",
                "--locked",
                "--no-default-features",
                "--features",
                "install",
            ],
            "destination": str(optional / "bin/totpm"),
            "mode": "0700",
            "config": str(config),
            "init_argv": [
                str(optional / "bin/totpm"),
                "--config",
                str(config),
                "init",
                "--local",
                "--tpm",
                "device:/dev/tpmrm0",
                "--system-data-path",
                str(state / "system"),
                "--user-data-path",
                str(state / "user"),
                "--presence-verification",
                "none",
            ],
            "initialization": "operator-only; creates a persistent TPM key; no automatic execution",
        },
        "excluded": [
            "package installation",
            "source execution",
            "key creation",
            "TPM initialization",
            "setuid",
            "TPM clearing",
            "device permissions",
            "PATH edits",
            "account changes",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--verify-kind", choices=("pass-otp", "totpm"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--apply-runtime", action="store_true")
    parser.add_argument("--pass-source", type=Path)
    parser.add_argument("--totpm-binary", type=Path)
    args = parser.parse_args(argv)
    if (
        not args.home.is_absolute()
        or args.home == Path("/")
        or ".." in args.home.parts
        or any(ord(character) < 32 for character in str(args.home))
    ):
        parser.error("home must be an absolute non-root path without controls or traversal")
    if bool(args.verify_kind) != bool(args.source):
        parser.error("source verification requires both --verify-kind and --source")
    if args.apply_runtime:
        if not args.pass_source or not args.totpm_binary or args.source:
            parser.error("runtime apply requires --pass-source and --totpm-binary only")
        try:
            result = apply_runtime(args.home, args.pass_source, args.totpm_binary)
        except OSError, ValueError:
            print(
                "Native runtime apply refused; inspect paths and reviewed fingerprints privately."
            )
            return 1
        print(f"Native runtime {result}; no key, package or TPM operations performed.")
        return 0
    if args.pass_source or args.totpm_binary:
        parser.error("runtime sources require --apply-runtime")
    if args.source:
        passed = verify_source(args.verify_kind, args.source)
        label = "Extension" if args.verify_kind == "pass-otp" else "Lockfile"
        print(f"{label} fingerprint {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1
    print(json.dumps(manifest(args.home), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
