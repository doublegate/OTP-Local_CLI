"""Fish wrappers preserve argument boundaries and statuses without credentials."""

import shutil
import subprocess
import unittest
from pathlib import Path


class FishTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("fish"), "fish unavailable")
    def test_syntax_and_argument_status(self):
        from authy_local.installer import WRAPPERS

        for name, command in (("otp1p", "show"), ("otp1pc", "copy"), ("otp1pf", "select")):
            source = Path("fish") / f"{name}.fish"
            self.assertEqual(source.read_text(), WRAPPERS[source.name])
            syntax = subprocess.run(["fish", "-n", str(source)], capture_output=True)
            self.assertEqual(syntax.returncode, 0)
            script = (
                "function otp-local; printf '%s\\n' $argv; return 17; end; "
                f"source {source}; {name} 'two words' '--account' 'scope'; exit $status"
            )
            result = subprocess.run(["fish", "--no-config", "-c", script], capture_output=True)
            self.assertEqual(result.returncode, 17)
            self.assertEqual(result.stdout, f"{command}\ntwo words\n--account\nscope\n".encode())
