"""Validate authored local links, task allocation, and immutable reference."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "ref-docs/Authy-to-1Password-and-Local-CLI-TOTP-Migration-Runbook-v2.md"
EXPECTED = "d4ae68a822ee2652c690aa155e071adce43561984826c0462bd5d01748e0faca"


def main():
    failures = []
    files = list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md"))
    files += list((ROOT / "to-dos").rglob("*.md"))
    files = [p for p in files if p.name not in ("AGENTS.md", "CLAUDE.md", "GEMINI.md")]
    for path in files:
        for destination in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            target = destination.split("#")[0]
            if target and "://" not in target and not target.startswith("mailto:"):
                if not (path.parent / target).exists():
                    failures.append(f"Missing local link: {path.relative_to(ROOT)}")
    tasks = []
    for path in (ROOT / "to-dos/sprints").glob("*.md"):
        tasks += re.findall(r"^- \[[ x]\] \*\*(T-AUTH-\d+):", path.read_text(), re.M)
    expected_tasks = {f"T-AUTH-{i:03}" for i in range(10, 62)} | {
        f"T-AUTH-{i:03}" for i in range(70, 78)
    }
    if len(tasks) != 60 or set(tasks) != expected_tasks:
        failures.append("Sprint task allocation changed or contains duplicate IDs")
    if hashlib.sha256(REF.read_bytes()).hexdigest() != EXPECTED:
        failures.append("Immutable reference hash changed")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Documentation PASS: {len(files)} files; links, task IDs, reference hash")


if __name__ == "__main__":
    main()
