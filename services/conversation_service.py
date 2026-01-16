"""
Conversation Service - Context management and token optimization

This service handles:
- Conversation history trimming to fit context windows
- Token counting and budget tracking
- RAG context injection
- System prompt composition

Used by: routes/chat_routes.py
"""

import tiktoken
from typing import List, Dict, Any, Optional, Tuple
from config import get_settings
from rag_db import search as rag_search
from rag import embed_texts

settings = get_settings()


class ConversationService:
    """Manages conversation context and token budgets"""

    def __init__(self):
        self.settings = get_settings()

    def trim_history(self, messages: List[Dict], model: str, max_tokens: Optional[int] = None) -> List[Dict]:
        """
        Trim message history to fit within model's context window.

        Args:
            messages: Full conversation history
            model: Model identifier for token encoding
            max_tokens: Maximum tokens allowed (defaults to 70% of model limit)

        Returns:
            Trimmed message list with system messages preserved
        """
        if max_tokens is None:
            model_limits = {
                "gpt-4": 8192,
                "gpt-4-turbo": 128000,
                "gpt-4o": 128000,
                "gpt-4o-mini": 128000,
                "gpt-5": 200000,
                "gpt-5-mini": 200000,
                "gpt-5-nano": 200000,
                "o1-mini": 128000,
                "o1-preview": 128000,
                "o1": 200000,
                "claude-3-5-sonnet-20241022": 200000,
                "claude-3-5-sonnet-20240620": 200000,
                "claude-3-opus-20240229": 200000,
            }
            max_tokens = model_limits.get(model, 8192)

        target = int(max_tokens * 0.7)

        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        def count_tokens(msgs):
            total = 0
            for m in msgs:
                content = m.get("content", "")
                if isinstance(content, str):
                    total += len(enc.encode(content))
            return total

        system_tokens = count_tokens(system_msgs)
        if not other_msgs:
            return system_msgs

        available = target - system_tokens
        if available <= 0:
            return system_msgs + other_msgs[-1:]

        current_tokens = count_tokens(other_msgs)
        if current_tokens <= available:
            return system_msgs + other_msgs

        trimmed_other = []
        running_tokens = 0
        for msg in reversed(other_msgs):
            content = msg.get("content", "")
            if isinstance(content, str):
                msg_tokens = len(enc.encode(content))
            else:
                msg_tokens = 0

            if running_tokens + msg_tokens > available:
                break

            trimmed_other.insert(0, msg)
            running_tokens += msg_tokens

        if not trimmed_other and other_msgs:
            trimmed_other = [other_msgs[-1]]

        return system_msgs + trimmed_other

    def inject_rag_context(self, prompt: str, top_k: int = 5) -> Tuple[str, List[Dict]]:
        """
        Retrieve and format RAG context for user query.

        Args:
            prompt: User query to embed and search
            top_k: Number of top results to retrieve

        Returns:
            (context_text, citations) tuple
        """
        try:
            qvec = embed_texts([prompt])[0]
            hits = rag_search(qvec, top_k=top_k, vault_name=self.settings.vault_name)

            blocks = [f"[{h['source']}#{h['ord']}] {h['text']}" for h in hits]
            context_text = "\n\n".join(blocks)

            citations = [
                {
                    "source": hit["source"],
                    "chunk_id": hit.get("chunk_id"),
                    "score": round(hit["score"], 4),
                    "snippet": (
                        hit["text"][:200] + "..." if len(hit["text"]) > 200 else hit["text"]
                    ),
                    "obsidian_link": hit.get("obsidian_link", ""),
                }
                for hit in hits
            ]

            return context_text, citations
        except Exception as e:
            # If RAG fails, return empty context rather than breaking the request
            return "", []

    def prepare_context(
        self,
        messages: List[Dict],
        system_prompts: List[str],
        model: str,
        max_tokens: Optional[int] = None,
        rag_query: Optional[str] = None,
        rag_enabled: bool = False
    ) -> Tuple[List[Dict], List[str], List[Dict]]:
        """
        Prepare conversation context with token budget constraints and optional RAG.

        Args:
            messages: Full conversation history
            system_prompts: Base system prompts
            model: Model identifier
            max_tokens: Maximum context tokens allowed
            rag_query: Optional query for RAG retrieval
            rag_enabled: Whether to include RAG context

        Returns:
            (trimmed_messages, system_prompts_with_rag, rag_citations)
        """
        citations = []

        # Add RAG context if enabled
        if rag_enabled and rag_query:
            context_text, citations = self.inject_rag_context(rag_query)
            if context_text:
                system_prompts = system_prompts + [
                    f"Relevant context from knowledge base:\n\n{context_text}"
                ]

        # Trim message history to fit token budget
        trimmed_messages = self.trim_history(messages, model, max_tokens)

        return trimmed_messages, system_prompts, citations
