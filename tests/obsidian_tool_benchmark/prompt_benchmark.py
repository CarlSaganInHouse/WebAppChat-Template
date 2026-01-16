#!/usr/bin/env python3
"""
Prompt Variant A/B Benchmark

Runs tool calling tests with different system prompt variants to measure
impact on accuracy. Generates comparative reports.

Usage:
    # Run all variants on default model
    python -m tests.obsidian_tool_benchmark.prompt_benchmark

    # Run specific variants
    python -m tests.obsidian_tool_benchmark.prompt_benchmark --variants NO_PROMPT,CURRENT,CLAUDE_STYLE

    # Quick test with subset
    python -m tests.obsidian_tool_benchmark.prompt_benchmark --variants NO_PROMPT,CURRENT -n 5

    # Test specific model
    python -m tests.obsidian_tool_benchmark.prompt_benchmark -m qwen3:8b --variants NO_PROMPT
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tests.obsidian_tool_benchmark.utils import (
    OLLAMA_URL,
    DEFAULT_MODELS,
    check_ollama_available,
    warmup_model,
    get_obsidian_tool_schemas,
    get_all_tool_schemas,
    call_ollama_chat_with_prompt,
    parse_tool_call,
    get_token_counts,
)
from tests.obsidian_tool_benchmark.prompt_variants import (
    PROMPT_VARIANTS,
    VARIANT_NAMES,
    get_system_message,
)
from tests.obsidian_tool_benchmark.test_definitions import ALL_TESTS


def get_current_time_context() -> Tuple[str, str, str]:
    """Get current date, time, and timezone for prompt variants."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S EST")  # Assuming EST
    tz = "America/New_York"
    return date_str, time_str, tz


def evaluate_tool_selection(
    expected_tool: Optional[str | List[str]],
    actual_tool: Optional[str]
) -> Tuple[bool, str]:
    """
    Evaluate if the actual tool matches expected.

    Returns:
        (success, details)
    """
    # Refusal tests: expected_tool is None
    if expected_tool is None:
        if actual_tool is None:
            return True, "Correctly refused"
        else:
            return False, f"Should refuse, got {actual_tool}"

    # Single expected tool
    if isinstance(expected_tool, str):
        if actual_tool == expected_tool:
            return True, f"Correct: {actual_tool}"
        else:
            return False, f"Expected {expected_tool}, got {actual_tool}"

    # Multiple acceptable tools
    if isinstance(expected_tool, list):
        if actual_tool in expected_tool:
            return True, f"Correct: {actual_tool}"
        else:
            return False, f"Expected one of {expected_tool}, got {actual_tool}"

    return False, f"Unknown expected type"


def run_single_test(
    model: str,
    test: Dict,
    tools: List[Dict],
    system_message: Optional[Dict],
    temperature: float = 0.1
) -> Dict:
    """
    Run a single test case.

    Returns dict with test results.
    """
    test_id = test["id"]
    prompt = test["prompt"]
    expected_tool = test.get("expected_tool")

    try:
        response, latency_ms = call_ollama_chat_with_prompt(
            model=model,
            prompt=prompt,
            tools=tools,
            system_message=system_message,
            temperature=temperature
        )

        actual_tool, params = parse_tool_call(response)
        prompt_tokens, completion_tokens, total_tokens = get_token_counts(response)

        success, details = evaluate_tool_selection(expected_tool, actual_tool)

        return {
            "test_id": test_id,
            "prompt": prompt,
            "expected_tool": expected_tool,
            "actual_tool": actual_tool,
            "actual_params": params,
            "success": success,
            "details": details,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    except Exception as e:
        return {
            "test_id": test_id,
            "prompt": prompt,
            "expected_tool": expected_tool,
            "actual_tool": None,
            "actual_params": {},
            "success": False,
            "details": f"Error: {str(e)}",
            "latency_ms": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "error": str(e),
        }


def run_variant_benchmark(
    model: str,
    variant_name: str,
    tests: List[Dict],
    tools: List[Dict],
    temperature: float = 0.1,
    verbose: bool = True
) -> Dict:
    """
    Run all tests for a single prompt variant.

    Returns summary dict with results.
    """
    date_str, time_str, tz = get_current_time_context()
    system_message = get_system_message(variant_name, date_str, time_str, tz)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Variant: {variant_name}")
        sys_content = system_message.get("content", "") if system_message else ""
        print(f"System prompt: {len(sys_content)} chars")
        print(f"{'='*60}")

    results = []
    passed = 0

    for test in tests:
        result = run_single_test(model, test, tools, system_message, temperature)
        results.append(result)

        if result["success"]:
            passed += 1

        if verbose:
            status = "PASS" if result["success"] else "FAIL"
            tool = result["actual_tool"] or "none"
            print(f"  [{status}] {result['test_id']}: {tool} ({result['latency_ms']:.0f}ms)")
            if not result["success"]:
                print(f"         {result['details']}")

    accuracy = passed / len(tests) if tests else 0

    if verbose:
        print(f"\n  Results: {passed}/{len(tests)} ({accuracy:.0%})")

    return {
        "variant": variant_name,
        "model": model,
        "temperature": temperature,
        "total_tests": len(tests),
        "passed": passed,
        "accuracy": accuracy,
        "avg_latency_ms": sum(r["latency_ms"] for r in results) / len(results) if results else 0,
        "results": results,
    }


def run_ab_benchmark(
    model: str,
    variants: List[str],
    tests: List[Dict],
    temperature: float = 0.1,
    verbose: bool = True,
    include_smart_home: bool = False
) -> Dict:
    """
    Run A/B benchmark across multiple prompt variants.

    Returns comprehensive comparison dict.
    """
    if include_smart_home:
        tools = get_all_tool_schemas()
        tool_desc = f"{len(tools)} tools (Obsidian + Smart Home)"
    else:
        tools = get_obsidian_tool_schemas()
        tool_desc = f"{len(tools)} Obsidian tools"

    print(f"\n{'#'*60}")
    print(f"# Prompt Variant A/B Benchmark")
    print(f"# Model: {model}")
    print(f"# Variants: {', '.join(variants)}")
    print(f"# Tests: {len(tests)}")
    print(f"# Temperature: {temperature}")
    print(f"# Tools: {tool_desc}")
    print(f"{'#'*60}")

    # Warmup model once
    warmup_model(model)

    variant_results = {}
    for variant_name in variants:
        result = run_variant_benchmark(
            model=model,
            variant_name=variant_name,
            tests=tests,
            tools=tools,
            temperature=temperature,
            verbose=verbose
        )
        variant_results[variant_name] = result

    # Generate comparison summary
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'Variant':<20} {'Accuracy':>10} {'Passed':>10} {'Avg Latency':>12}")
    print("-" * 60)

    best_variant = None
    best_accuracy = -1

    for variant_name, result in variant_results.items():
        acc_str = f"{result['accuracy']:.0%}"
        passed_str = f"{result['passed']}/{result['total_tests']}"
        latency_str = f"{result['avg_latency_ms']:.0f}ms"
        print(f"{variant_name:<20} {acc_str:>10} {passed_str:>10} {latency_str:>12}")

        if result['accuracy'] > best_accuracy:
            best_accuracy = result['accuracy']
            best_variant = variant_name

    print("-" * 60)
    print(f"Best: {best_variant} ({best_accuracy:.0%})")
    print(f"{'='*60}")

    return {
        "model": model,
        "temperature": temperature,
        "num_tests": len(tests),
        "num_tools": len(tools),
        "variants_tested": variants,
        "best_variant": best_variant,
        "best_accuracy": best_accuracy,
        "variant_results": variant_results,
        "timestamp": datetime.now().isoformat(),
    }


def generate_detailed_report(comparison: Dict) -> str:
    """Generate detailed markdown report from comparison results."""
    lines = []
    lines.append("# Prompt Variant A/B Test Report\n")
    lines.append(f"**Model:** {comparison['model']}")
    lines.append(f"**Temperature:** {comparison['temperature']}")
    lines.append(f"**Tests:** {comparison['num_tests']}")
    lines.append(f"**Tools:** {comparison['num_tools']}")
    lines.append(f"**Timestamp:** {comparison['timestamp']}")
    lines.append("")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| Variant | Accuracy | Passed | Avg Latency |")
    lines.append("|---------|----------|--------|-------------|")

    for variant_name, result in comparison["variant_results"].items():
        acc = f"{result['accuracy']:.0%}"
        passed = f"{result['passed']}/{result['total_tests']}"
        latency = f"{result['avg_latency_ms']:.0f}ms"
        lines.append(f"| {variant_name} | {acc} | {passed} | {latency} |")

    lines.append("")
    lines.append(f"**Best Variant:** {comparison['best_variant']} ({comparison['best_accuracy']:.0%})")
    lines.append("")

    # Per-test breakdown
    lines.append("## Per-Test Breakdown\n")
    lines.append("| Test ID | " + " | ".join(comparison["variants_tested"]) + " |")
    lines.append("|---------|" + "|".join(["---------"] * len(comparison["variants_tested"])) + "|")

    # Get test IDs from first variant
    first_variant = comparison["variants_tested"][0]
    test_ids = [r["test_id"] for r in comparison["variant_results"][first_variant]["results"]]

    for test_id in test_ids:
        row = [test_id]
        for variant_name in comparison["variants_tested"]:
            results = comparison["variant_results"][variant_name]["results"]
            test_result = next((r for r in results if r["test_id"] == test_id), None)
            if test_result:
                status = "PASS" if test_result["success"] else "FAIL"
                row.append(status)
            else:
                row.append("-")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Variant A/B Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available prompt variants:
  {', '.join(VARIANT_NAMES)}

Examples:
  # Run NO_PROMPT vs CURRENT
  python -m tests.obsidian_tool_benchmark.prompt_benchmark --variants NO_PROMPT,CURRENT

  # Run all variants
  python -m tests.obsidian_tool_benchmark.prompt_benchmark --all-variants

  # Quick test with 5 tests
  python -m tests.obsidian_tool_benchmark.prompt_benchmark --variants NO_PROMPT,CURRENT -n 5
"""
    )
    parser.add_argument("-m", "--model", default="qwen3:4b-instruct-2507-q4_K_M",
                        help="Model to test")
    parser.add_argument("--variants", type=str,
                        help="Comma-separated list of variants to test")
    parser.add_argument("--all-variants", action="store_true",
                        help="Test all available variants")
    parser.add_argument("-n", "--num", type=int,
                        help="Limit number of tests")
    parser.add_argument("-t", "--test", type=str,
                        help="Run specific test ID")
    parser.add_argument("--category", type=str,
                        help="Run tests from specific category")
    parser.add_argument("--temperature", type=float, default=0.1,
                        help="Sampling temperature (default: 0.1)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Minimal output")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save results to file")
    parser.add_argument("--all-tools", action="store_true",
                        help="Use all 16 tools (10 Obsidian + 6 Smart Home) instead of just 10 Obsidian tools")

    args = parser.parse_args()

    # Check Ollama availability
    if not check_ollama_available():
        print("Error: Ollama not available at", OLLAMA_URL)
        return

    # Determine variants to test
    if args.all_variants:
        variants = VARIANT_NAMES
    elif args.variants:
        variants = [v.strip() for v in args.variants.split(",")]
        # Validate variants
        for v in variants:
            if v not in PROMPT_VARIANTS:
                print(f"Error: Unknown variant '{v}'. Available: {VARIANT_NAMES}")
                return
    else:
        # Default: key variants
        variants = ["NO_PROMPT", "CURRENT", "CLAUDE_STYLE"]

    # Filter tests
    tests = ALL_TESTS

    if args.test:
        tests = [t for t in tests if t["id"] == args.test]
        if not tests:
            print(f"Test {args.test} not found")
            return

    if args.category:
        tests = [t for t in tests if t["category"] == args.category]
        if not tests:
            print(f"No tests in category {args.category}")
            return

    if args.num:
        tests = tests[:args.num]

    # Run benchmark
    comparison = run_ab_benchmark(
        model=args.model,
        variants=variants,
        tests=tests,
        temperature=args.temperature,
        verbose=not args.quiet,
        include_smart_home=args.all_tools
    )

    # Save results
    if not args.no_save:
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_safe = args.model.replace(":", "_").replace("/", "_")
        variants_str = "-".join(variants[:3])  # First 3 variants in filename
        if len(variants) > 3:
            variants_str += f"-plus{len(variants)-3}"

        # Save JSON results
        json_file = output_dir / f"prompt_ab_{model_safe}_{variants_str}_{timestamp}.json"
        with open(json_file, "w") as f:
            # Convert variant_results to serializable format
            serializable = {
                **comparison,
                "variant_results": {
                    k: {**v, "results": v["results"]}
                    for k, v in comparison["variant_results"].items()
                }
            }
            json.dump(serializable, f, indent=2, default=str)
        print(f"\nResults saved to: {json_file}")

        # Save markdown report
        md_file = output_dir / f"prompt_ab_{model_safe}_{variants_str}_{timestamp}.md"
        report = generate_detailed_report(comparison)
        with open(md_file, "w") as f:
            f.write(report)
        print(f"Report saved to: {md_file}")


if __name__ == "__main__":
    main()
