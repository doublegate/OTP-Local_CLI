"""A closed diagnostic sink must not turn usage errors into tracebacks."""

import io
import unittest
from unittest.mock import patch

from authy_local.cli import main


class ClosedSink(io.StringIO):
    def write(self, value):
        raise BrokenPipeError("SYNTHETIC_PRIVATE_SINK")


class SinkTests(unittest.TestCase):
    def test_usage_failure_preserves_exit_when_stderr_is_closed(self):
        self.assertEqual(main(["unknown"], stdout=io.StringIO(), stderr=ClosedSink()), 2)

    def test_cancel_preserves_exit_when_stderr_is_closed(self):
        with patch("authy_local.cli.parser", side_effect=KeyboardInterrupt):
            self.assertEqual(main([], stdout=io.StringIO(), stderr=ClosedSink()), 130)

    def test_stdout_failure_is_sanitized(self):
        with patch("authy_local.cli.doctor.report", return_value={}):
            self.assertEqual(
                main(["doctor", "--json"], stdout=ClosedSink(), stderr=io.StringIO()), 3
            )


if __name__ == "__main__":
    unittest.main()
