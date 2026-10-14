"""Legacy curses-based TUI compatibility layer.

Deprecated; retained for backward compatibility with external test harnesses and legacy bridges.
All modern interactive workflows use Textual in authy_local.tui.
"""

import os
import textwrap
from pathlib import Path

from .errors import MESSAGES, AppError
from .models import parse_code
from .tui import ACTIONS, BACKENDS, GUIDE, HELP, PROFILE_FIELDS, Capture


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
        "bitwarden": {},
        "keepass": {},
        "federated": {},
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
