#!/usr/bin/env python3
"""
Analyze A/B comparison CSVs (fixes formatting issues in original analyzer).
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from typing import Dict, List


NUMERIC_FIELDS = {
    "latency_ms": float,
    "cost_usd": float,
    "in_tokens": int,
    "out_tokens": int,
}
BOOL_FIELDS = {
    "tool_called",
    "args_valid",
    "success",
}


def load_results(csv_path: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row: Dict[str, object] = dict(raw)
            for key, cast in NUMERIC_FIELDS.items():
                if key in row:
                    row[key] = cast(row[key])
            for key in BOOL_FIELDS:
                if key in row:
                    row[key] = row[key].strip().lower() == "true"
            rows.append(row)
    return rows


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = int(round((len(ordered) - 1) * pct))
    return ordered[max(0, min(rank, len(ordered) - 1))]


def analyze(results: List[Dict[str, object]]) -> Dict[str, Dict[str, float]]:
    groups: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in results:
        groups[row["model"]].append(row)

    summary: Dict[str, Dict[str, float]] = {}
    for model, rows in groups.items():
        latencies = [row["latency_ms"] for row in rows]
        costs = [row["cost_usd"] for row in rows]
        total = len(rows)
        successes = sum(row["success"] for row in rows)
        tool_hits = sum(row["tool_called"] for row in rows)

        summary[model] = {
            "requests": total,
            "successes": successes,
            "success_rate": (successes / total * 100) if total else 0.0,
            "tool_hit_rate": (tool_hits / total * 100) if total else 0.0,
            "latency_mean": sum(latencies) / len(latencies) if latencies else 0.0,
            "latency_p50": percentile(latencies, 0.50),
            "latency_p90": percentile(latencies, 0.90),
            "cost_total": sum(costs),
            "cost_avg": sum(costs) / len(costs) if costs else 0.0,
            "tokens_total": sum(row["in_tokens"] + row["out_tokens"] for row in rows),
        }
    return summary


def print_summary(summary: Dict[str, Dict[str, float]]) -> None:
    models = sorted(summary.keys())
    if not models:
        print("No results")
        return

    header = f"{'Metric':<22}" + "".join(f"{model:<18}" for model in models)
    print(header)
    print("-" * len(header))

    metrics = [
        ("Requests", "requests", "{:.0f}"),
        ("Success Rate %", "success_rate", "{:.1f}"),
        ("Tool Hit %", "tool_hit_rate", "{:.1f}"),
        ("Latency mean ms", "latency_mean", "{:.0f}"),
        ("Latency p50 ms", "latency_p50", "{:.0f}"),
        ("Latency p90 ms", "latency_p90", "{:.0f}"),
        ("Cost total $", "cost_total", "${:.4f}"),
        ("Cost avg $", "cost_avg", "${:.4f}"),
        ("Tokens total", "tokens_total", "{:.0f}"),
    ]

    for label, key, fmt in metrics:
        line = [f"{label:<22}"]
        for model in models:
            value = summary[model].get(key, 0.0)
            line.append(f"{fmt.format(value):<18}")
        print("".join(line))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze A/B test CSV")
    parser.add_argument("csv_path")
    args = parser.parse_args()

    rows = load_results(args.csv_path)
    if not rows:
        print("No rows found")
        return

    summary = analyze(rows)
    print_summary(summary)


if __name__ == "__main__":
    main()
