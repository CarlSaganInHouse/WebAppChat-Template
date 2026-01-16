"""
Metrics Collector for Tool Calling Benchmark

Provides dataclasses for storing test results and aggregating statistics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict
import statistics

from .evaluation import FailureMode


@dataclass
class TestMetrics:
    """Metrics captured for each test execution"""

    # Identification
    test_id: str
    model: str
    timestamp: datetime

    # Test metadata
    difficulty: str = ""
    category: str = ""
    prompt: str = ""
    description: str = ""

    # Timing
    latency_ms: float = 0.0
    time_to_first_token_ms: float = 0.0

    # Token Usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Accuracy Scores
    tool_selection_score: float = 0.0
    parameter_score: float = 0.0
    combined_score: float = 0.0

    # Results
    expected_tool: Optional[Any] = None
    actual_tool: Optional[str] = None
    expected_params: Dict = field(default_factory=dict)
    actual_params: Dict = field(default_factory=dict)

    # Status
    success: bool = False
    tool_status: str = ""
    param_status: str = ""

    # Failure Info
    failure_mode: Optional[FailureMode] = None
    failure_details: str = ""

    # Raw Response
    raw_response: str = ""
    tool_call_json: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_id": self.test_id,
            "model": self.model,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "difficulty": self.difficulty,
            "category": self.category,
            "prompt": self.prompt,
            "description": self.description,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "tool_selection_score": self.tool_selection_score,
            "parameter_score": self.parameter_score,
            "combined_score": self.combined_score,
            "expected_tool": str(self.expected_tool) if self.expected_tool else None,
            "actual_tool": self.actual_tool,
            "actual_params": self.actual_params,
            "success": self.success,
            "tool_status": self.tool_status,
            "param_status": self.param_status,
            "failure_mode": self.failure_mode.value if self.failure_mode else None,
            "failure_details": self.failure_details,
            "raw_response": self.raw_response[:500] if self.raw_response else "",
        }


@dataclass
class ModelSummary:
    """Aggregated metrics for a model across all tests"""

    model_name: str
    total_tests: int = 0

    # Overall Accuracy
    overall_success_rate: float = 0.0
    tool_selection_accuracy: float = 0.0
    parameter_accuracy: float = 0.0
    avg_combined_score: float = 0.0

    # By Difficulty
    easy_success_rate: float = 0.0
    easy_count: int = 0
    medium_success_rate: float = 0.0
    medium_count: int = 0
    hard_success_rate: float = 0.0
    hard_count: int = 0

    # By Category
    category_rates: Dict[str, float] = field(default_factory=dict)

    # Performance
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    avg_tokens: float = 0.0

    # Failure Analysis
    failure_mode_counts: Dict[str, int] = field(default_factory=dict)
    failed_test_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "model_name": self.model_name,
            "total_tests": self.total_tests,
            "overall_success_rate": round(self.overall_success_rate, 4),
            "tool_selection_accuracy": round(self.tool_selection_accuracy, 4),
            "parameter_accuracy": round(self.parameter_accuracy, 4),
            "avg_combined_score": round(self.avg_combined_score, 4),
            "by_difficulty": {
                "EASY": {"success_rate": round(self.easy_success_rate, 4), "count": self.easy_count},
                "MEDIUM": {"success_rate": round(self.medium_success_rate, 4), "count": self.medium_count},
                "HARD": {"success_rate": round(self.hard_success_rate, 4), "count": self.hard_count},
            },
            "by_category": {k: round(v, 4) for k, v in self.category_rates.items()},
            "performance": {
                "avg_latency_ms": round(self.avg_latency_ms, 2),
                "p50_latency_ms": round(self.p50_latency_ms, 2),
                "p95_latency_ms": round(self.p95_latency_ms, 2),
                "min_latency_ms": round(self.min_latency_ms, 2),
                "max_latency_ms": round(self.max_latency_ms, 2),
                "avg_tokens": round(self.avg_tokens, 2),
            },
            "failure_analysis": {
                "total_failures": sum(self.failure_mode_counts.values()),
                "by_mode": self.failure_mode_counts,
                "failed_tests": self.failed_test_ids,
            }
        }


class MetricsCollector:
    """Collects and aggregates benchmark metrics"""

    def __init__(self):
        self.results: List[TestMetrics] = []
        self.by_model: Dict[str, List[TestMetrics]] = defaultdict(list)

    def add_result(self, result: TestMetrics):
        """Add a test result"""
        self.results.append(result)
        self.by_model[result.model].append(result)

    def get_model_summary(self, model: str) -> ModelSummary:
        """Calculate summary statistics for a model"""
        results = self.by_model.get(model, [])
        if not results:
            return ModelSummary(model_name=model)

        summary = ModelSummary(model_name=model)
        summary.total_tests = len(results)

        # Overall success
        successes = sum(1 for r in results if r.success)
        summary.overall_success_rate = successes / len(results)

        # Tool selection accuracy (average score)
        summary.tool_selection_accuracy = statistics.mean(
            r.tool_selection_score for r in results
        )

        # Parameter accuracy (average score)
        summary.parameter_accuracy = statistics.mean(
            r.parameter_score for r in results
        )

        # Combined score
        summary.avg_combined_score = statistics.mean(
            r.combined_score for r in results
        )

        # By difficulty
        easy = [r for r in results if r.difficulty == "EASY"]
        medium = [r for r in results if r.difficulty == "MEDIUM"]
        hard = [r for r in results if r.difficulty == "HARD"]

        summary.easy_count = len(easy)
        summary.medium_count = len(medium)
        summary.hard_count = len(hard)

        if easy:
            summary.easy_success_rate = sum(1 for r in easy if r.success) / len(easy)
        if medium:
            summary.medium_success_rate = sum(1 for r in medium if r.success) / len(medium)
        if hard:
            summary.hard_success_rate = sum(1 for r in hard if r.success) / len(hard)

        # By category
        categories = set(r.category for r in results)
        for cat in categories:
            cat_results = [r for r in results if r.category == cat]
            if cat_results:
                summary.category_rates[cat] = sum(
                    1 for r in cat_results if r.success
                ) / len(cat_results)

        # Latency statistics
        latencies = [r.latency_ms for r in results if r.latency_ms > 0]
        if latencies:
            summary.avg_latency_ms = statistics.mean(latencies)
            summary.min_latency_ms = min(latencies)
            summary.max_latency_ms = max(latencies)
            sorted_lat = sorted(latencies)
            summary.p50_latency_ms = sorted_lat[len(sorted_lat) // 2]
            p95_idx = int(len(sorted_lat) * 0.95)
            summary.p95_latency_ms = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]

        # Token usage
        tokens = [r.total_tokens for r in results if r.total_tokens > 0]
        if tokens:
            summary.avg_tokens = statistics.mean(tokens)

        # Failure analysis
        for r in results:
            if not r.success and r.failure_mode:
                mode = r.failure_mode.value
                summary.failure_mode_counts[mode] = summary.failure_mode_counts.get(mode, 0) + 1
                summary.failed_test_ids.append(r.test_id)

        return summary

    def get_all_summaries(self) -> Dict[str, ModelSummary]:
        """Get summaries for all models"""
        return {model: self.get_model_summary(model) for model in self.by_model.keys()}

    def get_difficulty_comparison(self) -> Dict[str, Dict[str, float]]:
        """Get success rates by difficulty for all models"""
        comparison = {}
        for model in self.by_model.keys():
            summary = self.get_model_summary(model)
            comparison[model] = {
                "EASY": summary.easy_success_rate,
                "MEDIUM": summary.medium_success_rate,
                "HARD": summary.hard_success_rate,
            }
        return comparison

    def get_test_comparison(self, test_id: str) -> Dict[str, TestMetrics]:
        """Get results for a specific test across all models"""
        return {
            model: next((r for r in results if r.test_id == test_id), None)
            for model, results in self.by_model.items()
        }

    def to_dict(self) -> Dict:
        """Convert all results to dictionary for JSON serialization"""
        return {
            "results": [r.to_dict() for r in self.results],
            "summaries": {
                model: self.get_model_summary(model).to_dict()
                for model in self.by_model.keys()
            }
        }
