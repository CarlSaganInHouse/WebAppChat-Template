"""
RAGService comprehensive unit tests.

Tests for text processing, embeddings, source management, and semantic search.
"""

import pytest
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.rag_service import RAGService, get_rag_service


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_rag.sqlite3"
    return str(db_path)


@pytest.fixture
def rag_service(temp_db):
    """Create a RAGService instance with temporary database."""
    service = RAGService(
        db_path=temp_db,
        chunk_size=500,
        embedding_model="text-embedding-ada-002"
    )
    return service


class TestInitialization:
    """Test RAGService initialization."""

    def test_creates_database(self, temp_db):
        """Should create database and initialize schema."""
        service = RAGService(db_path=temp_db)

        assert Path(temp_db).exists()

        # Verify schema
        conn = service.get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert 'sources' in tables
        assert 'chunks' in tables
        assert 'presets' in tables

    def test_uses_provided_config(self, temp_db):
        """Should use provided configuration."""
        service = RAGService(
            db_path=temp_db,
            chunk_size=1000,
            embedding_model="custom-model",
            api_key="test-key"
        )

        assert service.chunk_size == 1000
        assert service.embedding_model == "custom-model"
        assert service.api_key == "test-key"


class TestTextProcessing:
    """Test text chunking and tokenization."""

    def test_tokenize_len_empty_string(self, rag_service):
        """Empty string should have 0 tokens."""
        assert rag_service.tokenize_len("") == 0

    def test_tokenize_len_simple_text(self, rag_service):
        """Simple text should return reasonable token count."""
        count = rag_service.tokenize_len("Hello world")
        assert count > 0
        assert count < 10

    def test_chunk_text_respects_limit(self, rag_service):
        """Chunks should respect token limits."""
        # Create text with multiple paragraphs
        paragraphs = [f"Paragraph {i}. " + ("word " * 50) for i in range(10)]
        long_text = "\n\n".join(paragraphs)

        chunks = rag_service.chunk_text(long_text, max_tokens=200)

        # Verify chunks respect limit (with some margin for paragraph boundaries)
        for chunk in chunks:
            token_count = rag_service.tokenize_len(chunk)
            assert token_count <= 300  # Allow some overage

    def test_chunk_text_preserves_content(self, rag_service):
        """Chunking should not lose content."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

        chunks = rag_service.chunk_text(text, max_tokens=500)
        reassembled = "\n\n".join(chunks)

        assert "First paragraph" in reassembled
        assert "Second paragraph" in reassembled
        assert "Third paragraph" in reassembled

    def test_chunk_text_empty_returns_empty(self, rag_service):
        """Empty text should return empty list."""
        assert rag_service.chunk_text("") == []
        assert rag_service.chunk_text("   ") == []

    def test_chunk_text_single_paragraph(self, rag_service):
        """Single short paragraph should return one chunk."""
        text = "This is a short paragraph."
        chunks = rag_service.chunk_text(text, max_tokens=100)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_combines_short_paragraphs(self, rag_service):
        """Multiple short paragraphs should combine when under limit."""
        text = "First.\n\nSecond.\n\nThird."
        chunks = rag_service.chunk_text(text, max_tokens=100)

        assert len(chunks) == 1


class TestEmbeddings:
    """Test embedding generation."""

    @patch('services.rag_service.OpenAIEmbeddingProvider')
    def test_embed_texts_calls_provider(self, mock_provider_class, rag_service):
        """Should delegate to embedding provider."""
        mock_provider = Mock()
        mock_provider.embed_texts.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_provider_class.return_value = mock_provider

        texts = ["text1", "text2"]
        result = rag_service.embed_texts(texts)

        mock_provider.embed_texts.assert_called_once_with(texts)
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    @patch('services.rag_service.OpenAIEmbeddingProvider')
    def test_embed_texts_uses_config(self, mock_provider_class, rag_service):
        """Should use configured API key and model."""
        mock_provider = Mock()
        mock_provider.embed_texts.return_value = [[0.1, 0.2]]
        mock_provider_class.return_value = mock_provider

        rag_service.embed_texts(["test"])

        # Verify provider was initialized with correct config
        mock_provider_class.assert_called_once_with(
            api_key=rag_service.api_key,
            model=rag_service.embedding_model
        )


class TestSourceManagement:
    """Test source CRUD operations."""

    def test_upsert_source_creates_new(self, rag_service):
        """Should create new source."""
        source_id = rag_service.upsert_source("test_file.md")

        assert source_id > 0

        # Verify source exists
        conn = rag_service.get_conn()
        row = conn.execute(
            "SELECT id, name FROM sources WHERE id=?", (source_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[1] == "test_file.md"

    def test_upsert_source_returns_existing(self, rag_service):
        """Should return existing source ID."""
        source_id1 = rag_service.upsert_source("duplicate.md")
        source_id2 = rag_service.upsert_source("duplicate.md")

        assert source_id1 == source_id2

    def test_list_sources_empty(self, rag_service):
        """Should return empty list for new database."""
        sources = rag_service.list_sources()
        assert sources == []

    def test_list_sources_returns_all(self, rag_service):
        """Should list all sources with chunk counts."""
        # Create sources
        sid1 = rag_service.upsert_source("file1.md")
        sid2 = rag_service.upsert_source("file2.md")

        # Add chunks to first source
        rag_service.add_chunks(sid1, [(0, "chunk1", [0.1, 0.2, 0.3])])

        sources = rag_service.list_sources()

        assert len(sources) == 2
        assert any(s['name'] == 'file1.md' and s['chunks'] == 1 for s in sources)
        assert any(s['name'] == 'file2.md' and s['chunks'] == 0 for s in sources)

    def test_delete_source_removes_chunks(self, rag_service):
        """Should delete source and all its chunks."""
        # Create source with chunks
        source_id = rag_service.upsert_source("test.md")
        rag_service.add_chunks(source_id, [
            (0, "chunk1", [0.1, 0.2]),
            (1, "chunk2", [0.3, 0.4])
        ])

        # Delete source
        result = rag_service.delete_source(source_id)
        assert result is True

        # Verify source and chunks removed
        conn = rag_service.get_conn()
        source_row = conn.execute(
            "SELECT * FROM sources WHERE id=?", (source_id,)
        ).fetchone()
        chunk_rows = conn.execute(
            "SELECT * FROM chunks WHERE source_id=?", (source_id,)
        ).fetchall()
        conn.close()

        assert source_row is None
        assert len(chunk_rows) == 0

    def test_delete_source_nonexistent(self, rag_service):
        """Should return False for nonexistent source."""
        result = rag_service.delete_source(99999)
        assert result is False


class TestChunkStorage:
    """Test chunk storage operations."""

    def test_add_chunks_stores_data(self, rag_service):
        """Should store chunks with embeddings."""
        source_id = rag_service.upsert_source("test.md")
        chunks = [
            (0, "First chunk", [0.1, 0.2, 0.3]),
            (1, "Second chunk", [0.4, 0.5, 0.6])
        ]

        rag_service.add_chunks(source_id, chunks)

        # Verify chunks stored
        conn = rag_service.get_conn()
        rows = conn.execute(
            "SELECT ord, text, embedding FROM chunks WHERE source_id=? ORDER BY ord",
            (source_id,)
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] == 0
        assert rows[0][1] == "First chunk"
        assert json.loads(rows[0][2]) == [0.1, 0.2, 0.3]
        assert rows[1][0] == 1
        assert rows[1][1] == "Second chunk"


class TestSemanticSearch:
    """Test cosine similarity search."""

    def test_cosine_similarity_identical_vectors(self, rag_service):
        """Identical vectors should have similarity of 1.0."""
        vec = [1.0, 2.0, 3.0]
        similarity = rag_service._cosine_similarity(vec, vec)
        assert abs(similarity - 1.0) < 0.001

    def test_cosine_similarity_orthogonal_vectors(self, rag_service):
        """Orthogonal vectors should have similarity near 0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        similarity = rag_service._cosine_similarity(vec_a, vec_b)
        assert abs(similarity) < 0.001

    def test_cosine_similarity_opposite_vectors(self, rag_service):
        """Opposite vectors should have similarity of -1.0."""
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        similarity = rag_service._cosine_similarity(vec_a, vec_b)
        assert abs(similarity - (-1.0)) < 0.001

    def test_search_returns_top_k(self, rag_service):
        """Should return top k most similar chunks."""
        # Create source with multiple chunks
        source_id = rag_service.upsert_source("test.md")
        rag_service.add_chunks(source_id, [
            (0, "chunk1", [1.0, 0.0, 0.0]),
            (1, "chunk2", [0.0, 1.0, 0.0]),
            (2, "chunk3", [0.0, 0.0, 1.0]),
            (3, "chunk4", [1.0, 0.0, 0.0])  # Similar to chunk1
        ])

        # Search with query vector similar to [1.0, 0.0, 0.0]
        query_vec = [0.9, 0.1, 0.0]
        results = rag_service.search(query_vec, top_k=2)

        assert len(results) == 2
        # Should return chunk1 and chunk4 (most similar)
        texts = [r['text'] for r in results]
        assert 'chunk1' in texts
        assert 'chunk4' in texts

    def test_search_includes_scores(self, rag_service):
        """Search results should include similarity scores."""
        source_id = rag_service.upsert_source("test.md")
        rag_service.add_chunks(source_id, [
            (0, "chunk1", [1.0, 0.0, 0.0])
        ])

        query_vec = [1.0, 0.0, 0.0]
        results = rag_service.search(query_vec, top_k=1)

        assert len(results) == 1
        assert 'score' in results[0]
        assert abs(results[0]['score'] - 1.0) < 0.001  # Identical vector

    def test_search_with_obsidian_links(self, rag_service):
        """Should include Obsidian deep links when vault name provided."""
        source_id = rag_service.upsert_source("vault:notes/test.md")
        rag_service.add_chunks(source_id, [
            (0, "chunk1", [1.0, 0.0, 0.0])
        ])

        query_vec = [1.0, 0.0, 0.0]
        results = rag_service.search(query_vec, top_k=1, vault_name="MyVault")

        assert len(results) == 1
        assert 'obsidian_link' in results[0]
        assert 'obsidian://open' in results[0]['obsidian_link']
        assert 'MyVault' in results[0]['obsidian_link']

    def test_format_obsidian_link(self, rag_service):
        """Should generate correct Obsidian URI."""
        link = rag_service._format_obsidian_link("My Vault", "notes/test.md")

        assert link.startswith("obsidian://open?vault=")
        assert "My%20Vault" in link
        assert "notes%2Ftest.md" in link


class TestPresetManagement:
    """Test preset CRUD operations."""

    def test_add_preset(self, rag_service):
        """Should add new preset."""
        preset_id = rag_service.add_preset(
            label="Test Preset",
            system="You are a test assistant",
            temperature=0.7
        )

        assert preset_id > 0

        # Verify preset exists
        preset = rag_service.get_preset(preset_id)
        assert preset is not None
        assert preset['label'] == "Test Preset"
        assert preset['system'] == "You are a test assistant"
        assert preset['temperature'] == 0.7

    def test_list_presets_empty(self, rag_service):
        """Should return empty list for new database."""
        presets = rag_service.list_presets()
        assert presets == []

    def test_list_presets_returns_all(self, rag_service):
        """Should list all presets."""
        rag_service.add_preset("Preset1", "System1", 0.5)
        rag_service.add_preset("Preset2", "System2", 0.8)

        presets = rag_service.list_presets()

        assert len(presets) == 2
        labels = {p['label'] for p in presets}
        assert 'Preset1' in labels
        assert 'Preset2' in labels

    def test_get_preset_nonexistent(self, rag_service):
        """Should return None for nonexistent preset."""
        preset = rag_service.get_preset(99999)
        assert preset is None

    def test_update_preset(self, rag_service):
        """Should update existing preset."""
        preset_id = rag_service.add_preset("Original", "Original system", 0.5)

        result = rag_service.update_preset(
            preset_id,
            label="Updated",
            system="Updated system",
            temperature=0.9
        )
        assert result is True

        # Verify updated
        preset = rag_service.get_preset(preset_id)
        assert preset['label'] == "Updated"
        assert preset['system'] == "Updated system"
        assert preset['temperature'] == 0.9

    def test_update_preset_nonexistent(self, rag_service):
        """Should return False for nonexistent preset."""
        result = rag_service.update_preset(99999, "Test", "Test", 0.5)
        assert result is False

    def test_delete_preset(self, rag_service):
        """Should delete existing preset."""
        preset_id = rag_service.add_preset("Test", "Test", 0.5)

        result = rag_service.delete_preset(preset_id)
        assert result is True

        # Verify deleted
        preset = rag_service.get_preset(preset_id)
        assert preset is None

    def test_delete_preset_nonexistent(self, rag_service):
        """Should return False for nonexistent preset."""
        result = rag_service.delete_preset(99999)
        assert result is False


class TestSingletonAccess:
    """Test singleton pattern."""

    def test_get_rag_service_returns_singleton(self):
        """Should return same instance on multiple calls."""
        service1 = get_rag_service()
        service2 = get_rag_service()

        assert service1 is service2
