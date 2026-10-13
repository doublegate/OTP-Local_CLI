"""Export engine for offline backups, migration archives, and GPG encryption."""

import csv
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from .enrollment import OtpParameters
from .errors import AppError
from .processes import run


def format_uri_list(tokens: list[OtpParameters]) -> str:
    """Format token list as newline-delimited RFC 6238 URIs."""
    if not tokens:
        return ""
    return "\n".join(t.to_uri() for t in tokens) + "\n"


def format_aegis_json(tokens: list[OtpParameters]) -> str:
    """Format token list as standard unencrypted Aegis JSON export."""
    entries = []
    for t in tokens:
        info = {
            "secret": t.secret,
            "algo": t.algorithm,
            "digits": t.digits,
        }
        if t.token_type == "hotp":
            info["counter"] = t.counter
        else:
            info["period"] = t.period

        entries.append(
            {
                "type": t.token_type or "totp",
                "name": t.account,
                "issuer": t.issuer,
                "note": "",
                "favorite": False,
                "info": info,
            }
        )
    payload = {
        "version": 1,
        "header": {"slots": None, "params": None},
        "db": {
            "version": 1,
            "entries": entries,
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def format_csv(tokens: list[OtpParameters]) -> str:
    """Format token list as standard RFC 6238 CSV backup."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Account", "Issuer", "Secret", "Digits", "Period", "Algorithm", "Type", "URI"])
    for t in tokens:
        writer.writerow(
            [
                t.account,
                t.issuer,
                t.secret,
                t.digits,
                t.period,
                t.algorithm,
                t.token_type or "totp",
                t.to_uri(),
            ]
        )
    return out.getvalue()


def export_tokens_to_string(tokens: list[OtpParameters], fmt: str = "uri") -> str:
    """Serialize token parameters into selected export format."""
    if fmt == "uri":
        return format_uri_list(tokens)
    if fmt == "aegis":
        return format_aegis_json(tokens)
    if fmt == "csv":
        return format_csv(tokens)
    raise AppError(2)


def write_export_file(
    content: str,
    output_path: Path,
    *,
    encrypt_gpg: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Write export content with strict 0600 file permissions and optional GPG encryption."""
    dest = Path(output_path).resolve()
    dest_dir = dest.parent
    if not dest_dir.is_dir():
        raise AppError(2)

    raw_bytes = content.encode("utf-8")

    if encrypt_gpg:
        clean_env = env or dict(os.environ)
        gpg = shutil.which("gpg", path=clean_env.get("PATH", ""))
        if not gpg:
            raise AppError(3)
        res = run(
            [gpg, "--batch", "--yes", "--encrypt", "--armor", "-r", encrypt_gpg, "-o", str(dest)],
            env=clean_env,
            input_data=raw_bytes,
            timeout=30,
            stdout_cap=8192,
            stderr_cap=8192,
        )
        if res.returncode != 0:
            raise AppError(3)
        try:
            os.chmod(dest, 0o600)
        except OSError:
            pass
        return

    # Atomic write with 0600 permissions
    fd, temp_file = tempfile.mkstemp(prefix="otp-export-", dir=dest_dir)
    try:
        os.chmod(temp_file, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, dest)
    except Exception:
        try:
            os.unlink(temp_file)
        except OSError:
            pass
        raise AppError(2) from None


def collect_backend_tokens(
    backend: str,
    profile: dict[str, str],
    env: dict[str, str],
) -> list[OtpParameters]:
    """Collect OtpParameters from the specified backend scope."""
    tokens: list[OtpParameters] = []
    from .enrollment import parse_secret_or_uri

    if backend == "pass-otp":
        from .backends.local import LocalScope, child_environment, preflight, records

        store = profile.get("store")
        key_home = profile.get("key_home")
        if not store or not key_home:
            raise AppError(2)
        scope = LocalScope(backend="pass-otp", store=store, key_home=key_home)
        preflight(scope, env)
        recs = records(scope, env)
        clean_env = child_environment(scope, env)
        pass_bin = shutil.which("pass", path=clean_env.get("PATH", ""))
        if not pass_bin:
            raise AppError(3)

        for key, _ in recs:
            res = run(
                [pass_bin, "show", key],
                env=clean_env,
                timeout=10,
                stdout_cap=16384,
                preserve_session=True,
            )
            if res.returncode == 0 and res.stdout:
                text = res.stdout.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("otpauth://") or line.startswith("steam://"):
                        try:
                            tokens.append(parse_secret_or_uri(line))
                            break
                        except AppError:
                            pass
        return tokens

    if backend == "onepassword":
        from .backends import onepassword
        from .interaction import list_items

        account = profile.get("account")
        vault = profile.get("vault")
        tag = profile.get("tag", "OTP")
        if not account or not vault:
            raise AppError(2)

        op_bin = shutil.which("op", path=env.get("PATH", ""))
        if not op_bin:
            raise AppError(3)

        clean_env = onepassword.child_environment(env)
        items = list_items(account, vault, env, tag=tag)

        for item_id, title in items:
            res = run(
                [
                    op_bin,
                    "item",
                    "get",
                    item_id,
                    "--vault",
                    vault,
                    "--account",
                    account,
                    "--format",
                    "json",
                ],
                env=clean_env,
                timeout=15,
                stdout_cap=65536,
                preserve_session=True,
            )
            if res.returncode == 0 and res.stdout:
                try:
                    data = json.loads(res.stdout.decode("utf-8"))
                    fields = data.get("fields", [])
                    for f in fields:
                        val = f.get("value", "")
                        if isinstance(val, str) and (
                            val.startswith("otpauth://") or val.startswith("steam://")
                        ):
                            tokens.append(parse_secret_or_uri(val, fallback_label=title))
                            break
                except ValueError, AppError:
                    pass
        return tokens
    if backend in ("yubikey", "tpm2-totp"):
        return []

    raise AppError(2)
