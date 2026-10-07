"""Tests for semantic extraction module."""
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from chatgpt_graphify.semantic_extract import SemanticExtractor, extract_semantic
from chatgpt_graphify.extraction_schema import EXTRACTION_FUNCTION


class TestSemanticExtractor:
    """Tests for the SemanticExtractor class."""
    
    def test_init(self):
        """Test initialization with default and custom parameters."""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            extractor = SemanticExtractor()
            assert extractor.model == "gpt-4o"
            assert extractor.deep_mode is False
            assert extractor.chunk_size == 22
        
        extractor = SemanticExtractor(api_key="custom-key", model="gpt-4o-mini", deep_mode=True)
        assert extractor.model == "gpt-4o-mini"
        assert extractor.deep_mode is True
    
    def test_extract_empty_files(self):
        """Test extraction with empty file list."""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            extractor = SemanticExtractor()
            result = extractor.extract([])
            assert result == {
                "nodes": [],
                "edges": [],
                "hyperedges": [],
                "input_tokens": 0,
                "output_tokens": 0,
            }
    
    @patch('chatgpt_graphify.semantic_extract.check_semantic_cache')
    @patch('chatgpt_graphify.semantic_extract.save_semantic_cache')
    def test_extract_with_cached_files(self, mock_save_cache, mock_check_cache):
        """Test extraction when all files are cached."""
        mock_check_cache.return_value = (
            [{"id": "cached_node", "label": "Cached Node", "file_type": "document", "source_file": "test.md"}],
            [{"source": "cached_node", "target": "other", "relation": "references", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "test.md", "weight": 1.0}],
            []  # no uncached files
        )
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            extractor = SemanticExtractor()
            result = extractor.extract([Path("test.md")])
            
            assert len(result["nodes"]) == 1
            assert result["nodes"][0]["id"] == "cached_node"
            assert result["input_tokens"] == 0
            assert result["output_tokens"] == 0
            mock_save_cache.assert_not_called()
    
    @patch('chatgpt_graphify.semantic_extract.check_semantic_cache')
    @patch('chatgpt_graphify.semantic_extract.save_semantic_cache')
    @patch('chatgpt_graphify.semantic_extract.OpenAI')
    def test_extract_with_uncached_files(self, mock_openai, mock_save_cache, mock_check_cache):
        """Test extraction with uncached files using OpenAI."""
        # Setup mocks
        mock_check_cache.return_value = ([], [], [Path("test.md")])
        Path("test.md").write_text("# Test Document\n\nThis is a test.")
        
        # Mock OpenAI response
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.tool_calls = [Mock()]
        mock_response.choices[0].message.tool_calls[0].function.arguments = json.dumps({
            "nodes": [{"id": "test_concept", "label": "Test Concept", "file_type": "document", "source_file": "test.md", "source_location": None, "source_url": None, "captured_at": None, "author": None, "contributor": None}],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50
        })
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            extractor = SemanticExtractor()
            result = extractor.extract([Path("test.md")], progress=False)
            
            assert len(result["nodes"]) == 1
            assert result["nodes"][0]["id"] == "test_concept"
            assert result["input_tokens"] == 100
            assert result["output_tokens"] == 50
            mock_save_cache.assert_called_once()
    
    @patch('chatgpt_graphify.semantic_extract.check_semantic_cache')
    @patch('chatgpt_graphify.semantic_extract.OpenAI')
    def test_extract_handles_api_error(self, mock_openai, mock_check_cache):
        """Test extraction handles API errors gracefully."""
        mock_check_cache.return_value = ([], [], [Path("test.md")])
        Path("test.md").write_text("# Test Document")
        
        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            extractor = SemanticExtractor()
            result = extractor.extract([Path("test.md")], progress=False)
            
            # Should return cached results (empty) on error
            assert result["nodes"] == []
            assert result["edges"] == []
    
    def test_extraction_function_schema(self):
        """Test that the extraction function schema is valid."""
        assert EXTRACTION_FUNCTION["type"] == "function"
        assert EXTRACTION_FUNCTION["function"]["name"] == "extract_knowledge_graph"
        assert "parameters" in EXTRACTION_FUNCTION["function"]
        
        params = EXTRACTION_FUNCTION["function"]["parameters"]
        assert params["type"] == "object"
        assert "nodes" in params["properties"]
        assert "edges" in params["properties"]
        assert "hyperedges" in params["properties"]
        assert "input_tokens" in params["properties"]
        assert "output_tokens" in params["properties"]
        assert params["required"] == ["nodes", "edges", "hyperedges", "input_tokens", "output_tokens"]


class TestExtractSemantic:
    """Tests for the extract_semantic convenience function."""
    
    @patch('chatgpt_graphify.semantic_extract.SemanticExtractor')
    def test_extract_semantic_calls_extractor(self, mock_extractor_class):
        """Test that extract_semantic creates extractor and calls extract."""
        mock_extractor = Mock()
        mock_extractor_class.return_value = mock_extractor
        mock_extractor.extract.return_value = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
        
        result = extract_semantic([Path("test.md")], api_key="test-key", model="gpt-4o", deep_mode=True)
        
        mock_extractor_class.assert_called_once_with(api_key="test-key", model="gpt-4o", deep_mode=True)
        mock_extractor.extract.assert_called_once_with([Path("test.md")], progress=True)
        assert result == {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])