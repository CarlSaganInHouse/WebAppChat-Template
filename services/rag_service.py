"""
RAG (Retrieval-Augmented Generation) Service

Centralized service for document processing, embedding, and semantic search.
Combines chunking logic (rag.py) and database operations (rag_db.py).

This service encapsulates:
- Text chunking and tokenization
- Embedding generation via OpenAI
- Vector database operations
- Semantic search via cosine similarity
- Preset management for chat configurations
"""

import os
import re
import json
import time
import sqlite3
import urllib.parse
import tiktoken
import structlog
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

logger = structlog.get_logger()


class RAGService:
    """
    Unified RAG service for document processing and semantic search.

    Handles:
    - Text chunking with token limits
    - Embedding generation (OpenAI)
    - Vector storage in SQLite
    - Semantic search via cosine similarity
    - Preset management
    """

    def __init__(
        self,
        db_path: str = "rag.sqlite3",
        chunk_size: int = 500,
        embedding_model: str = "text-embedding-ada-002",
        api_key: Optional[str] = None
    ):
        """
        Initialize RAG service.

        Args:
            db_path: Path to SQLite database
            chunk_size: Maximum tokens per chunk
            embedding_model: OpenAI embedding model to use
            api_key: OpenAI API key (defaults to config)
        """
        self.db_path = db_path
        self.chunk_size = chunk_size
        self.embedding_model = embedding_model
        self.api_key = api_key

        # Initialize settings if not provided
        if self.api_key is None:
            try:
                from config import get_settings
                settings = get_settings()
                self.api_key = settings.openai_api_key
                self.chunk_size = settings.chunk_size
                self.embedding_model = settings.embedding_model
            except (ImportError, AttributeError):
                pass

        # Initialize database
        self.init_db()

    def get_conn(self) -> sqlite3.Connection:
        """Get database connection with WAL mode."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self) -> None:
        """Initialize database schema."""
        conn = self.get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                added_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                ord INTEGER,
                text TEXT,
                embedding TEXT,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                system TEXT,
                temperature REAL
            );
        """)
        conn.commit()
        conn.close()
        logger.debug("rag_db_initialized", db_path=self.db_path)

    # ========================================================================
    # TEXT PROCESSING
    # ========================================================================

    def tokenize_len(self, text: str, model: str = "gpt-4o-mini") -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for
            model: Model to use for tokenization

        Returns:
            Number of tokens
        """
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        return len(enc.encode(text))

    def chunk_text(
        self,
        text: str,
        model: str = "gpt-4o-mini",
        max_tokens: Optional[int] = None
    ) -> List[str]:
        """
        Split text into chunks based on token limits.

        Uses paragraph-based splitting with token-aware repacking.

        Args:
            text: Text to chunk
            model: Model to use for tokenization
            max_tokens: Maximum tokens per chunk (defaults to self.chunk_size)

        Returns:
            List of text chunks
        """
        if max_tokens is None:
            max_tokens = self.chunk_size

        # Split by paragraphs (2+ newlines)
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            # Try adding paragraph to current chunk
            candidate = (current_chunk + "\n\n" + paragraph).strip() if current_chunk else paragraph

            if self.tokenize_len(candidate, model) <= max_tokens:
                current_chunk = candidate
            else:
                # Current chunk full, start new one
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = paragraph

        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk)

        logger.info("text_chunked", chunks_count=len(chunks), max_tokens=max_tokens)
        return chunks

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts using OpenAI.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        from providers.embedding_provider import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(
            api_key=self.api_key,
            model=self.embedding_model
        )

        embeddings = provider.embed_texts(texts)
        logger.info("texts_embedded", count=len(texts), model=self.embedding_model)
        return embeddings

    # ========================================================================
    # SOURCE MANAGEMENT
    # ========================================================================

    def upsert_source(self, name: str) -> int:
        """
        Insert or get existing source.

        Args:
            name: Source name (e.g., filename)

        Returns:
            Source ID
        """
        conn = self.get_conn()
        cur = conn.execute(
            "INSERT OR IGNORE INTO sources(name, added_at) VALUES (?,?)",
            (name, int(time.time()))
        )

        if cur.rowcount == 0:
            # Source already exists, get its ID
            row = conn.execute("SELECT id FROM sources WHERE name=?", (name,)).fetchone()
            source_id = row[0]
        else:
            source_id = cur.lastrowid

        conn.commit()
        conn.close()

        logger.info("source_upserted", source_id=source_id, name=name)
        return source_id

    def add_chunks(
        self,
        source_id: int,
        chunks: List[Tuple[int, str, List[float]]]
    ) -> None:
        """
        Add chunks with embeddings to database.

        Args:
            source_id: Source ID from upsert_source()
            chunks: List of (order, text, embedding) tuples
        """
        conn = self.get_conn()
        conn.executemany(
            "INSERT INTO chunks(source_id, ord, text, embedding) VALUES (?,?,?,?)",
            [(source_id, ord_i, txt, json.dumps(vec)) for (ord_i, txt, vec) in chunks]
        )
        conn.commit()
        conn.close()

        logger.info("chunks_added", source_id=source_id, count=len(chunks))

    def list_sources(self) -> List[Dict[str, Any]]:
        """
        List all sources with chunk counts.

        Returns:
            List of source dicts with id, name, added_at, chunks
        """
        conn = self.get_conn()
        rows = conn.execute("""
            SELECT s.id, name, added_at, COUNT(c.id)
            FROM sources s
            LEFT JOIN chunks c ON c.source_id = s.id
            GROUP BY s.id
            ORDER BY added_at DESC
        """).fetchall()
        conn.close()

        sources = [
            {
                "id": r[0],
                "name": r[1],
                "added_at": r[2],
                "chunks": r[3]
            }
            for r in rows
        ]

        logger.debug("sources_listed", count=len(sources))
        return sources

    def delete_source(self, source_id: int) -> bool:
        """
        Delete a source and all its chunks.

        Args:
            source_id: Source ID to delete

        Returns:
            True if deleted, False if not found
        """
        conn = self.get_conn()

        # Check if source exists
        row = conn.execute("SELECT id FROM sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            conn.close()
            logger.warning("source_not_found", source_id=source_id)
            return False

        # Delete chunks first (foreign key)
        conn.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
        conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
        conn.commit()
        conn.close()

        logger.info("source_deleted", source_id=source_id)
        return True

    # ========================================================================
    # SEMANTIC SEARCH
    # ========================================================================

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec_a: First vector
            vec_b: Second vector

        Returns:
            Similarity score (0 to 1)
        """
        import numpy as np

        a = np.array(vec_a, dtype="float32")
        b = np.array(vec_b, dtype="float32")

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(a.dot(b) / (norm_a * norm_b))

    def search(
        self,
        query_vec: List[float],
        top_k: int = 5,
        vault_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using cosine similarity.

        Args:
            query_vec: Query embedding vector
            top_k: Number of top results to return
            vault_name: Optional Obsidian vault name for deep links

        Returns:
            List of dicts with chunk_id, source, ord, text, score, obsidian_link (optional)
        """
        conn = self.get_conn()
        rows = conn.execute("""
            SELECT c.id, s.name, c.ord, c.text, c.embedding
            FROM chunks c
            JOIN sources s ON s.id = c.source_id
        """).fetchall()
        conn.close()

        # Calculate similarity scores
        scored = []
        for (chunk_id, source_name, order, text, embedding_json) in rows:
            vec = json.loads(embedding_json)
            similarity = self._cosine_similarity(query_vec, vec)

            result = {
                "chunk_id": chunk_id,
                "source": source_name,
                "ord": order,
                "text": text,
                "score": similarity
            }

            # Add Obsidian deep link if vault name provided
            if vault_name:
                # Strip 'vault:' prefix from source name if present
                file_path = source_name[6:] if source_name.startswith('vault:') else source_name
                result["obsidian_link"] = self._format_obsidian_link(vault_name, file_path)

            scored.append(result)

        # Sort by score and return top k
        scored.sort(key=lambda x: x["score"], reverse=True)
        results = scored[:top_k]

        logger.info("search_completed", results_count=len(results), top_k=top_k)
        return results

    def _format_obsidian_link(self, vault_name: str, file_path: str) -> str:
        """
        Generate Obsidian deep link for a file.

        Args:
            vault_name: Name of the Obsidian vault
            file_path: Relative path to file within vault

        Returns:
            Obsidian URI scheme link
        """
        encoded_vault = urllib.parse.quote(vault_name)
        encoded_file = urllib.parse.quote(file_path)
        return f"obsidian://open?vault={encoded_vault}&file={encoded_file}"

    # ========================================================================
    # PRESET MANAGEMENT
    # ========================================================================

    def list_presets(self) -> List[Dict[str, Any]]:
        """
        List all chat presets.

        Returns:
            List of preset dicts with id, label, system, temperature
        """
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT id, label, system, temperature FROM presets ORDER BY id DESC"
        ).fetchall()
        conn.close()

        presets = [
            {
                "id": r[0],
                "label": r[1],
                "system": r[2],
                "temperature": r[3]
            }
            for r in rows
        ]

        logger.debug("presets_listed", count=len(presets))
        return presets

    def get_preset(self, preset_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a preset by ID.

        Args:
            preset_id: Preset ID

        Returns:
            Preset dict or None if not found
        """
        conn = self.get_conn()
        row = conn.execute(
            "SELECT id, label, system, temperature FROM presets WHERE id=?",
            (preset_id,)
        ).fetchone()
        conn.close()

        if not row:
            logger.warning("preset_not_found", preset_id=preset_id)
            return None

        return {
            "id": row[0],
            "label": row[1],
            "system": row[2],
            "temperature": row[3]
        }

    def add_preset(self, label: str, system: str, temperature: float) -> int:
        """
        Add a new preset.

        Args:
            label: Preset label/name
            system: System prompt
            temperature: Sampling temperature

        Returns:
            New preset ID
        """
        conn = self.get_conn()
        cur = conn.execute(
            "INSERT INTO presets(label, system, temperature) VALUES (?,?,?)",
            (label, system, temperature)
        )
        preset_id = cur.lastrowid
        conn.commit()
        conn.close()

        logger.info("preset_added", preset_id=preset_id, label=label)
        return preset_id

    def update_preset(
        self,
        preset_id: int,
        label: str,
        system: str,
        temperature: float
    ) -> bool:
        """
        Update an existing preset.

        Args:
            preset_id: Preset ID
            label: New label
            system: New system prompt
            temperature: New temperature

        Returns:
            True if updated, False if not found
        """
        conn = self.get_conn()

        # Check if exists
        row = conn.execute("SELECT id FROM presets WHERE id=?", (preset_id,)).fetchone()
        if not row:
            conn.close()
            logger.warning("preset_not_found", preset_id=preset_id)
            return False

        conn.execute(
            "UPDATE presets SET label=?, system=?, temperature=? WHERE id=?",
            (label, system, temperature, preset_id)
        )
        conn.commit()
        conn.close()

        logger.info("preset_updated", preset_id=preset_id, label=label)
        return True

    def delete_preset(self, preset_id: int) -> bool:
        """
        Delete a preset.

        Args:
            preset_id: Preset ID

        Returns:
            True if deleted, False if not found
        """
        conn = self.get_conn()

        # Check if exists
        row = conn.execute("SELECT id FROM presets WHERE id=?", (preset_id,)).fetchone()
        if not row:
            conn.close()
            logger.warning("preset_not_found", preset_id=preset_id)
            return False

        conn.execute("DELETE FROM presets WHERE id=?", (preset_id,))
        conn.commit()
        conn.close()

        logger.info("preset_deleted", preset_id=preset_id)
        return True


# Singleton instance for backward compatibility
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """
    Get the singleton RAG service instance.

    Returns:
        RAGService instance configured from settings
    """
    global _rag_service

    if _rag_service is None:
        _rag_service = RAGService()

    return _rag_service
