#!/usr/bin/env python3
"""
Tool Calling Benchmark for Local LLMs

This script evaluates how well different local models handle tool/function calling.
It tests various categories of queries and measures:
- Tool selection accuracy (did it pick the right tool?)
- Parameter extraction accuracy (did it extract the right values?)
- Response quality (did it answer the question?)

Usage:
    python tool_calling_benchmark.py [model_name]

    If no model specified, tests all native tool-calling models.

Example:
    python tool_calling_benchmark.py qwen3:14b
    python tool_calling_benchmark.py  # Tests all models
"""

import json
import time
import sys
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple

OLLAMA_URL = "http://localhost:11434"

# Models to test (native tool-calling models)
TEST_MODELS = [
    "qwen3:4b-instruct-2507-q4_K_M",
    "qwen3:8b",
    "qwen3:14b",
    "qwen3:30b",
    "qwen3:32b",
    "qwen2.5:7b",
    "qwen2.5:14b",
    "llama3.2:3b",
]

# Core tools available to local models (matches LOCAL_MODEL_CORE_TOOLS)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_thermostat_status",
            "description": "Get the current thermostat status including temperature, set point, and mode",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_thermostat",
            "description": "Control the thermostat - set temperature or change mode",
            "parameters": {
                "type": "object",
                "properties": {
                    "temperature": {"type": "number", "description": "Target temperature in Fahrenheit"},
                    "mode": {"type": "string", "enum": ["heat", "cool", "auto", "off"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_light_status",
            "description": "Get the status of lights in a room or all lights",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {"type": "string", "description": "Room name (optional, omit for all lights)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_lights",
            "description": "Control lights - turn on/off or set brightness",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {"type": "string", "description": "Room name"},
                    "action": {"type": "string", "enum": ["on", "off", "toggle"]},
                    "brightness": {"type": "number", "description": "Brightness 0-100"}
                },
                "required": ["room", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": "Search across all vault content for keywords or topics",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": "Read a specific note from the vault by path",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the note"}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_daily_note",
            "description": "Read today's daily note or a specific date's note",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format (optional)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_folder_contents",
            "description": "List files and folders in a vault directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "Folder path"}
                },
                "required": ["folder_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_daily_note",
            "description": "Add content to today's daily note",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to append"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_tasks",
            "description": "Get tasks from today's daily note",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]

# Test cases: (prompt, expected_tool, description, param_checks)
# param_checks is a dict of param_name -> expected_value or callable
TEST_CASES = [
    # ============ SMART HOME - THERMOSTAT ============
    {
        "category": "Thermostat",
        "prompt": "What's my thermostat set to?",
        "expected_tool": "get_thermostat_status",
        "description": "Simple thermostat query",
        "param_checks": {}
    },
    {
        "category": "Thermostat",
        "prompt": "What is the current temperature in my house?",
        "expected_tool": "get_thermostat_status",
        "description": "Natural language temperature query",
        "param_checks": {}
    },
    {
        "category": "Thermostat",
        "prompt": "Set the thermostat to 72 degrees",
        "expected_tool": "control_thermostat",
        "description": "Set temperature command",
        "param_checks": {"temperature": 72}
    },
    {
        "category": "Thermostat",
        "prompt": "Turn the heat on and set it to 70",
        "expected_tool": "control_thermostat",
        "description": "Mode + temperature command",
        "param_checks": {"mode": "heat", "temperature": 70}
    },

    # ============ SMART HOME - LIGHTS ============
    {
        "category": "Lights",
        "prompt": "Turn on the living room lights",
        "expected_tool": "control_lights",
        "description": "Simple light on command",
        "param_checks": {"action": "on"}
    },
    {
        "category": "Lights",
        "prompt": "What lights are currently on?",
        "expected_tool": "get_light_status",
        "description": "Light status query",
        "param_checks": {}
    },
    {
        "category": "Lights",
        "prompt": "Dim the bedroom lights to 50%",
        "expected_tool": "control_lights",
        "description": "Brightness control",
        "param_checks": {"brightness": 50}
    },
    {
        "category": "Lights",
        "prompt": "Turn off all the lights in the kitchen",
        "expected_tool": "control_lights",
        "description": "Light off command with room",
        "param_checks": {"action": "off"}
    },

    # ============ VAULT - READING ============
    {
        "category": "Vault Read",
        "prompt": "Read my daily note",
        "expected_tool": "read_daily_note",
        "description": "Read today's daily note",
        "param_checks": {}
    },
    {
        "category": "Vault Read",
        "prompt": "What's in my Reference folder?",
        "expected_tool": "list_folder_contents",
        "description": "List folder contents",
        "param_checks": {}
    },
    {
        "category": "Vault Read",
        "prompt": "Show me the contents of my Homelab folder",
        "expected_tool": "list_folder_contents",
        "description": "Natural language folder listing",
        "param_checks": {}
    },

    # ============ VAULT - SEARCH ============
    {
        "category": "Vault Search",
        "prompt": "Search for notes about Docker",
        "expected_tool": "search_vault",
        "description": "Simple vault search",
        "param_checks": {"query": lambda q: "docker" in q.lower()}
    },
    {
        "category": "Vault Search",
        "prompt": "Find any notes mentioning homelab",
        "expected_tool": "search_vault",
        "description": "Natural language search",
        "param_checks": {"query": lambda q: "homelab" in q.lower()}
    },

    # ============ VAULT - CREATION ============
    {
        "category": "Vault Create",
        "prompt": "Add a reminder to my daily note: Call the dentist tomorrow",
        "expected_tool": "append_to_daily_note",
        "description": "Append to daily note",
        "param_checks": {"content": lambda c: "dentist" in c.lower()}
    },

    # ============ TASKS ============
    {
        "category": "Tasks",
        "prompt": "What tasks do I have today?",
        "expected_tool": "get_today_tasks",
        "description": "Get today's tasks",
        "param_checks": {}
    },
    {
        "category": "Tasks",
        "prompt": "Show me my todo list",
        "expected_tool": "get_today_tasks",
        "description": "Natural language tasks query",
        "param_checks": {}
    },

    # ============ EDGE CASES ============
    {
        "category": "Edge Case",
        "prompt": "What's the weather like?",
        "expected_tool": None,  # Should NOT call a tool
        "description": "Query with no matching tool",
        "param_checks": {}
    },
]


def run_test(model: str, test_case: dict) -> dict:
    """Run a single test case and return results."""
    prompt = test_case["prompt"]
    expected_tool = test_case["expected_tool"]
    param_checks = test_case["param_checks"]

    messages = [{"role": "user", "content": prompt}]

    start_time = time.time()
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "tools": TOOLS,
                "options": {"temperature": 0.1},
                "stream": False
            },
            timeout=300
        )
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start_time

        # Extract tool calls
        message = data.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        # Determine if tool was called
        tool_called = None
        tool_args = {}
        if tool_calls:
            tool_called = tool_calls[0].get("function", {}).get("name")
            tool_args = tool_calls[0].get("function", {}).get("arguments", {})

        # Evaluate results
        tool_correct = (tool_called == expected_tool)

        # Check parameters
        params_correct = True
        param_errors = []
        for param_name, expected_value in param_checks.items():
            actual_value = tool_args.get(param_name)
            if callable(expected_value):
                if not expected_value(actual_value):
                    params_correct = False
                    param_errors.append(f"{param_name}: got '{actual_value}'")
            elif actual_value != expected_value:
                params_correct = False
                param_errors.append(f"{param_name}: expected '{expected_value}', got '{actual_value}'")

        return {
            "success": tool_correct and params_correct,
            "tool_correct": tool_correct,
            "params_correct": params_correct,
            "expected_tool": expected_tool,
            "actual_tool": tool_called,
            "tool_args": tool_args,
            "param_errors": param_errors,
            "response_content": content[:200] if content else "",
            "elapsed_seconds": elapsed,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "tool_correct": False,
            "params_correct": False,
            "expected_tool": expected_tool,
            "actual_tool": None,
            "tool_args": {},
            "param_errors": [],
            "response_content": "",
            "elapsed_seconds": time.time() - start_time,
            "error": str(e)
        }


def run_benchmark(model: str, verbose: bool = True) -> dict:
    """Run full benchmark for a model."""
    print(f"\n{'='*60}")
    print(f"BENCHMARKING: {model}")
    print(f"{'='*60}")

    # Verify model is available
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/show", json={"name": model}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR: Model {model} not available: {e}")
        return {"model": model, "error": str(e)}

    results = {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "tests": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "tool_selection_accuracy": 0,
            "param_extraction_accuracy": 0,
            "avg_latency_seconds": 0,
            "by_category": {}
        }
    }

    total_time = 0
    tool_correct_count = 0
    params_correct_count = 0
    tests_with_params = 0

    for i, test_case in enumerate(TEST_CASES):
        category = test_case["category"]
        description = test_case["description"]

        if verbose:
            print(f"\n[{i+1}/{len(TEST_CASES)}] {category}: {description}")
            print(f"    Prompt: \"{test_case['prompt'][:50]}...\"")

        result = run_test(model, test_case)
        result["category"] = category
        result["description"] = description
        result["prompt"] = test_case["prompt"]
        results["tests"].append(result)

        # Update counts
        results["summary"]["total"] += 1
        total_time += result["elapsed_seconds"]

        if result["tool_correct"]:
            tool_correct_count += 1
        if test_case["param_checks"]:
            tests_with_params += 1
            if result["params_correct"]:
                params_correct_count += 1

        if result["success"]:
            results["summary"]["passed"] += 1
            status = "✓ PASS"
        else:
            results["summary"]["failed"] += 1
            status = "✗ FAIL"

        # Track by category
        if category not in results["summary"]["by_category"]:
            results["summary"]["by_category"][category] = {"passed": 0, "failed": 0}
        if result["success"]:
            results["summary"]["by_category"][category]["passed"] += 1
        else:
            results["summary"]["by_category"][category]["failed"] += 1

        if verbose:
            print(f"    {status} | Expected: {result['expected_tool']} | Got: {result['actual_tool']}")
            if result["param_errors"]:
                print(f"    Param errors: {result['param_errors']}")
            if result["error"]:
                print(f"    Error: {result['error']}")
            print(f"    Latency: {result['elapsed_seconds']:.2f}s")

    # Calculate summary stats
    results["summary"]["tool_selection_accuracy"] = round(
        tool_correct_count / len(TEST_CASES) * 100, 1
    )
    results["summary"]["param_extraction_accuracy"] = round(
        params_correct_count / tests_with_params * 100 if tests_with_params > 0 else 100, 1
    )
    results["summary"]["avg_latency_seconds"] = round(total_time / len(TEST_CASES), 2)

    # Print summary
    print(f"\n{'-'*60}")
    print(f"SUMMARY: {model}")
    print(f"{'-'*60}")
    print(f"Overall: {results['summary']['passed']}/{results['summary']['total']} tests passed")
    print(f"Tool Selection Accuracy: {results['summary']['tool_selection_accuracy']}%")
    print(f"Parameter Extraction Accuracy: {results['summary']['param_extraction_accuracy']}%")
    print(f"Average Latency: {results['summary']['avg_latency_seconds']}s")
    print(f"\nBy Category:")
    for cat, stats in results["summary"]["by_category"].items():
        total = stats["passed"] + stats["failed"]
        pct = round(stats["passed"] / total * 100) if total > 0 else 0
        print(f"  {cat}: {stats['passed']}/{total} ({pct}%)")

    return results


def main():
    models_to_test = sys.argv[1:] if len(sys.argv) > 1 else TEST_MODELS

    all_results = []
    for model in models_to_test:
        results = run_benchmark(model)
        all_results.append(results)

    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/tool_benchmark_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n\nResults saved to: {output_file}")

    # Print comparison table if multiple models
    if len(all_results) > 1:
        print(f"\n{'='*80}")
        print("COMPARISON TABLE")
        print(f"{'='*80}")
        print(f"{'Model':<35} {'Pass%':>8} {'Tool%':>8} {'Param%':>8} {'Latency':>10}")
        print(f"{'-'*80}")
        for r in sorted(all_results, key=lambda x: x.get("summary", {}).get("tool_selection_accuracy", 0), reverse=True):
            if "error" in r and r.get("error"):
                print(f"{r['model']:<35} {'ERROR':>8}")
            else:
                s = r["summary"]
                pass_pct = round(s["passed"] / s["total"] * 100) if s["total"] > 0 else 0
                print(f"{r['model']:<35} {pass_pct:>7}% {s['tool_selection_accuracy']:>7}% {s['param_extraction_accuracy']:>7}% {s['avg_latency_seconds']:>9}s")


if __name__ == "__main__":
    main()
