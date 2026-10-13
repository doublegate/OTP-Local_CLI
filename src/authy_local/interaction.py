"""Ephemeral scoped metadata selection and explicit Wayland clipboard handoff."""

import json
import re
import shutil
import threading
import time
import unicodedata

from .backends.onepassword import child_environment, clear_probe_cache, foreign_auth, probe
from .errors import AppError
from .models import Scope
from .processes import handoff, run
from .tui_profiles import valid_tag


def capability(name: str, env: dict[str, str]) -> str:
    executable = shutil.which(name, path=env.get("PATH", ""))
    if executable is None:
        raise AppError(3)
    return executable


def clipboard_capability(env: dict[str, str]) -> str:
    if not env.get("WAYLAND_DISPLAY"):
        raise AppError(3)
    return capability("wl-copy", env)


def scrub_clipboard(
    expected_code: str,
    env: dict[str, str],
    *,
    delay: float = 45.0,
) -> threading.Thread | None:
    """Spawn an unprivileged background daemon thread that clears the clipboard after delay

    if and only if it still holds the exact expected OTP code.
    """
    if env.get("AUTHY_NO_CLIP_CLEAR") == "1" or delay <= 0:
        return None

    def _worker():
        try:
            time.sleep(delay)
            wl_paste = shutil.which("wl-paste", path=env.get("PATH", ""))
            wl_copy = shutil.which("wl-copy", path=env.get("PATH", ""))
            if not wl_paste or not wl_copy or not env.get("WAYLAND_DISPLAY"):
                return
            check = run(
                [wl_paste, "--no-newline"],
                env=child_environment(env),
                timeout=2,
                stdout_cap=128,
            )
            if (
                check.returncode == 0
                and check.stdout.decode("ascii", errors="ignore").strip() == expected_code.strip()
            ):
                run(
                    [wl_copy, "--clear"],
                    env=child_environment(env),
                    timeout=2,
                )
        except Exception:
            pass

    thread = threading.Thread(target=_worker, name="authy-clipboard-scrubber", daemon=True)
    thread.start()
    return thread


def copy_code(code: str, env: dict[str, str], *, scrub_delay: float = 45.0) -> None:
    executable = clipboard_capability(env)
    handoff(
        [executable, "--type", "text/plain"],
        env=child_environment(env),
        input_data=code.encode("ascii"),
    )
    scrub_clipboard(code, env, delay=scrub_delay)


def metadata(raw: bytes, account: str, vault: str) -> list[tuple[str, str]]:
    """Convert vendor metadata to bounded, terminal-safe rows; discard other fields."""
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) > 5000:
            raise ValueError
        rows = []
        seen = set()
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                raise ValueError
            identifier = item.get("id")
            if not isinstance(identifier, str) or not isinstance(item.get("vault"), dict):
                raise ValueError
            Scope(identifier, account, item["vault"].get("id", ""))
            if item["vault"]["id"] != vault or identifier in seen:
                raise ValueError
            seen.add(identifier)
            title = "".join(
                f"\\u{ord(char):04x}" if unicodedata.category(char).startswith("C") else char
                for char in item["title"][:160]
            )[:160]
            rows.append((identifier, f"{title} [{identifier[-8:]}]"))
        return rows
    except ValueError, TypeError, RecursionError, AppError:
        raise AppError(5) from None


def list_items(
    account: str, vault: str, env: dict[str, str], *, tag: str | None = None
) -> list[tuple[str, str]]:
    """List scoped Login metadata without selection tools or OTP generation."""
    Scope("a" * 26, account, vault)
    if tag is not None and not valid_tag(tag):
        raise AppError(2)
    if foreign_auth(env):
        raise AppError(3)
    backend = probe(env)
    if backend["state"] != "available":
        raise AppError(3)
    listing = run(
        [
            backend["path"],
            "item",
            "list",
            "--account",
            account,
            "--vault",
            vault,
            "--categories",
            "Login",
            *(["--tags", tag] if tag else []),
            "--format",
            "json",
            "--no-color",
            "--cache=false",
            "--debug=false",
        ],
        env=child_environment(env),
        stdout_cap=4 * 1024 * 1024,
        preserve_session=True,
    )
    if listing.returncode:
        raise AppError(4)
    rows = metadata(listing.stdout, account, vault)
    if not rows and tag is None:
        raise AppError(4)
    return rows


def select_item(account: str, vault: str, env: dict[str, str]) -> str:
    Scope("a" * 26, account, vault)
    if foreign_auth(env):
        raise AppError(3)
    executable = capability("fzf", env)
    clean = {
        key: value for key, value in child_environment(env).items() if not key.startswith("FZF_")
    }
    help_result = run(
        [executable, "--help"], env=clean, timeout=5, stdout_cap=65536, stderr_cap=8192
    )
    if help_result.returncode or any(
        flag not in help_result.stdout for flag in (b"--accept-nth", b"--delimiter")
    ):
        raise AppError(3)
    rows = list_items(account, vault, env)
    content = "".join(f"{index}\t{title}\n" for index, (_, title) in enumerate(rows)).encode()
    result = run(
        [executable, "--delimiter=\t", "--accept-nth=1", "--no-multi"],
        env=clean,
        input_data=content,
        timeout=300,
        stdout_cap=128,
        interactive=True,
    )
    if result.returncode in (1, 130):
        raise AppError(130)
    if result.returncode or re.fullmatch(rb"(?:0|[1-9][0-9]{0,3})\r?\n?", result.stdout) is None:
        raise AppError(6)
    index = int(result.stdout)
    if index >= len(rows):
        raise AppError(6)
    return rows[index][0]


def choose_records(rows: list[tuple[str, str]], env: dict[str, str]) -> str:
    """Select an opaque key from bounded metadata without running shell hooks."""
    if not rows or len(rows) > 5000:
        raise AppError(4)
    executable = capability("fzf", env)
    clean = {
        key: value for key, value in child_environment(env).items() if not key.startswith("FZF_")
    }
    help_result = run(
        [executable, "--help"], env=clean, timeout=5, stdout_cap=65536, stderr_cap=8192
    )
    if help_result.returncode or any(
        flag not in help_result.stdout for flag in (b"--accept-nth", b"--delimiter")
    ):
        raise AppError(3)
    content = "".join(
        f"{index}\t{''.join(c if c.isprintable() else '?' for c in label[:160])}\n"
        for index, (_, label) in enumerate(rows)
    ).encode()
    result = run(
        [executable, "--delimiter=\t", "--accept-nth=1", "--no-multi"],
        env=clean,
        input_data=content,
        timeout=300,
        stdout_cap=128,
        interactive=True,
    )
    if result.returncode in (1, 130):
        raise AppError(130)
    if result.returncode or re.fullmatch(rb"(?:0|[1-9][0-9]{0,3})\r?\n?", result.stdout) is None:
        raise AppError(6)
    index = int(result.stdout)
    if index >= len(rows):
        raise AppError(6)
    return rows[index][0]


def notify_desktop(title: str, message: str, env: dict[str, str]) -> None:
    """Send a safe desktop notification via notify-send without exposing secrets."""
    executable = shutil.which("notify-send", path=env.get("PATH", ""))
    if not executable:
        return
    try:
        run(
            [
                executable,
                "-a",
                "Authy Local",
                "-i",
                "dialog-password",
                "-t",
                "3000",
                title,
                message,
            ],
            env=child_environment(env),
            timeout=3,
        )
    except Exception:
        pass


def launch_picker(
    rows: list[tuple[str, str]],
    env: dict[str, str],
    *,
    launcher: str = "auto",
) -> str:
    """Select an item key from rows using a desktop launcher (wofi, rofi) or fzf."""
    if not rows or len(rows) > 5000:
        raise AppError(4)

    if launcher not in ("auto", "wofi", "rofi", "fzf"):
        raise AppError(2)

    target = launcher
    if target == "auto":
        if env.get("WAYLAND_DISPLAY") and shutil.which("wofi", path=env.get("PATH", "")):
            target = "wofi"
        elif shutil.which("rofi", path=env.get("PATH", "")):
            target = "rofi"
        elif shutil.which("fzf", path=env.get("PATH", "")):
            target = "fzf"
        else:
            raise AppError(3)

    if target == "fzf":
        return choose_records(rows, env)

    if target == "rofi":
        executable = capability("rofi", env)
        clean = {k: v for k, v in child_environment(env).items() if not k.startswith("ROFI_")}
        content = "".join(
            f"{''.join(c if c.isprintable() else '?' for c in label[:160])}\n" for _, label in rows
        ).encode()

        result = run(
            [executable, "-dmenu", "-i", "-format", "i", "-p", "OTP Item"],
            env=clean,
            input_data=content,
            timeout=300,
            stdout_cap=128,
            interactive=True,
        )
        if result.returncode in (1, 130):
            raise AppError(130)
        if result.returncode != 0:
            raise AppError(6)
        raw_out = result.stdout.decode("ascii", errors="ignore").strip()
        if not raw_out.isdigit():
            raise AppError(6)
        index = int(raw_out)
        if index < 0 or index >= len(rows):
            raise AppError(6)
        return rows[index][0]

    if target == "wofi":
        executable = capability("wofi", env)
        clean = {k: v for k, v in child_environment(env).items() if not k.startswith("WOFI_")}
        content = "".join(
            f"{index}: {''.join(c if c.isprintable() else '?' for c in label[:160])}\n"
            for index, (_, label) in enumerate(rows)
        ).encode()
        result = run(
            [executable, "--dmenu", "-i", "-p", "OTP Item"],
            env=clean,
            input_data=content,
            timeout=300,
            stdout_cap=256,
            interactive=True,
        )
        if result.returncode in (1, 130):
            raise AppError(130)
        if result.returncode != 0:
            raise AppError(6)
        raw_out = result.stdout.decode("utf-8", errors="ignore").strip()
        match = re.match(r"^(\d+):", raw_out)
        if not match:
            raise AppError(6)
        index = int(match.group(1))
        if index < 0 or index >= len(rows):
            raise AppError(6)
        return rows[index][0]

    raise AppError(3)


def interactive_unlock(env: dict[str, str], account: str | None = None) -> bool:
    """Interactively authenticate or unlock the 1Password CLI session."""
    if foreign_auth(env):
        raise AppError(3)
    if account is not None and not re.fullmatch(r"[A-Za-z0-9._@+-]{1,100}", account):
        raise AppError(2)
    backend = probe(env)
    if backend["state"] != "available":
        raise AppError(3)
    cmd = [backend["path"], "signin"]
    if account:
        cmd.extend(["--account", account])
    result = run(
        cmd,
        env=child_environment(env),
        timeout=120,
        stdout_cap=65536,
        stderr_cap=65536,
        interactive=True,
    )
    if result.returncode in (1, 130):
        raise AppError(130)
    if result.returncode != 0:
        raise AppError(4)
    clear_probe_cache()
    return True
