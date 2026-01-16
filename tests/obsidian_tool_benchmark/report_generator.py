"""
Report Generator for Tool Calling Benchmark

Generates JSON and Markdown reports from benchmark results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .metrics_collector import MetricsCollector, ModelSummary, TestMetrics
from .test_definitions import TEST_COUNTS


def generate_json_report(
    collector: MetricsCollector,
    output_path: str,
    models: List[str]
) -> str:
    """
    Generate JSON report from benchmark results.

    Args:
        collector: MetricsCollector with results
        output_path: Path to write JSON file
        models: List of models that were tested

    Returns:
        Path to generated report
    """
    report = {
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "suite_version": "1.0.0",
            "total_tests": TEST_COUNTS["total"],
            "models_tested": models,
            "test_counts": TEST_COUNTS,
        },
        "summary": {
            "by_model": {},
            "by_difficulty": {
                "EASY": {"count": TEST_COUNTS["by_difficulty"]["EASY"]},
                "MEDIUM": {"count": TEST_COUNTS["by_difficulty"]["MEDIUM"]},
                "HARD": {"count": TEST_COUNTS["by_difficulty"]["HARD"]},
            }
        },
        "tests": [],
        "failure_analysis": {}
    }

    # Per-model summaries
    for model in models:
        summary = collector.get_model_summary(model)
        report["summary"]["by_model"][model] = summary.to_dict()

    # Difficulty comparison
    difficulty_comp = collector.get_difficulty_comparison()
    for diff in ["EASY", "MEDIUM", "HARD"]:
        rates = [difficulty_comp.get(m, {}).get(diff, 0) for m in models]
        report["summary"]["by_difficulty"][diff]["avg_success_rate"] = (
            sum(rates) / len(rates) if rates else 0
        )
        report["summary"]["by_difficulty"][diff]["by_model"] = {
            m: difficulty_comp.get(m, {}).get(diff, 0) for m in models
        }

    # Per-test results
    for result in collector.results:
        report["tests"].append(result.to_dict())

    # Failure analysis
    for model in models:
        summary = collector.get_model_summary(model)
        report["failure_analysis"][model] = {
            "total_failures": len(summary.failed_test_ids),
            "by_mode": summary.failure_mode_counts,
            "failed_tests": summary.failed_test_ids,
        }

    # Write JSON
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(report, f, indent=2)

    return str(output)


def generate_markdown_report(
    collector: MetricsCollector,
    output_path: str,
    models: List[str]
) -> str:
    """
    Generate Markdown report from benchmark results.

    Args:
        collector: MetricsCollector with results
        output_path: Path to write Markdown file
        models: List of models that were tested

    Returns:
        Path to generated report
    """
    lines = []

    # Header
    lines.append("# Tool Calling Benchmark Report\n")
    lines.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append(f"**Test Suite Version:** 1.0.0")
    lines.append(f"**Total Tests:** {TEST_COUNTS['total']}\n")

    # Executive Summary
    lines.append("## Executive Summary\n")

    # Model comparison table
    headers = ["Model", "Success Rate", "Tool Selection", "Parameters", "Avg Latency"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for model in models:
        summary = collector.get_model_summary(model)
        row = [
            f"`{model}`",
            f"{summary.overall_success_rate:.0%}",
            f"{summary.tool_selection_accuracy:.0%}",
            f"{summary.parameter_accuracy:.0%}",
            f"{summary.avg_latency_ms:.0f}ms"
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Success by Difficulty
    lines.append("## Success by Difficulty\n")

    headers = ["Difficulty", "Tests"] + [f"`{m}`" for m in models]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    difficulty_comp = collector.get_difficulty_comparison()
    for diff in ["EASY", "MEDIUM", "HARD"]:
        row = [diff, str(TEST_COUNTS["by_difficulty"][diff])]
        for model in models:
            rate = difficulty_comp.get(model, {}).get(diff, 0)
            row.append(f"{rate:.0%}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Success by Category
    lines.append("## Success by Category\n")

    categories = list(TEST_COUNTS["by_category"].keys())
    headers = ["Category", "Tests"] + [f"`{m}`" for m in models]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for cat in categories:
        row = [cat, str(TEST_COUNTS["by_category"][cat])]
        for model in models:
            summary = collector.get_model_summary(model)
            rate = summary.category_rates.get(cat, 0)
            row.append(f"{rate:.0%}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Failure Analysis
    lines.append("## Failure Analysis\n")

    for model in models:
        summary = collector.get_model_summary(model)
        if not summary.failed_test_ids:
            lines.append(f"### `{model}` - No Failures\n")
            continue

        lines.append(f"### `{model}`\n")
        lines.append(f"**Total Failures:** {len(summary.failed_test_ids)}\n")

        # Failure modes
        lines.append("**By Failure Mode:**")
        if summary.failure_mode_counts:
            for mode, count in sorted(
                summary.failure_mode_counts.items(),
                key=lambda x: x[1],
                reverse=True
            ):
                lines.append(f"- `{mode}`: {count}")
        else:
            lines.append("- No categorized failures")

        lines.append("")

        # Failed tests
        lines.append("**Failed Tests:**")
        for test_id in summary.failed_test_ids[:10]:  # Limit to 10
            # Find the test result
            result = next(
                (r for r in collector.results
                 if r.test_id == test_id and r.model == model),
                None
            )
            if result:
                lines.append(f"- `{test_id}`: {result.failure_details[:60]}...")
            else:
                lines.append(f"- `{test_id}`")

        if len(summary.failed_test_ids) > 10:
            lines.append(f"- ... and {len(summary.failed_test_ids) - 10} more")

        lines.append("")

    # Performance Comparison
    lines.append("## Performance Comparison\n")

    headers = ["Model", "Avg", "P50", "P95", "Min", "Max", "Avg Tokens"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for model in models:
        summary = collector.get_model_summary(model)
        row = [
            f"`{model}`",
            f"{summary.avg_latency_ms:.0f}ms",
            f"{summary.p50_latency_ms:.0f}ms",
            f"{summary.p95_latency_ms:.0f}ms",
            f"{summary.min_latency_ms:.0f}ms",
            f"{summary.max_latency_ms:.0f}ms",
            f"{summary.avg_tokens:.0f}",
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Detailed Results (first 10 tests)
    lines.append("## Sample Detailed Results\n")
    lines.append("*Showing first 10 tests. See JSON report for complete results.*\n")

    # Group results by test
    from .test_definitions import ALL_TESTS
    for test in ALL_TESTS[:10]:
        test_id = test["id"]
        lines.append(f"### Test {test_id}: {test['description']}")
        lines.append(f"- **Difficulty:** {test['difficulty']}")
        lines.append(f"- **Category:** {test['category']}")
        lines.append(f"- **Prompt:** \"{test['prompt']}\"")
        lines.append(f"- **Expected Tool:** `{test['expected_tool']}`")
        lines.append("")

        headers = ["Model", "Result", "Tool Called", "Latency"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for model in models:
            result = next(
                (r for r in collector.results
                 if r.test_id == test_id and r.model == model),
                None
            )
            if result:
                status = "PASS" if result.success else "FAIL"
                row = [
                    f"`{model}`",
                    f"**{status}**",
                    f"`{result.actual_tool or 'none'}`",
                    f"{result.latency_ms:.0f}ms"
                ]
            else:
                row = [f"`{model}`", "N/A", "N/A", "N/A"]
            lines.append("| " + " | ".join(row) + " |")

        lines.append("")

    # Recommendations
    lines.append("## Recommendations\n")

    # Find best model for each difficulty
    for diff in ["EASY", "MEDIUM", "HARD"]:
        best_model = None
        best_rate = 0
        for model in models:
            rate = difficulty_comp.get(model, {}).get(diff, 0)
            if rate > best_rate:
                best_rate = rate
                best_model = model
        if best_model:
            lines.append(f"- **{diff} tasks:** Use `{best_model}` ({best_rate:.0%} success rate)")

    lines.append("")

    # Overall recommendation
    best_overall = None
    best_score = 0
    for model in models:
        summary = collector.get_model_summary(model)
        if summary.overall_success_rate > best_score:
            best_score = summary.overall_success_rate
            best_overall = model

    if best_overall:
        summary = collector.get_model_summary(best_overall)
        lines.append(f"**Best Overall:** `{best_overall}` with {summary.overall_success_rate:.0%} success rate, ")
        lines.append(f"{summary.avg_latency_ms:.0f}ms average latency.\n")

    # Footer
    lines.append("---")
    lines.append("*Report generated by WebAppChat Tool Calling Benchmark Suite*")

    # Write Markdown
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        f.write("\n".join(lines))

    return str(output)


def print_summary(collector: MetricsCollector, models: List[str]):
    """Print a quick summary to console"""
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    # Quick table
    print(f"\n{'Model':<35} {'Success':>10} {'Latency':>10}")
    print("-" * 55)

    for model in models:
        summary = collector.get_model_summary(model)
        print(f"{model:<35} {summary.overall_success_rate:>9.0%} {summary.avg_latency_ms:>9.0f}ms")

    print("-" * 55)

    # Difficulty breakdown
    print("\nSuccess by Difficulty:")
    difficulty_comp = collector.get_difficulty_comparison()
    for diff in ["EASY", "MEDIUM", "HARD"]:
        rates = [f"{difficulty_comp.get(m, {}).get(diff, 0):.0%}" for m in models]
        print(f"  {diff}: {', '.join(rates)}")

    print("")
