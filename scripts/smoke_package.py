"""Install the built wheel in an isolated scratch environment and check its CLI."""

import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    scratch = Path("/tmp/Authy-to-1Password_Local")
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-smoke-", dir=scratch) as directory:
        home = Path(directory)
        venv.create(home / "venv", with_pip=True)
        wheels = sorted((ROOT / "dist").glob("authy_local-*.whl"))
        if len(wheels) != 1:
            raise SystemExit("Expected exactly one current development wheel")
        python = home / "venv/bin/python"
        env = {"HOME": str(home), "PATH": "", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
        wheelhouse = ROOT / "dist/wheels"
        pip_args = [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--no-index",
        ]
        if wheelhouse.is_dir() and any(wheelhouse.glob("*.whl")):
            pip_args.extend(["--find-links", str(wheelhouse)])
        else:
            pip_args.append("--no-deps")
        pip_args.append(str(wheels[0]))
        subprocess.run(
            pip_args,
            cwd=home,
            env=env,
            check=True,
            timeout=30,
        )
        command = home / "venv/bin/otp-local"
        for arguments in (
            ["--help"],
            ["--version"],
            ["tui", "--help"],
            ["copy", "--help"],
            ["select", "--help"],
            ["enroll", "--help"],
            ["guide", "setup"],
            ["guide", "acceptance"],
            ["guide", "tui"],
        ):
            result = subprocess.run(
                [str(command), *arguments],
                cwd=home,
                env=env,
                check=True,
                capture_output=True,
                timeout=5,
            )
            if not result.stdout or result.stderr:
                raise SystemExit("Packaged CLI smoke check failed")
        subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                "from authy_local import tui, installer, optional_setup; "
                "from authy_local.backends import local; import textual",
            ],
            cwd=home,
            env=env,
            check=True,
            timeout=5,
        )
    print(
        "Package PASS: isolated CLI/TUI/installer wheel (Textual); help/version, no backend access"
    )


if __name__ == "__main__":
    main()
