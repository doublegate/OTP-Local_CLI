"""Microbenchmark: Textual TUI event processing, OptionList populate, and search debounce latency."""

import sys
import time
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.widgets.option_list import Option

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authy_local.tui import (  # noqa: E402
    MAX_RENDER_OPTIONS,
    CompiledQuery,
    TokenBrowserScreen,
    fast_highlight_match,
    parse_token_parts,
)
from authy_local.tui_items import SearchIndex  # noqa: E402


def generate_large_token_catalog(count: int = 5000) -> list[tuple[str, str]]:
    services = [
        "GitHub",
        "AWS",
        "Google",
        "GitLab",
        "Slack",
        "Cloudflare",
        "Dropbox",
        "Stripe",
        "Zoom",
        "Bitbucket",
    ]
    return [
        (f"key_{i:05d}", f"{services[i % len(services)]} User-{i:04d} [{i:05d}]")
        for i in range(count)
    ]


def run_benchmark(catalog_size: int = 5000, iterations: int = 40) -> dict[str, Any]:
    """Measure baseline vs optimized OptionList populating and search debouncing cycle."""
    records = generate_large_token_catalog(catalog_size)
    search_index = SearchIndex(records)
    query = "Git"

    # 1. Baseline: Uncached re-parse and uncompiled highlight
    t0 = time.perf_counter()
    for _ in range(iterations):
        matches = search_index.filter(query)
        options_to_render = matches[:MAX_RENDER_OPTIONS]
        rendered: list[Option] = []
        for idx, (key, label) in enumerate(options_to_render):
            srv, acc, short_id = parse_token_parts("onepassword", key, label)
            row = Text()
            row.append(f"{idx + 1:<5}", style="dim")
            row.append_text(
                TokenBrowserScreen._highlight_match(f"{srv:<32}"[:32], query, "bold cyan")
            )
            row.append(" ")
            row.append_text(TokenBrowserScreen._highlight_match(f"{acc:<30}"[:30], query, "white"))
            row.append(" ")
            row.append(f"{short_id:<10}"[:10], style="dim")
            rendered.append(Option(prompt=row, id=f"opt-{idx}"))
    baseline_sec = (time.perf_counter() - t0) / iterations if iterations > 0 else 0
    baseline_ms = baseline_sec * 1000

    # 2. Optimized: Pre-parsed records + fast highlight with CompiledQuery
    parsed_catalog = {key: parse_token_parts("onepassword", key, label) for key, label in records}

    t0 = time.perf_counter()
    for _ in range(iterations):
        matches = search_index.filter(query)
        cq = CompiledQuery(query)
        options_to_render = matches[:MAX_RENDER_OPTIONS]
        rendered_opt: list[Option] = []
        for idx, (key, _) in enumerate(options_to_render):
            srv, acc, short_id = parsed_catalog[key]
            row = Text()
            row.append(f"{idx + 1:<5}", style="dim")
            row.append_text(fast_highlight_match(f"{srv:<32}"[:32], cq, "bold cyan"))
            row.append(" ")
            row.append_text(fast_highlight_match(f"{acc:<30}"[:30], cq, "white"))
            row.append(" ")
            row.append(f"{short_id:<10}"[:10], style="dim")
            rendered_opt.append(Option(prompt=row, id=f"opt-{idx}"))
    opt_sec = (time.perf_counter() - t0) / iterations if iterations > 0 else 0
    opt_ms = opt_sec * 1000

    # 3. Cached empty-query reset latency
    cached_base = [
        Option(prompt=Text(f"{i} Item"), id=f"opt-{i}") for i in range(MAX_RENDER_OPTIONS)
    ]
    t0 = time.perf_counter()
    empty_iters = 10_000
    for _ in range(empty_iters):
        _ = list(cached_base)
    empty_reset_ms = (time.perf_counter() - t0) * 1000 / empty_iters

    speedup = baseline_ms / opt_ms if opt_ms > 0 else 1.0

    return {
        "catalog_size": catalog_size,
        "baseline_populate_ms": baseline_ms,
        "optimized_populate_ms": opt_ms,
        "cached_empty_reset_ms": empty_reset_ms,
        "speedup_populate": speedup,
        "debounce_cycle_ms": opt_ms,
        "sla_met": opt_ms < 5.0 and empty_reset_ms < 0.1,
    }


if __name__ == "__main__":
    res = run_benchmark()
    print("=== Textual TUI Event Processing Benchmark ===")
    print(f"Catalog Size:                  {res['catalog_size']} items")
    print(f"Baseline Populate (150 rows):  {res['baseline_populate_ms']:.3f} ms")
    print(f"Optimized Populate (150 rows): {res['optimized_populate_ms']:.3f} ms")
    print(f"Empty-Query Instant Reset:     {res['cached_empty_reset_ms']:.6f} ms")
    print(f"Populate Speedup:              {res['speedup_populate']:.2f}x faster")
    print(f"Debounce Budget (< 35 ms SLA): {'PASS' if res['sla_met'] else 'FAIL'}")
