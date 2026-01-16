"""
Cost Tracking Service - Token usage logging and budget management

This service handles:
- Token usage to cost conversion
- CSV logging to usage_log_path
- Chat budget tracking and enforcement
- Cost accumulation in chat metadata

Used by: routes/chat_routes.py
"""

import os
import csv
import datetime
from typing import Dict, Any, Tuple, Optional
from config import get_settings
from prices import prices_for
from storage import load_chat, save_chat

settings = get_settings()


class CostTrackingService:
    """Handles usage logging and cost tracking"""

    def __init__(self):
        self.settings = get_settings()
        self.usage_log_path = str(self.settings.usage_log_path)

    def log_usage(
        self,
        chat_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        prompt: str
    ) -> float:
        """
        Log usage to CSV and update chat costs.

        Args:
            chat_id: Chat identifier
            model: Model used
            input_tokens: Input token count
            output_tokens: Output token count
            prompt: User prompt (for logging)

        Returns:
            Total cost in USD
        """
        # Calculate costs
        PRICE_IN, PRICE_OUT = prices_for(model)
        cost_in = (input_tokens / 1_000_000.0) * PRICE_IN
        cost_out = (output_tokens / 1_000_000.0) * PRICE_OUT
        cost_total = cost_in + cost_out

        # Log to CSV
        self._log_to_csv(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_in=cost_in,
            cost_out=cost_out,
            cost_total=cost_total,
            prompt=prompt,
            chat_id=chat_id
        )

        # Update chat metadata
        self._update_chat_cost(chat_id, cost_total)

        return cost_total

    def check_budget(self, chat: Dict) -> Tuple[bool, float, Optional[float]]:
        """
        Check if chat is within budget.

        Args:
            chat: Chat object with meta.budget_usd and meta.spent_usd

        Returns:
            (ok, spent, budget) tuple
            ok=True if under budget or no budget set
        """
        meta = chat.get("meta", {})
        budget = meta.get("budget_usd")
        spent = meta.get("spent_usd", 0.0)

        if budget is None:
            return True, spent, None

        return spent < budget, spent, budget

    def _log_to_csv(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_in: float,
        cost_out: float,
        cost_total: float,
        prompt: str,
        chat_id: str
    ):
        """Append usage entry to CSV log file."""
        new_file = not os.path.exists(self.usage_log_path)

        with open(self.usage_log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow([
                    "timestamp_iso",
                    "model",
                    "input_tokens",
                    "output_tokens",
                    "cost_input_usd",
                    "cost_output_usd",
                    "cost_total_usd",
                    "prompt",
                    "chat_id",
                ])
            w.writerow([
                datetime.datetime.now().isoformat(timespec="seconds"),
                model,
                input_tokens,
                output_tokens,
                f"{cost_in:.6f}",
                f"{cost_out:.6f}",
                f"{cost_total:.6f}",
                prompt,
                chat_id,
            ])

    def _update_chat_cost(self, chat_id: str, cost_to_add: float):
        """Update chat metadata with accumulated cost."""
        if not chat_id:
            return

        chat = load_chat(chat_id)
        if not chat:
            return

        chat.setdefault("meta", {})
        chat["meta"].setdefault("spent_usd", 0.0)
        chat["meta"]["spent_usd"] = (chat["meta"].get("spent_usd") or 0.0) + cost_to_add

        save_chat(chat)

    def get_chat_costs(self, chat_id: str) -> Dict[str, Any]:
        """
        Get current cost information for a chat.

        Returns:
            {"spent": float, "budget": Optional[float], "remaining": Optional[float]}
        """
        chat = load_chat(chat_id)
        if not chat:
            return {"spent": 0.0, "budget": None, "remaining": None}

        meta = chat.get("meta", {})
        spent = meta.get("spent_usd", 0.0)
        budget = meta.get("budget_usd")

        remaining = None
        if budget is not None:
            remaining = budget - spent

        return {
            "spent": spent,
            "budget": budget,
            "remaining": remaining
        }

    def set_chat_budget(self, chat_id: str, budget: Optional[float]):
        """Set budget limit for a chat."""
        chat = load_chat(chat_id)
        if not chat:
            return False

        chat.setdefault("meta", {})
        chat["meta"]["budget_usd"] = budget
        save_chat(chat)
        return True
