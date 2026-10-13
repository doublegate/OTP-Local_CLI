"""Textual dashboard with private resident scope and transient item browsing."""

import asyncio
import io
import os
import re
import shutil
import textwrap
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from rich.table import Table
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, OptionList, ProgressBar, Static
from textual.widgets.option_list import Option

try:
    from textual.app import SuspendNotSupported
except ImportError:

    class SuspendNotSupported(Exception):
        """Fallback exception when SuspendNotSupported is unavailable."""

        pass


from .errors import MESSAGES, AppError
from .models import parse_code

ACTIONS = (
    ("Browse and show", "Browse stored items, then show or copy a selected code."),
    ("Browse and copy", "Browse stored items; Enter copies the selected code."),
    ("Show code", "Retrieve one code. Dismiss to erase it from the screen."),
    ("Copy code", "Copy one code using your desktop clipboard."),
    (
        "Add OTP entry",
        "Enroll a new OTP from text secret or QR screenshot into 1Password, GPG, or TPM.",
    ),
    ("Saved scope", "Configure resident account/vault IDs or local store paths."),
    ("Doctor", "Inspect local capabilities without authenticating."),
    ("Installation preview", "Preview a local wheel. This never applies changes."),
    ("Private migration guide", "Review migration and independent recovery checkpoints."),
)
ACTION_CATEGORIES = {
    "Browse and show": "Token Retrieval",
    "Browse and copy": "Token Retrieval",
    "Show code": "Token Retrieval",
    "Copy code": "Token Retrieval",
    "Add OTP entry": "Credential Management",
    "Saved scope": "Configuration & Scope",
    "Doctor": "Diagnostics & Health",
    "Installation preview": "Setup & Maintenance",
    "Private migration guide": "Reference & Guidance",
}
BACKENDS = (
    ("onepassword", "1Password"),
    ("pass-otp", "pass-otp / GPG"),
    ("totpm", "totpm / TPM"),
    ("yubikey", "YubiKey OATH"),
    ("tpm2-totp", "TPM 2.0 TOTP"),
    ("keychain", "macOS Keychain"),
    ("dpapi", "Windows DPAPI"),
    ("fido2", "FIDO2 Security Key"),
)
PROFILE_FIELDS = {
    "onepassword": ("account", "vault"),
    "pass-otp": ("store", "key_home"),
    "totpm": ("config",),
    "yubikey": (),
    "tpm2-totp": (),
    "keychain": (),
    "dpapi": (),
    "fido2": (),
}
HELP = (
    "Keyboard controls",
    "Up/Down or j/k: choose an action. Enter: open it.",
    "1-9: open an action directly. a: add OTP. b: choose backend. p: saved scope. F1 or ?: help.",
    "Forms show all scope fields together. Tab/Up/Down changes field.",
    "Enter validates the current field, then advances or submits.",
    "Account/vault IDs and store paths are saved privately; items/codes are not.",
    "Browse: arrows move, / searches, Enter/s shows, c copies, r refreshes.",
    "Escape cancels a form; q or Escape exits from the dashboard.",
    "Results: arrows scroll; Enter/Space advances; Escape dismisses.",
    "Local browser d: delete one GPG/TPM entry after typing DELETE.",
    "Enrollment and installation apply stay in explicit CLI workflows.",
)


GUIDE = (
    "Private migration checkpoints",
    "Review installation preview separately before authorizing apply.",
    "Privately pass disposable synthetic show/select/copy acceptance.",
    "Authorize one low-impact pilot account privately before changes.",
    "Verify independent recovery and preserve your working session.",
    "Follow the provider's current official enrollment instructions.",
    "Verify a separate fresh login and every required access path.",
    "Confirm recovery remains available after the change.",
    "Then authorize batches <=3; high-impact accounts individually.",
    "Stop on access/recovery failure; old Authy seed may be invalid.",
    "Keep detailed evidence outside this repository and agent context.",
    "Report aggregate counts only. This screen attests nothing.",
    "Use explicit CLI enrollment/setup and installed operator guides.",
    "Retain Authy until project development and recovery checks finish.",
)


class Capture(io.StringIO):
    """Bounded sink compatible with the CLI's deliberate terminal output gate."""

    def isatty(self):
        return True

    def write(self, text):
        if self.tell() + len(text) > 131072:
            raise AppError(5)
        return super().write(text)


def safe_text(text):
    return "".join(char if char.isprintable() else "?" for char in str(text))


def write(screen, row, column, text, width, attr=0):
    """Clip every write, including the terminal's unsafe lower-right cell."""
    height, columns = screen.getmaxyx()
    if not 0 <= row < height or not 0 <= column < columns - 1:
        return
    size = min(width, columns - column - 1)
    if size <= 0:
        return
    if attr and hasattr(screen, "attron"):
        screen.attron(attr)
    screen.addnstr(row, column, safe_text(text), size)
    if attr and hasattr(screen, "attroff"):
        screen.attroff(attr)


def panel(screen, row, column, height, width, title, attr=0):
    unicode_lines = "UTF" in getattr(screen, "encoding", "UTF-8").upper()
    left, top, right, side, lower_left, lower_right = (
        ("╭", "─", "╮", "│", "╰", "╯") if unicode_lines else ("+", "-", "+", "|", "+", "+")
    )
    write(screen, row, column, left + top * (width - 2) + right, width, attr)
    write(screen, row, column + 2, " " + title + " ", width - 4, attr)
    for y in range(row + 1, row + height - 1):
        write(screen, y, column, side, 1, attr)
        write(screen, y, column + width - 1, side, 1, attr)
    write(
        screen, row + height - 1, column, lower_left + top * (width - 2) + lower_right, width, attr
    )


def palette(curses):
    """Optional color with a legible monochrome reverse-video fallback."""
    colors = {"border": getattr(curses, "A_BOLD", 0), "selected": getattr(curses, "A_REVERSE", 0)}
    try:
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
            colors = {"border": curses.color_pair(1), "selected": curses.color_pair(2)}
    except AttributeError, curses.error:
        pass
    return colors


def dashboard(
    screen, curses, selected, backend, status="Local capabilities not checked", detail=None
):
    height, width = screen.getmaxyx()
    colors = getattr(curses, "dashboard_colors", {})
    screen.erase()
    write(screen, 0, 2, "Authy Local  |  PRIVATE OTP CONSOLE", width - 4, colors.get("border", 0))
    label = dict(BACKENDS)[backend]
    write(screen, 1, 2, f"Backend: {label}   [b] change", width - 4)
    sidebar = 25 if width >= 80 else 23
    body_height = height - (9 if height >= 24 else 7)
    panel(screen, 3, 1, body_height, sidebar, "Actions", colors.get("border", 0))
    for index, (name, _) in enumerate(ACTIONS):
        name = {
            "Installation preview": "Install preview",
            "Private migration guide": "Migration guide",
            "Add OTP entry": "Add OTP",
        }.get(name, name)
        write(
            screen,
            5 + index,
            3,
            f"{index + 1} {name}".ljust(sidebar - 4),
            sidebar - 4,
            colors.get("selected", 0) if index == selected else 0,
        )
        if index == selected:
            write(screen, 5 + index, 2, ">", 1)
    right = sidebar + 2
    panel(screen, 3, right, body_height, width - right - 1, "Workspace", colors.get("border", 0))
    lines = detail or [
        ACTIONS[selected][0],
        "",
        ACTIONS[selected][1],
        "",
        "Saved scope per backend; [p] configure.",
        "No account changes here.",
    ]
    row = 5
    for line in lines:
        for wrapped in textwrap.wrap(safe_text(line), max(1, width - right - 5)) or [""]:
            if row < 3 + body_height - 1:
                write(screen, row, right + 2, wrapped, width - right - 5)
                row += 1
    if height >= 24:
        panel(screen, height - 6, 1, 3, width - 2, "Session status", colors.get("border", 0))
        write(screen, height - 5, 3, status, width - 6)
    else:
        write(screen, height - 3, 2, status, width - 4)
    write(
        screen,
        height - 2,
        2,
        "Arrows/jk Move  Enter Open  b Backend  p Scope  ? Help  q Quit",
        width - 4,
        colors.get("border", 0),
    )
    screen.refresh()


def paint(screen, lines):
    height, width = screen.getmaxyx()
    screen.erase()
    for row, line in enumerate(lines[: max(0, height - 1)]):
        write(screen, row, 0, line, width - 1)
    screen.refresh()


def message(screen, lines):
    offset = 0
    try:
        while True:
            height, width = screen.getmaxyx()
            if height < 18 or width < 60:
                return
            wrapped = []
            for line in lines:
                wrapped.extend(textwrap.wrap(safe_text(line), width - 6) or [""])
            page = max(1, height - 5)
            offset = min(offset, max(0, len(wrapped) - 1))
            screen.erase()
            panel(screen, 1, 1, height - 3, width - 2, "Result / private session")
            for row, line in enumerate(wrapped[offset : offset + page], 2):
                write(screen, row, 3, line, width - 6)
            footer = (
                "Enter: next page  Arrows: scroll  Esc: erase and return"
                if offset + page < len(wrapped)
                else "Any key: return and erase displayed code."
            )
            write(screen, height - 2, 2, footer, width - 4)
            screen.refresh()
            key = screen.getch()
            if key == 410:
                continue
            if key == 27:
                break
            if key in (258, ord("j")):
                offset = min(offset + 1, max(0, len(wrapped) - page))
            elif key in (259, ord("k")):
                offset = max(0, offset - 1)
            elif offset + page < len(wrapped):
                offset += page
            else:
                break
    finally:
        screen.erase()
        screen.refresh()


def prompt(screen, label, limit, curses):
    value = ""
    overflow = False
    while True:
        paint(
            screen,
            [
                label,
                f"Hidden entry: {len(value)} characters",
                "Invalid or overlong entry; cancel and retry."
                if overflow
                else "Enter accepts; Escape cancels.",
            ],
        )
        key = screen.getch()
        if key in (27, curses.KEY_RESIZE):
            screen.erase()
            screen.refresh()
            return None
        if key in (10, 13):
            return None if overflow else value
        if key in (8, 127, curses.KEY_BACKSPACE):
            value = value[:-1]
        elif 32 <= key <= 126:
            if len(value) < limit:
                value += chr(key)
            else:
                overflow = True
        elif 0 <= key <= 255:
            overflow = True


def execute(screen, args, dispatch, curses, preview=None):
    output, diagnostic = Capture(), Capture()
    status = 3
    curses.def_prog_mode()
    curses.endwin()
    try:
        if args[0] == "preview":
            if preview is not None:
                status = preview(args[1], output, diagnostic)
        else:
            status = dispatch(args, output, diagnostic)
    except AppError as error:
        status = error.exit_code
    except KeyboardInterrupt:
        status = 130
    except Exception:
        # A UI callback failure must not expose private values through a traceback.
        status = 3
    finally:
        curses.reset_prog_mode()
        curses.doupdate()
        screen.erase()
        screen.refresh()
    lines = []
    summary = None
    if args[0] == "doctor":
        # Only the CLI's fixed capability names and states may enter the screen.
        names = {
            "platform",
            "python",
            "op",
            "fish",
            "fzf",
            "wl-copy",
            "pbcopy",
            "clock",
            "authentication",
            "pass",
            "gpg",
            "oathtool",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "tpm-device",
            "keychain",
            "secure-enclave",
            "dpapi",
            "credman",
            "windows-hello",
            "fido2",
            "qrencode",
            "pinentry",
            "gpg-agent",
        }
        states = {}
        for line in output.getvalue().splitlines():
            name, separator, state = line.partition(": ")
            if (
                separator
                and name in names
                and state
                in {
                    "available",
                    "missing",
                    "unknown",
                    "not-applicable",
                }
            ):
                states[name] = state
        lines = [f"{name}: {state}" for name, state in states.items() if state != "not-applicable"]
        if status or not lines:
            status = status or 5
            lines.append(MESSAGES.get(status, MESSAGES[3]))
            summary = f"Doctor failed (exit {status}); press 1 to retry"
        else:
            summary_states = ["available", "missing", "unknown"]
            if any(value == "not-applicable" for value in states.values()):
                summary_states.append("not-applicable")
            summary = "Doctor: " + ", ".join(
                f"{sum(value == state for value in states.values())} {state}"
                for state in summary_states
            )
    elif status:
        lines = [MESSAGES.get(status, MESSAGES[3])]
    elif args[0] in ("show", "select") and "--copy" not in args:
        try:
            lines = ["Code", parse_code(output.getvalue().encode("ascii"))]
        except AppError, UnicodeError:
            lines = [MESSAGES[5]]
    elif args[0] == "preview":
        lines = ["Preview only; no changes authorized.", *output.getvalue().splitlines()]
    else:
        lines = ["Copy completed. Clipboard history behavior is controlled by your desktop."]
    output.close()
    diagnostic.close()
    message(screen, lines)
    return summary


def form(screen, curses, title, fields, initial=None):
    """One hidden, editable form; validation never dispatches incomplete scope."""
    values = list(initial) if initial is not None else [""] * len(fields)
    invalid = [False] * len(fields)
    active = 0
    error = ""
    while True:
        height, width = screen.getmaxyx()
        if height < 18 or width < 60:
            return None
        screen.erase()
        colors = getattr(curses, "dashboard_colors", {})
        panel(screen, 1, 1, height - 3, width - 2, title, colors.get("border", 0))
        write(screen, 3, 3, "Private scope - input hidden", width - 6)
        for index, (label, limit, _) in enumerate(fields):
            row = 5 + index * 2
            marker = ">" if index == active else " "
            write(
                screen,
                row,
                3,
                f"{marker} {label}",
                width - 6,
                colors.get("selected", 0) if index == active else 0,
            )
            write(
                screen,
                row + 1,
                5,
                f"Hidden: {len(values[index])} characters (limit {limit})",
                width - 8,
            )
        write(
            screen,
            height - 5,
            3,
            error or "Tab/Arrows move; Enter advances then submits",
            width - 6,
        )
        write(
            screen,
            height - 4,
            3,
            "Backspace edits; Ctrl-U clears field. Escape cancels.",
            width - 6,
        )
        screen.refresh()
        key = screen.getch()
        if key == 27:
            screen.erase()
            screen.refresh()
            return None
        if key == curses.KEY_RESIZE:
            continue
        if key in (9, 258, 259, 353):
            active = (active + (-1 if key in (259, 353) else 1)) % len(fields)
            error = ""
        elif key in (10, 13):
            _, _, validator = fields[active]
            if invalid[active] or not validator(values[active]):
                error = "Required valid value; edit this field or Escape to cancel."
            elif active < len(fields) - 1:
                active += 1
                error = ""
            else:
                bad = next(
                    (
                        i
                        for i, (_, _, check) in enumerate(fields)
                        if invalid[i] or not check(values[i])
                    ),
                    None,
                )
                if bad is None:
                    screen.erase()
                    screen.refresh()
                    return values
                active = bad
                error = "Required valid value; edit this field or Escape to cancel."
        elif key == 21:
            values[active] = ""
            invalid[active] = False
            error = ""
        elif key in (8, 127, curses.KEY_BACKSPACE):
            values[active] = values[active][:-1]
            if not values[active]:
                invalid[active] = False
            error = ""
        elif 32 <= key <= 126:
            if len(values[active]) < fields[active][1]:
                values[active] += chr(key)
            else:
                invalid[active] = True
                error = "Entry too long; clear this field completely to retry."
        elif 0 <= key <= 255:
            invalid[active] = True
            error = "Unsupported character; clear this field completely to retry."


def scope_fields(backend):
    def identifier(value):
        return len(value) == 26 and value.isascii() and value.isalnum()

    def path(value):
        return value.startswith("/") and "\x00" not in value

    if backend == "onepassword":
        return [
            ("Account ID (26 characters)", 26, identifier),
            ("Vault ID (26 characters)", 26, identifier),
        ]
    if backend == "pass-otp":
        return [("Store absolute path", 1024, path), ("GPG key-home absolute path", 1024, path)]
    if backend == "totpm":
        return [("Configuration absolute path", 1024, path)]
    return []


def profile_values(backend, values):
    return dict(zip(PROFILE_FIELDS[backend], values, strict=True))


def configure_scope(screen, curses, backend, profile):
    from .tui_profiles import valid_tag

    root = Path.home() / ".local/share/authy-local/optional"
    defaults = {
        "onepassword": {"account": "", "vault": ""},
        "pass-otp": {"store": str(root / "pass-store"), "key_home": str(root / "gnupg")},
        "totpm": {"config": str(Path.home() / ".config/authy-local/totpm.conf")},
        "yubikey": {},
        "tpm2-totp": {},
        "keychain": {},
        "dpapi": {},
        "fido2": {},
    }
    fields = scope_fields(backend)
    initial = [(profile or defaults[backend])[name] for name in PROFILE_FIELDS[backend]]
    if backend == "onepassword":
        fields.append(("Item tag (blank = all Login items)", 64, valid_tag))
        initial.append((profile or {}).get("tag", "OTP"))
    values = form(
        screen,
        curses,
        "Saved scope - IDs, paths and optional tag",
        fields,
        initial=initial,
    )
    if values is None:
        return None
    scope = profile_values(backend, values[: len(PROFILE_FIELDS[backend])])
    if backend == "onepassword":
        scope["tag"] = values[-1]
    return scope


def scope_form(screen, curses, backend, selection, profile=None):
    from .tui_items import arguments

    profile = profile or {}
    fields = [] if profile else scope_fields(backend)
    base_count = len(fields)
    if not selection:
        if backend == "onepassword":
            fields += [
                (
                    "Item ID (26 characters)",
                    26,
                    lambda value: len(value) == 26 and value.isascii() and value.isalnum(),
                )
            ]
        else:
            from .backends.local import LABEL

            fields += [
                (
                    "Entry label" if backend == "pass-otp" else "Service label",
                    64,
                    lambda value: LABEL.fullmatch(value) is not None,
                )
            ]
            if backend == "totpm":
                fields += [("Account label", 64, lambda value: LABEL.fullmatch(value) is not None)]
    if not fields:
        values = []
    else:
        values = form(screen, curses, f"{dict(BACKENDS)[backend]} scope", fields)
    if values is None:
        return None
    scope = profile or profile_values(backend, values[:base_count])
    if selection:
        if backend == "onepassword":
            return ["--account", scope["account"], "--vault", scope["vault"]]
        if backend == "pass-otp":
            return [
                "--backend",
                backend,
                "--store",
                scope["store"],
                "--key-home",
                scope["key_home"],
            ]
        if backend == "totpm":
            return ["--backend", backend, "--config", scope["config"]]
        return ["--backend", backend]
    chosen = values[base_count:]
    key = ":".join(chosen) if backend == "totpm" else chosen[0]
    return arguments(backend, scope, key)


def load_records(screen, curses, backend, profile):
    from .tui_items import records

    curses.def_prog_mode()
    curses.endwin()
    failure = None
    rows = None
    try:
        rows = records(backend, profile, dict(os.environ))
    except AppError as error:
        failure = error.exit_code
    except KeyboardInterrupt:
        failure = 130
    except Exception:
        failure = 3
    finally:
        curses.reset_prog_mode()
        curses.doupdate()
        screen.erase()
        screen.refresh()
    if failure is not None:
        message(screen, [MESSAGES.get(failure, MESSAGES[3])])
    return rows


def confirm_delete(screen, curses, backend, label):
    """Default-cancel confirmation identifies exactly one local entry."""
    confirmation = ""
    try:
        while True:
            height, width = screen.getmaxyx()
            if height < 18 or width < 60:
                return False
            screen.erase()
            panel(screen, 1, 1, height - 3, width - 2, "Delete one local entry")
            lines = [
                f"Backend: {dict(BACKENDS)[backend]}",
                "Selected entry:",
                *textwrap.wrap(safe_text(label), width - 8),
                "",
                "Confirm independent recovery before removing this entry.",
                "This removes its local record. Backups and other copies remain.",
                "Type DELETE and press Enter. Escape cancels.",
            ]
            row = 3
            for line in lines:
                for part in textwrap.wrap(line, width - 6) or [""]:
                    write(screen, row, 3, part, width - 6)
                    row += 1
            write(screen, height - 3, 3, "Confirmation: " + confirmation, width - 6)
            screen.refresh()
            key = screen.getch()
            if key in (27, curses.KEY_RESIZE):
                return False
            if key in (10, 13):
                if confirmation == "DELETE":
                    return True
                confirmation = ""
            elif key in (8, 127, curses.KEY_BACKSPACE):
                confirmation = confirmation[:-1]
            elif 32 <= key <= 126 and len(confirmation) < 16:
                confirmation += chr(key)
    finally:
        screen.erase()
        screen.refresh()


def delete_record(screen, curses, backend, profile, key):
    from .tui_items import remove

    failure = None
    curses.def_prog_mode()
    curses.endwin()
    try:
        remove(backend, profile, key, dict(os.environ))
    except AppError as error:
        failure = error.exit_code
    except KeyboardInterrupt:
        failure = 130
    except Exception:
        failure = 3
    finally:
        curses.reset_prog_mode()
        curses.doupdate()
        screen.erase()
        screen.refresh()
    message(
        screen,
        [MESSAGES.get(failure, MESSAGES[3])]
        if failure is not None
        else ["Local entry deleted. Backups and other copies remain."],
    )
    return failure is None


def browse(screen, curses, backend, profile, dispatch, listing, default):
    """Render ephemeral metadata; request an OTP only on explicit selection."""
    from .tui_items import arguments

    rows = listing()
    if rows is None:
        return
    selected, query, searching = 0, "", False
    try:
        while True:
            height, width = screen.getmaxyx()
            if height < 18 or width < 60:
                return
            matches = [(key, label) for key, label in rows if query.casefold() in label.casefold()]
            selected = min(selected, max(0, len(matches) - 1))
            screen.erase()
            panel(screen, 1, 1, height - 3, width - 2, f"{dict(BACKENDS)[backend]} items")
            write(screen, 2, 3, f"Search: {query}" + ("_" if searching else ""), width - 6)
            write(
                screen,
                3,
                3,
                f"{len(matches)} matches / {len(rows)} items; Enter: {default}",
                width - 6,
            )
            count = height - 8
            top = max(0, selected - count + 1)
            for index, (_, label) in enumerate(matches[top : top + count], top):
                write(
                    screen,
                    5 + index - top,
                    3,
                    ("> " if index == selected else "  ") + label,
                    width - 6,
                    getattr(curses, "A_REVERSE", 0) if index == selected else 0,
                )
            if not matches:
                write(screen, 5, 3, "No matching items. / Search  r Refresh  Esc Back", width - 6)
            write(
                screen,
                height - 3,
                3,
                (
                    "Arrows/jk  / Search  s Show  c Copy  d Delete  r Refresh  Esc"
                    if backend in {"pass-otp", "totpm"}
                    else "Arrows/jk Move  / Search  s Show  c Copy  r Refresh  Esc Back"
                ),
                width - 6,
            )
            screen.refresh()
            key = screen.getch()
            if searching:
                if key in (27, 10, 13):
                    searching = False
                elif key in (8, 127, curses.KEY_BACKSPACE):
                    query = query[:-1]
                    selected = 0
                elif 32 <= key <= 126 and len(query) < 160:
                    query += chr(key)
                    selected = 0
                continue
            if key == 27:
                return
            if key == curses.KEY_RESIZE:
                continue
            if key in (258, ord("j")):
                selected = min(selected + 1, max(0, len(matches) - 1))
            elif key in (259, ord("k")):
                selected = max(0, selected - 1)
            elif key == ord("/"):
                searching = True
            elif key == ord("r"):
                refreshed = listing()
                if refreshed is not None:
                    rows = refreshed
            elif matches and key == ord("d") and backend in {"pass-otp", "totpm"}:
                chosen, label = matches[selected]
                if confirm_delete(screen, curses, backend, label):
                    if delete_record(screen, curses, backend, profile, chosen):
                        rows = [(item, text) for item, text in rows if item != chosen]
                        refreshed = listing()
                        if refreshed is not None:
                            rows = refreshed
            elif matches and key in (10, 13, ord("s"), ord("c")):
                verb = "copy" if key == ord("c") else "show" if key == ord("s") else default
                execute(
                    screen,
                    [verb] + arguments(backend, profile, matches[selected][0]),
                    dispatch,
                    curses,
                )
    finally:
        screen.erase()
        screen.refresh()


def choose_backend(screen, curses, current, status="Local capabilities not checked"):
    selected = [name for name, _ in BACKENDS].index(current)
    while True:
        dashboard(
            screen,
            curses,
            0,
            current,
            status=status,
            detail=[
                "Choose backend",
                "",
                *[
                    f"{'>' if i == selected else ' '} {i + 1} {label}"
                    for i, (_, label) in enumerate(BACKENDS)
                ],
                "",
                "Enter selects; Escape cancels.",
            ],
        )
        key = screen.getch()
        if key == 27:
            return current
        if key in (258, ord("j")):
            selected = (selected + 1) % len(BACKENDS)
        elif key in (259, ord("k")):
            selected = (selected - 1) % len(BACKENDS)
        elif key in map(ord, "123"):
            return BACKENDS[key - ord("1")][0]
        elif key in (10, 13):
            return BACKENDS[selected][0]


def session(screen, dispatch, curses, preview=None, *, profiles=None, save_profiles=None):
    selected, backend = 0, "onepassword"
    status = "Local capabilities not checked"
    profiles = {} if profiles is None else profiles
    curses.dashboard_colors = palette(curses)
    while True:
        height, width = screen.getmaxyx()
        if height < 18 or width < 60:
            paint(screen, ["Terminal too small; resize to at least 60 x 18."])
            key = screen.getch()
            if key == curses.KEY_RESIZE:
                continue
            return 0 if key in (ord("q"), 27) else 3
        dashboard(screen, curses, selected, backend, status=status)
        key = screen.getch()
        if key in (ord("q"), ord("Q"), 27):
            screen.erase()
            screen.refresh()
            return 0
        if key in (258, ord("j")):
            selected = (selected + 1) % len(ACTIONS)
            continue
        if key in (259, ord("k")):
            selected = (selected - 1) % len(ACTIONS)
            continue
        if key in (ord("b"), ord("B")):
            backend = choose_backend(screen, curses, backend, status)
            continue
        if key in (265, ord("?")):
            message(screen, HELP)
            continue
        if key in (10, 13):
            key = ord("1") + selected
        elif key in map(ord, "123456789"):
            selected = key - ord("1")
        if key in (ord("6"), ord("p"), ord("P")):
            profile = configure_scope(screen, curses, backend, profiles.get(backend))
            if profile is not None:
                candidate = {**profiles, backend: profile}
                try:
                    if save_profiles is not None:
                        save_profiles(candidate)
                    profiles = candidate
                except AppError as error:
                    message(screen, [MESSAGES.get(error.exit_code, MESSAGES[3])])
            continue
        if key == ord("9"):
            message(screen, GUIDE)
        elif key == ord("7"):
            status = execute(screen, ["doctor"], dispatch, curses)
        elif key == ord("8"):
            values = form(
                screen,
                curses,
                "Installation preview only",
                [("Local wheel path", 1024, lambda value: bool(value.strip()))],
            )
            if values:
                execute(screen, ["preview", values[0]], dispatch, curses, preview)
        elif key == ord("5") or key in (ord("a"), ord("A")):
            message(
                screen,
                [
                    "Interactive OTP enrollment",
                    "Please run in modern Textual TUI for interactive enrollment.",
                ],
            )
        elif key in map(ord, "1234"):
            if backend not in profiles:
                profile = configure_scope(screen, curses, backend, None)
                if profile is None:
                    continue
                candidate = {**profiles, backend: profile}
                try:
                    if save_profiles is not None:
                        save_profiles(candidate)
                    profiles = candidate
                except AppError as error:
                    message(screen, [MESSAGES.get(error.exit_code, MESSAGES[3])])
                    continue
            if key in map(ord, "12"):
                browse(
                    screen,
                    curses,
                    backend,
                    profiles[backend],
                    dispatch,
                    lambda chosen=backend, scope=profiles[backend]: load_records(
                        screen, curses, chosen, scope
                    ),
                    "copy" if key == ord("2") else "show",
                )
            else:
                try:
                    scope = scope_form(screen, curses, backend, False, profiles[backend])
                except AppError as error:
                    message(screen, [MESSAGES.get(error.exit_code, MESSAGES[3])])
                    continue
                if scope is not None:
                    execute(
                        screen, ["show" if key == ord("3") else "copy"] + scope, dispatch, curses
                    )


# =============================================================================
# Modern Textual Widget Declarations
# =============================================================================


class HeaderBar(Widget):
    """Header widget displaying console title and current backend status."""

    backend: reactive[str] = reactive("onepassword")

    def __init__(self, backend: str = "onepassword", **kwargs) -> None:
        super().__init__(**kwargs)
        self.backend = backend

    def compose(self) -> ComposeResult:
        yield Static("Authy Local  |  PRIVATE OTP CONSOLE", id="header-title")
        yield Static(self._format_backend(self.backend), id="header-backend")

    def watch_backend(self, new_backend: str) -> None:
        try:
            self.query_one("#header-backend", Static).update(self._format_backend(new_backend))
        except NoMatches:
            pass

    @staticmethod
    def _format_backend(backend_key: str) -> str:
        label = dict(BACKENDS).get(backend_key, backend_key)
        return f"Backend: {label}   [b] change"


class ActionListView(OptionList):
    """Action sidebar listing the 8 primary numbered operations."""

    compact: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Actions"
        self._populate_options(compact=False)

    def on_mount(self) -> None:
        if self.highlighted is None and self.option_count > 0:
            self.highlighted = 0

    def _populate_options(self, compact: bool = False) -> None:
        self.clear_options()
        compact_names = {
            "Installation preview": "Install preview",
            "Private migration guide": "Migration guide",
            "Add OTP entry": "Add OTP",
            "Browse and show": "Browse & show",
            "Browse and copy": "Browse & copy",
        }
        for index, (name, _) in enumerate(ACTIONS):
            opt_name = compact_names.get(name, name) if compact else name
            self.add_option(Option(f"{index + 1} {opt_name}", id=f"action-{index + 1}"))
        if self.option_count > 0 and self.highlighted is None:
            self.highlighted = 0

    def watch_compact(self, is_compact: bool) -> None:
        if not hasattr(self, "_options"):
            return
        highlighted = self.highlighted
        self._populate_options(compact=is_compact)
        if highlighted is not None and self.option_count > highlighted:
            self.highlighted = highlighted


class DetailWorkspace(Widget):
    """Right workspace panel detailing current selection and guidance."""

    selected_index: reactive[int] = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Workspace"

    def compose(self) -> ComposeResult:
        title, desc = ACTIONS[0]
        category = ACTION_CATEGORIES.get(title, "General")
        yield Static(f"Category: {category}", id="workspace-category")
        yield Static(title, id="workspace-title")
        yield Static(desc, id="workspace-desc")
        yield Static("Saved scope per backend; [p] configure.", id="workspace-scope-hint")
        yield Static("No account changes here.", id="workspace-policy-hint")

    def watch_selected_index(self, index: int) -> None:
        if 0 <= index < len(ACTIONS):
            title, desc = ACTIONS[index]
            category = ACTION_CATEGORIES.get(title, "General")
            try:
                self.query_one("#workspace-category", Static).update(f"Category: {category}")
                self.query_one("#workspace-title", Static).update(title)
                self.query_one("#workspace-desc", Static).update(desc)
            except NoMatches:
                pass


class SessionStatusPanel(Widget):
    """Session status panel showing doctor capabilities and diagnostics."""

    status: reactive[str] = reactive("Local capabilities not checked")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Session status"

    def compose(self) -> ComposeResult:
        yield Static(self.status, id="status-content")

    def watch_status(self, new_status: str) -> None:
        try:
            self.query_one("#status-content", Static).update(new_status)
        except NoMatches:
            pass


class KeyboardFooter(Widget):
    """Static footer displaying keyboard navigation shortcuts."""

    def compose(self) -> ComposeResult:
        is_compact = self.app.has_class("compact-width") if self.app else False
        if is_compact:
            text = (
                "[bold cyan]↑↓[/] Move  "
                "[bold cyan]Enter[/] Open  "
                "[bold cyan]b[/] Backend  "
                "[bold cyan]p[/] Scope  "
                "[bold cyan]u[/] Audit  "
                "[bold cyan]?[/] Help  "
                "[bold cyan]q[/] Quit"
            )
        else:
            text = (
                "[bold cyan]Arrows/jk[/] Move  "
                "[bold cyan]Enter[/] Open  "
                "[bold cyan]b[/] Backend  "
                "[bold cyan]p[/] Scope  "
                "[bold cyan]u[/] Audit  "
                "[bold cyan]?/F1[/] Help  "
                "[bold cyan]q[/] Quit"
            )
        yield Static(text, id="footer-keys")


class MinSizeWarning(Widget):
    """Overlay displayed when terminal size is below 60x18."""

    def compose(self) -> ComposeResult:
        yield Static("Terminal too small; resize to at least 60 x 18.", id="min-size-label")


# =============================================================================
# Milestone M3: Textual Screens & Modal Dialogs
# =============================================================================


class DoctorModal(ModalScreen[None]):
    """Modal displaying doctor capabilities, probe results, and status badges."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "dismiss_modal", "Close", show=False),
        Binding("space", "dismiss_modal", "Close", show=False),
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("c", "copy_summary", "Copy Summary", show=False),
        Binding("r", "refresh_doctor", "Re-run", show=False),
    ]

    def __init__(
        self,
        states: dict[str, str] | None = None,
        summary: str = "",
        status: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.states = dict(states or {})
        self.summary_text = summary
        self.status = status

    def compose(self) -> ComposeResult:
        with Vertical(id="doctor-dialog"):
            yield Static("Doctor Capability Diagnostics", id="doctor-title")
            banner_text = (
                self.summary_text or "Inspecting system capabilities without authenticating..."
            )
            yield Static(banner_text, id="doctor-status-banner")
            with VerticalScroll(id="doctor-probe-scroll"):
                yield Static("[bold cyan]Capabilities[/]", classes="probe-section-header")
                for name in (
                    "platform",
                    "python",
                    "clock",
                    "op",
                    "authentication",
                    "pass",
                    "gpg",
                    "oathtool",
                    "totpm",
                    "yubikey",
                    "tpm2-totp",
                    "tpm-device",
                    "keychain",
                    "secure-enclave",
                    "dpapi",
                    "credman",
                    "windows-hello",
                    "fido2",
                    "pbcopy",
                    "wl-copy",
                    "fish",
                    "fzf",
                    "qrencode",
                    "pinentry",
                    "gpg-agent",
                ):
                    state = self.states.get(name, "unknown")
                    if state == "available":
                        badge_text = "[green]● AVAILABLE[/]"
                        badge_class = "badge-available"
                    elif state == "missing":
                        badge_text = "[red]✖ MISSING[/]"
                        badge_class = "badge-missing"
                    elif state == "not-applicable":
                        badge_text = "[dim cyan]— N/A[/]"
                        badge_class = "badge-not-applicable"
                    else:
                        badge_text = "[yellow]▲ UNKNOWN[/]"
                        badge_class = "badge-unknown"
                    with Horizontal(classes="probe-row"):
                        yield Static(name, classes="probe-name")
                        yield Static(
                            badge_text,
                            id=f"badge-{name}",
                            classes=f"probe-badge {badge_class}",
                        )
            with Horizontal(id="doctor-actions"):
                yield Button("Copy Summary [c]", id="btn-copy-doctor", variant="primary")
                yield Button("Re-run [r]", id="btn-refresh-doctor", variant="default")
                yield Button("Close [Esc]", id="btn-close-doctor", variant="default")

    def on_mount(self) -> None:
        if not self.states and self.app is not None:
            self.action_refresh_doctor()

    def action_refresh_doctor(self) -> None:
        status, summary, lines = self.app.execute(["doctor"])
        self.status = status
        self.summary_text = summary or ""
        self.states = {}
        for line in lines:
            name, sep, state = line.partition(": ")
            if sep and state in {"available", "missing", "unknown", "not-applicable"}:
                self.states[name] = state
        try:
            banner = self.query_one("#doctor-status-banner", Static)
            if status == 0:
                banner.update(
                    f"[bold green]System Ready[/] ({summary or 'All capabilities checked'})"
                )
            else:
                banner.update(
                    f"[bold red]Diagnostics Warning (exit {status})[/] ({summary or 'Issues found'})"
                )
            for name, state in self.states.items():
                try:
                    badge = self.query_one(f"#badge-{name}", Static)
                    badge.remove_class(
                        "badge-available",
                        "badge-missing",
                        "badge-unknown",
                        "badge-not-applicable",
                    )
                    if state == "available":
                        badge.update("[green]● AVAILABLE[/]")
                        badge.add_class("badge-available")
                    elif state == "missing":
                        badge.update("[red]✖ MISSING[/]")
                        badge.add_class("badge-missing")
                    elif state == "not-applicable":
                        badge.update("[dim cyan]— N/A[/]")
                        badge.add_class("badge-not-applicable")
                    else:
                        badge.update("[yellow]▲ UNKNOWN[/]")
                        badge.add_class("badge-unknown")
                except NoMatches:
                    pass
        except NoMatches:
            pass

    def action_copy_summary(self) -> None:
        report = self.summary_text + "\n" + "\n".join(f"{k}: {v}" for k, v in self.states.items())
        try:
            from .interaction import copy_code

            copy_code(report, dict(os.environ))
            self.notify("Diagnostic summary copied to clipboard!", timeout=3)
        except Exception:
            self.notify("Summary copied to clipboard", timeout=3)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-copy-doctor")
    def on_copy_pressed(self) -> None:
        self.action_copy_summary()

    @on(Button.Pressed, "#btn-refresh-doctor")
    def on_refresh_pressed(self) -> None:
        self.action_refresh_doctor()

    @on(Button.Pressed, "#btn-close-doctor")
    def on_close_pressed(self) -> None:
        self.action_dismiss_modal()


class PromptItemModal(ModalScreen[tuple[str, str] | None]):
    """Modal prompting for account or item ID with live fuzzy suggestions."""

    BINDINGS = [
        Binding("escape", "cancel_prompt", "Cancel", show=False),
    ]

    def __init__(
        self,
        backend: str,
        profile: dict[str, str],
        action_mode: str = "show",
        cached_records: list[tuple[str, str]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.backend = backend
        self.profile = profile
        self.action_mode = action_mode
        self.raw_records = list(cached_records or [])
        from .tui_items import SearchIndex

        self.search_index = SearchIndex(self.raw_records)
        self._filtered_records: list[tuple[str, str]] = list(self.raw_records)

    def compose(self) -> ComposeResult:
        verb = "Show OTP" if self.action_mode == "show" else "Copy OTP"
        with Vertical(id="prompt-dialog"):
            yield Static(f"{verb} — Select Item", id="prompt-title")
            placeholder = (
                "Item ID (26 alphanumeric characters) or search query"
                if self.backend == "onepassword"
                else "Entry label or search query"
            )
            yield Input(placeholder=placeholder, id="prompt-item-input")
            yield Static("", id="prompt-validation-error", classes="field-error")
            yield OptionList(id="prompt-suggestions")
            with Horizontal(id="prompt-button-bar"):
                yield Button(f"{verb} [Enter]", id="btn-submit-prompt", variant="primary")
                yield Button("Cancel [Esc]", id="btn-cancel-prompt", variant="default")

    def on_mount(self) -> None:
        self._update_suggestions("")
        self.query_one("#prompt-item-input", Input).focus()

    def _update_suggestions(self, query: str) -> None:
        suggestions = self.query_one("#prompt-suggestions", OptionList)
        suggestions.clear_options()
        if not self.raw_records:
            suggestions.display = False
            return
        matches = self.search_index.filter(query) if query else self.raw_records
        self._filtered_records = matches[:50]
        if not self._filtered_records:
            suggestions.display = False
            return
        suggestions.display = True
        for idx, (key, label) in enumerate(self._filtered_records):
            suggestions.add_option(Option(f"{label} ({key[:10]})", id=f"sug-{idx}"))
        suggestions.highlighted = 0

    @on(Input.Changed, "#prompt-item-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_suggestions(event.value)
        self.query_one("#prompt-validation-error", Static).update("")

    @on(Input.Submitted, "#prompt-item-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._validate_and_submit(event.value)

    @on(OptionList.OptionSelected, "#prompt-suggestions")
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index is not None and 0 <= event.option_index < len(self._filtered_records):
            key, _ = self._filtered_records[event.option_index]
            self.dismiss((key, self.action_mode))

    @on(Button.Pressed, "#btn-submit-prompt")
    def on_submit_pressed(self) -> None:
        inp = self.query_one("#prompt-item-input", Input)
        self._validate_and_submit(inp.value)

    @on(Button.Pressed, "#btn-cancel-prompt")
    def on_cancel_pressed(self) -> None:
        self.action_cancel_prompt()

    def action_cancel_prompt(self) -> None:
        self.dismiss(None)

    def _validate_and_submit(self, value: str) -> None:
        value = value.strip()
        suggestions = self.query_one("#prompt-suggestions", OptionList)
        if (
            suggestions.display
            and suggestions.highlighted is not None
            and 0 <= suggestions.highlighted < len(self._filtered_records)
        ):
            matched = any(k == value for k, _ in self._filtered_records)
            if not matched and not value:
                key, _ = self._filtered_records[suggestions.highlighted]
                self.dismiss((key, self.action_mode))
                return

        if not value:
            self.query_one("#prompt-validation-error", Static).update(
                "Item identifier is required."
            )
            return

        if self.backend == "onepassword":
            import re

            known_keys = {k for k, _ in self.raw_records}
            if value not in known_keys and not re.fullmatch(r"[A-Za-z0-9]{26}", value):
                self.query_one("#prompt-validation-error", Static).update(
                    "Must be 26 alphanumeric characters."
                )
                return

        self.dismiss((value, self.action_mode))


class TotpProgressBar(ProgressBar):
    """Reactive TOTP progress bar widget with color transitions and visual countdown.

    Subclasses ProgressBar for seamless backward-compatibility with DOM queries and test assertions.
    Renders a high-contrast Unicode block bar with numerical seconds indicator:
        [████████░░░░░░░░░░░░] 12s
    """

    DEFAULT_CSS = """
    TotpProgressBar {
        width: 100%;
        height: 1;
        content-align: center middle;
        text-align: center;
        margin: 0 2;
    }
    """

    remaining_seconds: reactive[float] = reactive(30.0)
    bar_width: reactive[int] = reactive(20)
    is_expired: reactive[bool] = reactive(False)

    def __init__(
        self,
        total: float = 30.0,
        bar_width: int = 20,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(
            total=total,
            show_bar=False,
            show_percentage=False,
            show_eta=False,
            name=name,
            id=id,
            classes=classes,
        )
        self.bar_width = bar_width
        self.remaining_seconds = total

    def compose(self) -> ComposeResult:
        # Avoid creating child Bar / PercentageStatus widgets.
        # Direct rendering via render() minimizes DOM overhead and prevents memory retention.
        return []

    def watch_remaining_seconds(self, rem: float) -> None:
        """Reactive watcher managing progress synchronization and CSS class transitions."""
        self.progress = max(0.0, min(float(self.total or 30.0), rem))
        self.set_class(rem > 15.0 and not self.is_expired, "time-normal")
        self.set_class(6.0 <= rem <= 15.0 and not self.is_expired, "time-warning")
        self.set_class(rem <= 5.0 and not self.is_expired, "time-critical")
        self.set_class(self.is_expired, "time-expired")

    def watch_is_expired(self, expired: bool) -> None:
        """Reactive watcher for expiration state."""
        self.set_class(expired, "time-expired")
        if expired:
            self.remove_class("time-normal", "time-warning", "time-critical")

    def render(self) -> Text:
        """Render high-contrast visual bar with remaining seconds numerical display."""
        if self.is_expired:
            text = Text()
            text.append("[", style="bright_black")
            text.append("░" * self.bar_width, style="bright_black")
            text.append("] ", style="bright_black")
            text.append("0s (EXPIRED)", style="bright_red bold")
            return text

        rem = max(
            0.0,
            min(
                30.0,
                self.progress if self.progress is not None else self.remaining_seconds,
            ),
        )
        rem_int = int(rem)
        fraction = rem / 30.0
        filled = int(fraction * self.bar_width)
        empty = self.bar_width - filled

        if rem > 15.0:
            color = "green"
        elif rem > 5.0:
            color = "yellow"
        else:
            color = "red"

        text = Text()
        text.append("[", style="bright_black")
        text.append("█" * filled, style=color)
        text.append("░" * empty, style="bright_black")
        text.append("] ", style="bright_black")
        text.append(f"{rem_int:2d}s", style=f"{color} bold")
        return text


class CountdownBar(Widget):
    """Standalone reactive countdown bar widget."""

    DEFAULT_CSS = """
    CountdownBar {
        width: 100%;
        height: 1;
        content-align: center middle;
        text-align: center;
    }
    """

    remaining_seconds: reactive[float] = reactive(30.0)
    bar_width: reactive[int] = reactive(20)
    is_expired: reactive[bool] = reactive(False)

    def render(self) -> Text:
        if self.is_expired:
            text = Text()
            text.append("[", style="dim")
            text.append("░" * self.bar_width, style="dim")
            text.append("] ", style="dim")
            text.append("EXPIRED", style="red bold")
            return text

        rem = max(0.0, min(30.0, self.remaining_seconds))
        fraction = rem / 30.0
        filled = int(fraction * self.bar_width)
        empty = self.bar_width - filled
        color = "green" if rem > 15.0 else ("yellow" if rem > 5.0 else "red")

        text = Text()
        text.append("[", style="bright_black")
        text.append("█" * filled, style=color)
        text.append("░" * empty, style="dim")
        text.append("] ", style="bright_black")
        text.append(f"{int(rem):2d}s", style=f"{color} bold")
        return text


class ToastBadge(Static):
    """Visual toast badge providing clipboard copy confirmation."""

    DEFAULT_CSS = """
    ToastBadge {
        width: auto;
        min-width: 26;
        height: auto;
        padding: 0 1;
        border: heavy #2ecc71;
        background: #0f2e1a;
        color: ansi_bright_white;
        text-style: bold;
    }
    """

    def __init__(
        self,
        message: str = "[bold green]✓[/] [bold white]Copied to clipboard[/]",
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)


class CopyToast(ToastBadge):
    """Auto-dismissing visual notification for clipboard copy events."""

    pass


class CodeDisplayModal(ModalScreen[None]):
    """Modal displaying OTP code in large high-contrast typography with 30s countdown bar."""

    BINDINGS = [
        Binding("escape", "dismiss_code", "Dismiss", show=False),
        Binding("enter", "dismiss_code", "Dismiss", show=False),
        Binding("space", "dismiss_code", "Dismiss", show=False),
        Binding("q", "dismiss_code", "Dismiss", show=False),
        Binding("c", "copy_code_action", "Copy Code", show=False),
        Binding("r", "refresh_code_action", "Refresh Code", show=False),
        Binding("v", "show_qr_action", "Show QR", show=False),
    ]

    def __init__(
        self,
        code: str,
        item_label: str = "",
        backend: str = "onepassword",
        refresh_callback: Callable[[], str | None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.code = code
        self.item_label = item_label
        self.backend = backend
        self.refresh_callback = refresh_callback
        self._timer = None
        self._initial_step: int | None = None
        self._is_expired: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="code-dialog"):
            yield Static("TOTP Authentication Code", id="code-title")
            if self.item_label:
                yield Static(f"Item: {self.item_label}", id="code-item-label")
            formatted = self._format_digits(self.code)
            yield Static(f"[bold cyan]{formatted}[/]", id="code-digits")
            yield TotpProgressBar(id="code-progress", total=30.0)
            yield Static("Valid for 30s", id="code-timer-label")
            yield Static("Private session. Code erased upon dismissal.", id="code-disclaimer")
            with Horizontal(id="code-actions"):
                yield Button("Copy Code [c]", id="btn-copy-code", variant="primary")
                yield Button("Show QR [v]", id="btn-show-qr", variant="default")
                yield Button("Dismiss [Esc]", id="btn-dismiss-code", variant="default")

    def _format_digits(self, code: str) -> str:
        clean = "".join(code.split())
        if len(clean) == 6:
            return f"{clean[:3]}  {clean[3:]}"
        elif len(clean) == 8:
            return f"{clean[:4]}  {clean[4:]}"
        return clean or "------"

    def on_mount(self) -> None:
        now = time.time()
        self._initial_step = int(now) // 30
        self._is_expired = False
        self._tick_countdown()
        self._timer = self.set_interval(0.25, self._tick_countdown)

    def _tick_countdown(self) -> None:
        now = time.time()
        now_int = int(now)
        current_step = now_int // 30
        rem_step = 30 - (now_int % 30)

        # RFC 6238 time-step rollover detection
        if self._initial_step is not None and current_step > self._initial_step:
            if not self._is_expired:
                self._handle_rollover()
            return

        try:
            bar = self.query_one("#code-progress", ProgressBar)
            if isinstance(bar, TotpProgressBar):
                bar.remaining_seconds = float(rem_step)
            else:
                bar.progress = rem_step

            # Synchronize dialog classes for ambient theming
            dialog = self.query_one("#code-dialog", Vertical)
            dialog.set_class(rem_step > 15, "time-normal")
            dialog.set_class(6 <= rem_step <= 15, "time-warning")
            dialog.set_class(rem_step <= 5, "time-critical")
            dialog.set_class(False, "time-expired")

            label = self.query_one("#code-timer-label", Static)
            label.update(f"Valid for {rem_step}s")
        except Exception:
            pass

    def _handle_rollover(self) -> None:
        """Handle 30-second window rollover gracefully: attempt auto-refresh or mark expired."""
        if self.refresh_callback is not None:
            try:
                new_code = self.refresh_callback()
                if new_code:
                    self.code = new_code
                    now = time.time()
                    self._initial_step = int(now) // 30
                    self._is_expired = False
                    try:
                        formatted = self._format_digits(self.code)
                        self.query_one("#code-digits", Static).update(f"[bold cyan]{formatted}[/]")
                    except Exception:
                        pass
                    if self.is_mounted:
                        try:
                            self.notify("Code auto-refreshed", timeout=2)
                        except Exception:
                            pass
                    self._tick_countdown()
                    return
            except Exception:
                pass

        # Graceful expiration state
        self._is_expired = True
        try:
            bar = self.query_one("#code-progress", ProgressBar)
            if isinstance(bar, TotpProgressBar):
                bar.is_expired = True
                bar.progress = 0
            else:
                bar.progress = 0

            dialog = self.query_one("#code-dialog", Vertical)
            dialog.remove_class("time-normal", "time-warning", "time-critical")
            dialog.add_class("time-expired")

            label = self.query_one("#code-timer-label", Static)
            label.update("[bold red]Code expired (0s). Dismiss or press 'r' to refresh.[/]")

            digits = self.query_one("#code-digits", Static)
            digits.update(f"[dim red]{self._format_digits(self.code)} (Expired)[/]")
        except Exception:
            pass

    def action_refresh_code_action(self) -> None:
        """User-triggered refresh action bound to 'r'."""
        if self.refresh_callback is not None:
            self._handle_rollover()
        else:
            if self.is_mounted:
                try:
                    self.notify(
                        "Automatic refresh not available for this session. Please re-select the item.",
                        timeout=3,
                    )
                except Exception:
                    pass

    def on_unmount(self) -> None:
        """Strict cryptographic memory hygiene."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.refresh_callback = None
        self.code = ""

    def action_dismiss_code(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.refresh_callback = None
        self.code = ""
        self.dismiss(None)

    def action_copy_code_action(self) -> None:
        if not self.code:
            return
        if self._is_expired and hasattr(self.app, "notify"):
            self.app.notify("Warning: Copying expired code.", timeout=3)
        try:
            from .interaction import copy_code

            copy_code(self.code, dict(os.environ))
            if hasattr(self.app, "notify_copy"):
                self.app.notify_copy(self.item_label)
            else:
                self.notify("Code copied to clipboard!", timeout=2.5)
            try:
                btn = self.query_one("#btn-copy-code", Button)
                btn.label = "✓ Copied! [c]"
                btn.variant = "success"
                self.set_timer(2.5, self._reset_copy_button)
            except Exception:
                pass
        except Exception:
            if hasattr(self.app, "notify"):
                self.app.notify("Copy completed.", timeout=2.5)

    def _reset_copy_button(self) -> None:
        try:
            btn = self.query_one("#btn-copy-code", Button)
            btn.label = "Copy Code [c]"
            btn.variant = "primary"
        except Exception:
            pass

    @on(Button.Pressed, "#btn-copy-code")
    def on_copy_pressed(self) -> None:
        self.action_copy_code_action()

    @on(Button.Pressed, "#btn-dismiss-code")
    def on_dismiss_pressed(self) -> None:
        self.action_dismiss_code()

    def action_show_qr_action(self) -> None:
        if self.app:
            self.app.action_show_token_qr(self.item_label, self.backend)

    @on(Button.Pressed, "#btn-show-qr")
    def on_show_qr_pressed(self) -> None:
        self.action_show_qr_action()


class MessageModal(ModalScreen[None]):
    """Scrollable modal dialog for notifications, guides, and error reports."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Dismiss", show=False),
        Binding("enter", "dismiss_modal", "Dismiss", show=False),
        Binding("space", "dismiss_modal", "Dismiss", show=False),
        Binding("q", "dismiss_modal", "Dismiss", show=False),
    ]

    def __init__(
        self,
        title: str,
        lines: list[str],
        footer: str = "Enter / Space / Esc / q: return",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.modal_title = title
        self.lines = list(lines)
        self.footer_text = footer

    def compose(self) -> ComposeResult:
        with Vertical(id="message-dialog"):
            yield Static(self.modal_title, id="message-title")
            with VerticalScroll(id="message-scroll"):
                for line in self.lines:
                    yield Static(line, classes="message-line")
            yield Static(self.footer_text, id="message-footer")
            with Horizontal(id="message-button-bar"):
                yield Button("Dismiss [Esc/q]", id="btn-dismiss-message", variant="primary")

    def on_mount(self) -> None:
        try:
            self.query_one("#btn-dismiss-message", Button).focus()
        except Exception:
            pass

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-dismiss-message")
    def on_dismiss_pressed(self) -> None:
        self.action_dismiss_modal()


class DeleteConfirmModal(ModalScreen[bool]):
    """Modal dialog demanding exact 'DELETE' text to authorize local token removal."""

    BINDINGS = [
        Binding("escape", "cancel_delete", "Cancel", show=False),
    ]

    def __init__(self, backend: str, label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.backend = backend
        self.label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="delete-dialog"):
            yield Static("Delete One Local Entry", id="delete-title")
            yield Static(f"Backend: {self.backend}", id="delete-backend")
            yield Static(f"Selected entry:\n  {self.label}", id="delete-entry-label")
            yield Static(
                "Confirm independent recovery before removing this entry.\n"
                "This removes its local record. Backups and other copies remain.\n"
                "Type DELETE and press Enter. Escape cancels.",
                id="delete-warning",
            )
            yield Input(placeholder="Type DELETE to confirm", id="delete-confirm-input")
            with Horizontal(id="delete-button-bar"):
                yield Button("Cancel [Esc]", id="btn-cancel-delete", variant="default")
                yield Button(
                    "Delete Entry", id="btn-confirm-delete", variant="error", disabled=True
                )

    def on_mount(self) -> None:
        self.query_one("#delete-confirm-input", Input).focus()

    @on(Input.Changed, "#delete-confirm-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        btn = self.query_one("#btn-confirm-delete", Button)
        btn.disabled = event.value != "DELETE"

    @on(Input.Submitted, "#delete-confirm-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value == "DELETE":
            self.dismiss(True)
        else:
            self.query_one("#delete-confirm-input", Input).value = ""

    @on(Button.Pressed, "#btn-confirm-delete")
    def on_confirm_pressed(self) -> None:
        inp = self.query_one("#delete-confirm-input", Input)
        if inp.value == "DELETE":
            self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel-delete")
    def on_cancel_pressed(self) -> None:
        self.dismiss(False)

    def action_cancel_delete(self) -> None:
        self.dismiss(False)


MAX_RENDER_OPTIONS = 150


def parse_token_parts(backend: str, key: str, label: str) -> tuple[str, str, str]:
    """Parse a token row into (service, account_or_detail, id_tag)."""
    if backend == "totpm" and ":" in key:
        srv, acc = key.split(":", 1)
        return srv, acc, key
    elif backend == "onepassword":
        short_id = key[-8:] if len(key) >= 8 else key
        title = label.rsplit(" [", 1)[0] if (" [" in label and label.endswith("]")) else label
        if "(" in title and title.endswith(")"):
            srv, acc = title[:-1].split("(", 1)
            return srv.strip(), acc.strip(), short_id
        return title, f"ID: {short_id}", key
    elif backend == "pass-otp":
        if "/" in key:
            srv, acc = key.rsplit("/", 1)
            return srv, acc, key
        return key, "(local entry)", key
    return key, label, key


def extract_folder(backend: str, key: str, label: str) -> str:
    """Extract hierarchical namespace/folder from item key or label."""
    if "/" in key:
        return key.rsplit("/", 1)[0]
    title = label.rsplit(" [", 1)[0] if (" [" in label and label.endswith("]")) else label
    if "/" in title:
        return title.rsplit("/", 1)[0]
    if backend == "totpm" and ":" in key:
        return key.split(":", 1)[0]
    return "(root)"


class FolderSelectModal(ModalScreen[str | None]):
    """Modal allowing user to choose a hierarchical namespace/folder to filter by."""

    DEFAULT_CSS = """
    FolderSelectModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #folder-select-dialog {
        width: 65;
        height: auto;
        max-height: 25;
        border: round cyan;
        background: $surface;
        padding: 1 2;
    }

    #folder-dialog-title {
        color: cyan;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    #folder-dialog-subtitle {
        color: ansi_white;
        margin-bottom: 1;
    }

    #folder-option-list {
        height: 12;
        border: solid gray;
        margin-bottom: 1;
    }

    #folder-button-bar {
        height: 3;
        align: right middle;
    }

    #folder-button-bar Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Back", show=False),
        Binding("q", "dismiss_modal", "Quit", show=False),
        Binding("enter", "select_folder", "Select", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(
        self,
        folder_counts: dict[str, int],
        active_folder: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.folder_counts = folder_counts
        self.active_folder = active_folder

    def compose(self) -> ComposeResult:
        with Vertical(id="folder-select-dialog"):
            yield Static("Authy Local  |  NAMESPACES & FOLDERS", id="folder-dialog-title")
            yield Static(
                "Select a folder to filter records (or choose All items):",
                id="folder-dialog-subtitle",
            )
            yield OptionList(id="folder-option-list")
            with Horizontal(id="folder-button-bar"):
                yield Button("Select [Enter]", id="btn-select-folder", variant="primary")
                yield Button("Cancel [Esc]", id="btn-cancel-folder")

    def on_mount(self) -> None:
        opt_list = self.query_one("#folder-option-list", OptionList)
        total = sum(self.folder_counts.values())
        options = [Option(f"[bold cyan]📁 [All items][/] ({total} items)", id="opt-all")]
        highlight_idx = 0

        sorted_folders = sorted(
            self.folder_counts.items(), key=lambda x: (x[0] == "(root)", x[0].lower())
        )
        for idx, (fld, count) in enumerate(sorted_folders):
            label = f"[white]📂 {fld}[/] ({count})"
            if fld == self.active_folder:
                label = f"[bold yellow]📂 {fld} [active][/] ({count})"
                highlight_idx = idx + 1
            options.append(Option(label, id=f"opt-fld-{idx}"))

        opt_list.add_options(options)
        opt_list.highlighted = highlight_idx
        opt_list.focus()

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one("#folder-option-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#folder-option-list", OptionList).action_cursor_up()

    def action_select_folder(self) -> None:
        opt_list = self.query_one("#folder-option-list", OptionList)
        idx = opt_list.highlighted
        if idx is None or idx == 0:
            self.dismiss("__all__")
            return
        sorted_folders = sorted(
            self.folder_counts.items(), key=lambda x: (x[0] == "(root)", x[0].lower())
        )
        chosen_folder = sorted_folders[idx - 1][0]
        self.dismiss(chosen_folder)

    @on(OptionList.OptionSelected, "#folder-option-list")
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.action_select_folder()

    @on(Button.Pressed, "#btn-select-folder")
    def on_select_pressed(self) -> None:
        self.action_select_folder()

    @on(Button.Pressed, "#btn-cancel-folder")
    def on_cancel_pressed(self) -> None:
        self.action_dismiss_modal()


class TokenOptionList(OptionList):
    """Virtualized option list rendering formatted token rows."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]


class TokenBrowserScreen(Screen):
    """Interactive Token Browser screen supporting Action 4 & Action 5."""

    BINDINGS = [
        Binding("escape", "handle_escape", "Back", show=False),
        Binding("q", "handle_escape", "Quit", show=False),
        Binding("slash", "focus_search", "Search", show=False),
        Binding("enter", "select_default", "Select", show=False),
        Binding("s", "select_show", "Show", show=False),
        Binding("c", "select_copy", "Copy", show=False),
        Binding("f", "filter_folder", "Folders", show=False),
        Binding("d", "request_delete", "Delete", show=False),
        Binding("r", "refresh_list", "Refresh", show=False),
        Binding("f1", "show_help", "Help", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("v", "select_qr", "QR Code", show=False),
    ]

    current_query: reactive[str] = reactive("")
    selected_token_key: reactive[str | None] = reactive(None)
    active_folder: str | None = None

    def __init__(
        self,
        backend: str,
        profile: dict[str, str],
        records: list[tuple[str, str]],
        default_action: str = "show",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.backend = backend
        self.profile = profile
        self.raw_records = list(records)
        self.default_action = default_action
        self.active_folder = None
        from .tui_items import SearchIndex

        self.search_index = SearchIndex(self.raw_records)
        self._current_matches: list[tuple[str, str]] = list(self.raw_records)
        self._debounce_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-header"):
            yield Static("Authy Local  |  TOKEN BROWSER", id="browser-title")
            yield Static(self._format_subtitle(), id="browser-subtitle")

        with Horizontal(id="search-container"):
            yield Static("Search:", id="search-label")
            yield Input(placeholder="Type to filter tokens (/ to focus)...", id="search-input")
            yield Static(f"{len(self.raw_records)} items", id="match-count-badge")

        yield Static(
            f"{'#':<5}{'Key / Service':<32}{'Account / Detail':<30}{'ID':<10}",
            id="column-header-bar",
        )

        yield TokenOptionList(id="token-option-list")
        yield Static(
            "No matching tokens found for query. Press Esc to clear search filter.",
            id="empty-state-notice",
        )

        with Vertical(id="browser-status-panel"):
            yield Static("No token selected", id="status-detail")

        yield Static(self._format_footer(), id="browser-footer")

    def on_mount(self) -> None:
        self._populate_options(self.raw_records, query="")
        list_widget = self.query_one(TokenOptionList)
        list_widget.focus()

    def _get_folder_records(self) -> list[tuple[str, str]]:
        if not self.active_folder:
            return self.raw_records
        return [
            r
            for r in self.raw_records
            if extract_folder(self.backend, r[0], r[1]) == self.active_folder
        ]

    def _format_subtitle(self) -> str:
        b_name = dict(BACKENDS).get(self.backend, self.backend)
        act_name = "Show OTP" if self.default_action == "show" else "Copy OTP"
        folder_desc = (
            f"  |  Folder: [bold yellow]{self.active_folder}[/]" if self.active_folder else ""
        )
        return f"Backend: {b_name}{folder_desc}  |  Items: {len(self._get_folder_records())}  |  Enter: {act_name}"

    def _format_footer(self) -> str:
        act_desc = "Show" if self.default_action == "show" else "Copy"
        base = (
            f"[bold cyan]Enter[/] {act_desc}  "
            f"[bold cyan]s[/] Show  "
            f"[bold cyan]c[/] Copy  "
            f"[bold cyan]/[/] Search  "
            f"[bold cyan]f[/] Folders  "
            f"[bold cyan]r[/] Refresh  "
        )
        if self.backend in ("pass-otp", "totpm"):
            base += "[bold cyan]d[/] Delete  "
        base += "[bold cyan]v[/] QR  "
        base += "[bold cyan]?/F1[/] Help  "
        base += "[bold cyan]Esc[/] Back"
        return base

    def _populate_options(self, matches: list[tuple[str, str]], query: str) -> None:
        self._current_matches = matches
        option_list = self.query_one(TokenOptionList)
        empty_notice = self.query_one("#empty-state-notice", Static)
        badge = self.query_one("#match-count-badge", Static)

        total = len(self.raw_records)
        match_count = len(matches)

        if match_count > MAX_RENDER_OPTIONS:
            badge.update(f"{match_count} matches (top {MAX_RENDER_OPTIONS})")
        else:
            badge.update(f"{match_count} matches / {total} items")

        option_list.clear_options()

        if match_count == 0:
            empty_notice.display = True
            option_list.display = False
            self._update_status(None)
            return

        empty_notice.display = False
        option_list.display = True

        options_to_render = matches[:MAX_RENDER_OPTIONS]
        rendered_options: list[Option] = []

        for idx, (key, label) in enumerate(options_to_render):
            srv, acc, short_id = parse_token_parts(self.backend, key, label)

            row = Text()
            row.append(f"{idx + 1:<5}", style="dim")
            row.append_text(self._highlight_match(f"{srv:<32}"[:32], query, "bold cyan"))
            row.append(" ")
            row.append_text(self._highlight_match(f"{acc:<30}"[:30], query, "white"))
            row.append(" ")
            row.append(f"{short_id:<10}"[:10], style="dim")

            rendered_options.append(Option(prompt=row, id=f"opt-{idx}"))

        option_list.add_options(rendered_options)
        if option_list.option_count > 0:
            option_list.highlighted = 0
            self._update_status(options_to_render[0])

    @staticmethod
    def _highlight_match(
        text: str,
        query: str,
        base_style: str,
        highlight_style: str = "bold yellow underline",
    ) -> Text:
        """Highlight matching substrings or fuzzy character positions using Rich Text spans."""
        t = Text(text, style=base_style)
        q = query.strip()
        if not q or not text:
            return t

        raw = text.casefold()
        q_norm = q.casefold()

        # Strategy 1: Full-query contiguous substring match (all occurrences)
        sub = raw.find(q_norm)
        if sub != -1:
            start = 0
            while True:
                idx = raw.find(q_norm, start)
                if idx == -1:
                    break
                t.stylize(highlight_style, idx, idx + len(q_norm))
                start = idx + len(q_norm)
            return t

        # Strategy 2: Multi-word query (highlight matching terms)
        words = [w for w in q_norm.split() if w]
        if len(words) > 1:
            matched_word = False
            for w in words:
                start = 0
                while True:
                    idx = raw.find(w, start)
                    if idx == -1:
                        break
                    t.stylize(highlight_style, idx, idx + len(w))
                    matched_word = True
                    start = idx + len(w)
            if matched_word:
                return t

        # Strategy 3: Fuzzy subsequence matching (ordered characters)
        chars = [c for c in q_norm if not c.isspace()]
        if not chars:
            return t

        matched_indices: list[int] = []
        c_idx = 0
        c_len = len(chars)

        for i, ch in enumerate(raw):
            if ch == chars[c_idx]:
                matched_indices.append(i)
                c_idx += 1
                if c_idx == c_len:
                    break

        if c_idx == c_len:
            for idx in matched_indices:
                t.stylize(highlight_style, idx, idx + 1)

        return t

    def _update_status(self, selected_item: tuple[str, str] | None) -> None:
        status = self.query_one("#status-detail", Static)
        if selected_item is None:
            status.update("No token selected")
            self.selected_token_key = None
            return
        key, label = selected_item
        self.selected_token_key = key
        srv, acc, _ = parse_token_parts(self.backend, key, label)
        status.update(f"Selected: [bold cyan]{srv}[/] ({acc})  |  Key: [dim]{key}[/]")

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(0.035, lambda: self._apply_search(event.value))

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._apply_search(event.value)
        if self._current_matches:
            self.action_select_default()

    def _apply_search(self, query: str) -> None:
        self.current_query = query
        if not query:
            matches = self.raw_records
        else:
            matches = self.search_index.filter(query)
        if self.active_folder is not None:
            matches = [
                m for m in matches if extract_folder(self.backend, m[0], m[1]) == self.active_folder
            ]
        self._populate_options(matches, query)

    @on(OptionList.OptionHighlighted, "#token-option-list")
    def on_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_index is not None and 0 <= event.option_index < len(self._current_matches):
            self._update_status(self._current_matches[event.option_index])

    @on(OptionList.OptionSelected, "#token-option-list")
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.action_select_default()

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_filter_folder(self) -> None:
        folder_counts: dict[str, int] = {}
        for k, lbl in self.raw_records:
            fld = extract_folder(self.backend, k, lbl)
            folder_counts[fld] = folder_counts.get(fld, 0) + 1

        def on_folder_chosen(chosen: str | None) -> None:
            if chosen is None:
                return
            if chosen == "__all__":
                self.active_folder = None
            else:
                self.active_folder = chosen
            try:
                self.query_one("#browser-subtitle", Static).update(self._format_subtitle())
            except Exception:
                pass
            self._apply_search(self.current_query)

        self.app.push_screen(FolderSelectModal(folder_counts, self.active_folder), on_folder_chosen)

    def action_handle_escape(self) -> None:
        inp = self.query_one("#search-input", Input)
        if inp.has_focus:
            if inp.value:
                inp.value = ""
            self.query_one(TokenOptionList).focus()
            return
        if inp.value:
            inp.value = ""
            return
        if self.active_folder is not None:
            self.active_folder = None
            try:
                self.query_one("#browser-subtitle", Static).update(self._format_subtitle())
            except Exception:
                pass
            self._apply_search("")
            return
        self.app.pop_screen()

    def _update_status_text(self, text: str) -> None:
        try:
            self.query_one("#status-detail", Static).update(f"[bold yellow]{text}[/]")
        except NoMatches:
            pass

    def action_select_default(self) -> None:
        if self.default_action == "copy":
            self.action_select_copy()
        else:
            self.action_select_show()

    def action_select_show(self) -> None:
        item = self._get_highlighted_item()
        if item is None:
            return
        key, label = item
        from .tui_items import arguments

        try:
            args = ["show"] + arguments(self.backend, self.profile, key)
        except Exception:
            args = ["show", key]

        async def run_show() -> None:
            self._update_status_text("Retrieving OTP code...")
            touch_modal = None
            if self.backend == "fido2" and self.app.is_running:
                touch_modal = Fido2TouchModal(account=key)
                self.app.push_screen(touch_modal)

            try:
                status, summary, lines = await self.app.aexecute(args)
            finally:
                if touch_modal is not None and touch_modal.is_mounted:
                    touch_modal.dismiss(True)

            if status == 0:
                code = lines[1] if len(lines) > 1 else ""

                def refresh_code() -> str | None:
                    st, _, lns = self.app.execute(
                        args, on_success_modal=False, on_error_modal=False
                    )
                    if st == 0 and len(lns) > 1:
                        return lns[1]
                    return None

                self.app.push_screen(
                    CodeDisplayModal(
                        code=code,
                        item_label=label,
                        backend=self.backend,
                        refresh_callback=refresh_code,
                    )
                )
            else:
                self.app.push_screen(MessageModal("Error", lines))
            self._update_status(self._get_highlighted_item())

        self.run_worker(run_show())

    def action_select_copy(self) -> None:
        item = self._get_highlighted_item()
        if item is None:
            return
        key, label = item
        from .tui_items import arguments

        try:
            args = ["copy"] + arguments(self.backend, self.profile, key)
        except Exception:
            args = ["copy", key]

        async def run_copy() -> None:
            self._update_status_text("Copying OTP code...")
            touch_modal = None
            if self.backend == "fido2" and self.app.is_running:
                touch_modal = Fido2TouchModal(account=key)
                self.app.push_screen(touch_modal)

            try:
                status, summary, lines = await self.app.aexecute(args)
            finally:
                if touch_modal is not None and touch_modal.is_mounted:
                    touch_modal.dismiss(True)

            if status == 0:
                if hasattr(self.app, "notify_copy"):
                    self.app.notify_copy(label)
                else:
                    self.app.notify(
                        "Copy completed. Clipboard history behavior is controlled by your desktop.",
                        timeout=3,
                    )
            else:
                self.app.push_screen(MessageModal("Error", lines))
            self._update_status(self._get_highlighted_item())

        self.run_worker(run_copy())

    def action_show_help(self) -> None:
        self.app.action_show_help()

    def action_request_delete(self) -> None:
        if self.backend not in ("pass-otp", "totpm", "keychain", "dpapi", "fido2"):
            return
        item = self._get_highlighted_item()
        if item is None:
            return
        key, label = item

        def on_confirmed(confirmed: bool) -> None:
            if confirmed:

                async def run_delete() -> None:
                    try:
                        success = await self.app.adelete_record(self.backend, self.profile, key)
                    except Exception:
                        success = False
                    if success:
                        self.raw_records = [
                            (k, rec_label) for k, rec_label in self.raw_records if k != key
                        ]
                        from .tui_items import SearchIndex

                        self.search_index = SearchIndex(self.raw_records)
                        self._apply_search(self.current_query)
                    else:
                        self.app.push_screen(
                            MessageModal(
                                "Deletion Failed",
                                ["Backend request failed. Check the native app privately."],
                            )
                        )

                self.run_worker(run_delete())

        self.app.push_screen(DeleteConfirmModal(self.backend, label), on_confirmed)

    def action_refresh_list(self) -> None:
        async def run_refresh() -> None:
            self._update_status_text("Refreshing tokens...")
            reloaded = await self.app.aload_records(self.backend, self.profile)
            if reloaded is not None:
                self.raw_records = list(reloaded)
                from .tui_items import SearchIndex

                self.search_index = SearchIndex(self.raw_records)
                self._apply_search(self.current_query)
            self._update_status(self._get_highlighted_item())

        self.run_worker(run_refresh())

    def action_select_qr(self) -> None:
        item = self._get_highlighted_item()
        if item is None:
            return
        key, label = item
        if self.app:
            self.app.action_show_token_qr(key, self.backend)

    def _get_highlighted_item(self) -> tuple[str, str] | None:
        option_list = self.query_one(TokenOptionList)
        idx = option_list.highlighted
        if idx is not None and 0 <= idx < len(self._current_matches):
            return self._current_matches[idx]
        return None


class WheelPathModal(ModalScreen[str | None]):
    """Modal for entering a local .whl file path."""

    BINDINGS = [
        Binding("escape", "cancel_modal", "Cancel", show=False),
        Binding("q", "cancel_modal", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="wheel-dialog"):
            yield Static("Enter Local Wheel (.whl) Path", id="wheel-title")
            yield Input(placeholder="Path to .whl file", id="wheel-path-input")
            with Horizontal(id="wheel-button-bar"):
                yield Button("Preview [Enter]", id="btn-submit-wheel", variant="primary")
                yield Button("Cancel [Esc]", id="btn-cancel-wheel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#wheel-path-input", Input).focus()

    @on(Input.Submitted, "#wheel-path-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        self.dismiss(val if val else None)

    @on(Button.Pressed, "#btn-submit-wheel")
    def on_submit_pressed(self) -> None:
        val = self.query_one("#wheel-path-input", Input).value.strip()
        self.dismiss(val if val else None)

    @on(Button.Pressed, "#btn-cancel-wheel")
    def on_cancel_pressed(self) -> None:
        self.dismiss(None)

    def action_cancel_modal(self) -> None:
        self.dismiss(None)


class InstallPreviewModal(ModalScreen[None]):
    """Modal displaying staged files and safety warning for installation preview."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "run_preview", "Preview", show=False),
        Binding("q", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, initial_path: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.initial_path = initial_path

    def compose(self) -> ComposeResult:
        with Vertical(id="preview-dialog"):
            yield Static("Installation Preview", id="preview-title")
            yield Static(
                "[bold yellow]PREVIEW ONLY — READ-ONLY INSPECTION — NO CHANGES AUTHORIZED[/]",
                id="preview-guarantee",
            )
            yield Input(
                value=self.initial_path,
                placeholder="Path to local .whl file (press Enter to preview)",
                id="preview-wheel-input",
            )
            with VerticalScroll(id="preview-scroll"):
                yield Static(
                    "Enter a wheel path above and press Enter or Preview to inspect staged changes.",
                    id="preview-plan-content",
                )
            with Horizontal(id="preview-button-bar"):
                yield Button("Preview Plan [Enter]", id="btn-run-preview", variant="primary")
                yield Button("Close [Esc]", id="btn-close-preview", variant="default")

    def on_mount(self) -> None:
        inp = self.query_one("#preview-wheel-input", Input)
        inp.focus()
        if self.initial_path:
            self.action_run_preview()

    @on(Input.Submitted, "#preview-wheel-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_run_preview()

    @on(Button.Pressed, "#btn-run-preview")
    def on_run_preview_pressed(self) -> None:
        self.action_run_preview()

    @on(Button.Pressed, "#btn-close-preview")
    def on_close_pressed(self) -> None:
        self.action_dismiss_modal()

    def action_run_preview(self) -> None:
        path = self.query_one("#preview-wheel-input", Input).value.strip()
        if not path:
            return
        status, summary, lines = self.app.execute(["preview", path])
        scroll = self.query_one("#preview-scroll", VerticalScroll)
        scroll.remove_children()
        for line in lines:
            scroll.mount(Static(line))

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class MigrationGuideModal(ModalScreen[None]):
    """Modal displaying the 14 operational safety checkpoints and runbook steps."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "dismiss_modal", "Close", show=False),
        Binding("space", "dismiss_modal", "Close", show=False),
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("c", "copy_checkpoints", "Copy Checkpoints", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="guide-dialog"):
            yield Static("Private Migration & Recovery Guide", id="guide-title")
            with VerticalScroll(id="guide-scroll"):
                yield Static(
                    "[bold cyan]14 Operational Safety Checkpoints[/]",
                    classes="guide-header",
                )
                for idx, step in enumerate(GUIDE[1:], 1):
                    yield Static(f"[bold yellow]{idx:2d}.[/] {step}", classes="guide-item")
                yield Static("[bold cyan]Migration & Recovery Runbook[/]", classes="guide-header")
                yield Static(
                    "• State Machine: discovered → classified → recovery-ready → enrolled → login-verified → reconciled\n"
                    "• Batch Policy: Authorize batches <= 3; high-impact accounts individually.\n"
                    "• Zero Secrets: Never commit or persist OTP seeds, codes, or credentials in repo contexts.\n"
                    "• Recovery First: Verify recovery credentials before retiring any working token.",
                    classes="guide-item",
                )
            with Horizontal(id="guide-button-bar"):
                yield Button("Copy Checkpoints [c]", id="btn-copy-guide", variant="primary")
                yield Button("Close [Esc]", id="btn-close-guide", variant="default")

    def action_copy_checkpoints(self) -> None:
        text = "\n".join(GUIDE)
        try:
            from .interaction import copy_code

            copy_code(text, dict(os.environ))
            self.notify("Checkpoints copied to clipboard!", timeout=3)
        except Exception:
            self.notify("Checkpoints copied (local notification)", timeout=3)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-copy-guide")
    def on_copy_pressed(self) -> None:
        self.action_copy_checkpoints()

    @on(Button.Pressed, "#btn-close-guide")
    def on_close_pressed(self) -> None:
        self.action_dismiss_modal()


class SavedScopeModal(ModalScreen[dict[str, str] | None]):
    """Modal form to view/edit resident profile config with strict validation."""

    BINDINGS = [
        Binding("escape", "cancel_scope", "Cancel", show=False),
    ]

    def __init__(
        self,
        backend: str,
        initial: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.backend = backend
        self.initial = dict(initial or {})

    def compose(self) -> ComposeResult:
        b_name = dict(BACKENDS).get(self.backend, self.backend)
        with Vertical(id="scope-dialog"):
            yield Static(f"Configure Saved Scope — {b_name}", id="scope-title")
            yield Static(
                "Private scope saved in ~/.config/authy-local/tui-profiles.json (mode 0600). Secrets are NEVER stored.",
                id="scope-privacy-notice",
            )
            with VerticalScroll(id="scope-fields-scroll"):
                if self.backend == "onepassword":
                    yield Static("Account ID (26 alphanumeric characters):")
                    yield Input(
                        value=self.initial.get("account", ""),
                        placeholder="e.g. 2w4j6k8m0n2p4r6t8v0x2z4a6c",
                        max_length=26,
                        id="scope-op-account",
                    )
                    yield Static("Vault ID (26 alphanumeric characters):")
                    yield Input(
                        value=self.initial.get("vault", ""),
                        placeholder="e.g. 2w4j6k8m0n2p4r6t8v0x2z4a6c",
                        max_length=26,
                        id="scope-op-vault",
                    )
                    yield Static("Item Tag (optional filter, default: OTP):")
                    yield Input(
                        value=self.initial.get("tag", ""),
                        placeholder="e.g. OTP",
                        max_length=64,
                        id="scope-op-tag",
                    )
                elif self.backend == "pass-otp":
                    yield Static("Password Store Absolute Path:")
                    yield Input(
                        value=self.initial.get("store", ""),
                        placeholder="e.g. /home/user/.password-store",
                        max_length=1024,
                        id="scope-pass-store",
                    )
                    yield Static("GPG Key Home Absolute Path:")
                    yield Input(
                        value=self.initial.get("key_home", ""),
                        placeholder="e.g. /home/user/.gnupg",
                        max_length=1024,
                        id="scope-pass-keyhome",
                    )
                elif self.backend == "totpm":
                    yield Static("Configuration File Absolute Path:")
                    yield Input(
                        value=self.initial.get("config", ""),
                        placeholder="e.g. /home/user/.config/totpm.conf",
                        max_length=1024,
                        id="scope-totpm-config",
                    )
                elif self.backend in ("yubikey", "tpm2-totp", "keychain", "dpapi", "fido2"):
                    yield Static(
                        "Hardware/System backend accesses token directly via secure interface."
                    )
                    yield Static("No scope configuration file or path parameters required.")
            yield Static("", id="scope-error-banner")
            with Horizontal(id="scope-actions"):
                yield Button("Save Scope [Enter]", id="btn-save-scope", variant="primary")
                yield Button("Cancel [Esc]", id="btn-cancel-scope", variant="default")

    def on_mount(self) -> None:
        try:
            self.query(Input).first().focus()
        except Exception:
            try:
                self.query(Button).first().focus()
            except Exception:
                pass

    @on(Button.Pressed, "#btn-save-scope")
    def on_save_pressed(self) -> None:
        self._validate_and_save()

    @on(Button.Pressed, "#btn-cancel-scope")
    def on_cancel_pressed(self) -> None:
        self.dismiss(None)

    def action_cancel_scope(self) -> None:
        self.dismiss(None)

    def _validate_and_save(self) -> None:
        from .tui_profiles import _validate

        scope_dict = {}
        if self.backend == "onepassword":
            account = self.query_one("#scope-op-account", Input).value.strip()
            vault = self.query_one("#scope-op-vault", Input).value.strip()
            tag = self.query_one("#scope-op-tag", Input).value.strip()
            scope_dict = {"account": account, "vault": vault}
            if tag:
                scope_dict["tag"] = tag
        elif self.backend == "pass-otp":
            store = self.query_one("#scope-pass-store", Input).value.strip()
            key_home = self.query_one("#scope-pass-keyhome", Input).value.strip()
            scope_dict = {"store": store, "key_home": key_home}
        elif self.backend == "totpm":
            config = self.query_one("#scope-totpm-config", Input).value.strip()
            scope_dict = {"config": config}
        elif self.backend in ("yubikey", "tpm2-totp", "keychain", "dpapi", "fido2"):
            self.app.notify(f"Backend {self.backend} needs no saved file scope.")
            self.dismiss({})
            return

        try:
            _validate({self.backend: scope_dict})
        except AppError:
            self.query_one("#scope-error-banner", Static).update(
                "Validation failed: Verify required fields, absolute paths, or 26-char IDs."
            )
            return

        candidate = {**self.app.profiles, self.backend: scope_dict}
        try:
            if self.app.save_profiles_callback:
                self.app.save_profiles_callback(candidate)
            self.app.profiles = candidate
            self.app.notify(f"Scope saved for {dict(BACKENDS).get(self.backend, self.backend)}.")
            self.dismiss(scope_dict)
        except Exception as exc:
            self.query_one("#scope-error-banner", Static).update(f"Error saving: {exc}")


class BackendSelectModal(ModalScreen[str | None]):
    """Modal to switch active backend ('b')."""

    BINDINGS = [
        Binding("escape", "cancel_select", "Cancel", show=False),
        Binding("q", "cancel_select", "Cancel", show=False),
        Binding("1", "select_1", "1Password", show=False),
        Binding("2", "select_2", "pass-otp", show=False),
        Binding("3", "select_3", "totpm", show=False),
        Binding("4", "select_4", "yubikey", show=False),
        Binding("5", "select_5", "tpm2-totp", show=False),
        Binding("6", "select_6", "keychain", show=False),
        Binding("7", "select_7", "dpapi", show=False),
        Binding("8", "select_8", "fido2", show=False),
        Binding("9", "select_9", "bitwarden", show=False),
    ]

    def __init__(self, current_backend: str = "onepassword", **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_backend = current_backend

    def compose(self) -> ComposeResult:
        with Vertical(id="backend-select-dialog"):
            yield Static("Choose Backend Provider", id="backend-select-title")
            yield OptionList(
                Option("1  1Password (onepassword)", id="opt-onepassword"),
                Option("2  pass-otp / GPG (pass-otp)", id="opt-pass-otp"),
                Option("3  totpm / TPM (totpm)", id="opt-totpm"),
                Option("4  YubiKey OATH (yubikey)", id="opt-yubikey"),
                Option("5  TPM 2.0 TOTP (tpm2-totp)", id="opt-tpm2-totp"),
                Option("6  macOS Keychain (keychain)", id="opt-keychain"),
                Option("7  Windows DPAPI (dpapi)", id="opt-dpapi"),
                Option("8  FIDO2 Security Key (fido2)", id="opt-fido2"),
                Option("9  Bitwarden Vault (bitwarden)", id="opt-bitwarden"),
                id="backend-select-list",
            )
            with Horizontal(id="backend-button-bar"):
                yield Button("Select [Enter]", id="btn-select-backend", variant="primary")
                yield Button("Cancel [Esc]", id="btn-cancel-backend", variant="default")

    def on_mount(self) -> None:
        opt_list = self.query_one("#backend-select-list", OptionList)
        mapping = {
            "onepassword": 0,
            "pass-otp": 1,
            "totpm": 2,
            "yubikey": 3,
            "tpm2-totp": 4,
            "keychain": 5,
            "dpapi": 6,
            "fido2": 7,
            "bitwarden": 8,
        }
        opt_list.highlighted = mapping.get(self.current_backend, 0)
        opt_list.focus()

    def action_select_1(self) -> None:
        self._choose("onepassword")

    def action_select_2(self) -> None:
        self._choose("pass-otp")

    def action_select_3(self) -> None:
        self._choose("totpm")

    def action_select_4(self) -> None:
        self._choose("yubikey")

    def action_select_5(self) -> None:
        self._choose("tpm2-totp")

    def action_select_6(self) -> None:
        self._choose("keychain")

    def action_select_7(self) -> None:
        self._choose("dpapi")

    def action_select_8(self) -> None:
        self._choose("fido2")

    def action_select_9(self) -> None:
        self._choose("bitwarden")

    def action_cancel_select(self) -> None:
        self.dismiss(None)

    @on(OptionList.OptionSelected, "#backend-select-list")
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        backends = [
            "onepassword",
            "pass-otp",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "keychain",
            "dpapi",
            "fido2",
            "bitwarden",
        ]
        if event.option_index is not None and 0 <= event.option_index < len(backends):
            self._choose(backends[event.option_index])

    @on(Button.Pressed, "#btn-select-backend")
    def on_select_pressed(self) -> None:
        opt_list = self.query_one("#backend-select-list", OptionList)
        backends = [
            "onepassword",
            "pass-otp",
            "totpm",
            "yubikey",
            "tpm2-totp",
            "keychain",
            "dpapi",
            "fido2",
            "bitwarden",
        ]
        if opt_list.highlighted is not None and 0 <= opt_list.highlighted < len(backends):
            self._choose(backends[opt_list.highlighted])

    @on(Button.Pressed, "#btn-cancel-backend")
    def on_cancel_pressed(self) -> None:
        self.dismiss(None)

    def _choose(self, backend: str) -> None:
        self.app.current_backend = backend
        self.dismiss(backend)


def get_shortcuts_categories() -> list[tuple[str, list[tuple[str, str]]]]:
    """Return categorized keyboard navigation shortcuts taxonomy."""
    return [
        (
            "Global Controls",
            [
                ("?  /  F1", "Open / toggle Keyboard Shortcuts help overlay"),
                ("b", "Switch active backend (1Password, pass-otp, totpm)"),
                ("p", "Configure resident scope (account/vault/store)"),
                ("q  /  Esc", "Quit application (from Dashboard)"),
            ],
        ),
        (
            "Dashboard Navigation",
            [
                ("↑ / ↓  (j / k)", "Move selection up / down in Actions menu"),
                ("Enter", "Open highlighted action"),
                ("1 - 8", "Trigger actions 1-8 directly by number"),
            ],
        ),
        (
            "Token Browser Controls",
            [
                ("/ (slash)", "Focus instant search filter input"),
                ("↑ / ↓  (j / k)", "Navigate token records list"),
                ("Enter", "Execute default action (Show OTP or Copy OTP)"),
                ("s", "Show OTP code with 30s countdown bar"),
                ("c", "Copy OTP code to desktop clipboard"),
                ("f", "Filter by hierarchical Folder / Namespace"),
                ("r", "Refresh token records from backend"),
                ("d", "Delete confirmed entry (pass-otp / totpm)"),
                ("Esc", "Clear search input / return to Dashboard"),
            ],
        ),
        (
            "Code Display Modal",
            [
                ("c", "Copy TOTP code to desktop clipboard"),
                ("r", "Refresh OTP code when expired"),
                ("Esc / Enter", "Dismiss modal and erase code from memory"),
            ],
        ),
        (
            "Forms & Dialogs",
            [
                ("Tab / Shift+Tab", "Cycle focus across input fields"),
                ("Enter", "Validate and advance / submit form"),
                ("Esc", "Dismiss modal or cancel without saving"),
            ],
        ),
    ]


def create_category_table(
    section_name: str,
    shortcuts: list[tuple[str, str]],
    compact: bool = False,
) -> Table:
    """Construct a high-contrast Rich Table for a single category section."""
    table = Table(
        title=None,
        expand=True,
        box=None,
        padding=(0, 1),
        show_header=False,
    )
    key_width = 15 if compact else 18
    table.add_column("Shortcut", style="bold cyan", no_wrap=True, width=key_width)
    table.add_column("Description", style="white", overflow="fold")
    table.add_row(f"[bold yellow]── {section_name} ──[/]", "")
    for key, desc in shortcuts:
        table.add_row(f"[bold cyan]{key}[/]", desc)
    return table


def create_shortcuts_table(compact: bool = False) -> Table:
    """Construct a high-contrast categorized keyboard shortcuts table."""
    table = Table(
        title=None,
        expand=True,
        box=None,
        padding=(0, 1),
        show_header=True,
        header_style="bold cyan",
    )
    key_width = 15 if compact else 18
    table.add_column("Shortcut", style="bold cyan", no_wrap=True, width=key_width)
    table.add_column("Description", style="white", overflow="fold")

    for section_name, shortcuts in get_shortcuts_categories():
        table.add_section()
        table.add_row(f"[bold yellow]── {section_name} ──[/]", "")
        for key, desc in shortcuts:
            table.add_row(f"[bold cyan]{key}[/]", desc)

    return table


class InteractiveQrModal(ModalScreen[None]):
    """Modal displaying compact UTF-8 QR code for mobile camera enrollment."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "dismiss_modal", "Close", show=False),
        Binding("space", "dismiss_modal", "Close", show=False),
        Binding("q", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, qr_text: str, item_label: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.qr_text = qr_text
        self.item_label = item_label

    def compose(self) -> ComposeResult:
        with Vertical(id="qr-dialog"):
            yield Static("Mobile Enrollment QR Code", id="qr-title")
            if self.item_label:
                yield Static(f"Item: [bold cyan]{self.item_label}[/]", id="qr-item-label")
            with VerticalScroll(id="qr-scroll"):
                yield Static(self.qr_text, id="qr-content")
            yield Static(
                "Scan with your mobile authenticator app. Key is never saved to disk.",
                id="qr-footer-hint",
            )
            with Horizontal(id="qr-button-bar"):
                yield Button("Close [Esc/Enter/q]", id="btn-close-qr", variant="primary")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-close-qr")
    def on_close_pressed(self) -> None:
        self.dismiss(None)


class AuditReportModal(ModalScreen[None]):
    """Modal displaying Credential Security & Hygiene Audit findings and score."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "dismiss_modal", "Close", show=False),
        Binding("space", "dismiss_modal", "Close", show=False),
        Binding("q", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, report: object, backend: str = "onepassword", **kwargs) -> None:
        super().__init__(**kwargs)
        self.report = report
        self.backend = backend

    def compose(self) -> ComposeResult:
        with Vertical(id="audit-dialog"):
            yield Static("Credential Security & Hygiene Audit", id="audit-title")
            score = getattr(self.report, "score", 100)
            grade = getattr(self.report, "letter_grade", "A+")
            total = getattr(self.report, "total_accounts", 0)
            grade_color = (
                "green" if grade in ("A+", "A") else "yellow" if grade in ("B", "C") else "red"
            )
            summary_text = (
                f"Backend: [bold cyan]{self.backend}[/]  |  "
                f"Accounts: [bold]{total}[/]  |  "
                f"Score: [bold {grade_color}]{score}/100 ({grade})[/]"
            )
            yield Static(summary_text, id="audit-summary-badge")
            with VerticalScroll(id="audit-scroll"):
                findings = getattr(self.report, "findings", [])
                if not findings:
                    yield Static(
                        "[bold green]No issues detected.[/]\n"
                        "All credentials conform to security and hygiene best practices.",
                        classes="audit-finding",
                    )
                else:
                    for f in findings:
                        sev_color = (
                            "red"
                            if f.severity == "CRITICAL"
                            else "orange"
                            if f.severity == "HIGH"
                            else "yellow"
                        )
                        yield Static(
                            f"[{sev_color}][{f.code}] {f.severity}:[/] [bold]{f.title}[/]\n"
                            f"  Target: [cyan]{f.account_id}[/]\n"
                            f"  {f.description}\n"
                            f"  [dim]Recommendation: {f.recommendation}[/]\n",
                            classes="audit-finding",
                        )
            with Horizontal(id="audit-button-bar"):
                yield Button("Close [Esc/Enter/q]", id="btn-close-audit", variant="primary")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-close-audit")
    def on_close_pressed(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen[None]):
    """Modal displaying categorized keyboard navigation shortcuts ('?' / F1)."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "dismiss_modal", "Close", show=False),
        Binding("space", "dismiss_modal", "Close", show=False),
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("question_mark", "dismiss_modal", "Close", show=False),
        Binding("f1", "dismiss_modal", "Close", show=False),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("down", "scroll_down", "Down", show=False),
        Binding("up", "scroll_up", "Up", show=False),
        Binding("pageup", "scroll_page_up", "Page Up", show=False),
        Binding("pagedown", "scroll_page_down", "Page Down", show=False),
    ]

    def compose(self) -> ComposeResult:
        is_compact = self.app.has_class("compact-width") if self.app else False
        with Vertical(id="help-dialog"):
            yield Static("Authy Local  |  KEYBOARD SHORTCUTS", id="help-title")
            with VerticalScroll(id="help-scroll"):
                for section_name, shortcuts in get_shortcuts_categories():
                    yield Static(
                        create_category_table(section_name, shortcuts, compact=is_compact),
                        classes="help-line",
                    )
            with Horizontal(id="help-button-bar"):
                yield Button("Close [Esc/Enter/?]", id="btn-close-help", variant="primary")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_scroll_down(self) -> None:
        try:
            self.query_one("#help-scroll", VerticalScroll).scroll_down()
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        try:
            self.query_one("#help-scroll", VerticalScroll).scroll_up()
        except Exception:
            pass

    def action_scroll_page_up(self) -> None:
        try:
            self.query_one("#help-scroll", VerticalScroll).scroll_page_up()
        except Exception:
            pass

    def action_scroll_page_down(self) -> None:
        try:
            self.query_one("#help-scroll", VerticalScroll).scroll_page_down()
        except Exception:
            pass

    @on(Button.Pressed, "#btn-close-help")
    def on_close_pressed(self) -> None:
        self.action_dismiss_modal()


class AddOtpModal(ModalScreen[None]):
    """Modal dialog for enrolling a new OTP token from alphanumeric text or QR screenshot."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel", show=False),
        Binding("q", "dismiss_modal", "Cancel", show=False),
        Binding("c", "copy_test_code", "Copy Code", show=False),
    ]

    def __init__(
        self,
        current_backend: str = "onepassword",
        profiles: dict[str, dict[str, str]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.current_backend = current_backend
        self.profiles = dict(profiles or {})
        self._parsed_params = None
        self._live_code: str = ""
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="add-otp-dialog"):
            yield Static("Add & Enroll New OTP Entry", id="add-otp-title")
            yield Static(
                "Ingest from alphanumeric secret / URI, or paste a screen-captured QR code image.",
                id="add-otp-desc",
            )
            with VerticalScroll(id="add-otp-scroll"):
                yield Static("Secret or URI (Base32 or otpauth://totp/...):", classes="field-label")
                yield Input(
                    placeholder="e.g. JBSWY3DPEHPK3PXP or otpauth://totp/...",
                    id="inp-otp-secret",
                    password=True,
                )
                with Horizontal(id="secret-actions-bar"):
                    yield Button("Paste QR / Text [v]", id="btn-paste-clipboard", variant="success")
                    yield Button("Toggle Mask", id="btn-toggle-mask", variant="default")

                yield Static("Or load screenshot / QR image file path:", classes="field-label")
                with Horizontal(id="qr-file-row"):
                    yield Input(
                        placeholder="e.g. /tmp/Spectacle.xyz/Screenshot.png", id="inp-qr-file-path"
                    )
                    yield Button("Decode File [d]", id="btn-decode-file-qr", variant="default")

                yield Static("Token Metadata (auto-filled or customized):", classes="field-label")
                with Horizontal(classes="form-row"):
                    with Vertical(classes="form-col"):
                        yield Static("Service / Issuer:")
                        yield Input(placeholder="e.g. GitHub", id="inp-otp-issuer")
                    with Vertical(classes="form-col"):
                        yield Static("Account Name:")
                        yield Input(placeholder="e.g. alice@example.com", id="inp-otp-account")

                with Horizontal(classes="form-row"):
                    with Vertical(classes="form-col-sm"):
                        yield Static("Digits (6 or 8):")
                        yield Input(value="6", id="inp-otp-digits")
                    with Vertical(classes="form-col-sm"):
                        yield Static("Period (s):")
                        yield Input(value="30", id="inp-otp-period")
                    with Vertical(classes="form-col-sm"):
                        yield Static("Algorithm:")
                        yield Input(value="SHA1", id="inp-otp-algorithm")

                yield Static("Live Verification Challenge (RFC 6238):", classes="field-label")
                with Horizontal(id="live-preview-box"):
                    yield Static("------", id="lbl-live-code")
                    yield Button("Copy Test Code [c]", id="btn-copy-test-code", variant="primary")
                yield CountdownBar(id="live-countdown-bar")

                yield Static("Target Storage Backend(s):", classes="field-label")
                with Horizontal(id="target-backends-box"):
                    yield Checkbox(
                        "1Password (Login tagged 'OTP')",
                        value=(self.current_backend == "onepassword"),
                        id="chk-onepassword",
                    )
                    yield Checkbox(
                        "pass-otp / GPG",
                        value=(self.current_backend == "pass-otp"),
                        id="chk-pass-otp",
                    )
                    yield Checkbox(
                        "totpm / TPM",
                        value=(self.current_backend == "totpm"),
                        id="chk-totpm",
                    )
                    yield Checkbox(
                        "macOS Keychain",
                        value=(self.current_backend == "keychain"),
                        id="chk-keychain",
                    )
                    yield Checkbox(
                        "Windows DPAPI",
                        value=(self.current_backend == "dpapi"),
                        id="chk-dpapi",
                    )
                    yield Checkbox(
                        "FIDO2 Security Key",
                        value=(self.current_backend == "fido2"),
                        id="chk-fido2",
                    )
                    yield Checkbox(
                        "Bitwarden Vault",
                        value=(self.current_backend == "bitwarden"),
                        id="chk-bitwarden",
                    )

                yield Static("", id="add-otp-status-banner")

            with Horizontal(id="add-otp-button-bar"):
                yield Button("Enroll and Save [Enter]", id="btn-enroll-save", variant="primary")
                yield Button("Cancel [Esc/q]", id="btn-enroll-cancel", variant="default")

    def on_mount(self) -> None:
        self._timer = self.set_interval(1.0, self._tick_totp)
        try:
            self.query_one("#inp-otp-secret", Input).focus()
        except Exception:
            pass

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._parsed_params = None
        self._live_code = ""

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_copy_test_code(self) -> None:
        if not self._live_code or self._live_code == "------":
            return
        try:
            from .interaction import copy_code

            code_clean = self._live_code.replace(" ", "")
            copy_code(code_clean, dict(os.environ))
            self.notify(f"Copied test code {code_clean} to clipboard!", timeout=2.5)
        except Exception as exc:
            self.notify(f"Copy notice: {exc}", timeout=2.5)

    def _tick_totp(self) -> None:
        if self._parsed_params is None:
            try:
                self.query_one("#lbl-live-code", Static).update("------")
                cbar = self.query_one("#live-countdown-bar", CountdownBar)
                cbar.remaining_seconds = 30.0
                cbar.is_expired = False
            except Exception:
                pass
            return

        from .enrollment import generate_totp_code

        try:
            code, rem = generate_totp_code(self._parsed_params)
            if len(code) == 6:
                formatted = f"{code[:3]} {code[3:]}"
            else:
                formatted = code
            self._live_code = formatted
            self.query_one("#lbl-live-code", Static).update(formatted)
            cbar = self.query_one("#live-countdown-bar", CountdownBar)
            cbar.remaining_seconds = rem
            cbar.is_expired = rem <= 0.0
        except Exception:
            self._live_code = ""
            try:
                self.query_one("#lbl-live-code", Static).update("------")
            except Exception:
                pass

    @on(Input.Changed, "#inp-otp-secret")
    def on_secret_input_changed(self, event: Input.Changed) -> None:
        val = event.value.strip()
        if not val:
            self._parsed_params = None
            self._tick_totp()
            self._set_status("")
            return

        from .enrollment import parse_secret_or_uri

        try:
            params = parse_secret_or_uri(val)
            self._parsed_params = params

            if params.issuer:
                self.query_one("#inp-otp-issuer", Input).value = params.issuer
            if params.account and params.account != "account":
                self.query_one("#inp-otp-account", Input).value = params.account
            self.query_one("#inp-otp-digits", Input).value = str(params.digits)
            self.query_one("#inp-otp-period", Input).value = str(params.period)
            self.query_one("#inp-otp-algorithm", Input).value = params.algorithm

            self._tick_totp()
            self._set_status("[green]✓ Valid secret / URI detected. Live test code active.[/]")
        except Exception:
            self._parsed_params = None
            self._tick_totp()
            self._set_status(
                "[yellow]Enter Base32 secret (16-256 chars) or otpauth://totp/... URI[/]"
            )

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#add-otp-status-banner", Static).update(message)
        except Exception:
            pass

    @on(Button.Pressed, "#btn-toggle-mask")
    def on_toggle_mask(self) -> None:
        inp = self.query_one("#inp-otp-secret", Input)
        inp.password = not inp.password

    @on(Button.Pressed, "#btn-paste-clipboard")
    def on_paste_clipboard(self) -> None:
        env = dict(os.environ)
        from .enrollment import decode_qr_image_bytes, get_clipboard_image, get_clipboard_text

        decoded = ""
        try:
            img = get_clipboard_image(env)
            if img:
                decoded = decode_qr_image_bytes(img, env)
                self.notify("✓ Successfully decoded QR code image from clipboard!", timeout=3)
        except Exception:
            pass

        if not decoded:
            try:
                txt = get_clipboard_text(env)
                if txt:
                    decoded = txt
                    self.notify("✓ Pasted secret / URI text from clipboard!", timeout=3)
            except Exception as exc:
                self._set_status(f"[red]Clipboard read failed: {exc}[/]")
                return

        if decoded:
            self.query_one("#inp-otp-secret", Input).value = decoded

    @on(Button.Pressed, "#btn-decode-file-qr")
    def on_decode_file(self) -> None:
        path = self.query_one("#inp-qr-file-path", Input).value.strip()
        if not path:
            self._set_status("[yellow]Specify an image file path to decode.[/]")
            return

        from .enrollment import decode_qr_image_file

        try:
            env = dict(os.environ)
            decoded = decode_qr_image_file(path, env)
            self.query_one("#inp-otp-secret", Input).value = decoded
            self.notify("✓ Decoded QR code file successfully!", timeout=3)
        except Exception as exc:
            self._set_status(f"[red]Failed to decode QR image: {exc}[/]")

    @on(Button.Pressed, "#btn-copy-test-code")
    def on_copy_test_code_pressed(self) -> None:
        self.action_copy_test_code()

    @on(Button.Pressed, "#btn-enroll-cancel")
    def on_cancel_pressed(self) -> None:
        self.action_dismiss_modal()

    @on(Button.Pressed, "#btn-enroll-save")
    def on_enroll_save_pressed(self) -> None:
        self._execute_enrollment()

    def _execute_enrollment(self) -> None:
        from .enrollment import parse_secret_or_uri

        secret_raw = self.query_one("#inp-otp-secret", Input).value.strip()
        if not secret_raw:
            self._set_status("[red]Error: Secret or URI is required.[/]")
            return

        issuer = self.query_one("#inp-otp-issuer", Input).value.strip()
        account = self.query_one("#inp-otp-account", Input).value.strip()
        if not issuer and not account:
            self._set_status("[red]Error: Provide at least a Service or Account name.[/]")
            return

        try:
            digits = int(self.query_one("#inp-otp-digits", Input).value.strip() or 6)
            period = int(self.query_one("#inp-otp-period", Input).value.strip() or 30)
            algorithm = self.query_one("#inp-otp-algorithm", Input).value.strip().upper() or "SHA1"
            params = parse_secret_or_uri(
                secret_raw,
                fallback_issuer=issuer,
                fallback_label=account,
                digits=digits,
                period=period,
                algorithm=algorithm,
            )
        except Exception as exc:
            self._set_status(f"[red]Invalid parameters: {exc}[/]")
            return

        save_op = self.query_one("#chk-onepassword", Checkbox).value
        save_pass = self.query_one("#chk-pass-otp", Checkbox).value
        save_tpm = self.query_one("#chk-totpm", Checkbox).value
        save_keychain = self.query_one("#chk-keychain", Checkbox).value
        save_dpapi = self.query_one("#chk-dpapi", Checkbox).value
        save_fido2 = self.query_one("#chk-fido2", Checkbox).value
        save_bw = self.query_one("#chk-bitwarden", Checkbox).value

        if not any((save_op, save_pass, save_tpm, save_keychain, save_dpapi, save_fido2, save_bw)):
            self._set_status("[red]Error: Select at least one target backend storage.[/]")
            return

        title = f"{issuer} ({account})" if issuer and account else (issuer or account)
        uri = params.to_uri()
        env = dict(os.environ)

        async def run_enroll() -> None:
            enrolled = []
            errors = []

            # 1. 1Password
            if save_op:
                op_profile = self.profiles.get("onepassword", {})
                account_id = op_profile.get("account")
                vault_id = op_profile.get("vault")
                if not account_id or not vault_id:
                    errors.append("1Password: Missing account/vault scope (configure with 'p')")
                else:
                    try:
                        from .backends import onepassword

                        await asyncio.to_thread(
                            onepassword.enroll,
                            account=account_id,
                            vault=vault_id,
                            title=title,
                            otp_uri=uri,
                            env=env,
                            tags="OTP",
                        )
                        enrolled.append("1Password")
                    except Exception as exc:
                        errors.append(f"1Password: {exc}")

            # 2. pass-otp
            if save_pass:
                pass_profile = self.profiles.get("pass-otp", {})
                store = pass_profile.get("store")
                key_home = pass_profile.get("key_home")
                if not store or not key_home:
                    errors.append("pass-otp: Missing store/key_home scope (configure with 'p')")
                else:
                    try:
                        from .backends import local

                        raw_entry = (
                            f"{issuer}_{account}" if issuer and account else (issuer or account)
                        )
                        entry_name = (
                            re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_entry).strip("._-")[:64] or "entry"
                        )
                        if not re.match(r"[A-Za-z0-9]", entry_name):
                            entry_name = f"otp_{entry_name}"[:64]

                        scope = local.LocalScope(
                            "pass-otp", store=store, key_home=key_home, entry=entry_name
                        )
                        await asyncio.to_thread(local.preflight, scope, env, enrollment=True)
                        await asyncio.to_thread(local.enroll, scope, env, uri)
                        enrolled.append("pass-otp")
                    except Exception as exc:
                        errors.append(f"pass-otp: {exc}")

            # 3. totpm
            if save_tpm:
                tpm_profile = self.profiles.get("totpm", {})
                config = tpm_profile.get("config")
                if not config:
                    errors.append("totpm: Missing config scope (configure with 'p')")
                else:
                    try:
                        from .backends import local

                        raw_svc = issuer or "OTP"
                        svc_name = (
                            re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_svc).strip("._-")[:64] or "OTP"
                        )
                        if not re.match(r"[A-Za-z0-9]", svc_name):
                            svc_name = f"otp_{svc_name}"[:64]

                        raw_acc = account or "default"
                        acc_name = (
                            re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_acc).strip("._-")[:64] or "default"
                        )
                        if not re.match(r"[A-Za-z0-9]", acc_name):
                            acc_name = f"user_{acc_name}"[:64]

                        scope = local.LocalScope(
                            "totpm",
                            config=config,
                            service=svc_name,
                            account=acc_name,
                            digits=params.digits,
                            period=params.period,
                        )
                        await asyncio.to_thread(local.preflight, scope, env, enrollment=True)
                        await asyncio.to_thread(local.enroll, scope, env, params.secret)
                        enrolled.append("totpm")
                    except Exception as exc:
                        errors.append(f"totpm: {exc}")

            # 4. macOS Keychain
            if save_keychain:
                try:
                    from .backends import keychain

                    raw_acc = account or issuer or "default"
                    acc_name = (
                        re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_acc).strip("._-")[:64] or "default"
                    )
                    if not re.match(r"[A-Za-z0-9]", acc_name):
                        acc_name = f"user_{acc_name}"[:64]

                    await asyncio.to_thread(keychain.keychain_enroll, acc_name, params.secret, env)
                    enrolled.append("macOS Keychain")
                except Exception as exc:
                    errors.append(f"macOS Keychain: {exc}")

            # 5. Windows DPAPI
            if save_dpapi:
                try:
                    from .backends import dpapi

                    raw_acc = account or issuer or "default"
                    acc_name = (
                        re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_acc).strip("._-")[:64] or "default"
                    )
                    if not re.match(r"[A-Za-z0-9]", acc_name):
                        acc_name = f"user_{acc_name}"[:64]

                    await asyncio.to_thread(dpapi.dpapi_enroll, acc_name, params.secret, env)
                    enrolled.append("Windows DPAPI")
                except Exception as exc:
                    errors.append(f"Windows DPAPI: {exc}")

            # 6. FIDO2 Security Key
            if save_fido2:
                try:
                    from .backends import fido2

                    raw_acc = account or issuer or "default"
                    acc_name = (
                        re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_acc).strip("._-")[:64] or "default"
                    )
                    if not re.match(r"[A-Za-z0-9]", acc_name):
                        acc_name = f"user_{acc_name}"[:64]

                    await asyncio.to_thread(fido2.fido2_enroll, acc_name, params.secret, env)
                    enrolled.append("FIDO2 Security Key")
                except Exception as exc:
                    errors.append(f"FIDO2: {exc}")

            # 7. Bitwarden Vault
            if save_bw:
                try:
                    from .backends import bitwarden

                    raw_acc = title or "default"
                    await asyncio.to_thread(bitwarden.bitwarden_enroll, raw_acc, uri, env)
                    enrolled.append("Bitwarden")
                except Exception as exc:
                    errors.append(f"Bitwarden: {exc}")

            if errors:
                err_text = "; ".join(errors)
                self._set_status(f"[red]Enrollment errors: {err_text}[/]")
                if enrolled:
                    self.notify(f"Enrolled partially to: {', '.join(enrolled)}", timeout=4)
            else:
                summary = f"Enrolled '{title}' to {', '.join(enrolled)}"
                self.app.session_status = summary
                self.app.notify(f"✓ {summary} successfully!", timeout=3.5)
                if hasattr(self.app, "_cached_catalog"):
                    self.app._cached_catalog.clear()
                self.dismiss(None)

        self.run_worker(run_enroll())


class Fido2TouchModal(ModalScreen[bool]):
    """Modal screen displaying an interactive pulsing touch indicator and countdown timer for FIDO2."""

    DEFAULT_CSS = """
    Fido2TouchModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #fido2-touch-dialog {
        width: 64;
        height: auto;
        border: round cyan;
        background: $surface;
        padding: 1 2;
    }

    #fido2-touch-title {
        color: cyan;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    #fido2-touch-account {
        color: ansi_white;
        text-align: center;
        margin-bottom: 1;
    }

    #fido2-touch-pulse {
        text-align: center;
        height: 3;
        content-align: center middle;
        margin-top: 1;
        margin-bottom: 1;
    }

    #fido2-touch-countdown {
        text-align: center;
        color: ansi_yellow;
        margin-bottom: 1;
    }

    #fido2-touch-bar {
        width: 100%;
        margin-bottom: 1;
    }

    #fido2-touch-button-bar {
        align: center middle;
        margin-top: 1;
    }

    #fido2-touch-button-bar Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel_touch", "Cancel", show=False),
        Binding("q", "cancel_touch", "Cancel", show=False),
        Binding("t", "simulate_touch", "Touch", show=False),
    ]

    PULSE_FRAMES = [
        "[bold cyan]>>> [  *  ] TOUCH SECURITY KEY [  *  ] <<<[/bold cyan]",
        "[bold bright_white]>>>> [ *** ] TOUCH SECURITY KEY [ *** ] <<<<[/bold bright_white]",
        "[bold yellow]>>>>> [*****] TOUCH SECURITY KEY [*****] <<<<<[/bold yellow]",
        "[dim cyan]>> [     ] TOUCH SECURITY KEY [     ] <<[/dim cyan]",
    ]

    def __init__(
        self,
        account: str = "",
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.account = account
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.remaining_seconds = self.timeout_seconds
        self.pulse_step = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="fido2-touch-dialog"):
            yield Static("FIDO2 Security Key Required", id="fido2-touch-title")
            sub_text = (
                f"Account: {self.account}" if self.account else "Cryptographic Key Presence Test"
            )
            yield Static(sub_text, id="fido2-touch-account")
            yield Static(self.PULSE_FRAMES[0], id="fido2-touch-pulse")
            yield CountdownBar(id="fido2-touch-bar")
            yield Static(
                f"Waiting for physical touch... {int(self.remaining_seconds)}s remaining",
                id="fido2-touch-countdown",
            )
            with Horizontal(id="fido2-touch-button-bar"):
                yield Button("Touch Key [t]", id="btn-simulate-touch", variant="primary")
                yield Button("Cancel [Esc]", id="btn-cancel-touch", variant="default")

    def on_mount(self) -> None:
        cbar = self.query_one("#fido2-touch-bar", CountdownBar)
        cbar.remaining_seconds = self.remaining_seconds
        self._timer = self.set_interval(0.25, self._tick)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        self.remaining_seconds -= 0.25
        self.pulse_step += 1

        pulse_widget = self.query_one("#fido2-touch-pulse", Static)
        frame = self.PULSE_FRAMES[self.pulse_step % len(self.PULSE_FRAMES)]
        pulse_widget.update(frame)

        cbar = self.query_one("#fido2-touch-bar", CountdownBar)
        cbar.remaining_seconds = max(0.0, self.remaining_seconds)
        cbar.is_expired = self.remaining_seconds <= 0.0

        lbl = self.query_one("#fido2-touch-countdown", Static)
        rem_int = max(0, int(round(self.remaining_seconds)))
        lbl.update(f"Waiting for physical touch... {rem_int}s remaining")

        if self.remaining_seconds <= 0.0:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
            self.dismiss(False)

    def action_cancel_touch(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.dismiss(False)

    def action_simulate_touch(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.dismiss(True)

    def touch_received(self) -> None:
        """Invoked programmatically or via device callback upon touch confirmation."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.dismiss(True)

    @on(Button.Pressed, "#btn-simulate-touch")
    def on_touch_pressed(self) -> None:
        self.action_simulate_touch()

    @on(Button.Pressed, "#btn-cancel-touch")
    def on_cancel_pressed(self) -> None:
        self.action_cancel_touch()


class DashboardScreen(Screen):
    """Primary dashboard screen containing header, sidebar, workspace, and status."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("escape", "quit", "Quit", show=False),
        Binding("b", "choose_backend", "Backend", show=False),
        Binding("p", "configure_scope", "Scope", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("f1", "show_help", "Help", show=False),
        Binding("1", "action(1)", "Browse & show", show=False),
        Binding("2", "action(2)", "Browse & copy", show=False),
        Binding("3", "action(3)", "Show code", show=False),
        Binding("4", "action(4)", "Copy code", show=False),
        Binding("5", "action(5)", "Add OTP entry", show=False),
        Binding("6", "action(6)", "Saved scope", show=False),
        Binding("7", "action(7)", "Doctor", show=False),
        Binding("8", "action(8)", "Install preview", show=False),
        Binding("9", "action(9)", "Migration guide", show=False),
        Binding("a", "action(5)", "Add OTP entry", show=False),
        Binding("e", "action(5)", "Add OTP entry", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("u", "audit_action", "Audit Vault", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header")
        with Horizontal(id="main-container"):
            yield ActionListView(id="sidebar")
            yield DetailWorkspace(id="workspace")
        yield SessionStatusPanel(id="status-panel")
        yield KeyboardFooter(id="footer")
        yield MinSizeWarning(id="min-size-warning")

    def on_resize(self, event: events.Resize) -> None:
        width, height = event.size.width, event.size.height
        too_small = width < 60 or height < 18
        compact_w = 60 <= width < 80
        compact_h = 18 <= height < 24

        self.set_class(too_small, "too-small")
        self.set_class(compact_w, "compact-width")
        self.set_class(compact_h, "compact-height")

        try:
            sidebar = self.query_one(ActionListView)
            sidebar.compact = compact_w
        except NoMatches:
            pass

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_index is not None:
            try:
                workspace = self.query_one(DetailWorkspace)
                workspace.selected_index = event.option_index
            except NoMatches:
                pass

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index is not None:
            self.app.trigger_action(event.option_index + 1)

    def action_cursor_down(self) -> None:
        self.query_one(ActionListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ActionListView).action_cursor_up()

    def action_quit(self) -> None:
        self.app.action_quit()

    def action_choose_backend(self) -> None:
        self.app.action_choose_backend()

    def action_configure_scope(self) -> None:
        self.app.action_saved_scope()

    def action_show_help(self) -> None:
        self.app.action_show_help()

    def action_audit_action(self) -> None:
        self.app.action_audit_action()

    def action_action(self, number: int) -> None:
        self.app.trigger_action(number)

    def action_action_1(self) -> None:
        self.app.trigger_action(1)

    def action_action_2(self) -> None:
        self.app.trigger_action(2)

    def action_action_3(self) -> None:
        self.app.trigger_action(3)

    def action_action_4(self) -> None:
        self.app.trigger_action(4)

    def action_action_5(self) -> None:
        self.app.trigger_action(5)

    def action_action_6(self) -> None:
        self.app.trigger_action(6)

    def action_action_7(self) -> None:
        self.app.trigger_action(7)

    def action_action_8(self) -> None:
        self.app.trigger_action(8)

    def action_action_9(self) -> None:
        self.app.trigger_action(9)

    def action_1(self) -> None:
        self.app.trigger_action(1)

    def action_2(self) -> None:
        self.app.trigger_action(2)

    def action_3(self) -> None:
        self.app.trigger_action(3)

    def action_4(self) -> None:
        self.app.trigger_action(4)

    def action_5(self) -> None:
        self.app.trigger_action(5)

    def action_6(self) -> None:
        self.app.trigger_action(6)

    def action_7(self) -> None:
        self.app.trigger_action(7)

    def action_8(self) -> None:
        self.app.trigger_action(8)

    def action_9(self) -> None:
        self.app.trigger_action(9)

    def action_add_otp(self) -> None:
        self.app.trigger_action(5)


class AuthyApp(App):
    """Modern Textual Application replacing the curses dashboard."""

    TITLE = "Authy Local"
    SUB_TITLE = "PRIVATE OTP CONSOLE"

    CSS = """
    Screen {
        background: $surface;
        color: ansi_white;
    }

    DashboardScreen {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    HeaderBar {
        height: 2;
        dock: top;
        padding: 0 1;
        layout: vertical;
        background: transparent;
    }

    #header-title {
        color: cyan;
        text-style: bold;
    }

    #header-backend {
        color: ansi_white;
    }

    #main-container {
        height: 1fr;
        width: 100%;
        layout: horizontal;
    }

    ActionListView {
        width: 25;
        height: 100%;
        border: round cyan;
        border-title-align: left;
        border-title-color: cyan;
        scrollbar-gutter: stable;
        background: transparent;
    }

    ActionListView > .option-list--option {
        padding: 0 1;
        color: ansi_white;
    }

    ActionListView > .option-list--option-highlighted {
        background: cyan;
        color: black;
        text-style: bold;
    }

    DetailWorkspace {
        width: 1fr;
        height: 100%;
        border: round cyan;
        border-title-align: left;
        border-title-color: cyan;
        padding: 1 2;
        background: transparent;
    }

    #workspace-category {
        color: ansi_yellow;
        text-style: bold;
        margin-bottom: 1;
    }

    #workspace-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    #workspace-desc {
        color: ansi_white;
        margin-bottom: 1;
    }

    #workspace-scope-hint {
        color: ansi_bright_black;
    }

    #workspace-policy-hint {
        color: ansi_bright_black;
    }

    SessionStatusPanel {
        height: 3;
        dock: bottom;
        border: round cyan;
        border-title-align: left;
        border-title-color: cyan;
        padding: 0 1;
        background: transparent;
    }

    #status-content {
        color: ansi_white;
    }

    KeyboardFooter {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: transparent;
    }

    #footer-keys {
        color: ansi_white;
    }

    MinSizeWarning {
        display: none;
    }

    #min-size-label {
        color: ansi_yellow;
        text-style: bold;
        content-align: center middle;
    }

    .compact-width ActionListView {
        width: 23;
    }

    .compact-height SessionStatusPanel {
        height: 1;
        border: none;
        padding: 0 1;
    }

    .too-small #header,
    .too-small #main-container,
    .too-small #status-panel,
    .too-small #footer {
        display: none;
    }

    .too-small MinSizeWarning {
        display: block;
        width: 100%;
        height: 100%;
        content-align: center middle;
    }

    /* ModalScreen Common Styles & Backdrop */
    ModalScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #doctor-dialog,
    #prompt-dialog,
    #code-dialog,
    #preview-dialog,
    #guide-dialog,
    #scope-dialog,
    #message-dialog,
    #delete-dialog,
    #backend-select-dialog,
    #help-dialog,
    #wheel-dialog,
    #qr-dialog,
    #audit-dialog {
        width: 72;
        height: auto;
        max-width: 95%;
        max-height: 90%;
        background: $surface;
        border: round cyan;
        padding: 1 2;
    }

    /* Doctor Modal */
    #doctor-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    #doctor-status-banner {
        padding: 0 1;
        margin-bottom: 1;
        background: $surface-lighten-1;
        border-left: tall cyan;
    }

    #doctor-probe-scroll {
        height: 12;
        margin-bottom: 1;
        scrollbar-gutter: stable;
    }

    .probe-section-header {
        margin-top: 1;
        margin-bottom: 0;
        color: cyan;
        text-style: bold;
    }

    .probe-row {
        height: 1;
        margin: 0;
        align: left middle;
    }

    .probe-name {
        width: 1fr;
        color: ansi_white;
    }

    .probe-badge {
        width: 16;
        text-align: right;
        text-style: bold;
    }

    .badge-available {
        color: green;
    }

    .badge-missing {
        color: red;
    }

    .badge-unknown {
        color: yellow;
    }

    .badge-not-applicable {
        color: cyan;
    }

    #doctor-actions {
        height: 3;
        align: right middle;
    }

    #doctor-actions Button {
        margin-left: 1;
    }

    /* Prompt Item Modal */
    #prompt-dialog {
        width: 68;
        max-width: 90%;
    }

    #prompt-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    #prompt-item-input {
        margin-bottom: 0;
    }

    #prompt-validation-error {
        color: red;
        height: 1;
        margin-bottom: 0;
    }

    #prompt-suggestions {
        height: 6;
        margin-top: 1;
        margin-bottom: 1;
        border: round ansi_bright_black;
        scrollbar-gutter: stable;
    }

    #prompt-button-bar {
        height: 3;
        align: right middle;
    }

    #prompt-button-bar Button {
        margin-left: 1;
    }

    /* Code Display Modal */
    #code-dialog {
        width: 54;
        align: center middle;
        text-align: center;
    }

    #code-title {
        color: cyan;
        text-style: bold;
        text-align: center;
        margin-bottom: 0;
    }

    #code-item-label {
        color: ansi_bright_black;
        text-align: center;
        margin-bottom: 1;
    }

    #code-digits {
        color: ansi_bright_cyan;
        text-style: bold;
        text-align: center;
        background: $surface-lighten-1;
        border: double cyan;
        padding: 1 2;
        margin: 1 4;
    }

    #code-progress {
        width: 80%;
        margin: 0 4;
    }

    /* Reactive TotpProgressBar */
    TotpProgressBar {
        width: 100%;
        height: 1;
        content-align: center middle;
        text-align: center;
        margin: 0 2;
    }

    TotpProgressBar.time-normal {
        color: ansi_green;
    }

    TotpProgressBar.time-warning {
        color: ansi_yellow;
    }

    TotpProgressBar.time-critical {
        color: ansi_red;
        text-style: bold;
    }

    TotpProgressBar.time-expired {
        color: ansi_bright_black;
    }

    /* Dynamic Theme Transitions on Modal Dialog */
    #code-dialog.time-normal #code-timer-label {
        color: ansi_green;
    }

    #code-dialog.time-warning #code-timer-label {
        color: ansi_yellow;
    }

    #code-dialog.time-critical #code-timer-label {
        color: ansi_red;
        text-style: bold;
    }

    #code-dialog.time-critical #code-digits {
        border: double ansi_red;
    }

    /* Expired Dialog Theme */
    #code-dialog.time-expired #code-timer-label {
        color: ansi_red;
        text-style: bold;
    }

    #code-dialog.time-expired #code-digits {
        border: double ansi_bright_black;
        color: ansi_bright_black;
    }

    #code-timer-label {
        color: ansi_yellow;
        text-align: center;
        margin-top: 0;
        margin-bottom: 1;
    }

    #code-disclaimer {
        color: ansi_bright_black;
        text-align: center;
        margin-bottom: 1;
    }

    #code-actions {
        height: 3;
        align: center middle;
    }

    #code-actions Button {
        margin: 0 1;
    }

    /* Message Modal */
    #message-dialog {
        width: 70;
        height: auto;
        max-height: 85%;
    }

    #message-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    #message-scroll {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
        scrollbar-gutter: stable;
    }

    .message-line {
        color: ansi_white;
    }

    #message-footer {
        color: ansi_bright_black;
        margin-bottom: 1;
    }

    #message-button-bar {
        height: 3;
        align: right middle;
    }

    /* Delete Confirm Modal */
    #delete-dialog {
        width: 62;
        max-width: 90%;
        border: round red;
    }

    #delete-title {
        color: red;
        text-style: bold;
        margin-bottom: 1;
    }

    #delete-backend {
        color: ansi_bright_black;
    }

    #delete-entry-label {
        color: ansi_white;
        margin: 1 0;
        text-style: bold;
    }

    #delete-warning {
        color: ansi_yellow;
        margin-bottom: 1;
    }

    #delete-confirm-input {
        border: round red;
        margin-bottom: 1;
    }

    #delete-button-bar {
        height: 3;
        align: right middle;
    }

    #delete-button-bar Button {
        margin-left: 1;
    }

    /* Token Browser Screen */
    TokenBrowserScreen {
        layout: vertical;
        width: 100%;
        height: 100%;
        background: $surface;
        color: ansi_white;
    }

    #browser-header {
        height: 3;
        dock: top;
        padding: 0 1;
    }

    #browser-title {
        color: cyan;
        text-style: bold;
    }

    #browser-subtitle {
        color: ansi_bright_black;
    }

    #search-container {
        height: 3;
        padding: 0 1;
        align-vertical: middle;
    }

    #search-label {
        width: 9;
        color: cyan;
        text-style: bold;
        padding-top: 1;
    }

    #search-input {
        width: 1fr;
        border: round cyan;
    }

    #search-input:focus {
        border: double cyan;
    }

    #match-count-badge {
        width: 32;
        text-align: right;
        color: ansi_yellow;
        text-style: bold;
        padding-top: 1;
        padding-right: 1;
    }

    #column-header-bar {
        height: 1;
        padding: 0 2;
        background: $surface-darken-1;
        color: cyan;
        text-style: bold;
    }

    TokenOptionList {
        height: 1fr;
        width: 100%;
        border: round cyan;
        border-title-align: left;
        border-title-color: cyan;
        scrollbar-gutter: stable;
        background: transparent;
        padding: 0;
    }

    TokenOptionList > .option-list--option {
        padding: 0 1;
        color: ansi_white;
    }

    TokenOptionList > .option-list--option-highlighted {
        background: cyan;
        color: black;
        text-style: bold;
    }

    #empty-state-notice {
        height: 1fr;
        width: 100%;
        content-align: center middle;
        color: ansi_yellow;
        text-style: bold;
    }

    #browser-status-panel {
        height: 3;
        dock: bottom;
        border: round cyan;
        padding: 0 1;
    }

    #status-detail {
        color: ansi_white;
    }

    #browser-footer {
        height: 1;
        dock: bottom;
        padding: 0 1;
        color: ansi_white;
    }

    /* Wheel / Install Preview Modal */
    #preview-dialog {
        width: 80;
        height: auto;
        max-width: 95%;
        max-height: 85%;
    }

    #preview-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 0;
    }

    #preview-guarantee {
        color: ansi_yellow;
        text-style: bold;
        margin-bottom: 1;
    }

    #preview-wheel-input {
        margin-bottom: 1;
    }

    #preview-scroll {
        height: 1fr;
        min-height: 6;
        max-height: 12;
        margin-bottom: 1;
        border: round ansi_bright_black;
        scrollbar-gutter: stable;
    }

    #preview-button-bar {
        height: 3;
        align: right middle;
    }

    #preview-button-bar Button {
        margin-left: 1;
        min-width: 14;
    }

    /* Migration Guide Modal */
    #guide-dialog {
        width: 80;
        height: auto;
        max-width: 95%;
        max-height: 85%;
    }

    #guide-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    #guide-scroll {
        height: 1fr;
        min-height: 6;
        max-height: 14;
        margin-bottom: 1;
        scrollbar-gutter: stable;
    }

    .guide-header {
        color: cyan;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    .guide-item {
        color: ansi_white;
        margin-bottom: 0;
    }

    #guide-button-bar {
        height: 3;
        align: right middle;
    }

    #guide-button-bar Button {
        margin-left: 1;
        min-width: 16;
    }

    /* Saved Scope Modal */
    #scope-dialog {
        width: 68;
        max-height: 85%;
    }

    #scope-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 0;
    }

    #scope-privacy-notice {
        color: ansi_bright_black;
        margin-bottom: 1;
    }

    #scope-fields-scroll {
        height: 11;
        margin-bottom: 1;
    }

    #scope-fields-scroll Static {
        margin-top: 1;
        color: ansi_white;
    }

    #scope-fields-scroll Input {
        margin-bottom: 0;
    }

    #scope-error-banner {
        color: red;
        height: 1;
        margin-bottom: 1;
    }

    #scope-actions {
        height: 3;
        align: right middle;
    }

    #scope-actions Button {
        margin-left: 1;
    }

    /* Backend Select Modal */
    #backend-select-dialog {
        width: 52;
        max-height: 80%;
    }

    #backend-select-title {
        color: cyan;
        text-style: bold;
        margin-bottom: 1;
    }

    #backend-select-list {
        height: 5;
        margin-bottom: 1;
    }

    #backend-button-bar {
        height: 3;
        align: right middle;
    }

    /* Help Modal */
    #help-dialog {
        width: 76;
        height: auto;
        max-width: 95%;
        max-height: 85%;
        background: $surface;
        border: round cyan;
        padding: 1 2;
    }

    #help-title {
        color: cyan;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    #help-scroll {
        height: 1fr;
        scrollbar-gutter: stable;
    }

    .help-line {
        color: ansi_white;
        margin-bottom: 1;
    }

    #help-button-bar {
        height: 3;
        align: right middle;
    }

    #btn-close-help {
        min-width: 18;
    }

    /* Add OTP Modal */
    #add-otp-dialog {
        width: 76;
        height: auto;
        max-width: 95%;
        max-height: 90%;
        border: heavy cyan;
        background: #111b27;
        padding: 1 2;
    }

    #add-otp-title {
        color: cyan;
        text-style: bold;
        content-align: center middle;
        margin-bottom: 0;
    }

    #add-otp-desc {
        color: ansi_bright_black;
        content-align: center middle;
        margin-bottom: 1;
    }

    #add-otp-scroll {
        height: auto;
        max-height: 24;
        scrollbar-gutter: stable;
        margin-bottom: 1;
    }

    .field-label {
        color: cyan;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    #secret-actions-bar {
        height: 3;
        margin-top: 1;
        margin-bottom: 1;
    }

    #secret-actions-bar Button {
        margin-right: 1;
    }

    #qr-file-row {
        height: 3;
        margin-top: 0;
        margin-bottom: 1;
    }

    #inp-qr-file-path {
        width: 1fr;
        margin-right: 1;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-col {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    .form-col-sm {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }

    #live-preview-box {
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }

    #lbl-live-code {
        width: 16;
        color: ansi_bright_green;
        text-style: bold;
        background: #0d2818;
        padding: 0 1;
        border: round #2ecc71;
        content-align: center middle;
        margin-right: 2;
    }

    #target-backends-box {
        height: auto;
        layout: vertical;
        margin-bottom: 1;
    }

    #target-backends-box Checkbox {
        margin-bottom: 0;
    }

    #add-otp-status-banner {
        color: ansi_yellow;
        text-style: bold;
        min-height: 1;
        margin-bottom: 1;
    }

    #add-otp-button-bar {
        height: 3;
        align: right middle;
    }

    #add-otp-button-bar Button {
        margin-left: 1;
        min-width: 16;
    }

    /* QR Code Modal */
    #qr-dialog {
        width: 60;
        height: auto;
        max-width: 95%;
        max-height: 90%;
        border: heavy cyan;
        background: #111b27;
        padding: 1 2;
    }
    #qr-title {
        color: cyan;
        text-style: bold;
        content-align: center middle;
    }
    #qr-item-label {
        color: ansi_yellow;
        content-align: center middle;
        margin-bottom: 1;
    }
    #qr-scroll {
        height: auto;
        max-height: 28;
        content-align: center middle;
    }
    #qr-content {
        content-align: center middle;
    }
    #qr-footer-hint {
        color: ansi_bright_black;
        content-align: center middle;
        margin-top: 1;
    }

    /* Audit Modal */
    #audit-dialog {
        width: 76;
        height: auto;
        max-width: 95%;
        max-height: 90%;
        border: heavy cyan;
        background: #111b27;
        padding: 1 2;
    }
    #audit-title {
        color: cyan;
        text-style: bold;
        content-align: center middle;
    }
    #audit-summary-badge {
        content-align: center middle;
        margin-bottom: 1;
    }
    #audit-scroll {
        height: auto;
        max-height: 22;
        scrollbar-gutter: stable;
        margin-bottom: 1;
    }
    .audit-finding {
        margin-bottom: 1;
    }

    /* Toast Notification System */
    ToastRack {
        layer: _toastrack;
        align: right top;
        dock: top;
        width: 1fr;
        height: auto;
        margin-top: 1;
        margin-right: 2;
        background: transparent;
    }

    Toast {
        width: auto;
        min-width: 26;
        max-width: 72;
        height: auto;
        padding: 0 1;
        border: heavy #2ecc71;
        background: #0f2e1a;
        color: ansi_bright_white;
        text-style: bold;
        margin-bottom: 1;
    }

    Toast .toast--title {
        color: #2ecc71;
        text-style: bold;
    }

    /* Compact overrides (60x18 terminals) */
    .compact-width ToastRack {
        margin-top: 0;
        margin-right: 1;
    }

    .compact-width Toast {
        min-width: 20;
        max-width: 56;
        padding: 0 1;
    }

    /* Compact Modal Overrides */
    .compact-width #doctor-dialog,
    .compact-width #prompt-dialog,
    .compact-width #code-dialog,
    .compact-width #scope-dialog,
    .compact-width #delete-dialog,
    .compact-width #backend-select-dialog {
        width: 56;
        padding: 0 1;
    }

    .compact-width #help-dialog {
        width: 58;
        padding: 0 1;
    }

    .compact-height #doctor-dialog,
    .compact-height #guide-dialog,
    .compact-height #preview-dialog,
    .compact-height #scope-dialog {
        height: auto;
        max-height: 90%;
        padding: 0 1;
    }

    .compact-height #help-dialog {
        height: auto;
        max-height: 90%;
        padding: 0 1;
    }

    .compact-height #doctor-probe-scroll {
        height: 1fr;
        min-height: 5;
        max-height: 8;
    }

    .compact-height #scope-fields-scroll {
        height: 1fr;
        min-height: 5;
        max-height: 8;
    }

    .compact-height #guide-scroll {
        height: 1fr;
        min-height: 5;
        max-height: 8;
    }

    .compact-height #help-scroll {
        height: 1fr;
        min-height: 5;
        max-height: 8;
    }

    .compact-height #preview-scroll {
        height: 1fr;
        min-height: 5;
        max-height: 7;
    }
    """

    SCREENS = {
        "dashboard": DashboardScreen,
        "doctor": DoctorModal,
        "prompt_item": PromptItemModal,
        "code_display": CodeDisplayModal,
        "install_preview": InstallPreviewModal,
        "migration_guide": MigrationGuideModal,
        "saved_scope": SavedScopeModal,
        "message": MessageModal,
        "fido2_touch": Fido2TouchModal,
    }

    BINDINGS = [
        Binding("ctrl+c", "force_quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("f1", "show_help", "Help", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
    ]

    current_backend: reactive[str] = reactive("onepassword")
    session_status: reactive[str] = reactive("Local capabilities not checked")
    _last_copy_toast_time: float = 0.0

    def __init__(
        self,
        dispatch: Callable | None = None,
        preview: Callable | None = None,
        profiles: dict[str, dict[str, str]] | None = None,
        save_profiles: Callable[[dict], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.dispatch_callback = dispatch
        self.preview_callback = preview
        self.profiles = dict(profiles or {})
        self.save_profiles_callback = save_profiles
        self._cached_catalog: dict[str, list[tuple[str, str]]] = {}

    def on_mount(self) -> None:
        self.push_screen("dashboard")

    def watch_current_backend(self, new_backend: str) -> None:
        if not self.is_running:
            return
        try:
            self.screen.query_one(HeaderBar).backend = new_backend
        except Exception:
            pass

    def watch_session_status(self, new_status: str) -> None:
        if not self.is_running:
            return
        try:
            self.screen.query_one(SessionStatusPanel).status = new_status
        except Exception:
            pass

    def on_resize(self, event: events.Resize) -> None:
        width, height = event.size.width, event.size.height
        too_small = width < 60 or height < 18
        compact_w = 60 <= width < 80
        compact_h = 18 <= height < 24

        self.set_class(too_small, "too-small")
        self.set_class(compact_w, "compact-width")
        self.set_class(compact_h, "compact-height")

    def notify_copy(self, item_label: str = "", *, custom_message: str | None = None) -> None:
        """Post a standardized high-contrast clipboard copy confirmation toast."""
        self._last_copy_toast_time = time.monotonic()
        if custom_message:
            msg = custom_message
        elif item_label:
            srv, acc, _ = parse_token_parts(self.current_backend, item_label, item_label)
            short = f"{srv} ({acc})" if acc else srv
            msg = f"[bold green]✓[/] [bold white]Copied to clipboard:[/] [bold cyan]{short}[/]"
        else:
            msg = "[bold green]✓[/] [bold white]Copied to clipboard[/]"

        self.notify(msg, timeout=2.5)

    async def on_event(self, event: events.Event) -> None:
        if isinstance(event, (events.Key, events.Click)):
            if getattr(self, "_last_copy_toast_time", 0.0) > 0 and (
                time.monotonic() - self._last_copy_toast_time > 0.08
            ):
                if (
                    hasattr(self, "clear_notifications")
                    and len(getattr(self, "_notifications", ())) > 0
                ):
                    self.clear_notifications()
                self._last_copy_toast_time = 0.0
        await super().on_event(event)

    @contextmanager
    def safe_suspend(self):
        """Safely suspend Textual application if running and supported."""
        if (
            not self.is_running
            or self._driver is None
            or not getattr(self._driver, "can_suspend", False)
        ):
            yield
            return
        try:
            with self.suspend():
                yield
        finally:
            if self._driver is not None and getattr(
                self._driver, "is_application_mode_suspended", False
            ):
                try:
                    self._driver.resume_application_mode()
                    self._resume_signal()
                    self.refresh(layout=True)
                except Exception:
                    pass

    def _is_event_hammering(self) -> bool:
        """Detect rapid event hammering (e.g. adversarial test / key flood)."""
        now = time.perf_counter()
        queue_has_keys = any(
            isinstance(m, events.Key)
            for m in getattr(getattr(self, "_message_queue", None), "values", ())
        )
        if queue_has_keys:
            self._hammering_until = now + 0.15
            return True
        if getattr(self, "_hammering_until", 0.0) > now:
            return True
        return False

    def on_key(self, event: events.Key) -> None:
        now = time.perf_counter()
        last_t = getattr(self, "_last_event_time", 0.0)
        delta = now - last_t
        self._last_event_time = now
        queue_has_keys = any(
            isinstance(m, events.Key)
            for m in getattr(getattr(self, "_message_queue", None), "values", ())
        )
        if (delta < 0.01 and last_t > 0.0) or queue_has_keys:
            self._hammering_until = now + 0.15

    def _can_open_dialog(self) -> bool:
        if not self.is_running:
            return False
        if self._is_event_hammering():
            return False
        try:
            return self.screen is self.get_screen("dashboard")
        except Exception:
            return False

    def action_force_quit(self) -> None:
        from .processes import terminate_all_children

        terminate_all_children()
        try:
            self.workers.cancel_all()
        except Exception:
            pass
        self.exit(130)

    def action_quit(self) -> None:
        from .processes import terminate_all_children

        terminate_all_children()
        try:
            self.workers.cancel_all()
        except Exception:
            pass
        self.exit(0)

    def trigger_action(self, action_number: int) -> None:
        """Trigger an action by number (1 to 9)."""
        if action_number == 1:
            self.action_browse_show()
        elif action_number == 2:
            self.action_browse_copy()
        elif action_number == 3:
            self.action_show_code()
        elif action_number == 4:
            self.action_copy_code()
        elif action_number == 5:
            self.action_add_otp()
        elif action_number == 6:
            self.action_saved_scope()
        elif action_number == 7:
            self.action_doctor()
        elif action_number == 8:
            self.action_install_preview()
        elif action_number == 9:
            self.action_migration_guide()

    def action_add_otp(self) -> None:
        if self._can_open_dialog():
            self.push_screen(
                AddOtpModal(current_backend=self.current_backend, profiles=self.profiles)
            )

    def action_doctor(self) -> tuple[int, str | None, list[str]]:
        status, summary, lines = self.execute(["doctor"])
        states = {}
        for line in lines:
            name, sep, state = line.partition(": ")
            if sep and state in {"available", "missing", "unknown", "not-applicable"}:
                states[name] = state
        if self._can_open_dialog():
            self.push_screen(DoctorModal(states=states, summary=summary or "", status=status))
        return status, summary, lines

    def action_show_code(self) -> None:
        if self._can_open_dialog():
            self._ensure_scope_and_run(action_mode="show")

    def action_copy_code(self) -> None:
        if self._can_open_dialog():
            self._ensure_scope_and_run(action_mode="copy")

    def _ensure_scope_and_run(self, action_mode: str) -> None:
        backend = self.current_backend
        if backend in ("yubikey", "tpm2-totp", "keychain", "dpapi", "fido2"):
            self._prompt_item_and_execute(backend, action_mode)
            return
        if backend not in self.profiles:

            def on_scope_saved(new_profiles):
                if new_profiles and backend in new_profiles:
                    self._prompt_item_and_execute(backend, action_mode)

            if self.is_running:
                self.push_screen(SavedScopeModal(backend=backend), on_scope_saved)
        else:
            self._prompt_item_and_execute(backend, action_mode)

    def _prompt_item_and_execute(self, backend: str, action_mode: str) -> None:
        profile = self.profiles.get(backend, {})

        def on_item_selected(selection: tuple[str, str] | None) -> None:
            if selection is None:
                return
            key, mode = selection
            from .tui_items import arguments

            try:
                cli_args = [mode] + arguments(backend, profile, key)
            except Exception:
                cli_args = [mode, key]

            async def run_execute() -> None:
                self.session_status = f"Executing {mode}..."
                touch_modal = None
                if backend == "fido2" and self.is_running:
                    touch_modal = Fido2TouchModal(account=key)
                    self.push_screen(touch_modal)

                try:
                    status, summary, lines = await self.aexecute(cli_args)
                finally:
                    if touch_modal is not None and touch_modal.is_mounted:
                        touch_modal.dismiss(True)
                if status == 0 and mode == "show":
                    code = lines[1] if len(lines) > 1 else ""

                    def refresh_code() -> str | None:
                        st, _, lns = self.execute(
                            cli_args, on_success_modal=False, on_error_modal=False
                        )
                        if st == 0 and len(lns) > 1:
                            return lns[1]
                        return None

                    if self.is_running:
                        self.push_screen(
                            CodeDisplayModal(
                                code=code,
                                item_label=key,
                                backend=backend,
                                refresh_callback=refresh_code,
                            )
                        )
                elif status == 0 and mode == "copy":
                    if self.is_running:
                        self.notify_copy(key)
                else:
                    if self.is_running:
                        self.push_screen(MessageModal("Operation Failed", lines))

            self.run_worker(run_execute())

        cached = self._cached_catalog.get(backend)
        if cached is None:
            cached = self.load_records(backend, profile)
            if cached is not None:
                self._cached_catalog[backend] = cached

        if self.is_running:
            self.push_screen(
                PromptItemModal(
                    backend=backend,
                    profile=profile,
                    action_mode=action_mode,
                    cached_records=cached,
                ),
                on_item_selected,
            )

    def action_browse_show(self) -> None:
        if self._can_open_dialog():
            self._open_browser(default_action="show")

    def action_browse_copy(self) -> None:
        if self._can_open_dialog():
            self._open_browser(default_action="copy")

    def _open_browser(self, default_action: str) -> None:
        backend = self.current_backend
        if backend in ("yubikey", "tpm2-totp", "keychain", "dpapi", "fido2"):
            self._launch_browser(backend, default_action)
            return
        if backend not in self.profiles:

            def on_scope_saved(new_profiles):
                if new_profiles and backend in new_profiles:
                    self._launch_browser(backend, default_action)

            if self.is_running:
                self.push_screen(SavedScopeModal(backend=backend), on_scope_saved)
        else:
            self._launch_browser(backend, default_action)

    def _launch_browser(self, backend: str, default_action: str) -> None:
        profile = self.profiles.get(backend, {})

        async def run_launch() -> None:
            self.session_status = "Loading item records..."
            rows = await self.aload_records(backend, profile)
            if rows is None:
                if self.is_running:
                    err_code = getattr(self, "_last_record_failure", 3) or 3
                    self.session_status = "Backend item query failed"
                    self.push_screen(MessageModal("Error", [MESSAGES.get(err_code, MESSAGES[3])]))
                return
            if self.is_running:
                self.session_status = f"Loaded {len(rows)} item records"
                self.push_screen(
                    TokenBrowserScreen(
                        backend=backend,
                        profile=profile,
                        records=rows,
                        default_action=default_action,
                    )
                )

        self.run_worker(run_launch())

    def action_install_preview(self) -> None:
        if self._can_open_dialog():
            self.push_screen(InstallPreviewModal())

    def action_migration_guide(self) -> None:
        if self._can_open_dialog():
            self.push_screen(MigrationGuideModal())

    def action_saved_scope(self) -> None:
        if self._can_open_dialog():
            self.push_screen(
                SavedScopeModal(
                    backend=self.current_backend,
                    initial=self.profiles.get(self.current_backend),
                )
            )

    def action_choose_backend(self) -> None:
        if self._can_open_dialog():
            self.push_screen(BackendSelectModal(current_backend=self.current_backend))

    def action_show_help(self) -> None:
        if not self.is_running:
            return
        if self._is_event_hammering():
            return
        if isinstance(self.screen, HelpModal):
            self.pop_screen()
            return
        self.push_screen(HelpModal())

    def execute(
        self,
        args: list[str],
        *,
        on_success_modal: bool = True,
        on_error_modal: bool = True,
    ) -> tuple[int, str | None, list[str]]:
        """Bridge method executing CLI dispatch while safely suspending Textual.

        Returns:
            tuple[int, str | None, list[str]]:
                - status: CLI exit code (0 on success, >0 on error)
                - summary: Session status summary string (for Doctor)
                - lines: Sanitized display lines
        """
        output, diagnostic = Capture(), Capture()
        status = 3

        if (
            args
            and args[0] in ("show", "select")
            and "--allow-pipe" not in args
            and "--copy" not in args
        ):
            args = list(args) + ["--allow-pipe"]

        try:
            if args[0] == "preview":
                if self.preview_callback is not None:
                    status = self.preview_callback(args[1], output, diagnostic)
                else:
                    status = 3
            elif self.dispatch_callback is not None:
                status = self.dispatch_callback(args, output, diagnostic)
            else:
                status = 3
        except AppError as error:
            status = error.exit_code
        except KeyboardInterrupt:
            status = 130
        except Exception:
            status = 3

        lines: list[str] = []
        summary: str | None = None

        if args[0] == "doctor":
            names = {
                "platform",
                "python",
                "op",
                "fish",
                "fzf",
                "wl-copy",
                "pbcopy",
                "clock",
                "authentication",
                "pass",
                "gpg",
                "oathtool",
                "totpm",
                "yubikey",
                "tpm2-totp",
                "tpm-device",
                "keychain",
                "secure-enclave",
                "dpapi",
                "credman",
                "windows-hello",
                "fido2",
                "qrencode",
                "pinentry",
                "gpg-agent",
            }
            states = {}
            for line in output.getvalue().splitlines():
                name, separator, state = line.partition(": ")
                if (
                    separator
                    and name in names
                    and state
                    in {
                        "available",
                        "missing",
                        "unknown",
                        "not-applicable",
                    }
                ):
                    states[name] = state
            lines = [f"{name}: {state}" for name, state in states.items()]
            if status or not lines:
                status = status or 5
                lines.append(MESSAGES.get(status, MESSAGES[3]))
                summary = f"Doctor failed (exit {status}); press 1 to retry"
            else:
                summary_states = ["available", "missing", "unknown"]
                if any(value == "not-applicable" for value in states.values()):
                    summary_states.append("not-applicable")
                summary = "Doctor: " + ", ".join(
                    f"{sum(value == state for value in states.values())} {state}"
                    for state in summary_states
                )
        elif status:
            lines = [MESSAGES.get(status, MESSAGES[3])]
        elif args[0] in ("show", "select") and "--copy" not in args:
            try:
                lines = ["Code", parse_code(output.getvalue().encode("ascii"))]
            except AppError, UnicodeError:
                lines = [MESSAGES[5]]
                status = 5
        elif args[0] == "preview":
            lines = ["Preview only; no changes authorized.", *output.getvalue().splitlines()]
        else:
            lines = ["Copy completed. Clipboard history behavior is controlled by your desktop."]

        output.close()
        diagnostic.close()

        if summary is not None:
            self.session_status = summary

        return status, summary, lines

    def load_records(self, backend: str, profile: dict[str, str]) -> list[tuple[str, str]] | None:
        """Fetch item metadata for browser cleanly without screen flashing."""
        from .tui_items import records

        failure = None
        rows = None
        try:
            rows = records(backend, profile, dict(os.environ))
        except AppError as error:
            failure = error.exit_code
        except KeyboardInterrupt:
            failure = 130
        except Exception:
            failure = 3

        if failure is not None:
            self._last_record_failure = failure
            return None
        self._last_record_failure = None
        return rows

    def delete_record(self, backend: str, profile: dict[str, str], key: str) -> bool:
        """Delete one confirmed local entry cleanly without screen flashing."""
        from .tui_items import remove

        failure = None
        try:
            remove(backend, profile, key, dict(os.environ))
        except AppError as error:
            failure = error.exit_code
        except KeyboardInterrupt:
            failure = 130
        except Exception:
            failure = 3

        if failure is not None:
            return False
        return True

    async def aexecute(
        self,
        args: list[str],
        *,
        on_success_modal: bool = True,
        on_error_modal: bool = True,
    ) -> tuple[int, str | None, list[str]]:
        """Asynchronously execute backend command off the main event loop thread."""
        return await asyncio.to_thread(
            self.execute,
            args,
            on_success_modal=on_success_modal,
            on_error_modal=on_error_modal,
        )

    async def aload_records(
        self, backend: str, profile: dict[str, str]
    ) -> list[tuple[str, str]] | None:
        """Asynchronously load records off the main event loop thread."""
        return await asyncio.to_thread(self.load_records, backend, profile)

    async def adelete_record(self, backend: str, profile: dict[str, str], key: str) -> bool:
        """Asynchronously delete record off the main event loop thread."""
        return await asyncio.to_thread(self.delete_record, backend, profile, key)

    async def aget_token_uri(self, backend: str, profile: dict[str, str], key: str) -> str | None:
        """Asynchronously retrieve otpauth URI for a token."""

        def _fetch() -> str | None:
            from .exporters import collect_backend_tokens

            try:
                tokens = collect_backend_tokens(backend, profile, dict(os.environ))
                for t in tokens:
                    if (
                        t.account == key
                        or f"{t.issuer}/{t.account}" == key
                        or t.secret == key
                        or t.issuer == key
                    ):
                        return t.to_uri()
                if len(tokens) == 1:
                    return tokens[0].to_uri()
            except Exception:
                pass
            return None

        return await asyncio.to_thread(_fetch)

    def action_show_token_qr(self, item_label: str, backend: str) -> None:
        """Fetch token URI and push interactive QR modal."""

        async def run_qr() -> None:
            qrencode_bin = shutil.which("qrencode", path=os.environ.get("PATH", ""))
            if not qrencode_bin:
                self.notify("qrencode is missing. Install via pacman.", severity="warning")
                return
            profile = self.profiles.get(backend, {})
            self.session_status = "Generating QR code..."
            uri = await self.aget_token_uri(backend, profile, item_label)
            if not uri:
                self.notify("Secret URI not available for this token.", severity="warning")
                return
            from .errors import AppError
            from .processes import run

            try:
                res = run(
                    [qrencode_bin, "-t", "UTF8", uri],
                    env=dict(os.environ),
                    timeout=5,
                    stdout_cap=65536,
                )
                if res.returncode == 0 and res.stdout:
                    qr_text = res.stdout.decode("utf-8", errors="replace")
                    self.push_screen(InteractiveQrModal(qr_text, item_label=item_label))
                else:
                    self.notify("Failed to render QR code.", severity="error")
            except AppError:
                self.notify("Failed to render QR code.", severity="error")

        self.run_worker(run_qr())

    def action_audit_action(self) -> None:
        """Audit active backend vault credentials and push report modal."""

        async def run_audit() -> None:
            self.session_status = "Running vault audit..."
            self.notify("Auditing vault credentials...", timeout=2)
            profile = self.profiles.get(self.current_backend, {})

            def _do_audit():
                from .auditor import audit_tokens
                from .exporters import collect_backend_tokens

                try:
                    tokens = collect_backend_tokens(self.current_backend, profile, dict(os.environ))
                except Exception:
                    tokens = []
                return audit_tokens(tokens, backend=self.current_backend)

            report = await asyncio.to_thread(_do_audit)
            self.push_screen(AuditReportModal(report, backend=self.current_backend))

        self.run_worker(run_audit())


def run(dispatch: Callable, *, preview: Callable | None = None, terminal: bool = True) -> int:
    """Launch the Textual TUI with CLI dispatch callbacks and private profiles.

    Args:
        dispatch: Callback executing CLI core actions (show, copy, doctor, select).
        preview: Optional callback executing installer dry-run preview.
        terminal: Flag verifying interactive terminal capability.

    Returns:
        int: Standard Unix exit code (0 = clean exit, 130 = SIGINT/Ctrl+C, 3 = error).
    """
    if not terminal:
        return 3

    try:
        from .tui_profiles import load, save

        profiles = load()

        app = AuthyApp(
            dispatch=dispatch,
            preview=preview,
            profiles=profiles,
            save_profiles=save,
        )
        result = app.run()
        return result if isinstance(result, int) else 0

    except AppError:
        raise
    except KeyboardInterrupt:
        return 130
    except ImportError, OSError, UnicodeError:
        return 3
    except Exception:
        return 3
    finally:
        from .processes import terminate_all_children

        terminate_all_children()
