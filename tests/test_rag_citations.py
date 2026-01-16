"""
Tests for RAG citations feature.
Validates Obsidian deep link generation and citation tracking in responses.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from rag_db import format_obsidian_link, search


class TestObsidianLinkGeneration:
    """Tests for Obsidian deep link generation."""

    def test_basic_link_generation(self):
        """Test generating a basic Obsidian deep link."""
        vault = "MyVault"
        file_path = "Projects/Q4.md"
        result = format_obsidian_link(vault, file_path)
        assert result == "obsidian://open?vault=MyVault&file=Projects/Q4.md"

    def test_link_with_spaces(self):
        """Test link generation with spaces in vault/file names."""
        vault = "My Vault"
        file_path = "Projects/Q4 2025.md"
        result = format_obsidian_link(vault, file_path)
        assert result == "obsidian://open?vault=My%20Vault&file=Projects/Q4%202025.md"

    def test_link_with_special_characters(self):
        """Test link generation with special characters."""
        vault = "My-Vault"
        file_path = "Projects/Q4 (2025).md"
        result = format_obsidian_link(vault, file_path)
        # URL encoding: ( = %28, ) = %29
        assert result == "obsidian://open?vault=My-Vault&file=Projects/Q4%20%282025%29.md"

    def test_link_with_nested_path(self):
        """Test link generation with deeply nested file paths."""
        vault = "Vault"
        file_path = "Work/Projects/2025/Q4/Notes.md"
        result = format_obsidian_link(vault, file_path)
        assert result == "obsidian://open?vault=Vault&file=Work/Projects/2025/Q4/Notes.md"

    def test_link_with_unicode(self):
        """Test link generation with Unicode characters."""
        vault = "MyVault"
        file_path = "Notes/日本語.md"
        result = format_obsidian_link(vault, file_path)
        # Unicode should be URL encoded
        assert "obsidian://open?vault=MyVault&file=" in result
        assert "%E6%97%A5%E6%9C%AC%E8%AA%9E" in result

    def test_link_with_ampersand(self):
        """Test link generation with ampersand in file name."""
        vault = "MyVault"
        file_path = "Projects/R&D.md"
        result = format_obsidian_link(vault, file_path)
        assert result == "obsidian://open?vault=MyVault&file=Projects/R%26D.md"

    def test_link_with_hash(self):
        """Test link generation with hash in file name."""
        vault = "MyVault"
        file_path = "Notes/Issue #123.md"
        result = format_obsidian_link(vault, file_path)
        assert result == "obsidian://open?vault=MyVault&file=Notes/Issue%20%23123.md"


class TestSearchWithCitations:
    """Tests for search() function with citation support."""

    @pytest.fixture
    def mock_db_with_chunks(self):
        """Create a mock database with sample chunks."""
        chunks = [
            (1, "Projects/Q4.md", 0, "Project deadline is Friday",
             json.dumps([0.1] * 1536)),
            (2, "Notes/Meeting.md", 0, "Discussed project timeline",
             json.dumps([0.2] * 1536)),
            (3, "Reference/Docs.md", 0, "Important reference material",
             json.dumps([0.15] * 1536)),
        ]
        return chunks

    def test_search_without_vault_name(self, mock_db_with_chunks, tmp_path):
        """Test search without vault_name doesn't include obsidian_link."""
        db_path = tmp_path / "test.db"

        with patch('rag_db.get_db') as mock_get_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = mock_db_with_chunks
            mock_get_db.return_value = mock_conn

            query_vec = [0.15] * 1536
            results = search(query_vec, top_k=3)

            assert len(results) == 3
            for result in results:
                assert "obsidian_link" not in result
                assert "chunk_id" in result
                assert "source" in result
                assert "score" in result
                assert "text" in result

    def test_search_with_vault_name(self, mock_db_with_chunks, tmp_path):
        """Test search with vault_name includes obsidian_link."""
        db_path = tmp_path / "test.db"

        with patch('rag_db.get_db') as mock_get_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = mock_db_with_chunks
            mock_get_db.return_value = mock_conn

            query_vec = [0.15] * 1536
            results = search(query_vec, top_k=3, vault_name="MyVault")

            assert len(results) == 3
            for result in results:
                assert "obsidian_link" in result
                assert result["obsidian_link"].startswith("obsidian://open?vault=MyVault")
                assert "chunk_id" in result
                assert "source" in result
                assert "score" in result

    def test_search_top_k_limit(self, mock_db_with_chunks):
        """Test that search respects top_k parameter."""
        with patch('rag_db.get_db') as mock_get_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = mock_db_with_chunks
            mock_get_db.return_value = mock_conn

            query_vec = [0.15] * 1536
            results = search(query_vec, top_k=2, vault_name="MyVault")

            assert len(results) == 2

    def test_search_empty_database(self):
        """Test search with empty database returns empty list."""
        with patch('rag_db.get_db') as mock_get_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_get_db.return_value = mock_conn

            query_vec = [0.15] * 1536
            results = search(query_vec, top_k=5, vault_name="MyVault")

            assert len(results) == 0
            assert isinstance(results, list)


class TestCitationFormat:
    """Tests for citation formatting in API responses."""

    def test_citation_structure(self):
        """Test that citation has correct structure."""
        hit = {
            "chunk_id": 42,
            "source": "Projects/Q4.md",
            "ord": 0,
            "text": "This is a test chunk with more than 200 characters. " * 10,
            "score": 0.87123456,
            "obsidian_link": "obsidian://open?vault=MyVault&file=Projects/Q4.md"
        }

        # Simulate citation formatting from app.py
        citation = {
            "source": hit["source"],
            "chunk_id": hit["chunk_id"],
            "score": round(hit["score"], 4),
            "snippet": hit["text"][:200] + "..." if len(hit["text"]) > 200 else hit["text"],
            "obsidian_link": hit.get("obsidian_link", "")
        }

        assert citation["source"] == "Projects/Q4.md"
        assert citation["chunk_id"] == 42
        assert citation["score"] == 0.8712  # Rounded to 4 decimals
        assert len(citation["snippet"]) <= 203  # 200 chars + "..."
        assert citation["snippet"].endswith("...")
        assert citation["obsidian_link"] == "obsidian://open?vault=MyVault&file=Projects/Q4.md"

    def test_citation_snippet_truncation(self):
        """Test snippet truncation for long text."""
        long_text = "A" * 500
        snippet = long_text[:200] + "..." if len(long_text) > 200 else long_text

        assert len(snippet) == 203
        assert snippet.endswith("...")
        assert snippet.startswith("AAA")

    def test_citation_snippet_no_truncation(self):
        """Test snippet NOT truncated for short text."""
        short_text = "Short text"
        snippet = short_text[:200] + "..." if len(short_text) > 200 else short_text

        assert snippet == "Short text"
        assert not snippet.endswith("...")

    def test_citation_score_rounding(self):
        """Test score is rounded to 4 decimal places."""
        scores = [0.87123456, 0.1, 0.999999, 0.12345]
        rounded = [round(s, 4) for s in scores]

        assert rounded == [0.8712, 0.1, 1.0, 0.1235]


class TestCitationLogic:
    """Unit tests for citation logic without full API integration."""

    def test_citation_formatting_from_rag_hits(self):
        """Test citation formatting logic that runs in app.py."""
        # Simulate RAG hits from search()
        hits = [
            {
                "chunk_id": 1,
                "source": "Projects/Q4.md",
                "ord": 0,
                "text": "This is a long text that should be truncated because it exceeds 200 characters. " * 5,
                "score": 0.87123456,
                "obsidian_link": "obsidian://open?vault=MyVault&file=Projects/Q4.md"
            },
            {
                "chunk_id": 2,
                "source": "Notes/Meeting.md",
                "ord": 1,
                "text": "Short text",
                "score": 0.75,
                "obsidian_link": "obsidian://open?vault=MyVault&file=Notes/Meeting.md"
            }
        ]

        # Simulate the citation formatting from app.py
        citations = [
            {
                "source": hit["source"],
                "chunk_id": hit["chunk_id"],
                "score": round(hit["score"], 4),
                "snippet": hit["text"][:200] + "..." if len(hit["text"]) > 200 else hit["text"],
                "obsidian_link": hit.get("obsidian_link", "")
            }
            for hit in hits
        ]

        # Verify first citation (long text)
        assert citations[0]["source"] == "Projects/Q4.md"
        assert citations[0]["chunk_id"] == 1
        assert citations[0]["score"] == 0.8712
        assert len(citations[0]["snippet"]) == 203  # 200 + "..."
        assert citations[0]["snippet"].endswith("...")
        assert citations[0]["obsidian_link"] == "obsidian://open?vault=MyVault&file=Projects/Q4.md"

        # Verify second citation (short text)
        assert citations[1]["source"] == "Notes/Meeting.md"
        assert citations[1]["chunk_id"] == 2
        assert citations[1]["score"] == 0.75
        assert citations[1]["snippet"] == "Short text"
        assert not citations[1]["snippet"].endswith("...")

    def test_citation_array_included_with_rag(self):
        """Test that citations array is added when RAG is used."""
        # Simulate response construction in app.py
        use_rag = True
        citations = [
            {
                "source": "Test.md",
                "chunk_id": 1,
                "score": 0.8,
                "snippet": "Test snippet",
                "obsidian_link": "obsidian://open?vault=Vault&file=Test.md"
            }
        ]

        response_data = {
            "chatId": "test123",
            "text": "Response text",
            "usage": {"in_tokens": 10, "out_tokens": 5, "cost_total": 0.001}
        }

        # Add citations if RAG was used (from app.py logic)
        if use_rag and citations:
            response_data["citations"] = citations

        assert "citations" in response_data
        assert len(response_data["citations"]) == 1

    def test_citation_array_not_included_without_rag(self):
        """Test that citations array is NOT added when RAG is not used."""
        use_rag = False
        citations = []

        response_data = {
            "chatId": "test123",
            "text": "Response text",
            "usage": {"in_tokens": 10, "out_tokens": 5, "cost_total": 0.001}
        }

        # Add citations if RAG was used (from app.py logic)
        if use_rag and citations:
            response_data["citations"] = citations

        assert "citations" not in response_data
