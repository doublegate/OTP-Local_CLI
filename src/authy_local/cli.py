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
    root.add_argument("--daemon", action="store_true", help="Start background resident daemon")
    root.add_argument("--status", action="store_true", help="Query resident daemon status")
    root.add_argument("--stop", action="store_true", help="Stop resident daemon")
    root.add_argument("--clean", action="store_true", help="Clean stale PID and socket files")
    root.add_argument("--doctor", action="store_true", help="Run system diagnostics")
    root.add_argument("--pick", action="store_true", help="Launch interactive token picker")

    commands = root.add_subparsers(dest="command", required=False, parser_class=Parser)

    list_cmd = commands.add_parser(
        "list", allow_abbrev=False, help="List accounts and tokens non-interactively"
    )
    list_cmd.add_argument(
        "--backend",
        choices=(
            "onepassword",
            "pass-otp",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "keychain",
            "dpapi",
            "fido2",
            "bitwarden",
            "keepass",
            "federated",
        ),
        default="federated",
    )
    list_cmd.add_argument("--json", action="store_true", help="Output token listing in JSON format")
    for flag in ("account", "vault", "store", "key-home", "entry", "config", "service"):
        list_cmd.add_argument("--" + flag)

    search_cmd = commands.add_parser(
        "search", allow_abbrev=False, help="Search tokens non-interactively"
    )
    search_cmd.add_argument("query", help="Search query string")
    search_cmd.add_argument(
        "--backend",
        choices=(
            "onepassword",
            "pass-otp",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "keychain",
            "dpapi",
            "fido2",
            "bitwarden",
            "keepass",
            "federated",
        ),
        default="federated",
    )
    search_cmd.add_argument(
        "--json", action="store_true", help="Output search results in JSON format"
    )
    search_cmd.add_argument(
        "--code", action="store_true", help="Output current TOTP code for single match"
    )
    search_cmd.add_argument(
        "--copy", action="store_true", help="Copy TOTP code to clipboard for single match"
    )
    for flag in ("account", "vault", "store", "key-home", "entry", "config", "service"):
        search_cmd.add_argument("--" + flag)

    inspect = commands.add_parser("doctor", allow_abbrev=False)
    inspect.add_argument("--json", action="store_true")
    inspect.add_argument(
        "--pam",
        action="store_true",
        help="Validate PAM subsystem, module installation, and daemon connectivity",
    )
    inspect.add_argument(
        "--install",
        "--fix",
        action="store_true",
        help="Automatically install missing capabilities using system package manager",
    )
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
    enroll.add_argument(
        "--fido2",
        action="store_true",
        help="Enroll into FIDO2 hardware security key",
    )
    enroll.add_argument(
        "--backup-token",
        action="store_true",
        help="Enroll an additional backup FIDO2 hardware token",
    )
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
    audit_cmd.add_argument("--rotate", action="store_true")
    qr_cmd = commands.add_parser("qr", allow_abbrev=False)
    qr_cmd.add_argument("item", nargs="?")
    qr_cmd.add_argument("--allow-pipe", action="store_true")
    for command in (show, copy, select, enroll, pick, import_cmd, export_cmd, audit_cmd, qr_cmd):
        command.add_argument(
            "--backend",
            choices=(
                "onepassword",
                "pass-otp",
                "totpm",
                "yubikey",
                "tpm2-totp",
                "keychain",
                "dpapi",
                "fido2",
                "bitwarden",
                "keepass",
                "federated",
            ),
            default="onepassword",
        )
        for flag in ("account", "vault", "store", "key-home", "entry", "config", "service"):
            command.add_argument("--" + flag)
    agent_cmd = commands.add_parser("agent", allow_abbrev=False)
    agent_cmd.add_argument("action", choices=("status", "start", "stop", "lock"))
    agent_cmd.add_argument("--timeout", type=float, default=900.0)
    daemon_cmd = commands.add_parser("daemon", allow_abbrev=False)
    daemon_cmd.add_argument(
        "action",
        nargs="?",
        choices=(
            "start",
            "stop",
            "status",
            "restart",
            "clean",
            "reload",
            "systemd-install",
            "systemd-unit",
        ),
    )
    daemon_cmd.add_argument("--clean", action="store_true", help="Clean stale PID and socket files")
    daemon_cmd.add_argument("--foreground", action="store_true")
    daemon_cmd.add_argument("--timeout", type=float, default=900.0)
    unlock_cmd = commands.add_parser("unlock", allow_abbrev=False)
    unlock_cmd.add_argument("--account")
    return root


build_parser = parser


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

    from .security import init_runtime_security

    init_runtime_security()

    if argv is None:
        argv = sys.argv[1:]
    if argv:
        first = argv[0]
        if first == "--doctor":
            argv = ["doctor", *argv[1:]]
        elif first == "--pick":
            argv = ["pick", *argv[1:]]
        elif first == "--daemon":
            argv = ["daemon", "start", *argv[1:]]
        elif first == "--status":
            argv = ["daemon", "status", *argv[1:]]
        elif first == "--stop":
            argv = ["daemon", "stop", *argv[1:]]
        elif first == "--clean":
            argv = ["daemon", "clean", *argv[1:]]

    try:
        # argparse help/version use process streams; route them through the public sinks.
        from contextlib import redirect_stderr, redirect_stdout

        with redirect_stdout(stdout), redirect_stderr(stderr):
            args = parser().parse_args(argv)

        if args.command is None:
            if getattr(args, "clean", False):
                from .daemon import daemon_clean

                return daemon_clean(env=dict(os.environ))
            elif getattr(args, "status", False):
                from .daemon import daemon_status

                return daemon_status(env=dict(os.environ))
            elif getattr(args, "stop", False):
                from .daemon import daemon_stop

                return daemon_stop(env=dict(os.environ))
            elif getattr(args, "daemon", False):
                from .daemon import daemon_start

                return daemon_start(foreground=False, env=dict(os.environ))
            elif getattr(args, "doctor", False):
                result = doctor.report(dict(os.environ))
                for name, capability in result.items():
                    stdout.write(f"{name}: {capability['state']}\n")
                return doctor.status(result)
            elif getattr(args, "pick", False):
                return main(["pick"], stdin=stdin, stdout=stdout, stderr=stderr)
            else:
                raise AppError(2)

        if args.command == "list":
            from .federation import FederatedResolver

            env = dict(os.environ)
            backends = [args.backend] if args.backend != "federated" else None
            resolver = FederatedResolver(candidate_backends=backends)
            tokens = resolver.resolve_all(env)

            if getattr(args, "json", False):
                items = [
                    {
                        "key": t.key,
                        "title": t.title,
                        "badge": t.badge,
                        "backends": t.backends,
                        "account": getattr(t, "account", ""),
                        "issuer": getattr(t, "issuer", ""),
                    }
                    for t in tokens
                ]
                stdout.write(json.dumps(items, indent=2) + "\n")
                stdout.flush()
                return 0

            for t in tokens:
                stdout.write(f"{t.badge} {t.title}\n")
            stdout.flush()
            return 0

        if args.command == "search":
            from .federation import FederatedResolver

            env = dict(os.environ)
            backends = [args.backend] if args.backend != "federated" else None
            resolver = FederatedResolver(candidate_backends=backends)
            matched = resolver.search(args.query, env)

            if getattr(args, "code", False) or getattr(args, "copy", False):
                if not matched:
                    notice(stderr, f"No tokens found matching '{args.query}'.")
                    return 1
                if len(matched) > 1:
                    notice(stderr, f"Ambiguous search query: {len(matched)} tokens matched.")
                    return 1
                code = resolver.retrieve_code(matched[0], env)
                if getattr(args, "copy", False):
                    copy_code(code, env)
                    notice(stderr, "Code copied to clipboard.")
                    return 0
                stdout.write(code + "\n")
                stdout.flush()
                return 0

            if getattr(args, "json", False):
                items = [
                    {
                        "key": t.key,
                        "title": t.title,
                        "badge": t.badge,
                        "backends": t.backends,
                        "account": getattr(t, "account", ""),
                        "issuer": getattr(t, "issuer", ""),
                    }
                    for t in matched
                ]
                stdout.write(json.dumps(items, indent=2) + "\n")
                stdout.flush()
                return 0 if matched else 1

            if not matched:
                notice(stderr, f"No tokens found matching '{args.query}'.")
                return 1

            for t in matched:
                stdout.write(f"{t.badge} {t.title}\n")
            stdout.flush()
            return 0

        if args.command == "doctor":
            if getattr(args, "pam", False):
                from .pam_check import doctor_pam_cli

                return doctor_pam_cli(
                    dict(os.environ), stdout=stdout, stderr=stderr, as_json=args.json
                )
            if getattr(args, "install", False):
                doctor.install_missing(dict(os.environ), stdout=stdout, stderr=stderr)
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
                sys.platform not in ("linux", "darwin", "win32")
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
            if getattr(args, "fido2", False):
                if args.backend != "onepassword" and args.backend != "fido2":
                    raise AppError(2)
                args.backend = "fido2"
            if getattr(args, "backup_token", False) and args.backend != "fido2":
                raise AppError(2)
            if not args.apply:
                raise AppError(2)
            if (
                sys.platform not in ("linux", "darwin", "win32")
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
            elif args.backend == "keychain":
                from .backends import keychain

                if not args.account:
                    raise AppError(2)
                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            secret = getpass("Base32 enrollment secret (hidden): ")
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""
                keychain.keychain_enroll(args.account, secret, env)
            elif args.backend == "dpapi":
                from .backends import dpapi

                if not args.account:
                    raise AppError(2)
                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            secret = getpass("Base32 enrollment secret (hidden): ")
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""
                dpapi.dpapi_enroll(args.account, secret, env)
            elif args.backend == "fido2":
                from .backends import fido2

                if not args.account:
                    raise AppError(2)
                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            secret = getpass("Base32 enrollment secret (hidden): ")
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""
                if getattr(args, "backup_token", False):
                    fido2.fido2_add_backup_token(args.account, secret, env)
                else:
                    fido2.fido2_enroll(args.account, secret, env)
            elif args.backend == "bitwarden":
                from .backends import bitwarden

                title = getattr(args, "title", None) or args.account
                if not title:
                    raise AppError(2)
                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            secret = getpass("Base32 secret or TOTP URI (hidden): ")
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""
                bitwarden.bitwarden_enroll(title, secret, env)
            elif args.backend == "keepass":
                from .backends import keepass

                title = getattr(args, "title", None) or args.account
                if not title:
                    raise AppError(2)
                if not secret:
                    import warnings
                    from getpass import GetPassWarning, getpass

                    confirmation = ""
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", GetPassWarning)
                            secret = getpass("Base32 secret or TOTP URI (hidden): ")
                            confirmation = getpass("Repeat enrollment value (hidden): ")
                        if secret != confirmation:
                            raise AppError(2)
                    except GetPassWarning:
                        raise AppError(3) from None
                    finally:
                        confirmation = ""
                keepass.keepass_enroll(title, secret, env)
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
            if sys.platform not in ("linux", "darwin", "win32") or sys.version_info[:2] != (3, 14):
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
            elif args.backend in (
                "yubikey",
                "tpm2-totp",
                "keychain",
                "dpapi",
                "fido2",
                "bitwarden",
                "keepass",
                "federated",
            ):
                if args.backend == "federated":
                    from .federation import FederatedResolver

                    resolver = FederatedResolver()
                    tokens = resolver.resolve_all(env)
                    rows = [(t.key, t.display_label) for t in tokens]
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    tok = next((t for t in tokens if t.key == selected_id), None)
                    if not tok:
                        raise AppError(4)
                    code = resolver.retrieve_code(tok, env)
                elif args.backend == "keepass":
                    from .backends import keepass

                    rows = keepass.keepass_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = keepass.keepass_code(selected_id, env)
                elif args.backend == "bitwarden":
                    from .backends import bitwarden

                    rows = bitwarden.bitwarden_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = bitwarden.bitwarden_code(selected_id, env)
                elif args.backend == "fido2":
                    from .backends import fido2

                    rows = fido2.fido2_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = fido2.fido2_code(selected_id, env)
                elif args.backend == "dpapi":
                    from .backends import dpapi

                    rows = dpapi.dpapi_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = dpapi.dpapi_code(selected_id, env)
                elif args.backend == "keychain":
                    from .backends import keychain

                    rows = keychain.keychain_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = keychain.keychain_code(selected_id, env)
                elif args.backend == "yubikey":
                    from .backends import hardware

                    rows = hardware.yubikey_records(env)
                    selected_id = launch_picker(rows, env, launcher=args.launcher)
                    code = hardware.yubikey_code(selected_id, env)
                else:
                    from .backends import hardware

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
            if sys.platform not in ("linux", "darwin", "win32") or sys.version_info[:2] != (3, 14):
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
            rotate = getattr(args, "rotate", False)
            report = audit_tokens(tokens, backend=args.backend, env=env, rotate=rotate)
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
            elif args.backend == "bitwarden":
                from .backends import bitwarden

                item_name = args.item or args.account
                if not item_name:
                    raise AppError(2)
                items = bitwarden.list_items(env)
                for itm in items:
                    if itm.get("id") == item_name or itm.get("name") == item_name:
                        totp_raw = itm.get("login", {}).get("totp")
                        if totp_raw:
                            uri = (
                                totp_raw
                                if totp_raw.startswith("otpauth://")
                                else f"otpauth://totp/{itm.get('name')}?secret={totp_raw}"
                            )
                            break
            if not uri:
                raise AppError(4)

            qr_res = run([qrencode_bin, "-t", "UTF8", uri], env=env, timeout=5, stdout_cap=65536)
            if qr_res.returncode != 0 or not qr_res.stdout:
                raise AppError(4)
            stdout.write(qr_res.stdout.decode("utf-8", errors="replace"))
            stdout.flush()
            return 0
        if args.command == "agent":
            if sys.platform not in ("linux", "darwin", "win32") or sys.version_info[:2] != (3, 14):
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
                sys.platform not in ("linux", "darwin", "win32")
                or sys.version_info[:2] != (3, 14)
                or not has_terminal(stdin)
            ):
                raise AppError(3)
            from .interaction import interactive_unlock

            interactive_unlock(dict(os.environ), account=args.account)
            notice(stderr, "Session unlocked.")
            return 0
        if args.command == "daemon":
            if sys.platform not in ("linux", "darwin", "win32") or sys.version_info[:2] != (3, 14):
                raise AppError(3)
            from .daemon import (
                daemon_clean,
                daemon_reload,
                daemon_restart,
                daemon_start,
                daemon_status,
                daemon_stop,
                daemon_systemd_install,
                generate_systemd_unit,
            )

            env = dict(os.environ)
            if getattr(args, "clean", False) or args.action == "clean":
                return daemon_clean(env=env)
            elif args.action == "restart":
                return daemon_restart(foreground=getattr(args, "foreground", False), env=env)
            elif args.action == "start":
                return daemon_start(foreground=getattr(args, "foreground", False), env=env)
            elif args.action == "stop":
                return daemon_stop(env=env)
            elif args.action == "status":
                return daemon_status(env=env)
            elif args.action == "reload":
                return daemon_reload(env=env)
            elif args.action == "systemd-install":
                return daemon_systemd_install(env=env)
            elif args.action == "systemd-unit":
                stdout.write(generate_systemd_unit())
                return 0
            else:
                raise AppError(2)
        scope = None

        if args.backend == "onepassword":
            if any((args.store, args.key_home, args.entry, args.config, args.service)):
                raise AppError(2)
            scope = Scope(
                getattr(args, "item", None) or ("a" * 26 if args.command == "select" else ""),
                args.account or "",
                args.vault or "",
            )

        if sys.platform not in ("linux", "darwin", "win32") or sys.version_info[:2] != (3, 14):
            raise AppError(3)

        copying = args.command == "copy" or (args.command == "select" and args.copy)
        if not has_terminal(stdin) or (
            not copying and not stdout.isatty() and not getattr(args, "allow_pipe", False)
        ):
            raise AppError(3)
        env = dict(os.environ)
        if copying:
            clipboard_capability(env)
        if args.backend in (
            "yubikey",
            "tpm2-totp",
            "keychain",
            "dpapi",
            "fido2",
            "bitwarden",
            "keepass",
            "federated",
        ):
            from .interaction import choose_records

            if args.backend == "federated":
                from .federation import FederatedResolver

                resolver = FederatedResolver()
                if args.command == "select":
                    tokens = resolver.resolve_all(env)
                    rows = [(t.key, t.display_label) for t in tokens]
                    selected_id = choose_records(rows, env)
                    tok = next((t for t in tokens if t.key == selected_id), None)
                    if not tok:
                        raise AppError(4)
                    code = resolver.retrieve_code(tok, env)
                else:
                    target = getattr(args, "item", None) or args.account
                    if not target:
                        raise AppError(2)
                    tokens = resolver.search(target, env)
                    if not tokens:
                        raise AppError(4)
                    code = resolver.retrieve_code(tokens[0], env)
            elif args.backend == "keepass":
                from .backends import keepass

                if args.command == "select":
                    selected = choose_records(keepass.keepass_records(env), env)
                    code = keepass.keepass_code(selected, env)
                else:
                    item_id_or_name = getattr(args, "item", None) or args.account
                    if not item_id_or_name:
                        raise AppError(2)
                    code = keepass.keepass_code(item_id_or_name, env)
            elif args.backend == "bitwarden":
                from .backends import bitwarden

                if args.command == "select":
                    selected = choose_records(bitwarden.bitwarden_records(env), env)
                    code = bitwarden.bitwarden_code(selected, env)
                else:
                    item_id_or_name = getattr(args, "item", None) or args.account
                    if not item_id_or_name:
                        raise AppError(2)
                    code = bitwarden.bitwarden_code(item_id_or_name, env)
            elif args.backend == "fido2":
                from .backends import fido2

                if args.command == "select":
                    selected = choose_records(fido2.fido2_records(env), env)
                    code = fido2.fido2_code(selected, env)
                else:
                    if not args.account:
                        raise AppError(2)
                    code = fido2.fido2_code(args.account, env)
            elif args.backend == "dpapi":
                from .backends import dpapi

                if args.command == "select":
                    selected = choose_records(dpapi.dpapi_records(env), env)
                    code = dpapi.dpapi_code(selected, env)
                else:
                    if not args.account:
                        raise AppError(2)
                    code = dpapi.dpapi_code(args.account, env)
            elif args.backend == "keychain":
                from .backends import keychain

                if args.command == "select":
                    selected = choose_records(keychain.keychain_records(env), env)
                    code = keychain.keychain_code(selected, env)
                else:
                    if not args.account:
                        raise AppError(2)
                    code = keychain.keychain_code(args.account, env)
            elif args.backend == "yubikey":
                from .backends import hardware

                if args.command == "select":
                    selected = choose_records(hardware.yubikey_records(env), env)
                    code = hardware.yubikey_code(selected, env)
                else:
                    if not args.account:
                        raise AppError(2)
                    code = hardware.yubikey_code(args.account, env)
            else:
                from .backends import hardware

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
    except Exception:
        # Top-level shield: intercept unhandled exceptions and emit a static
        # diagnostic notice to prevent tracebacks from leaking secrets to stderr.
        from .errors import MESSAGES

        notice(stderr, MESSAGES[5])
        return 5
