# chatgpt-graphify

**A ChatGPT-compatible knowledge graph builder.** Run `chatgpt-graphify` on any folder - it reads your files, builds a knowledge graph, and gives you back structure you didn't know was there.

**Works WITH or WITHOUT OpenAI API key** — Code analysis runs locally; add API key for document/PDF/image understanding.

```
chatgpt-graphify .                        # works on any folder - your codebase, notes, papers, anything
```

```
graphify-out/
├── graph.json       persistent graph - query weeks later without re-reading
├── GRAPH_REPORT.md  god nodes, surprising connections, suggested questions
├── graph.html       interactive local data map
├── obsidian/        open as Obsidian vault
├── graph.svg        visual graph (with --svg)
├── graph.graphml    for Gephi/yEd (with --graphml)
├── cypher.txt       Neo4j import script (with --neo4j)
└── cache/           SHA256 cache - re-runs only process changed files
```

## Install

**Requires:** Python 3.9+

### Easy installer

For a no-command setup, download the repository and double-click the installer for your operating system:

- Windows: download the latest `ChatGPTGraphifyInstaller.exe` from the [Windows installer workflow artifacts](https://github.com/andrewPillai/chatgpt-graphify/actions/workflows/build-windows-installer.yml)
- macOS: `installers/install-macos.command`

The installer creates a desktop/app launcher with a folder picker. On Windows, the `.exe` installer downloads and installs Python automatically when needed. Users can choose a folder, optionally provide an OpenAI API key for document/PDF/image analysis, and start Graphify without typing commands.

You can also launch the graphical interface directly after installation with `chatgpt-graphify-gui`.

### Local data map

After analysis, open `graphify-out/graph.html` to explore how files, functions, concepts, and relationships are arranged. The desktop app exposes this as **Open data map** after a successful run. Select a node to inspect its source and neighbors, search for a concept, or filter communities from the legend.

![Local data map preview](assets/graphify-data-map-preview.png)

The preview above shows the local visualization experience. Each installation generates its own interactive map from the selected folder; the map is available only on that computer unless the user chooses to share the exported files.

The map is generated into the selected user's local `graphify-out` folder and contains that user's graph data. It is not uploaded or shared by Graphify. The optional OpenAI API key is used only during semantic extraction of documents, PDFs, or images; code-only analysis remains local.

```bash
# From local path
pip install /path/to/chatgpt-graphify

# Or from wheel
pip install chatgpt_graphify-0.1.0-py3-none-any.whl

# Or with pipx (isolated CLI)
pipx install /path/to/chatgpt-graphify
```

**Optional:** For document/PDF/image analysis
```bash
export OPENAI_API_KEY="your-api-key-here"
```

Then run in any directory:

```bash
# Code-only (no API key needed)
chatgpt-graphify .

# Full analysis (with API key)
chatgpt-graphify .
```

## Usage

```
chatgpt-graphify                          # run on current directory
chatgpt-graphify ./my-project             # run on a specific folder
chatgpt-graphify ./my-project --deep      # more aggressive INFERRED edge extraction
chatgpt-graphify ./my-project --update    # re-extract only changed files, merge into existing graph
chatgpt-graphify ./my-project --cluster-only  # re-cluster existing graph only
chatgpt-graphify ./my-project --no-viz    # skip visualizations (faster)

chatgpt-graphify query "how does authentication work?"
chatgpt-graphify query "what connects the API to the database?" --dfs
chatgpt-graphify path "UserService" "Database"
chatgpt-graphify explain "HttpClient"

chatgpt-graphify ./my-project --svg       # export graph.svg
chatgpt-graphify ./my-project --graphml   # export graph.graphml (Gephi, yEd)
chatgpt-graphify ./my-project --neo4j     # generate cypher.txt for Neo4j
chatgpt-graphify ./my-project --neo4j-push bolt://localhost:7687  # push directly to Neo4j
chatgpt-graphify ./my-project --mcp       # start MCP stdio server (requires Python 3.10+)

chatgpt-graphify hook install             # post-commit git hook - rebuilds graph on every commit
chatgpt-graphify hook status              # check hook status
chatgpt-graphify hook uninstall           # remove hook
```

### Two Modes

| Mode | Command | What You Get |
|------|---------|--------------|
| **Code-Only** (no API key) | `chatgpt-graphify ./project --no-viz` | 13 languages via AST, graph building, clustering, analysis |
| **Full** (with API key) | `export OPENAI_API_KEY=sk-... && chatgpt-graphify ./project --no-viz` | Code + Markdown + PDF + Images via OpenAI |

Works with file types:

| Type | Extensions | Extraction |
|------|-----------|------------|
| Code | `.py .ts .js .go .rs .java .c .cpp .rb .cs .kt .scala .php` | AST via tree-sitter + call-graph pass |
| Docs | `.md .txt .rst` | Concepts + relationships via OpenAI (needs API key) |
| Papers | `.pdf` | Citation mining + concept extraction (needs API key) |
| Images | `.png .jpg .webp .gif` | OpenAI vision (needs API key) |

## What you get

**God nodes** - highest-degree concepts (what everything connects through)

**Surprising connections** - ranked by composite score. Cross-module edges rank higher. Each result includes a plain-English why.

**Suggested questions** - 4-5 questions the graph is uniquely positioned to answer

**Token benchmark** - printed automatically after every run. Typical: **10-100x** fewer tokens per query vs reading raw files.

**Git commit hook** (`chatgpt-graphify hook install`) - installs a post-commit hook that rebuilds the graph after every commit. No background process needed. Works with any editor.

Every edge is tagged `EXTRACTED`, `INFERRED`, or `AMBIGUOUS` - you always know what was found vs guessed.

The interactive map is a local artifact for the person who ran the install. It is not a shared company dashboard or hosted service.

**See [USER_GUIDE.md](USER_GUIDE.md) for detailed documentation.**

## Tech stack

NetworkX + Leiden (graspologic) + tree-sitter + OpenAI (GPT-4o) + a dependency-free SVG viewer. No Neo4j required, no server, and the generated visualization does not contact a CDN.

## Architecture

```
detect()  →  extract()  →  build_graph()  →  cluster()  →  analyze()  →  report()  →  export()
```

Each stage is a single function in its own module. They communicate through plain Python dicts and NetworkX graphs - no shared state, no side effects outside `graphify-out/`.

### Module responsibilities

| Module | Function | Input → Output |
|--------|----------|----------------|
| `detect.py` | `detect(root)` | directory → `{files, total_words, warning}` |
| `extract.py` | `extract(path)` | file path → `{nodes, edges}` dict (AST only) |
| `semantic_extract.py` | `extract_semantic(files)` | files → `{nodes, edges, hyperedges}` (OpenAI) |
| `build.py` | `build_from_json(extractions)` | list of extraction dicts → `nx.Graph` |
| `cluster.py` | `cluster(G)` | graph → graph with `community` attr on each node |
| `analyze.py` | `analyze(G)` | graph → analysis dict (god nodes, surprises, questions) |
| `report.py` | `generate(G, analysis)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `export(G, out_dir, ...)` | graph → Obsidian vault, graph.json, graph.html, graph.svg |
| `cache.py` | `check_semantic_cache / save_semantic_cache` | files → (cached, uncached) split |
| `security.py` | validation helpers | URL / path / label → validated or raises |
| `validate.py` | `validate_extraction(data)` | extraction dict → raises on schema errors |
| `serve.py` | `start_server(graph_path)` | graph file path → MCP stdio server |
| `watch.py` | `watch(root, flag_path)` | directory → writes flag file on change |
| `benchmark.py` | `run_benchmark(graph_path)` | graph file → corpus vs subgraph token comparison |

## Confidence labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source (e.g., an import statement, a direct call) |
| `INFERRED` | Relationship is a reasonable deduction (e.g., call-graph second pass, co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

## Adding a new language extractor

1. Add a `extract_<lang>(path: Path) -> dict` function in `extract.py` following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for INFERRED `calls` edges).
2. Register the file suffix in `extract()` dispatch and `collect_files()`.
3. Add the suffix to `CODE_EXTENSIONS` in `detect.py` and `_WATCHED_EXTENSIONS` in `watch.py`.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py`.

## Security

All external input passes through `chatgpt_graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Graph file paths → `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

## Testing

```bash
pytest tests/ -q
```

## License

MIT
