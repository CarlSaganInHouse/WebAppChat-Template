"""
Observability and logging utilities for tool calling.

Provides structured logging, metrics collection, and error tracking for function calls.
Designed to be the central point for understanding tool call success/failure patterns.

Architecture:
- log_tool_call() is the entry point; called for every tool invocation
- ToolCallMetrics tracks aggregated stats in-memory (with size limits)
- Logs are written to structlog (configured globally in app.py)
- /debug/tool-call-stats endpoint exposes metrics for inspection
"""

import time
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from collections import deque
import structlog

logger = structlog.get_logger()


class ToolCallMetrics:
    """
    Track tool call success/failure rates and statistics.
    
    Uses a ring buffer (deque) to limit memory growth over long sessions.
    When the buffer is full, oldest entries are discarded.
    """
    
    MAX_ENTRIES = 1000  # Keep last 1000 calls
    
    def __init__(self):
        # Use deque for automatic ring buffer behavior
        self.calls = deque(maxlen=self.MAX_ENTRIES)
    
    def record(self, entry: Dict[str, Any]):
        """Add a tool call entry to metrics. Old entries auto-discard when full."""
        self.calls.append(entry)
    
    def get_all(self) -> list:
        """Return all entries currently in buffer (for debugging)"""
        return list(self.calls)
    
    def get_stats(self, filter_by_model: Optional[str] = None) -> Dict[str, Any]:
        """
        Return aggregated statistics.
        
        Format:
        {
            "gpt-4o-mini": {
                "create_simple_note": {
                    "total": 10,
                    "success": 9,
                    "failed": 1,
                    "avg_duration_ms": 245.3
                },
                ...
            },
            ...
        }
        """
        stats = {}
        
        for entry in self.calls:
            model = entry.get("model", "unknown")
            function = entry.get("function", "unknown")
            
            if filter_by_model and model != filter_by_model:
                continue
            
            if model not in stats:
                stats[model] = {}
            if function not in stats[model]:
                stats[model][function] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "durations_ms": []
                }
            
            stats[model][function]["total"] += 1
            if entry.get("success"):
                stats[model][function]["success"] += 1
            else:
                stats[model][function]["failed"] += 1
            
            if entry.get("duration_ms") is not None:
                stats[model][function]["durations_ms"].append(entry["duration_ms"])
        
        # Compute averages and clean up
        for model in stats:
            for function in stats[model]:
                durations = stats[model][function].pop("durations_ms", [])
                if durations:
                    stats[model][function]["avg_duration_ms"] = round(sum(durations) / len(durations), 2)
                else:
                    stats[model][function]["avg_duration_ms"] = 0
                
                # Compute success rate
                total = stats[model][function]["total"]
                success = stats[model][function]["success"]
                stats[model][function]["success_rate"] = round(success / total, 3) if total > 0 else 0
        
        return stats
    
    def summary(self) -> Dict[str, Any]:
        """Return a high-level summary of all tracked calls"""
        stats = self.get_stats()
        
        total_calls = sum(
            v["total"] for m in stats.values() 
            for v in m.values()
        )
        total_success = sum(
            v["success"] for m in stats.values() 
            for v in m.values()
        )
        
        return {
            "total_calls": total_calls,
            "total_success": total_success,
            "total_failed": total_calls - total_success,
            "overall_success_rate": round(total_success / total_calls, 3) if total_calls > 0 else 0,
            "by_model": stats
        }


# Global metrics instance
metrics = ToolCallMetrics()


def log_tool_call(
    call_id: str,
    model: str,
    function: str,
    status: str,
    call_index: Optional[int] = None,
    conversation_turn: Optional[int] = None,
    trimmed_tokens: Optional[int] = None,
    args: Optional[Dict] = None,
    error: Optional[str] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None
):
    """
    Log a tool call with structured metadata.
    
    This is the central observability entry point. Every tool call should generate
    exactly one log entry via this function.
    
    Args:
        call_id: Unique identifier for this tool call (string)
        model: Model name (e.g., "gpt-4o-mini", "claude-3-sonnet")
        function: Function name (e.g., "create_simple_note")
        status: One of: "initiated", "parse_error", "validation_error", 
                "execution_error", "success", "timeout"
        call_index: Position in current request (e.g., 1st of 2 tool calls in this response)
        conversation_turn: Absolute turn number in conversation (for "first call works, later fails" hypothesis)
        trimmed_tokens: Approximate token count of trimmed conversation context
        args: Function arguments (will be truncated if >500 chars to avoid log spam)
        error: Error message (if applicable). NEVER redacted; full message is essential for diagnosis.
        duration_ms: Execution time in milliseconds
        success: Boolean success indicator. If not provided, inferred from status.
    
    Side effects:
        - Writes to structlog (appears in Flask logs)
        - Records to in-memory metrics (used by /debug/tool-call-stats)
    """
    
    # Infer success from status if not provided
    if success is None:
        success = status == "success"
    
    # Truncate args for logging to avoid huge log lines
    # But NEVER truncate the error message itself
    args_str = ""
    if args:
        try:
            args_str = json.dumps(args)
            if len(args_str) > 500:
                args_str = args_str[:497] + "..."
        except (TypeError, ValueError):
            args_str = "[unserializable]"
    
    # Build the log entry
    entry = {
        "call_id": call_id,
        "model": model,
        "function": function,
        "status": status,
        "success": success,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    # Optional metadata
    if call_index is not None:
        entry["call_index_in_batch"] = call_index
    if conversation_turn is not None:
        entry["conversation_turn"] = conversation_turn
    if trimmed_tokens is not None:
        entry["trimmed_tokens"] = trimmed_tokens
    if args_str:
        entry["args_preview"] = args_str
    if error:
        entry["error"] = error  # FULL error message, never redacted
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    
    # Record to metrics
    metrics.record(entry)
    
    # Log using structlog
    # INFO for success, WARNING for failures
    if status == "success":
        logger.info("tool_call_success", **entry)
    else:
        logger.warning("tool_call_failed", **entry)


def get_tool_call_stats(model: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve aggregated tool call statistics.
    
    Returns nested dict: {model: {function: {total, success, failed, avg_duration_ms, success_rate}}}
    """
    return metrics.get_stats(filter_by_model=model)


def get_tool_call_summary() -> Dict[str, Any]:
    """
    Retrieve high-level summary of tool calling performance.
    
    Returns: {total_calls, total_success, total_failed, overall_success_rate, by_model}
    """
    return metrics.summary()


def reset_metrics():
    """
    Clear all accumulated metrics (useful for starting a fresh measurement window).
    """
    metrics.calls.clear()


# Utility for testing/debugging
def get_recent_tool_calls(limit: int = 10) -> list:
    """
    Retrieve the N most recent tool call log entries.
    Useful for spot-checking recent failures in /debug endpoints.
    """
    all_calls = metrics.get_all()
    return all_calls[-limit:] if all_calls else []
