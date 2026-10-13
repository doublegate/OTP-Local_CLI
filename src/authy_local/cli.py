"""Public terminal interface; diagnostics contain no caller or backend values."""

import argparse
import json
import os
import shutil
import sys

from . import __version__, doctor
from .backends.onepassword import retrieve
from .errors import AppError
from .interaction import clipboard_capability, copy_code, select_item
from .models import Scope
from .processes import run


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown arguments, which may contain secrets.
        raise AppError(2)


def has_terminal(stdin) -> bool:
    if not stdin.isatty():
        return False
    try:
        fd = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
        os.close(fd)
        return True
    except OSError:
        return False


def parser() -> Parser:
    root = Parser(prog="otp-local", allow_abbrev=False)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    inspect = commands.add_parser("doctor", allow_abbrev=False)
    inspect.add_argument("--json", action="store_true")
    commands.add_parser("tui", allow_abbrev=False)
    guide = commands.add_parser("guide", allow_abbrev=False)
    guide.add_argument(
        "topic", choices=("optional", "setup", "acceptance", "migration", "recovery", "tui")
    )
    show = commands.add_parser("show", allow_abbrev=False)
    show.add_argument("item", nargs="?")
    show.add_argument("--allow-pipe", action="store_true")
    copy = commands.add_parser("copy", allow_abbrev=False)
    copy.add_argument("item", nargs="?")
    select = commands.add_parser("select", allow_abbrev=False)
    select.add_argument("--copy", action="store_true")
    enroll = commands.add_parser("enroll", allow_abbrev=False)
    enroll.add_argument("--apply", action="store_true")
    enroll.add_argument("--digits", type=int, default=6)
    enroll.add_argument("--period", type=int, default=30)
    enroll.add_argument("--title")
    enroll.add_argument("--tags", default="OTP")
    enroll.add_argument("--item-id")
    enroll.add_argument("--qr-image")
    enroll.add_argument("--qr-clipboard", action="store_true")
    pick = commands.add_parser("pick", allow_abbrev=False)
    pick.add_argument("--launcher", choices=("auto", "wofi", "rofi", "fzf"), default="auto")
    pick.add_argument("--no-notify", action="store_true")
    pick.add_argument("--stdout", action="store_true")
    pick.add_argument("--allow-pipe", action="store_true")
    import_cmd = commands.add_parser("import", allow_abbrev=False)
    import_cmd.add_argument("source")
    import_cmd.add_argument(
        "--format",
        choices=("auto", "aegis", "bitwarden", "google-migration", "uri-list"),
        default="auto",
    )
    import_cmd.add_argument("--dry-run", action="store_true", default=False)
    import_cmd.add_argument("--apply", action="store_true", default=False)
    export_cmd = commands.add_parser("export", allow_abbrev=False)
    export_cmd.add_argument("--format", choices=("uri", "aegis", "csv"), default="uri")
    export_cmd.add_argument("--output")
    export_cmd.add_argument("--encrypt-gpg")
    export_cmd.add_argument("--stdout", action="store_true")
    export_cmd.add_argument("--allow-pipe", action="store_true")
    audit_cmd = commands.add_parser("audit", allow_abbrev=False)
    audit_cmd.add_argument("--json", action="store_true")
    qr_cmd = commands.add_parser("qr", allow_abbrev=False)
    qr_cmd.add_argument("item", nargs="?")
    qr_cmd.add_argument("--allow-pipe", action="store_true")
    for command in (show, copy, select, enroll, pick, import_cmd, export_cmd, audit_cmd, qr_cmd):
        command.add_argument(
            "--backend",
            choices=("onepassword", "pass-otp", "totpm", "yubikey", "tpm2-totp"),
            default="onepassword",
        )
        for flag in ("account", "vault", "store", "key-home", "entry", "config", "service"):
            command.add_argument("--" + flag)
    agent_cmd = commands.add_parser("agent", allow_abbrev=False)
    agent_cmd.add_argument("action", choices=("status", "start", "stop", "lock"))
    agent_cmd.add_argument("--timeout", type=float, default=900.0)
    unlock_cmd = commands.add_parser("unlock", allow_abbrev=False)
    unlock_cmd.add_argument("--account")
    return root


def local_scope(args):
    from .backends.local import LocalScope

    if getattr(args, "item", None) or args.vault:
        raise AppError(2)
    if args.backend == "pass-otp" and (args.account or args.service or args.config):
        raise AppError(2)
    if args.backend == "totpm" and (args.store or args.key_home or args.entry):
        raise AppError(2)
    return LocalScope(
        backend=args.backend,
        store=args.store,
        key_home=args.key_home,
        entry=args.entry,
        config=args.config,
        service=args.service,
        account=args.account,
        digits=getattr(args, "digits", 6),
        period=getattr(args, "period", 30),
    )


def local_operation(args, env):
    from dataclasses import replace

    from .backends import local
    from .interaction import choose_records

    scope = local_scope(args)
    if args.command == "select":
        if args.entry or args.service or args.account:
            raise AppError(2)
        selected = choose_records(local.records(scope, env), env)
        if args.backend == "pass-otp":
            scope = replace(scope, entry=selected)
        else:
            service, account = selected.split(":", 1)
            scope = replace(scope, service=service, account=account)
    return local.retrieve(scope, env)


def notice(stderr, message: str) -> None:
    try:
        stderr.write(message + "\n")
    except OSError, UnicodeError:
        pass


def main(argv=None, *, stdin=None, stdout=None, stderr=None) -> int:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        # argparse help/version use process streams; route them through the public sinks.
        from contextlib import redirect_stderr, redirect_stdout

        with redirect_stdout(stdout), redirect_stderr(stderr):
            args = parser().parse_args(argv)
        if args.command == "doctor":
            result = doctor.report(dict(os.environ))
            if args.json:
                stdout.write(json.dumps(result, sort_keys=True) + "\n")
            else:
                for name, capability in result.items():
                    stdout.write(f"{name}: {capability['state']}\n")
            return doctor.status(result)
        if args.command == "guide":
            from importlib.resources import files

            stdout.write(files("authy_local.guides").joinpath(args.topic + ".md").read_text())
            return 0
        if args.command == "tui":
            if (
                sys.platform != "linux"
                or sys.version_info[:2] != (3, 14)
                or not has_terminal(stdin)
                or not stdout.isatty()
            ):
                raise AppError(3)
            from pathlib import Path

            from . import tui
            from .installer import InstallError, operate

            def dispatch(arguments, output, diagnostic):
                return main(arguments, stdin=stdin, stdout=output, stderr=diagnostic)

            def preview(wheel, output, diagnostic):
                try:
                    plan = operate("install", Path.home(), wheel=Path(wheel))
                    output.write("PREVIEW (no changes)\n" + "\n".join(plan) + "\n")
                    return 0
                except InstallError, OSError, ValueError:
                    return 3

            return tui.run(dispatch, preview=preview)
        if args.command == "enroll":
            if not args.apply:
                raise AppError(2)
            if (
                sys.platform != "linux"
                or sys.version_info[:2] != (3, 14)
                or not has_terminal(stdin)
            ):
                raise AppError(3)

            from .enrollment import (
                decode_qr_image_bytes,
                decode_qr_image_file,
                get_clipboard_image,
                parse_secret_or_uri,
            )

            env = dict(os.environ)

            secret = ""
            if getattr(args, "qr_clipboard", False):
                img = get_clipboard_image(env)
                decoded = decode_qr_image_bytes(img, env)
                params = parse_secret_or_uri(decoded)
                secret = (
                    params.to_uri()
                    if args.backend in ("pass-otp", "onepassword")
                    else params.secret
                )
            elif getattr(args, "qr_image", None):
                decoded = decode_qr_image_file(args.qr_image, env)
                params = parse_secret_or_uri(decoded)
                secret = (
                    params.to_uri()
                    if args.backend in ("pass-otp", "onepassword")
                    else params.secret
                )

            if args.backend == "onepassword":
                from .backends import onepassword

                if not args.account or not args.vault or not getattr(args, "title", None):
                    raise AppError(2)

                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            secret = getpass("TOTP enrollment URI or Base32 secret (hidden): ")
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""

                params = parse_secret_or_uri(secret, fallback_label=args.title)
                uri = params.to_uri()
                onepassword.enroll(
                    account=args.account,
                    vault=args.vault,
                    title=args.title,
                    otp_uri=uri,
                    env=env,
                    item_id=getattr(args, "item_id", None),
                    tags=getattr(args, "tags", "OTP"),
                )
            else:
                from .backends import local

                scope = local_scope(args)
                local.preflight(scope, env, enrollment=True)

                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            prompt = (
                                "TOTP enrollment URI (hidden): "
                                if args.backend == "pass-otp"
                                else "Base32 enrollment secret (hidden): "
                            )
                            secret = getpass(prompt)
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""

                local.enroll(scope, env, secret)

            secret = ""
            notice(stderr, "Enrollment completed. Verify a fresh login and recovery privately.")
            return 0
        if args.command == "pick":
            if sys.platform != "linux" or sys.version_info[:2] != (3, 14):
                raise AppError(3)
            env = dict(os.environ)

            from .interaction import launch_picker, notify_desktop
            from .tui_profiles import load as load_profiles

            try:
                profiles = load_profiles()
            except AppError:
                profiles = {}
            profile = profiles.get(args.backend, {})

            if args.backend == "onepassword":
                if any((args.store, args.key_home, args.entry, args.config, args.service)):
                    raise AppError(2)
                account = args.account or profile.get("account")
                vault = args.vault or profile.get("vault")
                tag = profile.get("tag")
                if not account or not vault:
                    raise AppError(2)
                from .interaction import list_items

                rows = list_items(account, vault, env, tag=tag)
                selected_id = launch_picker(rows, env, launcher=args.launcher)
                scope = Scope(selected_id, account, vault)
                code = retrieve(scope, env)
            elif args.backend in ("yubikey", "tpm2-totp"):
                from .backends import hardware

                if args.backend == "yubikey":
                    rows = hardware.yubikey_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = hardware.yubikey_code(selected_id, env)
                else:
                    rows = hardware.tpm2_totp_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = hardware.tpm2_totp_code(selected_id, env)
            else:
                from dataclasses import replace

                from .backends import local

                if args.backend == "pass-otp":
                    if args.account or args.service or args.config:
                        raise AppError(2)
                    store = args.store or profile.get("store")
                    key_home = args.key_home or profile.get("key_home")
                    if not store or not key_home:
                        raise AppError(2)
                    scope = local.LocalScope(backend="pass-otp", store=store, key_home=key_home)
                else:
                    if args.store or args.key_home or args.entry:
                        raise AppError(2)
                    config = args.config or profile.get("config")
                    if not config:
                        raise AppError(2)
                    scope = local.LocalScope(backend="totpm", config=config)
                local.preflight(scope, env)
                rows = local.records(scope, env)
                selected = launch_picker(rows, env, launcher=args.launcher)
                if args.backend == "pass-otp":
                    scope = replace(scope, entry=selected)
                else:
                    service, account = selected.split(":", 1)
                    scope = replace(scope, service=service, account=account)
                code = local.retrieve(scope, env)

            if args.stdout:
                if not stdout.isatty() and not getattr(args, "allow_pipe", False):
                    raise AppError(3)
                stdout.write(code + "\n")
                stdout.flush()
                return 0

            copy_code(code, env)
            if not args.no_notify:
                notify_desktop("Authy Local", "OTP copied to clipboard (clears in 45s)", env)
            return 0
        if args.command == "import":
            if sys.platform != "linux" or sys.version_info[:2] != (3, 14):
                raise AppError(3)
            env = dict(os.environ)

            from .importers import detect_and_parse_import
            from .tui_profiles import load as load_profiles

            try:
                profiles = load_profiles()
            except AppError:
                profiles = {}
            profile = profiles.get(args.backend, {})

            tokens = detect_and_parse_import(args.source, fmt=getattr(args, "format", "auto"))
            if not tokens:
                raise AppError(2)

            if not args.apply:
                stdout.write(f"Migration preview: found {len(tokens)} TOTP token(s) in source:\n")
                for idx, t in enumerate(tokens, 1):
                    label = f"{t.issuer}: {t.account}" if t.issuer else t.account
                    stdout.write(
                        f"  {idx:3d}. {label} ({t.algorithm}, {t.digits} digits, {t.period}s)\n"
                    )
                stdout.write(
                    f"\nRun with --apply to enroll these tokens into backend '{args.backend}'.\n"
                )
                stdout.flush()
                return 0

            if args.backend == "onepassword":
                if any((args.store, args.key_home, args.entry, args.config, args.service)):
                    raise AppError(2)
                account = args.account or profile.get("account")
                vault = args.vault or profile.get("vault")
                if not account or not vault:
                    raise AppError(2)
                from .backends import onepassword

                for t in tokens:
                    title = f"{t.issuer}: {t.account}" if t.issuer else t.account
                    onepassword.enroll(
                        account=account,
                        vault=vault,
                        title=title,
                        otp_uri=t.to_uri(),
                        env=env,
                        tags="OTP",
                    )
            else:
                from dataclasses import replace

                from .backends import local
                from .backends.local import LABEL

                if args.backend == "pass-otp":
                    if args.account or args.service or args.config:
                        raise AppError(2)
                    store = args.store or profile.get("store")
                    key_home = args.key_home or profile.get("key_home")
                    if not store or not key_home:
                        raise AppError(2)
                    scope = local.LocalScope(backend="pass-otp", store=store, key_home=key_home)
                    local.preflight(scope, env, enrollment=True)
                    for t in tokens:
                        raw_entry = f"{t.issuer}/{t.account}" if t.issuer else t.account
                        safe_entry = "".join(
                            c if LABEL.fullmatch(c) else "_" for c in raw_entry
                        ).strip("_")
                        if not safe_entry:
                            safe_entry = f"otp_token_{t.digits}"
                        entry_scope = replace(scope, entry=safe_entry)
                        local.enroll(entry_scope, env, t.to_uri())
                else:
                    if args.store or args.key_home or args.entry:
                        raise AppError(2)
                    config = args.config or profile.get("config")
                    if not config:
                        raise AppError(2)
                    scope = local.LocalScope(backend="totpm", config=config)
                    local.preflight(scope, env, enrollment=True)
                    for t in tokens:
                        raw_srv = t.issuer or "OTP"
                        raw_acc = t.account or "account"
                        safe_srv = (
                            "".join(c if LABEL.fullmatch(c) else "_" for c in raw_srv).strip("_")
                            or "OTP"
                        )
                        safe_acc = (
                            "".join(c if LABEL.fullmatch(c) else "_" for c in raw_acc).strip("_")
                            or "account"
                        )
                        token_scope = replace(scope, service=safe_srv, account=safe_acc)
                        local.enroll(token_scope, env, t.secret)

            notice(stderr, f"Successfully imported {len(tokens)} token(s) into {args.backend}.")
            return 0
        if args.command == "export":
            if not args.output and not args.stdout:
                raise AppError(2)
            if args.stdout and not has_terminal(stdout) and not args.allow_pipe:
                raise AppError(2)

            from pathlib import Path

            from .exporters import (
                collect_backend_tokens,
                export_tokens_to_string,
                write_export_file,
            )
            from .tui_profiles import load as load_profiles

            env = dict(os.environ)
            try:
                profiles = load_profiles()
            except AppError:
                profiles = {}
            profile = dict(profiles.get(args.backend, {}))
            for f in ("account", "vault", "store", "key_home", "config", "service"):
                val = getattr(args, f, None)
                if val:
                    profile[f] = val

            tokens = collect_backend_tokens(args.backend, profile, env)
            content = export_tokens_to_string(tokens, fmt=args.format)

            if args.stdout:
                stdout.write(content)
                stdout.flush()
            else:
                out_path = Path(args.output)
                write_export_file(
                    content,
                    out_path,
                    encrypt_gpg=args.encrypt_gpg,
                    env=env,
                )
                notice(stderr, f"Successfully exported {len(tokens)} token(s) to {out_path}.")
            return 0
        if args.command == "audit":
            from .auditor import audit_tokens, format_audit_report
            from .exporters import collect_backend_tokens
            from .tui_profiles import load as load_profiles

            env = dict(os.environ)
            try:
                profiles = load_profiles()
            except AppError:
                profiles = {}
            profile = dict(profiles.get(args.backend, {}))
            for f in ("account", "vault", "store", "key_home", "config", "service"):
                val = getattr(args, f, None)
                if val:
                    profile[f] = val

            tokens = collect_backend_tokens(args.backend, profile, env)
            report = audit_tokens(tokens, backend=args.backend)
            if args.json:
                stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
            else:
                stdout.write(format_audit_report(report))
            stdout.flush()
            crit = sum(1 for f in report.findings if f.severity == "CRITICAL")
            return 1 if crit > 0 else 0
        if args.command == "qr":
            if not has_terminal(stdout) and not getattr(args, "allow_pipe", False):
                raise AppError(3)
            env = dict(os.environ)
            qrencode_bin = shutil.which("qrencode", path=env.get("PATH", ""))
            if not qrencode_bin:
                raise AppError(3)

            from .tui_profiles import load as load_profiles

            try:
                profiles = load_profiles()
            except AppError:
                profiles = {}
            profile = dict(profiles.get(args.backend, {}))
            for f in ("account", "vault", "store", "key_home", "config", "service"):
                val = getattr(args, f, None)
                if val:
                    profile[f] = val

            uri = None
            if args.backend == "pass-otp":
                from .backends.local import LocalScope, child_environment, preflight

                entry_name = args.item or args.entry
                if not entry_name:
                    raise AppError(2)
                store = profile.get("store")
                key_home = profile.get("key_home")
                if not store or not key_home:
                    raise AppError(2)
                scope = LocalScope(
                    backend="pass-otp", store=store, key_home=key_home, entry=entry_name
                )
                preflight(scope, env)
                clean_env = child_environment(scope, env)
                pass_bin = shutil.which("pass", path=clean_env.get("PATH", ""))
                if not pass_bin:
                    raise AppError(3)
                res = run(
                    [pass_bin, "show", entry_name],
                    env=clean_env,
                    timeout=10,
                    stdout_cap=16384,
                    preserve_session=True,
                )
                if res.returncode == 0 and res.stdout:
                    for line in res.stdout.decode("utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if line.startswith("otpauth://") or line.startswith("steam://"):
                            uri = line
                            break
            elif args.backend == "onepassword":
                item_name = args.item
                if not item_name:
                    raise AppError(2)
                account = profile.get("account")
                vault = profile.get("vault")
                if not account or not vault:
                    raise AppError(2)
                from .backends import onepassword

                clean_env = onepassword.child_environment(env)
                op_bin = shutil.which("op", path=env.get("PATH", ""))
                if not op_bin:
                    raise AppError(3)
                res = run(
                    [
                        op_bin,
                        "item",
                        "get",
                        item_name,
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
                        for f in data.get("fields", []):
                            val = f.get("value", "")
                            if isinstance(val, str) and (
                                val.startswith("otpauth://") or val.startswith("steam://")
                            ):
                                uri = val
                                break
                    except ValueError:
                        pass
            if not uri:
                raise AppError(4)

            qr_res = run([qrencode_bin, "-t", "UTF8", uri], env=env, timeout=5, stdout_cap=65536)
            if qr_res.returncode != 0 or not qr_res.stdout:
                raise AppError(4)
            stdout.write(qr_res.stdout.decode("utf-8", errors="replace"))
            stdout.flush()
            return 0
        if args.command == "agent":
            if sys.platform != "linux" or sys.version_info[:2] != (3, 14):
                raise AppError(3)
            from .agent import SessionAgent, send_agent_request

            if args.action == "start":
                agent = SessionAgent(idle_timeout=args.timeout)
                notice(
                    stderr,
                    f"Starting session agent daemon (auto-lock after {int(args.timeout)}s)...",
                )
                agent.run()
                return 0
            elif args.action == "status":
                resp = send_agent_request("status")
                if resp is None:
                    stdout.write("Session agent daemon is not running.\n")
                    return 0
                stdout.write(
                    f"Agent Status: active\n"
                    f"Locked: {resp.get('locked')}\n"
                    f"Cached Secrets: {resp.get('cached_count')}\n"
                    f"Idle Seconds: {resp.get('idle_seconds')}\n"
                )
                return 0
            elif args.action == "lock":
                resp = send_agent_request("lock")
                if resp is None:
                    notice(stderr, "Session agent daemon is not running.")
                    return 3
                notice(stderr, "Session agent daemon locked; memory wiped.")
                return 0
            elif args.action == "stop":
                resp = send_agent_request("stop")
                if resp is None:
                    notice(stderr, "Session agent daemon is not running.")
                    return 3
                notice(stderr, "Session agent daemon stopped.")
                return 0
        if args.command == "unlock":
            if (
                sys.platform != "linux"
                or sys.version_info[:2] != (3, 14)
                or not has_terminal(stdin)
            ):
                raise AppError(3)
            from .interaction import interactive_unlock

            interactive_unlock(dict(os.environ), account=args.account)
            notice(stderr, "Session unlocked.")
            return 0
        scope = None

        if args.backend == "onepassword":
            if any((args.store, args.key_home, args.entry, args.config, args.service)):
                raise AppError(2)
            scope = Scope(
                getattr(args, "item", None) or ("a" * 26 if args.command == "select" else ""),
                args.account or "",
                args.vault or "",
            )

        if sys.platform != "linux" or sys.version_info[:2] != (3, 14):
            raise AppError(3)

        copying = args.command == "copy" or (args.command == "select" and args.copy)
        if not has_terminal(stdin) or (
            not copying and not stdout.isatty() and not getattr(args, "allow_pipe", False)
        ):
            raise AppError(3)
        env = dict(os.environ)
        if copying:
            clipboard_capability(env)
        if args.backend in ("yubikey", "tpm2-totp"):
            from .backends import hardware
            from .interaction import choose_records

            if args.backend == "yubikey":
                if args.command == "select":
                    selected = choose_records(hardware.yubikey_records(env), env)
                    code = hardware.yubikey_code(selected, env)
                else:
                    if not args.account:
                        raise AppError(2)
                    code = hardware.yubikey_code(args.account, env)
            else:
                if args.command == "select":
                    selected = choose_records(hardware.tpm2_totp_records(env), env)
                    code = hardware.tpm2_totp_code(selected, env)
                else:
                    code = hardware.tpm2_totp_code(args.account or "default", env)
        elif args.backend != "onepassword":
            code = local_operation(args, env)
        elif args.command == "select":
            scope = Scope(select_item(args.account, args.vault, env), args.account, args.vault)
            code = retrieve(scope, env)
        else:
            code = retrieve(scope, env)
        if copying:
            copy_code(code, env)
            return 0
        stdout.write(code + "\n")
        stdout.flush()
        return 0
    except SystemExit as exit:
        return int(exit.code)
    except AppError as error:
        notice(stderr, str(error))
        return error.exit_code
    except KeyboardInterrupt:
        notice(stderr, "Operation cancelled.")
        return 130
    except OSError, UnicodeError:
        # No traceback or broken-pipe diagnostic may include external values.
        return 3
