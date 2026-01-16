#!/usr/bin/env python3
"""
Web App Benchmark Runner

Runs the same tool calling tests through the actual web app endpoint
to compare with direct Ollama benchmark.

Usage:
    python3 -m tests.obsidian_tool_benchmark.webapp_benchmark
"""

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import requests

# API configuration
WEBAPP_URL = "https://your-domain.com"
API_KEY = "s0_NKvPynyS9gWcFzxvs5hYwBS6F1XaHXLyz253LSCI"

# Import test definitions
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from tests.obsidian_tool_benchmark.test_definitions import ALL_TESTS


def get_docker_logs_since(seconds_ago: int = 5) -> str:
    """Get recent Docker logs from webchat-app container."""
    try:
        # Try direct docker command first (when running inside CT 500)
        result = subprocess.run(
            ["docker", "logs", "webchat-app", "--since", f"{seconds_ago}s"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stderr + result.stdout  # Docker logs go to stderr

        # Fall back to pct exec (when running from Proxmox host)
        result = subprocess.run(
            ["pct", "exec", "500", "--", "docker", "logs", "webchat-app",
             "--since", f"{seconds_ago}s"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stderr + result.stdout
    except Exception as e:
        print(f"  Warning: Could not get Docker logs: {e}")
        return ""


def extract_tool_from_logs(logs: str) -> Optional[str]:
    """Extract the most recent tool call from Docker logs."""
    # Remove ANSI color codes first
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_logs = ansi_escape.sub('', logs)

    # Pattern 1: Explicit tool_call log line (most reliable)
    matches = re.findall(r'\[FUNC\] Ollama tool_call: (\w+)', clean_logs)
    if matches:
        return matches[-1]  # Return the most recent

    # Pattern 2: function=tool_name in structlog output (validation warnings)
    matches = re.findall(r'function=(\w+)', clean_logs)
    if matches:
        return matches[-1]

    # Pattern 3: [FUNC] line showing specific tool (legacy)
    matches = re.findall(r'\[FUNC\].*?tool:\s*(\w+)', clean_logs)
    if matches:
        return matches[-1]

    return None


def call_webapp(prompt: str, model: str) -> Tuple[Dict, float]:
    """
    Call the web app /ask endpoint.

    Returns:
        (response_dict, latency_ms)
    """
    start = time.time()

    resp = requests.post(
        f"{WEBAPP_URL}/ask",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        },
        json={
            "prompt": prompt,
            "model": model,
            "debugToolCalls": True,
        },
        timeout=120
    )

    latency_ms = (time.time() - start) * 1000

    if resp.status_code != 200:
        return {"error": resp.text, "status_code": resp.status_code}, latency_ms

    return resp.json(), latency_ms


def evaluate_result(test: Dict, actual_tool: Optional[Union[str, List[str]]]) -> Tuple[bool, str]:
    """
    Evaluate if the actual tool matches expected.

    Returns:
        (success, details)
    """
    expected = test.get("expected_tool")

    # Multiple actual tools is always a failure for these tests
    if isinstance(actual_tool, list):
        if not actual_tool:
            actual_tool = None
        else:
            return False, f"Expected single tool, got multiple {actual_tool}"

    # Refusal tests: expected_tool is None
    if expected is None:
        if actual_tool is None:
            return True, "Correctly refused to call tool"
        else:
            return False, f"Should not have called tool, but called {actual_tool}"

    # Single expected tool
    if isinstance(expected, str):
        if actual_tool == expected:
            return True, f"Correct: {actual_tool}"
        else:
            return False, f"Expected {expected}, got {actual_tool}"

    # Multiple acceptable tools
    if isinstance(expected, list):
        if actual_tool in expected:
            return True, f"Correct: {actual_tool} (from {expected})"
        else:
            return False, f"Expected one of {expected}, got {actual_tool}"

    return False, f"Unknown expected type: {expected}"


def run_benchmark(model: str, tests: List[Dict] = None):
    """Run benchmark through web app."""
    if tests is None:
        tests = ALL_TESTS

    print(f"\nWeb App Benchmark")
    print(f"Model: {model}")
    print(f"Endpoint: {WEBAPP_URL}/ask")
    print(f"Tests: {len(tests)}")
    print("=" * 60)

    results = []
    passed = 0
    failed = 0

    for test in tests:
        test_id = test["id"]
        prompt = test["prompt"]

        print(f"\n  {test_id}: {prompt[:50]}...")

        # Mark time before call
        pre_call_time = time.time()

        # Call web app
        response, latency_ms = call_webapp(prompt, model)

        actual_tool: Optional[Union[str, List[str]]] = None
        debug_tool_calls = None
        if isinstance(response, dict):
            debug = response.get("debug")
            if isinstance(debug, dict) and "tool_calls" in debug:
                debug_tool_calls = debug.get("tool_calls")

        if debug_tool_calls is not None:
            if not debug_tool_calls:
                actual_tool = None
            elif len(debug_tool_calls) == 1:
                actual_tool = debug_tool_calls[0].get("name")
            else:
                actual_tool = [tc.get("name") for tc in debug_tool_calls if tc.get("name")]
        else:
            # Wait a moment for logs to be written
            time.sleep(0.5)

            # Get logs since just before the call (with extra buffer)
            logs = get_docker_logs_since(seconds_ago=int(latency_ms/1000) + 10)

            # Extract tool that was called
            actual_tool = extract_tool_from_logs(logs)

        # For refusal tests, check if any tool was called
        if test.get("expected_tool") is None and actual_tool is None:
            # No tool call is expected and none was made
            pass

        # Evaluate
        success, details = evaluate_result(test, actual_tool)

        status = "PASS" if success else "FAIL"
        if success:
            passed += 1
        else:
            failed += 1

        print(f"    [{status}] Tool: {actual_tool or 'none'} | {latency_ms:.0f}ms")
        if not success:
            print(f"           {details}")

        results.append({
            "test_id": test_id,
            "prompt": prompt,
            "expected_tool": test.get("expected_tool"),
            "actual_tool": actual_tool,
            "success": success,
            "details": details,
            "latency_ms": latency_ms,
            "response_text": response.get("text", "")[:200] if isinstance(response, dict) else str(response)[:200]
        })

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{len(tests)} passed ({passed/len(tests):.0%})")
    print("=" * 60)

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Web App Tool Calling Benchmark")
    parser.add_argument("-m", "--model", default="qwen3:4b-instruct-2507-q4_K_M",
                        help="Model to test")
    parser.add_argument("-t", "--test", help="Run specific test by ID")
    parser.add_argument("-n", "--num", type=int, help="Limit number of tests")
    parser.add_argument("--category", help="Run tests from specific category")

    args = parser.parse_args()

    # Filter tests
    tests = ALL_TESTS

    if args.test:
        tests = [t for t in tests if t["id"] == args.test]
        if not tests:
            print(f"Test {args.test} not found")
            return

    if args.category:
        tests = [t for t in tests if t["category"] == args.category]

    if args.num:
        tests = tests[:args.num]

    # Run benchmark
    results = run_benchmark(args.model, tests)

    # Save results
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"webapp_benchmark_{args.model.replace(':', '_')}_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump({
            "model": args.model,
            "timestamp": timestamp,
            "total_tests": len(tests),
            "passed": sum(1 for r in results if r["success"]),
            "results": results
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
