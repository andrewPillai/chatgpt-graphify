"""Semantic extraction using OpenAI function calling - replaces Claude Agent tool subagents."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

from .extraction_schema import EXTRACTION_FUNCTION
from .cache import check_semantic_cache, save_semantic_cache
from .security import sanitize_label

# Load the extraction prompt from the original skill.md
EXTRACTION_SYSTEM_PROMPT = """You are a graphify extraction subagent. Read the files listed and extract a knowledge graph fragment.
Output ONLY valid JSON matching the schema below - no explanation, no markdown fences, no preamble.

Rules:
- EXTRACTED: relationship explicit in source (import, call, citation, "see §3.2")
- INFERRED: reasonable inference (shared data structure, implied dependency)
- AMBIGUOUS: uncertain - flag for review, do not omit

Code files: focus on semantic edges AST cannot find (call relationships, shared data, arch patterns).
  Do not re-extract imports - AST already has those.
Doc/paper files: extract named concepts, entities, citations. For rationale (WHY decisions were made,
  trade-offs, design intent): store as a `rationale` attribute on the relevant concept node — do NOT
  create a separate rationale node. Valid `file_type` values are ONLY `code|document|paper|image` —
  never emit `file_type:"rationale"` or `file_type:"concept"`.
Image files: use vision to understand what the image IS - do not just OCR.
  UI screenshot: layout patterns, design decisions, key elements, purpose.
  Chart: metric, trend/insight, data source.
  Tweet/post: claim as node, author, concepts mentioned.
  Diagram: components and connections.
  Research figure: what it demonstrates, method, result.
  Handwritten/whiteboard: ideas and arrows, mark uncertain readings AMBIGUOUS.

DEEP_MODE (if --mode deep was given): be aggressive with INFERRED edges - indirect deps,
  shared assumptions, latent couplings. Mark uncertain ones AMBIGUOUS instead of omitting.

Semantic similarity: if two concepts in this chunk solve the same problem or represent the same idea without any structural link (no import, no call, no citation), add a `semantically_similar_to` edge marked INFERRED with a confidence_score reflecting how similar they are (0.6-0.95). Examples:
- Two functions that both validate user input but never call each other
- A class in code and a concept in a paper that describe the same algorithm
- Two error types that handle the same failure mode differently
Only add these when the similarity is genuinely non-obvious and cross-cutting. Do not add them for trivially similar things.

Hyperedges: if 3 or more nodes clearly participate together in a shared concept, flow, or pattern that is not captured by pairwise edges alone, add a hyperedge to a top-level `hyperedges` array. Examples:
- All classes that implement a common protocol or interface
- All functions in an authentication flow (even if they don't all call each other)
- All concepts from a paper section that form one coherent idea
Use sparingly — only when the group relationship adds information beyond the pairwise edges. Maximum 3 hyperedges per chunk.

If a file has YAML frontmatter (--- ... ---), copy source_url, captured_at, author,
  contributor onto every node from that file.

confidence_score rules:
- EXTRACTED edges: confidence_score must be 1.0
- INFERRED edges: score 0.4-0.9 based on how certain you are.
  Strong structural inference (e.g. two classes clearly share data): 0.8-0.9.
  Reasonable but not certain: 0.6-0.7. Weak inference: 0.4-0.5.
- AMBIGUOUS edges: score 0.1-0.3

Output exactly this JSON (no other text):
{"nodes":[{"id":"filestem_entityname","label":"Human Readable Name","file_type":"code|document|paper|image","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[{"id":"snake_case_id","label":"Human Readable Label","nodes":["node_id1","node_id2","node_id3"],"relation":"participate_in|implement|form","confidence":"EXTRACTED|INFERRED","confidence_score":0.75,"source_file":"relative/path"}],"input_tokens":0,"output_tokens":0}"""


class SemanticExtractor:
    """Handles semantic extraction for non-code files using OpenAI function calling."""
    
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o", deep_mode: bool = False):
        effective_key = api_key or os.getenv("OPENAI_API_KEY")
        if not effective_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key parameter.")
        self.client = OpenAI(api_key=effective_key)
        self.model = model
        self.deep_mode = deep_mode
        self.chunk_size = 22  # files per chunk (matches skill.md)
    
    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
    def _extract_chunk(self, file_contents: list[dict[str, str]], chunk_num: int, total_chunks: int) -> dict[str, Any]:
        """Extract knowledge graph from a chunk of files using OpenAI function calling."""
        
        # Build the file list for the prompt
        file_list_str = "\n".join([
            f"--- {f['path']} ---\n{f['content'][:50000]}"  # truncate large files
            for f in file_contents
        ])
        
        prompt = f"""Files (chunk {chunk_num} of {total_chunks}):
{file_list_str}

{'DEEP_MODE: true - be aggressive with INFERRED edges' if self.deep_mode else ''}"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            tools=[EXTRACTION_FUNCTION],
            tool_choice={"type": "function", "function": {"name": "extract_knowledge_graph"}},
            temperature=0.1,
        )
        
        # Parse the function call result
        tool_call = response.choices[0].message.tool_calls[0]
        result = json.loads(tool_call.function.arguments)
        
        # Add token usage
        result["input_tokens"] = response.usage.prompt_tokens
        result["output_tokens"] = response.usage.completion_tokens
        
        return result
    
    def extract(self, files: list[Path], progress: bool = True) -> dict[str, Any]:
        """Extract semantic knowledge from a list of non-code files."""
        # Check cache first
        cached_nodes, cached_edges, uncached_files = check_semantic_cache(files)
        
        if not uncached_files:
            return {
                "nodes": cached_nodes,
                "edges": cached_edges,
                "hyperedges": [],
                "input_tokens": 0,
                "output_tokens": 0,
            }
        
        # Read uncached files
        file_contents = []
        for f in uncached_files:
            try:
                if f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                    # For images, we'd need vision - for now skip and note
                    file_contents.append({
                        "path": str(f),
                        "content": f"[IMAGE FILE: {f.name} - vision extraction not yet implemented]"
                    })
                else:
                    content = f.read_text(errors="ignore")
                    file_contents.append({"path": str(f), "content": content})
            except Exception as e:
                print(f"Warning: Could not read {f}: {e}")
        
        if not file_contents:
            return {
                "nodes": cached_nodes,
                "edges": cached_edges,
                "hyperedges": [],
                "input_tokens": 0,
                "output_tokens": 0,
            }
        
        # Split into chunks
        chunks = [
            file_contents[i:i + self.chunk_size]
            for i in range(0, len(file_contents), self.chunk_size)
        ]
        
        all_nodes = list(cached_nodes)
        all_edges = list(cached_edges)
        all_hyperedges = []
        total_input_tokens = 0
        total_output_tokens = 0
        
        # Process chunks
        iterator = tqdm(chunks, desc="Semantic extraction", disable=not progress)
        for i, chunk in enumerate(iterator):
            try:
                result = self._extract_chunk(chunk, i + 1, len(chunks))
                
                # Deduplicate nodes by ID
                seen_ids = {n["id"] for n in all_nodes}
                for node in result.get("nodes", []):
                    if node["id"] not in seen_ids:
                        all_nodes.append(node)
                        seen_ids.add(node["id"])
                
                all_edges.extend(result.get("edges", []))
                all_hyperedges.extend(result.get("hyperedges", []))
                total_input_tokens += result.get("input_tokens", 0)
                total_output_tokens += result.get("output_tokens", 0)
                
            except Exception as e:
                print(f"Warning: Chunk {i+1} failed: {e}")
                continue
        
        # Save to cache
        new_nodes = [n for n in all_nodes if n not in cached_nodes]
        new_edges = [e for e in all_edges if e not in cached_edges]
        if new_nodes or new_edges:
            save_semantic_cache(new_nodes, new_edges)
        
        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "hyperedges": all_hyperedges,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        }


def extract_semantic(files: list[Path], api_key: str | None = None, model: str = "gpt-4o", deep_mode: bool = False, progress: bool = True) -> dict[str, Any]:
    """Convenience function for semantic extraction."""
    extractor = SemanticExtractor(api_key=api_key, model=model, deep_mode=deep_mode)
    return extractor.extract(files, progress=progress)