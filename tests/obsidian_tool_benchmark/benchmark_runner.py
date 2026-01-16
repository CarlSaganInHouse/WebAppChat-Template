#!/usr/bin/env python3
"""
Tool Calling Benchmark for WebAppChat Obsidian Operations

A comprehensive test suite to evaluate local LLM tool calling accuracy.

Usage:
    python -m tests.obsidian_tool_benchmark.benchmark_runner [options]

Examples:
    # Run all default models (automated)
    python -m tests.obsidian_tool_benchmark.benchmark_runner

    # Specific model
    python -m tests.obsidian_tool_benchmark.benchmark_runner -m qwen3:8b

    # Interactive mode
    python -m tests.obsidian_tool_benchmark.benchmark_runner --interactive -m qwen3:4b

    # Custom output directory
    python -m tests.obsidian_tool_benchmark.benchmark_runner -o /tmp/my_benchmark
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.obsidian_tool_benchmark.test_definitions import ALL_TESTS, get_test_by_id
from tests.obsidian_tool_benchmark.evaluation import (
    evaluate_tool_selection,
    evaluate_parameters,
    classify_failure,
    calculate_combined_score,
    is_test_success,
    FailureMode,
)
from tests.obsidian_tool_benchmark.metrics_collector import MetricsCollector, TestMetrics
from tests.obsidian_tool_benchmark.report_generator import (
    generate_json_report,
    generate_markdown_report,
    print_summary,
)
from tests.obsidian_tool_benchmark.utils import (
    OLLAMA_URL,
    DEFAULT_MODELS,
    get_obsidian_tool_schemas,
    check_ollama_available,
    list_available_models,
    warmup_model,
    call_ollama_chat,
    parse_tool_call,
    get_response_content,
    get_token_counts,
)


def execute_test(
    model: str,
    test: Dict,
    tools: List[Dict],
    verbose: bool = False
) -> TestMetrics:
    """
    Execute a single test case against a model.

    Args:
        model: Ollama model name
        test: Test definition dict
        tools: List of tool definitions in Ollama format
        verbose: Print detailed output

    Returns:
        TestMetrics with results
    """
    test_id = test["id"]
    prompt = test["prompt"]
    expected_tool = test.get("expected_tool")
    expected_params = test.get("expected_params", {})

    if verbose:
        print(f"    Executing {test_id}: {prompt[:40]}...")

    # Create base metrics
    metrics = TestMetrics(
        test_id=test_id,
        model=model,
        timestamp=datetime.utcnow(),
        difficulty=test.get("difficulty", ""),
        category=test.get("category", ""),
        prompt=prompt,
        description=test.get("description", ""),
        expected_tool=expected_tool,
        expected_params={k: str(v) for k, v in expected_params.items()},
    )

    try:
        # Call Ollama
        response, latency_ms = call_ollama_chat(
            model=model,
            prompt=prompt,
            tools=tools,
            timeout=120,
            temperature=0.1
        )

        metrics.latency_ms = latency_ms

        # Extract token counts
        prompt_tok, completion_tok, total_tok = get_token_counts(response)
        metrics.prompt_tokens = prompt_tok
        metrics.completion_tokens = completion_tok
        metrics.total_tokens = total_tok

        # Parse tool call
        actual_tool, actual_params = parse_tool_call(response)
        metrics.actual_tool = actual_tool
        metrics.actual_params = actual_params

        # Get text response
        metrics.raw_response = get_response_content(response)

        # Store raw tool call
        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            metrics.tool_call_json = tool_calls[0]

        # Evaluate tool selection
        tool_score, tool_status, tool_details = evaluate_tool_selection(
            expected_tool, actual_tool
        )
        metrics.tool_selection_score = tool_score
        metrics.tool_status = tool_status

        # Evaluate parameters
        param_score, param_status, param_details = evaluate_parameters(
            expected_params, actual_params
        )
        metrics.parameter_score = param_score
        metrics.param_status = param_status

        # Calculate combined score
        metrics.combined_score = calculate_combined_score(tool_score, param_score)

        # Determine success
        metrics.success = is_test_success(tool_score, param_score)

        # Classify failure if not successful
        if not metrics.success:
            failure_mode, failure_details = classify_failure(
                test, actual_tool, actual_params, tool_status, param_status
            )
            metrics.failure_mode = failure_mode
            metrics.failure_details = failure_details
        else:
            metrics.failure_details = f"Tool: {tool_details}; Params: {param_details}"

    except Exception as e:
        metrics.success = False
        metrics.failure_mode = FailureMode.API_ERROR
        metrics.failure_details = str(e)
        if verbose:
            print(f"      ERROR: {e}")

    return metrics


def run_automated(
    models: List[str],
    output_dir: str,
    verbose: bool = False,
    tests: Optional[List[Dict]] = None
):
    """
    Run benchmark suite in automated mode.

    Args:
        models: List of model names to test
        output_dir: Directory for output files
        verbose: Print detailed progress
        tests: Optional subset of tests to run (default: ALL_TESTS)
    """
    if tests is None:
        tests = ALL_TESTS

    print(f"\nTool Calling Benchmark - Automated Mode")
    print(f"Models: {', '.join(models)}")
    print(f"Tests: {len(tests)}")
    print(f"Output: {output_dir}")
    print("=" * 60)

    # Check Ollama
    if not check_ollama_available():
        print("ERROR: Ollama not available at", OLLAMA_URL)
        print("Make sure Ollama is running and accessible.")
        sys.exit(1)

    # Check models
    available = list_available_models()
    for model in models:
        if model not in available:
            print(f"WARNING: Model '{model}' not found. Available: {available[:5]}...")

    # Get tool schemas
    tools = get_obsidian_tool_schemas()
    print(f"Tools: {len(tools)} Obsidian tools loaded")

    # Initialize collector
    collector = MetricsCollector()

    # Run benchmarks
    for model in models:
        print(f"\n{'=' * 60}")
        print(f"Testing: {model}")
        print(f"{'=' * 60}")

        # Warm up model
        warmup_model(model)

        # Run all tests
        passed = 0
        failed = 0

        for i, test in enumerate(tests):
            result = execute_test(model, test, tools, verbose=verbose)
            collector.add_result(result)

            # Progress indicator
            status = "PASS" if result.success else "FAIL"
            if result.success:
                passed += 1
            else:
                failed += 1

            # Show progress
            desc = test.get("description", "")[:35]
            print(f"  [{status}] {test['id']}: {desc}...")

            if not result.success and verbose:
                print(f"       -> {result.failure_mode.value if result.failure_mode else 'unknown'}: {result.failure_details[:50]}")

        # Model summary
        print(f"\n  Results: {passed}/{len(tests)} passed ({passed/len(tests):.0%})")

    # Generate reports
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = generate_json_report(
        collector,
        str(output_path / f"benchmark_results_{timestamp}.json"),
        models
    )
    print(f"\nJSON report: {json_path}")

    md_path = generate_markdown_report(
        collector,
        str(output_path / f"BENCHMARK_REPORT_{timestamp}.md"),
        models
    )
    print(f"Markdown report: {md_path}")

    # Also save latest versions without timestamp
    generate_json_report(
        collector,
        str(output_path / "benchmark_results.json"),
        models
    )
    generate_markdown_report(
        collector,
        str(output_path / "BENCHMARK_REPORT.md"),
        models
    )

    # Print summary
    print_summary(collector, models)


def run_interactive(
    model: str,
    tests: Optional[List[Dict]] = None
):
    """
    Run benchmark in interactive mode with pauses for observation.

    Args:
        model: Model to test
        tests: Optional subset of tests to run
    """
    if tests is None:
        tests = ALL_TESTS

    print(f"\nTool Calling Benchmark - Interactive Mode")
    print(f"Model: {model}")
    print(f"Tests: {len(tests)}")
    print("=" * 60)
    print("\nCommands: [Enter] next, [r] repeat, [s] skip, [q] quit\n")

    # Check Ollama
    if not check_ollama_available():
        print("ERROR: Ollama not available at", OLLAMA_URL)
        sys.exit(1)

    # Get tools
    tools = get_obsidian_tool_schemas()

    # Warm up
    warmup_model(model)

    # Initialize collector for tracking
    collector = MetricsCollector()

    i = 0
    while i < len(tests):
        test = tests[i]

        print(f"\n{'=' * 60}")
        print(f"Test {i+1}/{len(tests)}: {test['id']}")
        print(f"{'=' * 60}")
        print(f"Difficulty: {test['difficulty']}")
        print(f"Category: {test['category']}")
        print(f"Description: {test['description']}")
        print(f"\nPrompt: \"{test['prompt']}\"")
        print(f"\nExpected Tool: {test['expected_tool']}")

        # Show expected params in readable form
        expected_params = test.get("expected_params", {})
        if expected_params:
            print("Expected Params:")
            for k, v in expected_params.items():
                if callable(v):
                    print(f"  - {k}: <validator function>")
                else:
                    print(f"  - {k}: {v}")

        input("\nPress Enter to execute...")

        # Execute
        result = execute_test(model, test, tools, verbose=True)
        collector.add_result(result)

        # Show results
        print(f"\n--- Result ---")
        print(f"Success: {'PASS' if result.success else 'FAIL'}")
        print(f"Tool Called: {result.actual_tool or 'none'}")
        print(f"Parameters: {json.dumps(result.actual_params, indent=2)}")
        print(f"Latency: {result.latency_ms:.0f}ms")
        print(f"Tokens: {result.total_tokens}")

        if not result.success:
            print(f"\nFailure Mode: {result.failure_mode.value if result.failure_mode else 'unknown'}")
            print(f"Details: {result.failure_details}")

        if result.raw_response:
            print(f"\nModel Response: {result.raw_response[:200]}...")

        # Get action
        action = input("\n[Enter] next, [r] repeat, [s] skip, [q] quit: ").lower().strip()

        if action == 'q':
            break
        elif action == 'r':
            continue  # Don't increment, repeat same test
        elif action == 's':
            pass  # Continue to next

        i += 1

    # Final summary
    if collector.results:
        print("\n" + "=" * 60)
        print("SESSION SUMMARY")
        print("=" * 60)
        summary = collector.get_model_summary(model)
        print(f"Tests Run: {summary.total_tests}")
        print(f"Success Rate: {summary.overall_success_rate:.0%}")
        print(f"Avg Latency: {summary.avg_latency_ms:.0f}ms")


def main():
    parser = argparse.ArgumentParser(
        description="Tool Calling Benchmark for WebAppChat Obsidian Operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all default models
    python -m tests.obsidian_tool_benchmark.benchmark_runner

    # Specific model
    python -m tests.obsidian_tool_benchmark.benchmark_runner -m qwen3:8b

    # Multiple specific models
    python -m tests.obsidian_tool_benchmark.benchmark_runner --models qwen3:4b qwen3:8b

    # Interactive mode
    python -m tests.obsidian_tool_benchmark.benchmark_runner --interactive -m qwen3:8b

    # Specific test only
    python -m tests.obsidian_tool_benchmark.benchmark_runner -m qwen3:8b --test TS001

    # Verbose output
    python -m tests.obsidian_tool_benchmark.benchmark_runner -v
        """
    )

    parser.add_argument(
        "--model", "-m",
        help="Specific model to test"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="List of models to test"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode with pauses"
    )
    parser.add_argument(
        "--output", "-o",
        default="/tmp/tool_benchmark",
        help="Output directory for reports (default: /tmp/tool_benchmark)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--test", "-t",
        help="Run specific test by ID (e.g., TS001)"
    )
    parser.add_argument(
        "--difficulty", "-d",
        choices=["EASY", "MEDIUM", "HARD"],
        help="Run only tests of specific difficulty"
    )
    parser.add_argument(
        "--category", "-c",
        choices=["tool_selection", "parameter_extraction", "refusal", "multi_step", "edge_case"],
        help="Run only tests of specific category"
    )
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="List all available tests and exit"
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Ollama models and exit"
    )

    args = parser.parse_args()

    # List tests
    if args.list_tests:
        print("Available Tests:")
        print("-" * 60)
        for test in ALL_TESTS:
            print(f"  {test['id']:6} [{test['difficulty']:6}] {test['category']:20} {test['description']}")
        return

    # List models
    if args.list_models:
        print("Checking Ollama models...")
        if not check_ollama_available():
            print("ERROR: Ollama not available")
            return
        models = list_available_models()
        print(f"\nAvailable Models ({len(models)}):")
        for m in models:
            marker = "*" if m in DEFAULT_MODELS else " "
            print(f"  {marker} {m}")
        print("\n* = default benchmark models")
        return

    # Determine models to test
    if args.model:
        models = [args.model]
    elif args.models:
        models = args.models
    else:
        models = DEFAULT_MODELS

    # Filter tests if specified
    tests = ALL_TESTS
    if args.test:
        test = get_test_by_id(args.test)
        if test:
            tests = [test]
        else:
            print(f"ERROR: Test '{args.test}' not found")
            return
    elif args.difficulty:
        tests = [t for t in ALL_TESTS if t["difficulty"] == args.difficulty]
    elif args.category:
        tests = [t for t in ALL_TESTS if t["category"] == args.category]

    if not tests:
        print("ERROR: No tests match the specified criteria")
        return

    # Run benchmark
    if args.interactive:
        if len(models) > 1:
            print("WARNING: Interactive mode only supports one model. Using:", models[0])
        run_interactive(models[0], tests)
    else:
        run_automated(models, args.output, args.verbose, tests)


if __name__ == "__main__":
    main()
