#!/usr/bin/env python3
"""
A/B Test Harness for GPT-5-Nano vs GPT-4o-Mini
Tests function calling accuracy, latency, and overall performance

Usage:
    python scripts/ab_openai_tools.py --models gpt-5-nano,gpt-4o-mini --trials 5 --output /app/data/ab_results.csv
"""

import argparse
import csv
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Any


# Test task definitions
TASKS = [
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


class ABTestHarness:
    """A/B Test harness for comparing OpenAI models on function calling tasks"""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.results = []
    
    def run_task(self, model: str, task: Dict[str, Any], trial_num: int) -> Dict[str, Any]:
        """
        Execute one task and collect metrics
        
        Returns dict with:
            - model: str
            - task: str
            - trial: int
            - latency_ms: float
            - tool_called: bool
            - tool_name: str | None
            - args_valid: bool
            - success: bool
            - error: str | None
            - cost_usd: float
        """
        print(f"  Trial {trial_num}: {task['name']} with {model}...", end=" ", flush=True)
        
        start_time = time.time()
        
        try:
            # Make request to /ask endpoint
            response = requests.post(
                f"{self.base_url}/ask",
                json={
                    "prompt": task["prompt"],
                    "model": model,
                    
                    "system": "You are a helpful assistant with access to an Obsidian vault.",
                },
                timeout=60,
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                print(f"❌ ERROR (HTTP {response.status_code})")
                return {
                    "model": model,
                    "task": task["name"],
                    "trial": trial_num,
                    "latency_ms": elapsed_ms,
                    "tool_called": False,
                    "tool_name": None,
                    "args_valid": False,
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text[:100]}",
                    "cost_usd": 0.0,
                    "in_tokens": 0,
                    "out_tokens": 0,
                }
            
            data = response.json()
            
            # Check if function was called by looking at the response text
            response_text = data.get("text", "").lower()
            
            # Indicators that a function was likely called
            function_indicators = [
                "file" in response_text,
                "folder" in response_text,
                "found" in response_text,
                "search" in response_text,
                "result" in response_text,
            ]
            
            tool_called = any(function_indicators)
            success = "error" not in data and len(response_text) > 0
            
            # Extract cost
            usage = data.get("usage", {})
            cost_usd = usage.get("cost_total", 0.0)
            in_tokens = usage.get("in_tokens", 0)
            out_tokens = usage.get("out_tokens", 0)
            
            print(f"✓ {elapsed_ms:.0f}ms (${cost_usd:.4f})")
            
            return {
                "model": model,
                "task": task["name"],
                "trial": trial_num,
                "latency_ms": round(elapsed_ms, 2),
                "tool_called": tool_called,
                "tool_name": task["expected_tool"],
                "args_valid": success,
                "success": success,
                "error": None,
                "cost_usd": cost_usd,
                "in_tokens": in_tokens,
                "out_tokens": out_tokens,
            }
            
        except requests.exceptions.Timeout:
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"❌ TIMEOUT")
            return {
                "model": model,
                "task": task["name"],
                "trial": trial_num,
                "latency_ms": elapsed_ms,
                "tool_called": False,
                "tool_name": None,
                "args_valid": False,
                "success": False,
                "error": "Request timeout",
                "cost_usd": 0.0,
                "in_tokens": 0,
                "out_tokens": 0,
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"❌ EXCEPTION: {str(e)[:50]}")
            return {
                "model": model,
                "task": task["name"],
                "trial": trial_num,
                "latency_ms": elapsed_ms,
                "tool_called": False,
                "tool_name": None,
                "args_valid": False,
                "success": False,
                "error": str(e)[:200],
                "cost_usd": 0.0,
                "in_tokens": 0,
                "out_tokens": 0,
            }
    
    def run_trials(self, models: List[str], tasks: List[Dict], trials_per_task: int = 5):
        """Run N trials for each model/task combination"""
        print(f"\n{'='*70}")
        print(f"A/B Test: {', '.join(models)}")
        print(f"Tasks: {len(tasks)} | Trials per task: {trials_per_task}")
        print(f"Total requests: {len(models) * len(tasks) * trials_per_task}")
        print(f"{'='*70}\n")
        
        for model in models:
            print(f"\n📊 Testing {model}")
            print(f"{'-'*70}")
            
            for task in tasks:
                print(f"\n  Task: {task['name']} - {task['description']}")
                
                for trial in range(1, trials_per_task + 1):
                    result = self.run_task(model, task, trial)
                    self.results.append(result)
                    time.sleep(0.5)
        
        print(f"\n{'='*70}")
        print(f"✅ Testing complete! {len(self.results)} results collected.")
        print(f"{'='*70}\n")
    
    def save_results(self, output_path: str):
        """Save results to CSV file"""
        if not self.results:
            print("⚠️  No results to save!")
            return
        
        fieldnames = [
            "timestamp", "model", "task", "trial", "latency_ms",
            "tool_called", "tool_name", "args_valid", "success",
            "error", "cost_usd", "in_tokens", "out_tokens",
        ]
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in self.results:
                row = {"timestamp": datetime.now().isoformat(), **result}
                writer.writerow(row)
        
        print(f"💾 Results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="A/B test OpenAI models on function calling")
    parser.add_argument("--models", type=str, default="gpt-5-nano,gpt-4o-mini")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=str, default="/app/data/ab_results.csv")
    parser.add_argument("--base-url", type=str, default="http://localhost:5000")
    
    args = parser.parse_args()
    models = [m.strip() for m in args.models.split(",")]
    
    harness = ABTestHarness(base_url=args.base_url)
    harness.run_trials(models=models, tasks=TASKS, trials_per_task=args.trials)
    harness.save_results(args.output)
    
    print(f"\n🎯 Next step: Analyze results with:")
    print(f"   python scripts/analyze_ab.py {args.output}")


if __name__ == "__main__":
    main()
