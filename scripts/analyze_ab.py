#!/usr/bin/env python3
"""
Analyze A/B test results and generate comparison report

Usage:
    python scripts/analyze_ab.py /app/data/ab_results.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from typing import List, Dict


def load_results(csv_path: str) -> List[Dict]:
    """Load results from CSV"""
    results = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                row["latency_ms"] = float(row["latency_ms"])
                row["cost_usd"] = float(row["cost_usd"])
                row["in_tokens"] = int(row["in_tokens"])
                row["out_tokens"] = int(row["out_tokens"])
                row["tool_called"] = row["tool_called"].lower() == "true"
                row["args_valid"] = row["args_valid"].lower() == "true"
                row["success"] = row["success"].lower() == "true"
                results.append(row)
        return results
    except FileNotFoundError:
        print(f"❌ Error: File not found: {csv_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading results: {e}")
        sys.exit(1)


def calculate_percentile(values: List[float], percentile: int) -> float:
    """Calculate percentile of a list of values"""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * (percentile / 100.0))
    return sorted_values[min(index, len(sorted_values) - 1)]


def analyze_by_model(results: List[Dict]) -> Dict[str, Dict]:
    """Analyze results grouped by model"""
    by_model = defaultdict(list)
    
    for result in results:
        by_model[result["model"]].append(result)
    
    analysis = {}
    
    for model, model_results in by_model.items():
        total = len(model_results)
        successful = sum(1 for r in model_results if r["success"])
        tool_called_count = sum(1 for r in model_results if r["tool_called"])
        
        latencies = [r["latency_ms"] for r in model_results]
        costs = [r["cost_usd"] for r in model_results]
        
        analysis[model] = {
            "total_requests": total,
            "successful": successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "tool_call_rate": (tool_called_count / total * 100) if total > 0 else 0,
            "latency_p50": calculate_percentile(latencies, 50),
            "latency_p95": calculate_percentile(latencies, 95),
            "latency_mean": sum(latencies) / len(latencies) if latencies else 0,
            "total_cost": sum(costs),
            "avg_cost_per_request": sum(costs) / len(costs) if costs else 0,
            "total_tokens": sum(r["in_tokens"] + r["out_tokens"] for r in model_results),
        }
    
    return analysis


def print_report(analysis: Dict[str, Dict]):
    """Print formatted comparison report"""
    print("\n" + "="*80)
    print("A/B TEST RESULTS SUMMARY")
    print("="*80 + "\n")
    
    # Get model names
    models = list(analysis.keys())
    
    if len(models) != 2:
        print(f"⚠️  Warning: Expected 2 models, found {len(models)}")
    
    # Print side-by-side comparison
    print(f"{Metric:<30} {models[0]:<25} {models[1]:<25}")
    print("-"*80)
    
    for model in models:
        stats = analysis[model]
        print(f"\n📊 {model}")
        print(f"  Total Requests:          {stats['total_requests']}")
        print(f"  Successful:              {stats['successful']} ({stats['success_rate']:.1f}%)")
        print(f"  Tool Call Rate:          {stats['tool_call_rate']:.1f}%")
        print(f"  Latency p50:             {stats['latency_p50']:.0f}ms")
        print(f"  Latency p95:             {stats['latency_p95']:.0f}ms")
        print(f"  Latency mean:            {stats['latency_mean']:.0f}ms")
        print(f"  Total Cost:              ${stats['total_cost']:.4f}")
        print(f"  Avg Cost/Request:        ${stats['avg_cost_per_request']:.4f}")
        print(f"  Total Tokens:            {stats['total_tokens']:,}")
    
    # Comparison
    if len(models) == 2:
        m1, m2 = models[0], models[1]
        s1, s2 = analysis[m1], analysis[m2]
        
        print("\n" + "="*80)
        print("COMPARISON")
        print("="*80 + "\n")
        
        # Success rate
        if s1["success_rate"] > s2["success_rate"]:
            winner = m1
            diff = s1["success_rate"] - s2["success_rate"]
        else:
            winner = m2
            diff = s2["success_rate"] - s1["success_rate"]
        print(f"✓ Success Rate Winner: {winner} (+{diff:.1f}%)")
        
        # Latency
        if s1["latency_p50"] < s2["latency_p50"]:
            winner = m1
            diff = s2["latency_p50"] - s1["latency_p50"]
        else:
            winner = m2
            diff = s1["latency_p50"] - s2["latency_p50"]
        print(f"⚡ Speed Winner (p50): {winner} ({diff:.0f}ms faster)")
        
        # Cost
        if s1["avg_cost_per_request"] < s2["avg_cost_per_request"]:
            winner = m1
            savings = (1 - s1["avg_cost_per_request"] / s2["avg_cost_per_request"]) * 100
        else:
            winner = m2
            savings = (1 - s2["avg_cost_per_request"] / s1["avg_cost_per_request"]) * 100
        print(f"💰 Cost Winner: {winner} ({savings:.1f}% cheaper)")
        
        # Overall recommendation
        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80 + "\n")
        
        # Simple scoring: success rate (40%), speed (30%), cost (30%)
        score1 = (
            s1["success_rate"] * 0.4 +
            (100 - (s1["latency_p50"] / max(s1["latency_p50"], s2["latency_p50"]) * 100)) * 0.3 +
            (100 - (s1["avg_cost_per_request"] / max(s1["avg_cost_per_request"], s2["avg_cost_per_request"]) * 100)) * 0.3
        )
        score2 = (
            s2["success_rate"] * 0.4 +
            (100 - (s2["latency_p50"] / max(s1["latency_p50"], s2["latency_p50"]) * 100)) * 0.3 +
            (100 - (s2["avg_cost_per_request"] / max(s1["avg_cost_per_request"], s2["avg_cost_per_request"]) * 100)) * 0.3
        )
        
        if score1 > score2:
            print(f"🏆 Overall Winner: {m1}")
            print(f"   Score: {score1:.1f} vs {score2:.1f}")
        else:
            print(f"🏆 Overall Winner: {m2}")
            print(f"   Score: {score2:.1f} vs {score1:.1f}")
        
        print("\n💡 Use case recommendations:")
        print(f"   • High-volume, cost-sensitive: {m1 if s1['avg_cost_per_request'] < s2['avg_cost_per_request'] else m2}")
        print(f"   • Low-latency required: {m1 if s1['latency_p50'] < s2['latency_p50'] else m2}")
        print(f"   • Best accuracy: {m1 if s1['success_rate'] > s2['success_rate'] else m2}")
    
    print("\n" + "="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Analyze A/B test results")
    parser.add_argument("csv_path", help="Path to results CSV file")
    
    args = parser.parse_args()
    
    results = load_results(args.csv_path)
    print(f"✓ Loaded {len(results)} results from {args.csv_path}")
    
    analysis = analyze_by_model(results)
    print_report(analysis)


if __name__ == "__main__":
    main()
