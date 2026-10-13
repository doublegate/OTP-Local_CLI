"""Copy public operator specs into the wheel; --check refuses stale bundles."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = {
    "optional": "specs/08-optional-backends.md",
    "setup": "operations/2026-10-12-optional-setup.md",
    "acceptance": "operations/2026-10-12-phase-4-5-operator-checkpoints.md",
    "migration": "specs/07-migration-and-recovery.md",
    "recovery": "specs/09-operations-and-completion.md",
    "tui": "specs/11-tui.md",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "src/authy_local/guides"
    for topic, source in GUIDES.items():
        content = (ROOT / "docs" / source).read_bytes()
        target = destination / (topic + ".md")
        if args.check:
            if not target.is_file() or target.read_bytes() != content:
                raise SystemExit("Installed guide bundle is stale; run scripts/bundle_guides.py")
        else:
            # These are generated public documentation, never private ledger data.
            if target.exists():
                target.read_bytes()
            target.write_bytes(content)
    print("Guide bundle PASS")


if __name__ == "__main__":
    main()
