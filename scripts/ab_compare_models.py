#!/usr/bin/env python3
"""
A/B Test Harness for comparing OpenAI function-calling models.

This script drives the WebAppChat /ask endpoint and records latency,
token/cost usage, and simple heuristics about tool usage for each prompt.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import requests


TASKS: List[Dict[str, Any]] = [
    {
        "name": "list_vault_files",
        "prompt": "List files in the Homelab folder",
        "expected_tool": "list_folder_contents",
        "required_args": ["folder_name"],
        "description": "Tests if model correctly identifies folder listing request",
    },
    {
        "name": "read_file",
        "prompt": "Read the file GPU_DETECTION_TROUBLESHOOTING_BRIEF.md from the Homelab folder",
        "expected_tool": "read_note",
        "required_args": ["file_path"],
        "description": "Tests if model correctly identifies file read request",
    },
    {
        "name": "search_vault",
        "prompt": "Search the vault for notes about Docker containers",
        "expected_tool": "search_vault",
        "required_args": ["query"],
        "description": "Tests if model correctly identifies search request",
    },
]


@dataclass
class ABResult:
    model: str
    task: str
    trial: int
    latency_ms: float
    tool_called: bool
    tool_name: str | None
    args_valid: bool
    success: bool
    error: str | None
    cost_usd: float
    in_tokens: int
    out_tokens: int
    response_text: str

    def to_row(self) -> Dict[str, Any]:
        return {
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "task": self.task,
            "trial": self.trial,
            "latency_ms": round(self.latency_ms, 2),
            "tool_called": self.tool_called,
            "tool_name": self.tool_name,
            "args_valid": self.args_valid,
            "success": self.success,
            "error": self.error,
            "cost_usd": self.cost_usd,
            "in_tokens": self.in_tokens,
            "out_tokens": self.out_tokens,
            "response_text": self.response_text,
        }


class ABTestHarness:
    """Drive the /ask endpoint and capture comparisons between models."""

    def __init__(self, base_url: str, verify_ssl: bool = False, timeout: float = 60.0, pause: float = 0.5) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.timeout = timeout
        self.pause = pause
        self.results: List[ABResult] = []

    def run_task(self, model: str, task: Dict[str, Any], trial_num: int) -> ABResult:
        print(f"  Trial {trial_num}: {task['name']} with {model}...", end=" ", flush=True)
        start_time = time.time()

        try:
            response = self.session.post(
                f"{self.base_url}/ask",
                json={
                    "prompt": task["prompt"],
                    "model": model,
                    "system": "You are a helpful assistant with access to an Obsidian vault.",
                },
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            elapsed_ms = (time.time() - start_time) * 1000
            print("⚠ TIMEOUT")
            result = ABResult(
                model=model,
                task=task["name"],
                trial=trial_num,
                latency_ms=elapsed_ms,
                tool_called=False,
                tool_name=None,
                args_valid=False,
                success=False,
                error="Request timeout",
                cost_usd=0.0,
                in_tokens=0,
                out_tokens=0,
                response_text="",
            )
            self.results.append(result)
            return result
        except requests.RequestException as exc:
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"⚠ EXCEPTION: {exc}")
            result = ABResult(
                model=model,
                task=task["name"],
                trial=trial_num,
                latency_ms=elapsed_ms,
                tool_called=False,
                tool_name=None,
                args_valid=False,
                success=False,
                error=str(exc),
                cost_usd=0.0,
                in_tokens=0,
                out_tokens=0,
                response_text="",
            )
            self.results.append(result)
            return result

        elapsed_ms = (time.time() - start_time) * 1000

        if response.status_code != 200:
            print(f"⚠ HTTP {response.status_code}")
            result = ABResult(
                model=model,
                task=task["name"],
                trial=trial_num,
                latency_ms=elapsed_ms,
                tool_called=False,
                tool_name=None,
                args_valid=False,
                success=False,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
                cost_usd=0.0,
                in_tokens=0,
                out_tokens=0,
                response_text=response.text[:200],
            )
            self.results.append(result)
            return result

        data = response.json()
        response_text = data.get("text", "")
        usage = data.get("usage", {})

        # Heuristic: if keywords suggesting vault output appear, assume tool call.
        lowered = response_text.lower()
        expected_tool = task.get("expected_tool")
        tool_called = any(keyword in lowered for keyword in ["vault:", "file", "folder", "search", "found"])

        success = bool(response_text) and "error" not in data
        args_valid = success  # without explicit arg echo we use same heuristic

        cost_usd = float(usage.get("cost_total", 0.0))
        in_tokens = int(usage.get("in_tokens", 0))
        out_tokens = int(usage.get("out_tokens", 0))

        print(f"✅ {elapsed_ms:.0f}ms (${cost_usd:.4f})")

        result = ABResult(
            model=model,
            task=task["name"],
            trial=trial_num,
            latency_ms=elapsed_ms,
            tool_called=tool_called,
            tool_name=expected_tool,
            args_valid=args_valid,
            success=success,
            error=None,
            cost_usd=cost_usd,
            in_tokens=in_tokens,
            out_tokens=out_tokens,
            response_text=response_text,
        )
        self.results.append(result)
        return result

    def run_trials(self, models: List[str], tasks: List[Dict[str, Any]], trials_per_task: int) -> None:
        total_requests = len(models) * len(tasks) * trials_per_task
        print("\n" + "=" * 70)
        print(f"A/B Test: {', '.join(models)}")
        print(f"Tasks: {len(tasks)} | Trials per task: {trials_per_task}")
        print(f"Total requests: {total_requests}")
        print("=" * 70 + "\n")

        for model in models:
            print(f"\n🤖 Testing {model}")
            print("-" * 70)
            for task in tasks:
                print(f"\n  Task: {task['name']} - {task['description']}")
                for trial in range(1, trials_per_task + 1):
                    self.run_task(model, task, trial)
                    time.sleep(self.pause)

        print("\n" + "=" * 70)
        print(f"✅ Testing complete! {len(self.results)} results collected.")
        print("=" * 70 + "\n")

    def save_results(self, output_path: str) -> None:
        if not self.results:
            print("⚠ No results to save.")
            return

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fieldnames = list(ABResult.__annotations__.keys()) + ["timestamp"]

        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=[
                "timestamp", "model", "task", "trial", "latency_ms",
                "tool_called", "tool_name", "args_valid", "success",
                "error", "cost_usd", "in_tokens", "out_tokens", "response_text"
            ])
            writer.writeheader()
            for result in self.results:
                writer.writerow(result.to_row())

        print(f"💾 Results saved to: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A/B test OpenAI models on function calling tasks")
    parser.add_argument("--models", type=str, default="gpt-4o-mini,gpt-5-mini")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=str, default="/app/data/ab_results.csv")
    parser.add_argument("--base-url", type=str, default="https://127.0.0.1:5000")
    parser.add_argument("--verify", action="store_true", help="Verify TLS certificates")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--pause", type=float, default=0.5, help="Seconds to wait between calls")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    models = [model.strip() for model in args.models.split(",") if model.strip()]

    harness = ABTestHarness(
        base_url=args.base_url,
        verify_ssl=args.verify,
        timeout=args.timeout,
        pause=args.pause,
    )

    harness.run_trials(models=models, tasks=TASKS, trials_per_task=args.trials)
    harness.save_results(args.output)

    print("\n📊 Next step: analyze results with:")
    print(f"   python scripts/analyze_ab.py {args.output}")


if __name__ == "__main__":
    main()
