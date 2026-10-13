"""Isolated opaque-box E2E test harness for Authy-to-1Password Local."""

import dataclasses
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from authy_local import cli, tui, tui_profiles
from authy_local.installer import InstallError, operate

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_WHEEL = REPO_ROOT / "dist" / "authy_local-1.0.0-py3-none-any.whl"


class MockCurses:
    KEY_RESIZE = 410
    KEY_BACKSPACE = 263
    KEY_UP = 259
    KEY_DOWN = 258
    KEY_LEFT = 260
    KEY_RIGHT = 261
    KEY_ENTER = 10
    A_BOLD = 1
    A_REVERSE = 2
    COLOR_CYAN = 6
    COLOR_BLACK = 0

    class error(Exception):
        pass

    def __init__(self):
        self.events = []
        self.dashboard_colors = {"border": 0, "selected": 0}

    def def_prog_mode(self):
        self.events.append("save")

    def endwin(self):
        self.events.append("suspend")

    def reset_prog_mode(self):
        self.events.append("restore")

    def doupdate(self):
        self.events.append("update")

    def has_colors(self):
        return False


class MockScreen:
    def __init__(self, keys=(), size=(24, 80)):
        self.key_list = list(keys)
        self.index = 0
        self.size = size
        self.frames = []
        self.current = []
        self.encoding = "UTF-8"

    def getmaxyx(self):
        return self.size

    def erase(self):
        if self.current:
            self.frames.append(list(self.current))
        self.current = []

    def addnstr(self, row, column, text, width):
        self.current.append(str(text)[:width])

    def refresh(self):
        pass

    def getch(self):
        if self.index < len(self.key_list):
            k = self.key_list[self.index]
            self.index += 1
            return k
        # Fallback sequence: Escape first to dismiss modals/browser, then 'q' to exit dashboard
        self.index += 1
        return 27 if self.index == len(self.key_list) + 1 else ord("q")

    def attron(self, attr):
        pass

    def attroff(self, attr):
        pass

    def all_text(self) -> str:
        all_lines = []
        for frame in self.frames:
            all_lines.extend(frame)
        all_lines.extend(self.current)
        return " ".join(all_lines)

    def has_text(self, substring: str) -> bool:
        return substring in self.all_text()


@dataclasses.dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str


class E2EEnvironment:
    """Hermetic isolated environment for E2E testing."""

    def __init__(self):
        self._temp_dir = tempfile.TemporaryDirectory(prefix="e2e-authy-")
        self.home = Path(self._temp_dir.name)
        self.bin_dir = self.home / "bin"
        self.bin_dir.mkdir(parents=True, mode=0o700)
        self.clipboard_file = self.home / "clipboard.txt"
        self.calls_log = self.home / "mock_calls.jsonl"
        self.wheel_path = self.home / "authy_local-1.0.0-py3-none-any.whl"

        # Setup mock executables
        self._setup_mock_op()
        self._setup_mock_clipboard()
        self._setup_mock_clock()
        self._setup_mock_fzf()
        self._setup_wheel()

        self.env = {
            "HOME": str(self.home),
            "PATH": str(self.bin_dir),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "WAYLAND_DISPLAY": "wayland-0",
            "MOCK_CALLS": str(self.calls_log),
            "MOCK_CLIPBOARD": str(self.clipboard_file),
            "PYTHONPATH": os.environ.get("PYTHONPATH", str(REPO_ROOT / "src")),
        }

    def _setup_mock_op(self):
        op_script = self.bin_dir / "op"
        op_script.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "calls = os.environ.get('MOCK_CALLS')\n"
            "if calls:\n"
            "    with open(calls, 'a') as f:\n"
            "        f.write(json.dumps({'bin': 'op', 'argv': sys.argv[1:]}) + '\\n')\n"
            "if sys.argv[1:] == ['--version']:\n"
            "    print('2.39.0')\n"
            "    sys.exit(0)\n"
            "if len(sys.argv) > 1 and sys.argv[1] == 'item':\n"
            "    if sys.argv[2] == 'get':\n"
            "        if '--otp' in sys.argv:\n"
            "            code = os.environ.get('MOCK_OTP_CODE', '001234')\n"
            "            print(code)\n"
            "            sys.exit(0)\n"
            "    elif sys.argv[2] == 'list':\n"
            "        vault_id = 'v' * 26\n"
            "        if '--vault' in sys.argv:\n"
            "            vault_id = sys.argv[sys.argv.index('--vault') + 1]\n"
            "        items = [\n"
            "            {'id': 'a' * 26, 'title': 'GitHub [prod]', 'vault': {'id': vault_id}},\n"
            "            {'id': 'b' * 26, 'title': 'AWS Root Account', 'vault': {'id': vault_id}},\n"
            "            {'id': 'c' * 26, 'title': 'Google Workspace', 'vault': {'id': vault_id}},\n"
            "        ]\n"
            "        print(json.dumps(items))\n"
            "        sys.exit(0)\n"
            "print('unknown op command', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        op_script.chmod(0o700)

    def _setup_mock_clipboard(self):
        wl_copy = self.bin_dir / "wl-copy"
        wl_copy.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            "dest = os.environ.get('MOCK_CLIPBOARD')\n"
            "content = sys.stdin.read()\n"
            "if dest:\n"
            "    with open(dest, 'w') as f:\n"
            "        f.write(content)\n"
            "sys.exit(0)\n"
        )
        wl_copy.chmod(0o700)

    def _setup_mock_clock(self):
        clock = self.bin_dir / "timedatectl"
        clock.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "if sys.argv[1:] == ['show', '--property=NTPSynchronized', '--value']:\n"
            "    print('yes')\n"
            "    sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        clock.chmod(0o700)

    def _setup_mock_fzf(self):
        fzf = self.bin_dir / "fzf"
        fzf.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "if '--help' in sys.argv:\n"
            "    print('--accept-nth --delimiter')\n"
            "    sys.exit(0)\n"
            "print('0')\n"
            "sys.exit(0)\n"
        )
        fzf.chmod(0o700)

    def _setup_wheel(self):
        if DIST_WHEEL.exists():
            self.wheel_path.write_bytes(DIST_WHEEL.read_bytes())
        else:
            # Fallback placeholder if wheel not in dist
            import zipfile
            with zipfile.ZipFile(self.wheel_path, "w") as z:
                z.writestr(
                    "authy_local-1.0.0.dist-info/METADATA",
                    "Metadata-Version: 2.1\nName: authy-local\nVersion: 1.0.0\n",
                )

    def clipboard_content(self) -> str:
        if self.clipboard_file.exists():
            return self.clipboard_file.read_text()
        return ""

    def save_profile(self, profiles: dict):
        tui_profiles.save(profiles, self.home)

    def load_profiles(self) -> dict:
        return tui_profiles.load(self.home)

    def invoke_cli(
        self,
        args: list[str],
        stdin: str = "",
        isatty: bool = True,
        stdout_isatty: bool | None = None,
        extra_env: dict | None = None,
    ) -> CLIResult:
        merged_env = dict(self.env)
        if extra_env:
            merged_env.update(extra_env)
        out, err = io.StringIO(), io.StringIO()
        effective_stdout_isatty = isatty if stdout_isatty is None else stdout_isatty
        out.isatty = lambda: effective_stdout_isatty
        with patch.dict(os.environ, merged_env, clear=True), patch("authy_local.cli.has_terminal", return_value=isatty):
            code = cli.main(args, stdin=io.StringIO(stdin), stdout=out, stderr=err)
        return CLIResult(exit_code=code, stdout=out.getvalue(), stderr=err.getvalue())

    def run_tui(self, keys: list[int], profiles: dict = None, size=(24, 80)) -> tuple[int, MockScreen]:
        screen = MockScreen(keys, size=size)
        curses = MockCurses()
        if profiles is not None:
            self.save_profile(profiles)
        active_profiles = self.load_profiles()

        def dispatch(arguments, output, diagnostic):
            with patch.dict(os.environ, self.env, clear=True), patch("authy_local.cli.has_terminal", return_value=True):
                return cli.main(arguments, stdin=io.StringIO(), stdout=output, stderr=diagnostic)

        def preview(wheel, output, diagnostic):
            try:
                plan = operate("install", self.home, wheel=Path(wheel))
                output.write("PREVIEW (no changes)\n" + "\n".join(plan) + "\n")
                return 0
            except (InstallError, OSError, ValueError):
                return 3

        with patch.dict(os.environ, self.env, clear=True):
            exit_code = tui.session(
                screen,
                dispatch,
                curses,
                preview=preview,
                profiles=active_profiles,
                save_profiles=self.save_profile,
            )
        return exit_code, screen

    def cleanup(self):
        self._temp_dir.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
