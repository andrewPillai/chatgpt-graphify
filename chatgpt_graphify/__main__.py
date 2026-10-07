"""chatgpt-graphify CLI - main entry point for the knowledge graph pipeline."""
from __future__ import annotations
import json
import sys
import shutil
import os
from pathlib import Path
from typing import Optional

from .detect import detect, detect_incremental, save_manifest, FileType
from .extract import collect_files, extract as ast_extract
from .build import build_from_json
from .cluster import cluster, score_all
from .analyze import god_nodes, surprising_connections, suggest_questions
from .report import generate
from .export import to_json, to_obsidian, to_canvas, to_html, to_svg, to_graphml, to_cypher, push_to_neo4j
from .cache import check_semantic_cache, save_semantic_cache
from .semantic_extract import extract_semantic
from .benchmark import run_benchmark, print_benchmark
from .hooks import install as hook_install, uninstall as hook_uninstall, status as hook_status
from .security import validate_graph_path


def _print_corpus_summary(detection: dict) -> None:
    """Print a clean summary of the detected corpus."""
    files = detection["files"]
    print(f"Corpus: {detection['total_files']} files · ~{detection['total_words']:,} words")
    for ftype in [FileType.CODE, FileType.DOCUMENT, FileType.PAPER, FileType.IMAGE]:
        count = len(files.get(ftype.value, []))
        if count:
            print(f"  {ftype.value:8}: {count} files")
    if detection["skipped_sensitive"]:
        print(f"  skipped: {len(detection['skipped_sensitive'])} sensitive files")
    if detection["warning"]:
        print(f"\n⚠ {detection['warning']}")


def _run_ast_extraction(code_files: list[Path]) -> dict:
    """Run AST extraction on code files."""
    if not code_files:
        return {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    
    print(f"Running AST extraction on {len(code_files)} code files...")
    result = ast_extract(code_files)
    print(f"AST: {len(result['nodes'])} nodes, {len(result['edges'])} edges")
    return result


def _run_semantic_extraction(non_code_files: list[Path], deep_mode: bool, api_key: Optional[str], model: str) -> dict:
    """Run semantic extraction on non-code files using OpenAI."""
    if not non_code_files:
        return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    
    # Check if API key is available
    effective_key = api_key or os.getenv("OPENAI_API_KEY")
    if not effective_key:
        print(f"⚠ No OpenAI API key provided - skipping semantic extraction on {len(non_code_files)} non-code files")
        print("  Set OPENAI_API_KEY env var or use --api-key to enable document/PDF/image analysis")
        return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    
    print(f"Running semantic extraction on {len(non_code_files)} non-code files...")
    result = extract_semantic(non_code_files, api_key=api_key, model=model, deep_mode=deep_mode)
    print(f"Semantic: {len(result['nodes'])} nodes, {len(result['edges'])} edges, {len(result.get('hyperedges', []))} hyperedges")
    return result


def _merge_extractions(ast_result: dict, semantic_result: dict) -> dict:
    """Merge AST and semantic extraction results."""
    # AST nodes first, semantic nodes deduplicated by id
    seen = {n['id'] for n in ast_result['nodes']}
    merged_nodes = list(ast_result['nodes'])
    for n in semantic_result['nodes']:
        if n['id'] not in seen:
            merged_nodes.append(n)
            seen.add(n['id'])
    
    merged_edges = ast_result['edges'] + semantic_result['edges']
    merged_hyperedges = semantic_result.get('hyperedges', [])
    
    merged = {
        'nodes': merged_nodes,
        'edges': merged_edges,
        'hyperedges': merged_hyperedges,
        'input_tokens': semantic_result.get('input_tokens', 0),
        'output_tokens': semantic_result.get('output_tokens', 0),
    }
    print(f"Merged: {len(merged_nodes)} nodes, {len(merged_edges)} edges ({len(ast_result['nodes'])} AST + {len(semantic_result['nodes'])} semantic)")
    return merged


def _build_and_analyze(extraction: dict, detection: dict, input_path: str) -> tuple:
    """Build graph, cluster, analyze, and generate report."""
    print("Building graph and running analysis...")
    
    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    
    tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f'Community {cid}' for cid in communities}
    questions = suggest_questions(G, communities, labels)
    
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, input_path, suggested_questions=questions)
    
    return G, communities, cohesion, gods, surprises, labels, questions, report


def _generate_outputs(G, communities, cohesion, labels, input_path: str, output_dir: Path, 
                      generate_viz: bool = True, export_svg: bool = False, export_graphml: bool = False,
                      export_neo4j: bool = False, neo4j_uri: Optional[str] = None,
                      export_mcp: bool = False) -> None:
    """Generate all output formats."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Always generate JSON and report
    to_json(G, communities, output_dir / "graph.json")
    print(f"Graph JSON: {output_dir / 'graph.json'}")
    
    # Generate Obsidian vault (default)
    if generate_viz:
        n = to_obsidian(G, communities, output_dir / "obsidian", community_labels=labels, cohesion=cohesion)
        print(f"Obsidian vault: {n} notes in {output_dir / 'obsidian'}")
        to_canvas(G, communities, output_dir / "obsidian" / "graph.canvas", community_labels=labels)
        print(f"Canvas: {output_dir / 'obsidian' / 'graph.canvas'}")
    
    # Generate HTML
    if generate_viz and G.number_of_nodes() <= 5000:
        to_html(G, communities, output_dir / "graph.html", community_labels=labels)
        print(f"HTML graph: {output_dir / 'graph.html'}")
    elif generate_viz:
        print(f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz. Use Obsidian vault instead.")
    
    # Optional exports
    if export_svg:
        to_svg(G, communities, output_dir / "graph.svg", community_labels=labels)
        print(f"SVG: {output_dir / 'graph.svg'}")
    
    if export_graphml:
        to_graphml(G, communities, output_dir / "graph.graphml")
        print(f"GraphML: {output_dir / 'graph.graphml'}")
    
    if export_neo4j:
        if neo4j_uri:
            result = push_to_neo4j(G, uri=neo4j_uri, communities=communities)
            print(f"Pushed to Neo4j: {result['nodes']} nodes, {result['edges']} edges")
        else:
            to_cypher(G, output_dir / "cypher.txt")
            print(f"Cypher: {output_dir / 'cypher.txt'}")
    
    if export_mcp:
        print(f"To start MCP server: python3 -m chatgpt_graphify.serve {output_dir / 'graph.json'}")


def _run_benchmark_if_needed(graph_path: Path, detection: dict) -> None:
    """Run token reduction benchmark if corpus is large enough."""
    if detection.get('total_words', 0) > 5000:
        print("\nRunning token reduction benchmark...")
        result = run_benchmark(str(graph_path), corpus_words=detection['total_words'])
        print_benchmark(result)


def _save_manifest_and_cleanup(detection: dict, extraction: dict, output_dir: Path) -> None:
    """Save manifest for --update and clean up temp files."""
    save_manifest(detection['files'])
    
    # Update cost tracker
    cost_path = output_dir / "cost.json"
    input_tok = extraction.get('input_tokens', 0)
    output_tok = extraction.get('output_tokens', 0)
    
    if cost_path.exists():
        cost = json.loads(cost_path.read_text())
    else:
        cost = {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}
    
    from datetime import datetime, timezone
    cost['runs'].append({
        'date': datetime.now(timezone.utc).isoformat(),
        'input_tokens': input_tok,
        'output_tokens': output_tok,
        'files': detection.get('total_files', 0),
    })
    cost['total_input_tokens'] += input_tok
    cost['total_output_tokens'] += output_tok
    cost_path.write_text(json.dumps(cost, indent=2))
    
    print(f"\nThis run: {input_tok:,} input tokens, {output_tok:,} output tokens")
    print(f"All time: {cost['total_input_tokens']:,} input, {cost['total_output_tokens']:,} output ({len(cost['runs'])} runs)")
    
    # Clean up temp files
    for temp_file in [
        ".graphify_detect.json", ".graphify_extract.json", ".graphify_ast.json",
        ".graphify_semantic.json", ".graphify_analysis.json", ".graphify_labels.json",
        ".graphify_cached.json", ".graphify_uncached.txt", ".graphify_semantic_new.json",
        ".graphify_incremental.json", ".graphify_old.json"
    ]:
        Path(temp_file).unlink(missing_ok=True)


def run_pipeline(input_path: str, deep_mode: bool = False, update_mode: bool = False,
                 cluster_only: bool = False, no_viz: bool = False,
                 export_svg: bool = False, export_graphml: bool = False,
                 export_neo4j: bool = False, neo4j_uri: Optional[str] = None,
                 export_mcp: bool = False, api_key: Optional[str] = None,
                 model: str = "gpt-4o") -> None:
    """Run the full graphify pipeline."""
    root = Path(input_path).resolve()
    output_dir = root / "graphify-out"
    
    print(f"chatgpt-graphify: processing {root}")
    
    if cluster_only:
        # Load existing graph and re-cluster
        print("Cluster-only mode: loading existing graph...")
        graph_path = output_dir / "graph.json"
        if not graph_path.exists():
            print("ERROR: No graph found. Run chatgpt-graphify first to build the graph.")
            sys.exit(1)
        
        import networkx as nx
        from networkx.readwrite import json_graph
        data = json.loads(graph_path.read_text())
        G = json_graph.node_link_graph(data, link='links')
        
        detection = {'total_files': 0, 'total_words': 99999, 'needs_graph': True, 'warning': None,
                     'files': {'code': [], 'document': [], 'paper': [], 'image': []}}
        tokens = {'input': 0, 'output': 0}
        
        communities = cluster(G)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels = {cid: f'Community {cid}' for cid in communities}
        
        report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, input_path)
        (output_dir / "GRAPH_REPORT.md").write_text(report)
        to_json(G, communities, output_dir / "graph.json")
        
        print(f"Re-clustered: {len(communities)} communities")
        return
    
    if update_mode:
        # Incremental update
        print("Update mode: detecting changed files...")
        detection = detect_incremental(root)
        new_total = detection.get('new_total', 0)
        
        if new_total == 0:
            print("No files changed since last run. Nothing to update.")
            return
        
        print(f"{new_total} new/changed file(s) to re-extract.")
        
        # Check if all changed files are code-only
        code_exts = {'.py','.ts','.js','.go','.rs','.java','.cpp','.c','.rb','.swift','.kt','.cs','.scala','.php','.cc','.cxx','.hpp','.h','.kts'}
        all_changed = [f for files in detection.get('new_files', {}).values() for f in files]
        code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
        
        if code_only:
            print("[chatgpt-graphify update] Code-only changes detected - skipping semantic extraction (no LLM needed)")
            # Run only AST on changed files
            code_files = [Path(f) for f in all_changed]
            ast_result = _run_ast_extraction(code_files)
            semantic_result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
        else:
            # Full extraction on changed files
            code_files = [Path(f) for f in detection.get('new_files', {}).get('code', [])]
            non_code_files = [Path(f) for ftype in ['document', 'paper', 'image'] 
                            for f in detection.get('new_files', {}).get(ftype, [])]
            ast_result = _run_ast_extraction(code_files)
            semantic_result = _run_semantic_extraction(non_code_files, deep_mode, api_key, model)
        
        # Merge with existing graph
        extraction = _merge_extractions(ast_result, semantic_result)
        
        # Load existing graph and merge
        import networkx as nx
        from networkx.readwrite import json_graph
        existing_data = json.loads((output_dir / "graph.json").read_text())
        G_existing = json_graph.node_link_graph(existing_data, link='links')
        G_new = build_from_json(extraction)
        G_existing.update(G_new)
        
        # Save old graph for diff
        shutil.copy(output_dir / "graph.json", ".graphify_old.json")
        
        # Re-analyze
        detection = detect(root)  # Full detection for report
        G, communities, cohesion, gods, surprises, labels, questions, report = _build_and_analyze(
            extraction, detection, input_path
        )
        
        # Show diff
        from .analyze import graph_diff
        old_data = json.loads(Path(".graphify_old.json").read_text())
        G_old = json_graph.node_link_graph(old_data, link='links')
        diff = graph_diff(G_old, G)
        print(diff['summary'])
        if diff['new_nodes']:
            print('New nodes:', ', '.join(n['label'] for n in diff['new_nodes'][:5]))
        if diff['new_edges']:
            print('New edges:', len(diff['new_edges']))
        Path(".graphify_old.json").unlink(missing_ok=True)
    else:
        # Full pipeline
        detection = detect(root)
        _print_corpus_summary(detection)
        
        if detection['total_files'] == 0:
            print(f"No supported files found in {input_path}.")
            sys.exit(1)
        
        if detection['warning'] and (detection['total_words'] > 500_000 or detection['total_files'] > 200):
            # Large corpus - ask which subfolder
            print("\nLarge corpus detected. Please specify a subfolder to process.")
            sys.exit(1)
        
        # Separate code and non-code files
        code_files = [Path(f) for f in detection['files'].get('code', [])]
        non_code_files = [Path(f) for ftype in ['document', 'paper', 'image'] 
                         for f in detection['files'].get(ftype, [])]
        
        # Run extractions in parallel (sequential for now, could use asyncio)
        ast_result = _run_ast_extraction(code_files)
        semantic_result = _run_semantic_extraction(non_code_files, deep_mode, api_key, model)
        
        # Merge
        extraction = _merge_extractions(ast_result, semantic_result)
        
        # Build and analyze
        G, communities, cohesion, gods, surprises, labels, questions, report = _build_and_analyze(
            extraction, detection, input_path
        )
    
    # Generate outputs
    _generate_outputs(G, communities, cohesion, labels, input_path, output_dir,
                      generate_viz=not no_viz, export_svg=export_svg, export_graphml=export_graphml,
                      export_neo4j=export_neo4j, neo4j_uri=neo4j_uri, export_mcp=export_mcp)
    
    # Benchmark
    _run_benchmark_if_needed(output_dir / "graph.json", detection)
    
    # Save manifest and cleanup
    _save_manifest_and_cleanup(detection, extraction, output_dir)
    
    # Print summary
    print(f"\nGraph complete. Outputs in: {output_dir}")
    print(f"  {output_dir / 'obsidian'} - open as Obsidian vault")
    print(f"  {output_dir / 'GRAPH_REPORT.md'} - full audit report")
    print(f"  {output_dir / 'graph.json'} - persistent graph")


def query_graph(graph_path: str, question: str, mode: str = "bfs", depth: int = 3, budget: int = 2000) -> str:
    """Query the knowledge graph."""
    from .serve import _load_graph, _score_nodes, _bfs, _dfs, _subgraph_to_text
    
    G = _load_graph(graph_path)
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scored = _score_nodes(G, terms)
    start_nodes = [nid for _, nid in scored[:3]]
    
    if not start_nodes:
        return "No matching nodes found for query terms: " + ", ".join(terms)
    
    nodes, edges = _dfs(G, start_nodes, depth) if mode == "dfs" else _bfs(G, start_nodes, depth)
    header = f"Traversal: {mode.upper()} depth={depth} | Start: {[G.nodes[n].get('label', n) for n in start_nodes]} | {len(nodes)} nodes found\n\n"
    return header + _subgraph_to_text(G, nodes, edges, budget)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: chatgpt-graphify <command> [options]")
        print()
        print("Commands:")
        print("  chatgpt-graphify <path>              # full pipeline on path")
        print("  chatgpt-graphify <path> --deep       # thorough extraction, richer INFERRED edges")
        print("  chatgpt-graphify <path> --update     # incremental - re-extract only changed files")
        print("  chatgpt-graphify <path> --cluster-only  # rerun clustering on existing graph")
        print("  chatgpt-graphify <path> --no-viz     # skip visualization, just report + JSON")
        print("  chatgpt-graphify <path> --svg        # also export graph.svg")
        print("  chatgpt-graphify <path> --graphml    # export graph.graphml (Gephi, yEd)")
        print("  chatgpt-graphify <path> --neo4j      # generate cypher.txt for Neo4j")
        print("  chatgpt-graphify <path> --neo4j-push <uri>  # push directly to Neo4j")
        print("  chatgpt-graphify <path> --mcp        # start MCP stdio server")
        print("  chatgpt-graphify query <question>    # query existing graph")
        print("  chatgpt-graphify query <question> --dfs  # DFS traversal")
        print("  chatgpt-graphify query <question> --budget N  # token budget")
        print("  chatgpt-graphify path <source> <target>  # shortest path between concepts")
        print("  chatgpt-graphify explain <concept>   # explain a node")
        print("  chatgpt-graphify hook install        # install post-commit git hook")
        print("  chatgpt-graphify hook uninstall      # remove post-commit git hook")
        print("  chatgpt-graphify hook status         # check hook status")
        print()
        print("Options:")
        print("  --api-key KEY      OpenAI API key (or set OPENAI_API_KEY env var)")
        print("                     Optional - only needed for document/PDF/image analysis")
        print("                     Code analysis (AST) works WITHOUT an API key")
        print("  --model MODEL      OpenAI model to use (default: gpt-4o)")
        return
    
    cmd = sys.argv[1]
    
    # Parse common options
    api_key = None
    model = "gpt-4o"
    args = sys.argv[2:]
    
    i = 0
    while i < len(args):
        if args[i] == "--api-key" and i + 1 < len(args):
            api_key = args[i + 1]
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        else:
            i += 1
    
    if cmd == "query":
        # chatgpt-graphify query "question" [--dfs] [--budget N]
        question = args[0] if args else ""
        mode = "bfs"
        depth = 3
        budget = 2000
        
        i = 1
        while i < len(args):
            if args[i] == "--dfs":
                mode = "dfs"
            elif args[i] == "--budget" and i + 1 < len(args):
                budget = int(args[i + 1])
                i += 1
            i += 1
        
        graph_path = "graphify-out/graph.json"
        result = query_graph(graph_path, question, mode, depth, budget)
        print(result)
        return
    
    elif cmd == "path":
        # chatgpt-graphify path "source" "target"
        if len(args) < 2:
            print("Usage: chatgpt-graphify path <source> <target>", file=sys.stderr)
            sys.exit(1)
        from .serve import _load_graph, _score_nodes
        import networkx as nx
        G = _load_graph("graphify-out/graph.json")
        src_scored = _score_nodes(G, [t.lower() for t in args[0].split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in args[1].split()])
        if not src_scored or not tgt_scored:
            print("Source or target not found")
            sys.exit(1)
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        try:
            path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
            segments = []
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                edata = G.edges[u, v]
                rel = edata.get("relation", "")
                conf = edata.get("confidence", "")
                conf_str = f" [{conf}]" if conf else ""
                if i == 0:
                    segments.append(G.nodes[u].get("label", u))
                segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
            print(f"Shortest path ({len(path_nodes)-1} hops):")
            print("  " + " ".join(segments))
        except nx.NetworkXNoPath:
            print(f"No path found between '{args[0]}' and '{args[1]}'")
        return
    
    elif cmd == "explain":
        # chatgpt-graphify explain "concept"
        if not args:
            print("Usage: chatgpt-graphify explain <concept>", file=sys.stderr)
            sys.exit(1)
        from .serve import _load_graph, _find_node
        G = _load_graph("graphify-out/graph.json")
        matches = _find_node(G, args[0])
        if not matches:
            print(f"No node matching '{args[0]}' found.")
            return
        nid = matches[0]
        d = G.nodes[nid]
        print(f"Node: {d.get('label', nid)}")
        print(f"  ID: {nid}")
        print(f"  Source: {d.get('source_file', '')} {d.get('source_location', '')}")
        print(f"  Type: {d.get('file_type', '')}")
        print(f"  Community: {d.get('community', '')}")
        print(f"  Degree: {G.degree(nid)}")
        if d.get('rationale'):
            print(f"  Rationale: {d['rationale']}")
        return
    
    elif cmd == "hook":
        subcmd = args[0] if args else ""
        if subcmd == "install":
            print(hook_install(Path(".")))
        elif subcmd == "uninstall":
            print(hook_uninstall(Path(".")))
        elif subcmd == "status":
            print(hook_status(Path(".")))
        else:
            print("Usage: chatgpt-graphify hook [install|uninstall|status]", file=sys.stderr)
            sys.exit(1)
        return
    
    else:
        # Main pipeline: chatgpt-graphify <path> [options]
        input_path = cmd
        deep_mode = "--deep" in args
        update_mode = "--update" in args
        cluster_only = "--cluster-only" in args
        no_viz = "--no-viz" in args
        export_svg = "--svg" in args
        export_graphml = "--graphml" in args
        export_neo4j = "--neo4j" in args
        export_mcp = "--mcp" in args
        neo4j_uri = None
        
        if "--neo4j-push" in args:
            idx = args.index("--neo4j-push")
            if idx + 1 < len(args):
                neo4j_uri = args[idx + 1]
                export_neo4j = True
        
        run_pipeline(input_path, deep_mode, update_mode, cluster_only, no_viz,
                     export_svg, export_graphml, export_neo4j, neo4j_uri, export_mcp,
                     api_key, model)


if __name__ == "__main__":
    main()