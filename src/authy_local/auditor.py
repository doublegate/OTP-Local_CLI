"""Credential Security, Hygiene, and Entropy Auditor v2 for stored OTP tokens."""

import base64
import math
import os
import re
import secrets
import shutil
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from .enrollment import OtpParameters, clean_base32
from .processes import run

# Known test vectors and sample secrets that should never be used in production
KNOWN_TEST_SEEDS = {
    "JBSWY3DPEHPK3PXP",  # RFC 6238 "Hello!"
    "GEZDGNBVGY3TQOJQ",  # RFC 4226 "1234567890"
    "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",  # RFC 4226 Appendix D 32-char
    "AAAAAAAAAAAAAAAA",  # All zeros
    "2345672345672345",  # Sequential
}


@dataclass
class AuditFinding:
    rule_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    title: str
    accounts: list[str]
    description: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditReport:
    backend: str
    total_tokens: int
    findings: list[AuditFinding]
    score: int
    grade: str
    rotations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "total_tokens": self.total_tokens,
            "score": self.score,
            "grade": self.grade,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "rotations": self.rotations,
        }


def _token_label(token: OtpParameters) -> str:
    if token.issuer and token.account:
        return f"{token.issuer} ({token.account})"
    return token.issuer or token.account or "unlabeled_entry"


def calculate_shannon_entropy(secret: str) -> float:
    """Calculate Shannon entropy in bits per character for a given string.

    Max theoretical entropy for Base32 (32 symbols) is 5.0 bits/char.
    """
    if not secret:
        return 0.0
    counts: dict[str, int] = {}
    for char in secret:
        counts[char] = counts.get(char, 0) + 1
    total = len(secret)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def check_time_drift(env: dict[str, str]) -> dict[str, Any]:
    """Inspect local clock drift and NTP synchronization against RFC 6238 timing boundaries."""
    # Synthetic test hook
    if "FAKE_TIME_SKEW_SECONDS" in env:
        try:
            skew = float(env["FAKE_TIME_SKEW_SECONDS"])
            return {
                "synchronized": abs(skew) < 1.0,
                "offset_seconds": skew,
                "skew_severity": "CRITICAL"
                if abs(skew) >= 5.0
                else ("HIGH" if abs(skew) >= 1.5 else "LOW"),
            }
        except ValueError:
            pass

    clock_bin = shutil.which("timedatectl", path=env.get("PATH", ""))
    if clock_bin:
        try:
            obs = run(
                [clock_bin, "timesync-status"],
                env=env,
                timeout=3,
                stdout_cap=4096,
            )
            if obs.returncode == 0 and obs.stdout:
                m = re.search(rb"Offset:\s*([+-]?\d+(?:\.\d+)?)\s*(us|ms|s)", obs.stdout)
                if m:
                    val = float(m.group(1))
                    unit = m.group(2).decode("ascii")
                    if unit == "ms":
                        val /= 1000.0
                    elif unit == "us":
                        val /= 1_000_000.0
                    return {
                        "synchronized": abs(val) < 1.0,
                        "offset_seconds": val,
                        "skew_severity": "HIGH" if abs(val) >= 2.0 else "LOW",
                    }
        except Exception:
            pass

    return {"synchronized": True, "offset_seconds": 0.0, "skew_severity": "NONE"}


def scan_environment_leaks(
    tokens: list[OtpParameters],
    env: dict[str, str],
    pid: int | None = None,
) -> list[AuditFinding]:
    """Scan process environment and shell history for accidentally leaked OTP seeds."""
    leaked_accounts: list[str] = []

    # Map normalized secrets to token labels
    secret_to_label: dict[str, str] = {}
    for t in tokens:
        try:
            clean = clean_base32(t.secret)
            if len(clean) >= 16 and clean not in KNOWN_TEST_SEEDS:
                secret_to_label[clean] = _token_label(t)
        except Exception:
            pass

    if not secret_to_label:
        return []

    # 1. Scan environment variables
    for k, v in env.items():
        if k.startswith("FAKE_"):
            continue
        for sec, label in secret_to_label.items():
            if sec in v:
                leaked_accounts.append(f"{label} (in env var ${k})")

    # 2. Scan process environ and command-line arguments if accessible
    proc_candidates = []
    fake_proc = env.get("FAKE_PROC_ENVIRON")
    if fake_proc:
        proc_candidates.append(fake_proc)
    fake_cmdline = env.get("FAKE_PROC_CMDLINE")
    if fake_cmdline:
        proc_candidates.append(fake_cmdline)

    curr_pid = pid or os.getpid()
    for ppath in (f"/proc/{curr_pid}/environ", f"/proc/{curr_pid}/cmdline"):
        if os.path.isfile(ppath):
            proc_candidates.append(ppath)

    for proc_path in proc_candidates:
        try:
            with open(proc_path, "rb") as f:
                raw = f.read().replace(b"\x00", b" ").decode("utf-8", errors="replace")
                for sec, label in secret_to_label.items():
                    if sec in raw:
                        desc = f"{label} (in process {os.path.basename(proc_path)})"
                        if desc not in leaked_accounts:
                            leaked_accounts.append(desc)
        except Exception:
            pass

    # 3. Scan shell history if present
    hist_candidates = []
    fake_hist = env.get("FAKE_SHELL_HISTORY")
    if fake_hist:
        hist_candidates.append(fake_hist)
    else:
        home = env.get("HOME")
        if home:
            for fname in (".bash_history", ".zsh_history", ".local/share/fish/fish_history"):
                p = os.path.join(home, fname)
                if os.path.isfile(p):
                    hist_candidates.append(p)

    for hist_path in hist_candidates:
        try:
            with open(hist_path, "r", errors="replace") as f:
                content = f.read()
                for sec, label in secret_to_label.items():
                    if sec in content:
                        desc = f"{label} (in shell history {os.path.basename(hist_path)})"
                        if desc not in leaked_accounts:
                            leaked_accounts.append(desc)
        except Exception:
            pass

    if leaked_accounts:
        return [
            AuditFinding(
                rule_id="SEC-007",
                severity="HIGH",
                title="Secret Key Leaked in Process Environment or Shell History",
                accounts=sorted(leaked_accounts),
                description="Plaintext secret seeds were identified in process environment variables or shell history logs.",
                recommendation="Rotate affected secrets and purge shell history / environment configurations.",
            )
        ]
    return []


def generate_rotation_advice(
    report: AuditReport,
    tokens: list[OtpParameters],
) -> list[dict[str, Any]]:
    """Generate cryptographically secure rotation recommendations for vulnerable tokens."""
    flagged_labels = set()
    reasons: dict[str, str] = {}
    for f in report.findings:
        if f.severity in ("CRITICAL", "HIGH"):
            for acc in f.accounts:
                # Strip metadata suffixes like [length: ...]
                base_acc = re.sub(r"\s*\[[^\]]+\]\s*$", "", acc).strip()
                flagged_labels.add(base_acc)
                reasons[base_acc] = f.title

    rotations: list[dict[str, Any]] = []
    for t in tokens:
        label = _token_label(t)
        if (
            label in flagged_labels
            or t.account in flagged_labels
            or (t.issuer and t.issuer in flagged_labels)
        ):
            # Generate new 160-bit (20 bytes -> 32 Base32 chars) high-entropy secret
            new_bytes = secrets.token_bytes(20)
            new_secret = base64.b32encode(new_bytes).decode("ascii").rstrip("=")
            rot = {
                "account": t.account,
                "issuer": t.issuer,
                "label": label,
                "reason": reasons.get(label, "Security finding"),
                "old_algorithm": t.algorithm,
                "recommended_algorithm": "SHA256" if t.algorithm == "SHA1" else t.algorithm,
                "new_secret": new_secret,
                "new_uri": f"otpauth://totp/{label}?secret={new_secret}&algorithm={t.algorithm}&digits={t.digits}",
            }
            rotations.append(rot)
    return rotations


def audit_tokens(
    tokens: list[OtpParameters],
    backend: str = "local",
    env: dict[str, str] | None = None,
    rotate: bool = False,
) -> AuditReport:
    """Analyze a list of OTP tokens for security vulnerabilities, entropy, and hygiene issues."""
    findings: list[AuditFinding] = []
    score = 100

    if not tokens:
        return AuditReport(
            backend=backend,
            total_tokens=0,
            findings=[],
            score=100,
            grade="A+",
        )

    # 1. Check for Duplicate Secrets (CRITICAL)
    secret_map: dict[str, list[str]] = defaultdict(list)
    for t in tokens:
        try:
            norm_secret = clean_base32(t.secret)
        except Exception:
            norm_secret = t.secret
        secret_map[norm_secret].append(_token_label(t))

    for _secret, labels in secret_map.items():
        if len(labels) > 1:
            findings.append(
                AuditFinding(
                    rule_id="SEC-001",
                    severity="CRITICAL",
                    title="Shared Seed / Duplicate Secret Re-use",
                    accounts=sorted(labels),
                    description=(
                        f"{len(labels)} accounts share the exact same OTP secret. "
                        "Compromise of one service exposes all associated accounts."
                    ),
                    recommendation="Re-enroll each service with a distinct, randomly generated MFA seed.",
                )
            )
            score -= min(30, 15 * (len(labels) - 1))

    # 2. Check for Weak / Low-Entropy Secrets and Known Sample Seeds (HIGH)
    weak_accounts = []
    test_seed_accounts = []
    low_entropy_accounts = []

    for t in tokens:
        label = _token_label(t)
        try:
            norm_secret = clean_base32(t.secret)
        except Exception:
            norm_secret = t.secret

        entropy = calculate_shannon_entropy(norm_secret)

        if norm_secret in KNOWN_TEST_SEEDS:
            test_seed_accounts.append(label)
        elif len(norm_secret) < 16:
            weak_accounts.append(f"{label} [length: {len(norm_secret)} chars / <80 bits]")
        elif entropy < 2.5 and len(norm_secret) >= 16:
            low_entropy_accounts.append(f"{label} [Shannon entropy: {entropy:.2f} bits/char]")

    if test_seed_accounts:
        findings.append(
            AuditFinding(
                rule_id="SEC-002",
                severity="HIGH",
                title="Known Sample / Default Test Seed In Use",
                accounts=sorted(test_seed_accounts),
                description="One or more accounts use published documentation test vectors as secret keys.",
                recommendation="Replace immediately with production MFA keys generated by your identity provider.",
            )
        )
        score -= 20 * len(test_seed_accounts)

    if weak_accounts:
        findings.append(
            AuditFinding(
                rule_id="SEC-003",
                severity="HIGH",
                title="Weak Secret (<80 bits or trivial entropy)",
                accounts=sorted(weak_accounts),
                description="Secrets under 16 Base32 characters fail RFC 4226 minimum entropy recommendations.",
                recommendation="Ensure secret keys are generated with at least 80 bits (16+ Base32 characters) of entropy.",
            )
        )
        score -= 10 * len(weak_accounts)

    if low_entropy_accounts:
        findings.append(
            AuditFinding(
                rule_id="SEC-005",
                severity="HIGH",
                title="Low Shannon Entropy Secret (<2.5 bits/char)",
                accounts=sorted(low_entropy_accounts),
                description="Secret exhibits highly repetitive patterns or predictable character distributions.",
                recommendation="Replace with a cryptographically secure pseudo-random Base32 seed.",
            )
        )
        score -= 10 * len(low_entropy_accounts)

    # 3. Check for Non-Standard / Deprecated Algorithms (MEDIUM)
    algo_accounts = []
    for t in tokens:
        algo = t.algorithm.upper()
        if algo not in {"SHA1", "SHA256", "SHA512", "STEAM"}:
            algo_accounts.append(f"{_token_label(t)} [algorithm: {t.algorithm}]")

    if algo_accounts:
        findings.append(
            AuditFinding(
                rule_id="SEC-004",
                severity="MEDIUM",
                title="Unsupported or Deprecated Digest Algorithm",
                accounts=sorted(algo_accounts),
                description="Token algorithm is unrecognized or not conforming to RFC 6238 standards.",
                recommendation="Migrate to standard SHA1, SHA256, or SHA512 digest algorithms.",
            )
        )
        score -= 10 * len(algo_accounts)

    # 4. Check for Non-Standard Digits / Period (INFO)
    non_std_params = []
    for t in tokens:
        if t.algorithm == "STEAM":
            continue
        if t.digits not in (6, 8):
            non_std_params.append(f"{_token_label(t)} [digits: {t.digits}]")
        elif t.token_type == "totp" and t.period not in (30, 60):
            non_std_params.append(f"{_token_label(t)} [period: {t.period}s]")

    if non_std_params:
        findings.append(
            AuditFinding(
                rule_id="HYG-001",
                severity="INFO",
                title="Non-Standard Token Parameters",
                accounts=sorted(non_std_params),
                description="Token uses non-standard digit counts or calculation periods.",
                recommendation="Verify that authenticator client apps support these non-standard parameters.",
            )
        )
        score -= 2 * len(non_std_params)

    # 5. Check for Missing or Ambiguous Metadata (LOW)
    hygiene_accounts = []
    for t in tokens:
        if not t.issuer and (not t.account or t.account in {"account", "entry"}):
            hygiene_accounts.append(_token_label(t))

    if hygiene_accounts:
        findings.append(
            AuditFinding(
                rule_id="HYG-002",
                severity="LOW",
                title="Ambiguous or Missing Token Metadata",
                accounts=sorted(hygiene_accounts),
                description="Token lacks descriptive issuer and account metadata, risking operator confusion.",
                recommendation="Assign clear service and username labels to distinguish accounts.",
            )
        )
        score -= 2 * len(hygiene_accounts)

    # 6. Environmental Leak Scans (T-AUTH-118)
    if env:
        leak_findings = scan_environment_leaks(tokens, env)
        for lf in leak_findings:
            findings.append(lf)
            score -= 15 * len(lf.accounts)

        # 7. Time Drift Analysis (T-AUTH-117)
        drift = check_time_drift(env)
        if not drift["synchronized"] or drift["offset_seconds"] >= 1.0:
            skew_sec = drift["offset_seconds"]
            findings.append(
                AuditFinding(
                    rule_id="SEC-006",
                    severity=drift["skew_severity"],
                    title="Host Time Drift Exceeds RFC 6238 Synchronization Window",
                    accounts=["System Clock"],
                    description=f"System clock is skewed by {skew_sec:+.2f} seconds relative to reference NTP.",
                    recommendation="Synchronize system time via timedatectl, chrony, or NTP.",
                )
            )
            score -= 15

    # Calculate final score and grade
    final_score = max(0, min(100, score))
    if final_score >= 95:
        grade = "A+"
    elif final_score >= 90:
        grade = "A"
    elif final_score >= 80:
        grade = "B"
    elif final_score >= 70:
        grade = "C"
    elif final_score >= 60:
        grade = "D"
    else:
        grade = "F"

    # Sort findings by severity order
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))

    report = AuditReport(
        backend=backend,
        total_tokens=len(tokens),
        findings=findings,
        score=final_score,
        grade=grade,
    )

    if rotate:
        report.rotations = generate_rotation_advice(report, tokens)

    return report


def format_audit_report(report: AuditReport) -> str:
    """Format AuditReport as clean, structured plain text for terminal output."""
    lines = [
        "=" * 78,
        "OTP Credential Security & Hygiene Audit",
        f"Backend: {report.backend} | Total Accounts Inspected: {report.total_tokens}",
        "=" * 78,
        "",
    ]

    if not report.findings:
        lines.append("All inspected tokens conform to security and hygiene best practices.")
        lines.append("No duplicate seeds, weak keys, or metadata deficiencies detected.")
        lines.append("")
    else:
        for idx, f in enumerate(report.findings, start=1):
            lines.append(f"[{f.severity}] {f.rule_id}: {f.title}")
            lines.append("  Affected Accounts:")
            for acc in f.accounts:
                lines.append(f"    * {acc}")
            lines.append(f"  Description:    {f.description}")
            lines.append(f"  Recommendation: {f.recommendation}")
            if idx < len(report.findings):
                lines.append("-" * 78)

    lines.append("=" * 78)
    lines.append("Audit Summary:")
    lines.append(f"  Accounts Inspected:       {report.total_tokens}")
    crit = sum(1 for f in report.findings if f.severity == "CRITICAL")
    high = sum(1 for f in report.findings if f.severity == "HIGH")
    med = sum(1 for f in report.findings if f.severity == "MEDIUM")
    low = sum(1 for f in report.findings if f.severity in ("LOW", "INFO"))
    lines.append(f"  Critical Vulnerabilities: {crit}")
    lines.append(f"  High Severity Issues:     {high}")
    lines.append(f"  Medium Severity Issues:   {med}")
    lines.append(f"  Hygiene Notices:          {low}")
    lines.append(f"  Security Score:           {report.score} / 100 (Grade: {report.grade})")

    if report.rotations:
        lines.append("-" * 78)
        lines.append("Guided Secret Rotation Recommendations:")
        for r in report.rotations:
            lines.append(f"  * Account: {r['label']}")
            lines.append(f"    Reason:  {r['reason']}")
            lines.append(f"    New Key: {r['new_secret']}")
            lines.append(f"    New URI: {r['new_uri']}")

    lines.append("=" * 78)
    return "\n".join(lines) + "\n"
