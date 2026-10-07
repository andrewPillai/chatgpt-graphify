"""Tests for the main CLI module."""
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from chatgpt_graphify.__main__ import (
    run_pipeline,
    query_graph,
    main,
    _print_corpus_summary,
    _run_ast_extraction,
    _run_semantic_extraction,
    _merge_extractions,
    _build_and_analyze,
    _generate_outputs,
    _run_benchmark_if_needed,
    _save_manifest_and_cleanup,
)


class TestMainCLI:
    """Tests for the main CLI functions."""
    
    @patch('chatgpt_graphify.__main__.detect')
    def test_print_corpus_summary(self, mock_detect):
        """Test corpus summary printing."""
        mock_detect.return_value = {
            "files": {
                "code": ["a.py", "b.py"],
                "document": ["readme.md"],
                "paper": ["paper.pdf"],
                "image": ["diagram.png"]
            },
            "total_files": 5,
            "total_words": 10000,
            "skipped_sensitive": [".env"],
            "warning": "Large corpus warning"
        }
        
        # Capture stdout
        import io
        import sys
        captured = io.StringIO()
        sys.stdout = captured
        try:
            _print_corpus_summary(mock_detect.return_value)
        finally:
            sys.stdout = sys.__stdout__
        
        output = captured.getvalue()
        assert "Corpus: 5 files · ~10,000 words" in output
        assert "  code    : 2 files" in output
        assert "  document: 1 files" in output
        assert "  paper   : 1 files" in output
        assert "  image   : 1 files" in output
        assert "skipped: 1 sensitive files" in output
        assert "Large corpus warning" in output
    
    @patch('chatgpt_graphify.__main__.ast_extract')
    def test_run_ast_extraction(self, mock_extract):
        """Test AST extraction."""
        mock_extract.return_value = {"nodes": [{"id": "n1"}], "edges": [{"source": "n1", "target": "n2"}]}
        
        result = _run_ast_extraction([Path("a.py"), Path("b.py")])
        
        assert len(result["nodes"]) == 1
        assert len(result["edges"]) == 1
        mock_extract.assert_called_once()
    
    @patch('chatgpt_graphify.__main__.extract_semantic')
    def test_run_semantic_extraction(self, mock_extract_semantic):
        """Test semantic extraction."""
        mock_extract_semantic.return_value = {
            "nodes": [{"id": "n1"}],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50
        }
        
        # Need to provide API key (or mock env var) for semantic extraction to run
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            result = _run_semantic_extraction([Path("readme.md")], deep_mode=False, api_key=None, model="gpt-4o")
        
        assert len(result["nodes"]) == 1
        assert result["input_tokens"] == 100
        mock_extract_semantic.assert_called_once()
    
    def test_merge_extractions(self):
        """Test merging AST and semantic extractions."""
        ast_result = {
            "nodes": [{"id": "ast_node", "label": "AST Node"}],
            "edges": [{"source": "ast_node", "target": "other"}],
            "input_tokens": 0,
            "output_tokens": 0
        }
        semantic_result = {
            "nodes": [{"id": "sem_node", "label": "Semantic Node"}, {"id": "ast_node", "label": "AST Node"}],  # duplicate
            "edges": [{"source": "sem_node", "target": "other"}],
            "hyperedges": [{"id": "hyper1", "nodes": ["n1", "n2", "n3"]}],
            "input_tokens": 100,
            "output_tokens": 50
        }
        
        merged = _merge_extractions(ast_result, semantic_result)
        
        # Should have 2 unique nodes (ast_node deduplicated)
        assert len(merged["nodes"]) == 2
        node_ids = {n["id"] for n in merged["nodes"]}
        assert "ast_node" in node_ids
        assert "sem_node" in node_ids
        
        # Should have 2 edges
        assert len(merged["edges"]) == 2
        
        # Should have hyperedges from semantic
        assert len(merged["hyperedges"]) == 1
        
        # Token counts from semantic
        assert merged["input_tokens"] == 100
        assert merged["output_tokens"] == 50
    
    @patch('chatgpt_graphify.__main__.build_from_json')
    @patch('chatgpt_graphify.__main__.cluster')
    @patch('chatgpt_graphify.__main__.score_all')
    @patch('chatgpt_graphify.__main__.god_nodes')
    @patch('chatgpt_graphify.__main__.surprising_connections')
    @patch('chatgpt_graphify.__main__.suggest_questions')
    @patch('chatgpt_graphify.__main__.generate')
    def test_build_and_analyze(self, mock_generate, mock_suggest, mock_surprises, mock_gods, mock_score, mock_cluster, mock_build):
        """Test build and analyze pipeline."""
        import networkx as nx
        
        mock_G = nx.Graph()
        mock_G.add_node("n1", label="Node 1")
        mock_build.return_value = mock_G
        mock_cluster.return_value = {0: ["n1"]}
        mock_score.return_value = {0: 0.8}
        mock_gods.return_value = [{"label": "Node 1", "edges": 5}]
        mock_surprises.return_value = []
        mock_suggest.return_value = ["Question 1"]
        mock_generate.return_value = "# Report"
        
        extraction = {"nodes": [{"id": "n1", "label": "Node 1"}], "edges": [], "input_tokens": 0, "output_tokens": 0}
        detection = {"total_files": 1, "total_words": 100}
        
        G, communities, cohesion, gods, surprises, labels, questions, report = _build_and_analyze(
            extraction, detection, "test_path"
        )
        
        assert G == mock_G
        assert communities == {0: ["n1"]}
        assert cohesion == {0: 0.8}
        assert gods == [{"label": "Node 1", "edges": 5}]
        assert questions == ["Question 1"]
        assert report == "# Report"
        assert labels == {0: "Community 0"}
    
    @patch('chatgpt_graphify.__main__.to_json')
    @patch('chatgpt_graphify.__main__.to_obsidian')
    @patch('chatgpt_graphify.__main__.to_canvas')
    @patch('chatgpt_graphify.__main__.to_html')
    def test_generate_outputs(self, mock_html, mock_canvas, mock_obsidian, mock_json):
        """Test output generation."""
        import networkx as nx
        
        mock_G = nx.Graph()
        mock_G.add_node("n1", label="Node 1")
        mock_G.number_of_nodes = Mock(return_value=10)
        
        communities = {0: ["n1"]}
        cohesion = {0: 0.8}
        labels = {0: "Test Community"}
        
        _generate_outputs(
            mock_G, communities, cohesion, labels, "test_path",
            Path("graphify-out"), generate_viz=True, export_svg=False,
            export_graphml=False, export_neo4j=False, neo4j_uri=None, export_mcp=False
        )
        
        mock_json.assert_called_once()
        mock_obsidian.assert_called_once()
        mock_canvas.assert_called_once()
        mock_html.assert_called_once()
    
    @patch('chatgpt_graphify.__main__.run_benchmark')
    @patch('chatgpt_graphify.__main__.print_benchmark')
    def test_run_benchmark_if_needed(self, mock_print, mock_run):
        """Test benchmark runs only for large corpora."""
        mock_run.return_value = {"reduction": 10}
        
        # Small corpus - should not run
        _run_benchmark_if_needed(Path("graph.json"), {"total_words": 1000})
        mock_run.assert_not_called()
        
        # Large corpus - should run
        _run_benchmark_if_needed(Path("graph.json"), {"total_words": 10000})
        mock_run.assert_called_once()
        mock_print.assert_called_once()
    
    @patch('chatgpt_graphify.__main__.save_manifest')
    def test_save_manifest_and_cleanup(self, mock_save_manifest):
        """Test manifest saving and cleanup."""
        detection = {"files": {"code": ["a.py"]}}
        extraction = {"input_tokens": 100, "output_tokens": 50}
        
        _save_manifest_and_cleanup(detection, extraction, Path("graphify-out"))
        
        mock_save_manifest.assert_called_once_with({"code": ["a.py"]})
        
        # Check cost.json was created
        cost_path = Path("graphify-out/cost.json")
        assert cost_path.exists()
        cost = json.loads(cost_path.read_text())
        assert cost["total_input_tokens"] == 100
        assert cost["total_output_tokens"] == 50
        assert len(cost["runs"]) == 1
        
        # Cleanup
        cost_path.unlink()


class TestQueryGraph:
    """Tests for the query_graph function."""
    
    @patch('chatgpt_graphify.serve._load_graph')
    @patch('chatgpt_graphify.serve._score_nodes')
    @patch('chatgpt_graphify.serve._bfs')
    @patch('chatgpt_graphify.serve._subgraph_to_text')
    def test_query_graph_bfs(self, mock_subgraph, mock_bfs, mock_score, mock_load):
        """Test BFS query."""
        import networkx as nx
        
        mock_G = nx.Graph()
        mock_G.add_node("n1", label="Node 1")
        mock_load.return_value = mock_G
        mock_score.return_value = [(1, "n1")]
        mock_bfs.return_value = ({"n1"}, [])
        mock_subgraph.return_value = "NODE Node 1"
        
        result = query_graph("graph.json", "test question", mode="bfs", depth=3, budget=2000)
        
        assert "Traversal: BFS" in result
        assert "NODE Node 1" in result
        mock_bfs.assert_called_once()
    
    @patch('chatgpt_graphify.serve._load_graph')
    @patch('chatgpt_graphify.serve._score_nodes')
    def test_query_graph_no_matches(self, mock_score, mock_load):
        """Test query with no matching nodes."""
        import networkx as nx
        
        mock_G = nx.Graph()
        mock_load.return_value = mock_G
        mock_score.return_value = []
        
        result = query_graph("graph.json", "nonexistent concept")
        
        assert "No matching nodes found" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])