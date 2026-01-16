"""
Obsidian Tool Benchmark Suite

A comprehensive test suite to evaluate local LLM tool calling accuracy
on Obsidian vault operations.

Usage:
    python -m tests.obsidian_tool_benchmark.benchmark_runner [options]

Examples:
    # Run all models (automated)
    python -m tests.obsidian_tool_benchmark.benchmark_runner

    # Specific model
    python -m tests.obsidian_tool_benchmark.benchmark_runner -m qwen3:8b

    # Interactive mode
    python -m tests.obsidian_tool_benchmark.benchmark_runner --interactive -m qwen3:4b
"""

__version__ = "1.0.0"
