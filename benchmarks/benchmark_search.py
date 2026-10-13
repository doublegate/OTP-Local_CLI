"""Microbenchmark: Linear uncached search vs pre-indexed ranked fuzzy search."""

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.tui_items import SearchIndex, fuzzy_filter  # noqa: E402


def generate_catalog(count: int) -> list[tuple[str, str]]:
    """Generate representative synthetic token catalog."""
    services = [
        "GitHub",
        "GitLab",
        "AWS",
        "Google",
        "DigitalOcean",
        "Cloudflare",
        "Slack",
        "Stripe",
        "PayPal",
        "Dropbox",
        "Bitbucket",
        "Heroku",
        "Fastmail",
        "ProtonMail",
        "1Password",
        "Bitwarden",
        "Tailscale",
        "NordVPN",
        "Sentry",
        "Datadog",
        "Splunk",
        "Grafana",
        "PagerDuty",
    ]
    accounts = [
        "admin@company.com",
        "ops-team@internal.net",
        "dev@personal.org",
        "billing@corp.io",
        "security@infra.co",
        "sre@cloud.tech",
    ]
    rows = []
    for i in range(count):
        srv = services[i % len(services)]
        acc = accounts[(i // len(services)) % len(accounts)]
        key = f"key_{i:06d}"
        label = f"{srv} ({acc}) [id:{i:04x}]"
        rows.append((key, label))
    return rows


def run_benchmark(counts: tuple[int, ...] = (1000, 5000)) -> dict[int, dict[str, Any]]:
    """Benchmark search latency across catalog sizes and query patterns."""
    queries = ["git", "aws", "security", "infra", "gh"]
    results = {}

    for count in counts:
        rows = generate_catalog(count)
        index = SearchIndex(rows)
        iterations = 50 if count <= 1000 else 15

        # 1. Baseline: linear uncached string search
        start = time.perf_counter()
        for _ in range(iterations):
            for q in queries:
                _ = [(k, lbl) for k, lbl in rows if q.casefold() in lbl.casefold()]
        baseline_sec = (time.perf_counter() - start) / (iterations * len(queries))

        # 2. Direct fuzzy_filter
        start = time.perf_counter()
        for _ in range(iterations):
            for q in queries:
                _ = fuzzy_filter(rows, q)
        direct_sec = (time.perf_counter() - start) / (iterations * len(queries))

        # 3. Pre-Indexed SearchIndex.filter
        start = time.perf_counter()
        for _ in range(iterations):
            for q in queries:
                _ = index.filter(q)
        indexed_sec = (time.perf_counter() - start) / (iterations * len(queries))

        results[count] = {
            "baseline_ms": baseline_sec * 1000,
            "direct_fuzzy_ms": direct_sec * 1000,
            "indexed_fuzzy_ms": indexed_sec * 1000,
            "speedup_vs_baseline": baseline_sec / indexed_sec if indexed_sec > 0 else 1.0,
            "speedup_vs_unindexed": direct_sec / indexed_sec if indexed_sec > 0 else 1.0,
            "interactive_sla_met": indexed_sec < 0.010,  # < 10ms SLA
        }

    return results


if __name__ == "__main__":
    res = run_benchmark()
    print("=== Search & Fuzzy Indexing Benchmark ===")
    for count, data in res.items():
        print(f"\nDataset Size: {count} items")
        print(f"  Unindexed fuzzy_filter:    {data['direct_fuzzy_ms']:.3f} ms")
        print(f"  Pre-Indexed SearchIndex:   {data['indexed_fuzzy_ms']:.3f} ms")
        print(f"  Speedup vs unindexed:      {data['speedup_vs_unindexed']:.1f}x faster")
        print(f"  Interactive SLA (<10ms):   {'PASS' if data['interactive_sla_met'] else 'FAIL'}")
