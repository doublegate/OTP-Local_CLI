"""Synthetic executable integration checks for interactive sinks."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authy_local import cli

A, V, ITEM = "a" * 26, "v" * 26, "i" * 26


class UX(unittest.TestCase):
    def setUp(self):
        root = Path("/tmp/Authy-to-1Password_Local")
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root, prefix="ux-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.log = self.home / "calls"
        program = (
            f"#!{sys.executable}\n"
            + """
import os,sys,json
from pathlib import Path
name=Path(sys.argv[0]).name
if sys.argv[1:]==['--version']:
 print('2.39.0');sys.exit()
if sys.argv[1:]==['--help']:
 print('--accept-nth --delimiter');sys.exit()
with open(os.environ['LOG'],'a') as f:
 f.write(json.dumps([name,sys.argv[1:],{k:v for k,v in os.environ.items() if k.startswith('FZF_')}])+'\\n')
if name=='op':
 if '--encoding' in sys.argv: sys.exit(1)
 if os.getsid(0)!=int(os.environ['EXPECTED_SID']): sys.exit(1)
 if sys.argv[1:3]==['item','list']:
  print(Path(os.environ['META_FILE']).read_text())
 else:
  print(os.environ.get('CODE','001234'))
 sys.exit(int(os.environ.get('FAKE_OP_EXIT','0')))
data=sys.stdin.buffer.read()
if name=='fzf':
 Path(os.environ['ROWS']).write_bytes(data)
 print(os.environ.get('CHOSEN','0'))
 sys.exit(int(os.environ.get('FAKE_FZF_EXIT','0')))
Path(os.environ['COPIED']).write_bytes(data)
sys.stderr.write('PRIVATE_DIAGNOSTIC')
sys.exit(int(os.environ.get('COPY_EXIT','0')))
"""
        )
        for name in ("op", "fzf", "wl-copy"):
            path = self.home / name
            path.write_text(program)
            path.chmod(0o700)
        self.env = {
            "PATH": str(self.home),
            "EXPECTED_SID": str(os.getsid(0)),
            "LOG": str(self.log),
            "ROWS": str(self.home / "rows"),
            "COPIED": str(self.home / "copied"),
            "WAYLAND_DISPLAY": "synthetic",
            "META": json.dumps([{"id": ITEM, "title": "Synthetic", "vault": {"id": V}}]),
        }

    def invoke(self, command="select", *, terminal=True, copying=False, **env):
        args = [command]
        if command == "copy":
            args.append(ITEM)
        args.extend(["--account", A, "--vault", V])
        if copying:
            args.append("--copy")
        out, err = io.StringIO(), io.StringIO()
        out.isatty = lambda: True
        merged = self.env | env
        metadata_file = self.home / "metadata.json"
        metadata_file.write_text(merged.pop("META"))
        merged["META_FILE"] = str(metadata_file)
        with patch.dict(os.environ, merged, clear=True):
            with patch.object(cli, "has_terminal", return_value=terminal):
                status = cli.main(args, stdout=out, stderr=err)
        self.assertNotIn("PRIVATE_DIAGNOSTIC", out.getvalue() + err.getvalue())
        return status, out.getvalue()

    def calls(self):
        return (
            [json.loads(x)[0] for x in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )

    def test_select_retrieves_only_selected_id(self):
        self.assertEqual(self.invoke(), (0, "001234\n"))
        self.assertEqual(self.calls(), ["op", "fzf", "op"])
        records = [json.loads(x) for x in self.log.read_text().splitlines()]
        argv = records[-1][1]
        self.assertEqual(argv[2], ITEM)
        self.assertEqual(argv[argv.index("--account") + 1], A)
        self.assertEqual(argv[argv.index("--vault") + 1], V)

    def test_local_picker_returns_only_original_key_and_neutralizes_labels(self):
        from authy_local.interaction import choose_records

        rows = [("first", "unsafe\x1b\tname"), ("second", "Synthetic")]
        env = self.env | {"CHOSEN": "1", "FZF_DEFAULT_OPTS": "--preview=unsafe"}
        self.assertEqual(choose_records(rows, env), "second")
        rendered = (self.home / "rows").read_bytes()
        self.assertNotIn(b"\x1b", rendered)
        self.assertEqual(rendered.count(b"\t"), 2)
        self.assertEqual(self.calls(), ["fzf"])

    def test_local_picker_rejects_forgery_and_propagates_cancel(self):
        from authy_local.errors import AppError
        from authy_local.interaction import choose_records

        for env, expected in (
            ({"CHOSEN": "99"}, 6),
            ({"CHOSEN": "01"}, 6),
            ({"FAKE_FZF_EXIT": "130"}, 130),
        ):
            with self.subTest(env=env), self.assertRaises(AppError) as caught:
                choose_records([("first", "Synthetic")], self.env | env)
            self.assertEqual(caught.exception.exit_code, expected)

    def test_local_picker_empty_or_unsupported_tool_fails_before_selection(self):
        from authy_local.errors import AppError
        from authy_local.interaction import choose_records
        from authy_local.processes import Completed

        with self.assertRaises(AppError):
            choose_records([], self.env)
        with patch("authy_local.interaction.run", return_value=Completed(0, b"old help")):
            with self.assertRaises(AppError) as caught:
                choose_records([("first", "Synthetic")], self.env)
            self.assertEqual(caught.exception.exit_code, 3)

    def test_select_copy_only_explicitly_selected_item(self):
        self.assertEqual(self.invoke(copying=True), (0, ""))
        self.assertEqual(self.calls(), ["op", "fzf", "op", "wl-copy"])
        self.assertEqual((self.home / "copied").read_bytes(), b"001234")

    def test_copy_has_no_stdout_and_code_only_stdin(self):
        self.assertEqual(self.invoke("copy"), (0, ""))
        self.assertEqual((self.home / "copied").read_bytes(), b"001234")

    def test_cancel_never_retrieves_or_copies(self):
        for status in (1, 130):
            self.assertEqual(self.invoke(FAKE_FZF_EXIT=str(status))[0], 130)
        self.assertNotIn("wl-copy", self.calls())
        self.assertEqual(self.calls().count("op"), 2)

    def test_forged_selection_is_failure(self):
        for choice in ("-1", "1", "00", "x", "0\n0", "0\x1b[0m"):
            with self.subTest(choice=choice):
                self.assertEqual(self.invoke(CHOSEN=choice)[0], 6)
        self.assertNotIn("wl-copy", self.calls())

    def test_metadata_boundary_rejects_invalid_records(self):
        good = {"id": ITEM, "title": "Synthetic", "vault": {"id": V}}
        for metadata in (
            "{}",
            "null",
            "[null]",
            "[{}]",
            "not-json",
            json.dumps([good, good]),
            json.dumps([good | {"vault": {"id": A}}]),
            json.dumps([good | {"title": 42}]),
            json.dumps([good] * 5001),
        ):
            with self.subTest(metadata=metadata[:30]):
                self.assertEqual(self.invoke(META=metadata)[0], 5)
        self.assertNotIn("fzf", self.calls())

    def test_empty_list_has_no_selector(self):
        self.assertEqual(self.invoke(META="[]")[0], 4)
        self.assertEqual(self.calls(), ["op"])

    def test_labels_are_bounded_and_controls_escaped(self):
        meta = [{"id": ITEM, "title": "evil\n\t\x1b\u202e" + "a" * 400, "vault": {"id": V}}]
        self.assertEqual(self.invoke(META=json.dumps(meta))[0], 0)
        row = (self.home / "rows").read_text()
        self.assertEqual(row.count("\n"), 1)
        self.assertEqual(row.count("\t"), 1)
        self.assertNotIn("\x1b", row)
        self.assertNotIn("\u202e", row)
        self.assertLess(len(row), 200)

    def test_fzf_environment_cannot_inject_commands(self):
        self.assertEqual(
            self.invoke(
                FZF_DEFAULT_OPTS="--preview=evil",
                FZF_DEFAULT_COMMAND="evil",
                FZF_DEFAULT_OPTS_FILE="evil",
            )[0],
            0,
        )
        calls = [json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertEqual(next(x[2] for x in calls if x[0] == "fzf"), {})

    def test_failed_retrieval_or_malformed_code_never_copies(self):
        self.assertEqual(self.invoke("copy", FAKE_OP_EXIT="1")[0], 4)
        self.assertEqual(self.invoke("copy", CODE="not a code")[0], 5)
        self.assertNotIn("wl-copy", self.calls())

    def test_copy_failure_is_static_sink_failure(self):
        self.assertEqual(self.invoke("copy", COPY_EXIT="1"), (6, ""))

    def test_missing_capabilities_and_terminal_fail_before_retrieval(self):
        self.assertEqual(self.invoke("copy", terminal=False)[0], 3)
        self.assertEqual(self.invoke("copy", WAYLAND_DISPLAY="")[0], 3)
        (self.home / "wl-copy").unlink()
        self.assertEqual(self.invoke("copy")[0], 3)
        self.assertEqual(self.calls(), [])

    def test_selector_foreign_auth_missing_fzf_and_backend_failure(self):
        self.assertEqual(self.invoke(OP_SESSION="synthetic")[0], 3)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.invoke(FAKE_OP_EXIT="1")[0], 4)
        self.assertEqual(self.calls(), ["op"])
        (self.home / "fzf").unlink()
        self.assertEqual(self.invoke()[0], 3)

    def test_selector_nonzero_and_invalid_utf8_are_static_failures(self):
        self.assertEqual(self.invoke(FAKE_FZF_EXIT="2")[0], 6)
        good = {"id": ITEM, "title": "Synthetic", "vault": {"id": None}}
        self.assertEqual(self.invoke(META=json.dumps([good]))[0], 5)
        good["id"] = None
        self.assertEqual(self.invoke(META=json.dumps([good]))[0], 5)
