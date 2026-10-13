# chatgpt-graphify User Guide

> **Build knowledge graphs from your codebase** — Works with or without OpenAI API key

---

## 🚀 Quick Start

### Install

```bash
# Option 1: From local path (development)
pip install /path/to/chatgpt-graphify

# Option 2: From built wheel (distribution)
pip install chatgpt_graphify-0.1.0-py3-none-any.whl

# Option 3: From GitHub (if published)
pip install git+https://github.com/your-org/chatgpt-graphify.git

# Option 4: With pipx (isolated CLI)
pipx install /path/to/chatgpt-graphify
```

### Run on Your Project

```bash
# Basic usage (code-only, NO API key needed)
chatgpt-graphify ./my-project --no-viz

# Full analysis (requires OpenAI API key)
export OPENAI_API_KEY="sk-..."
chatgpt-graphify ./my-project --no-viz

# Or pass key directly
chatgpt-graphify ./my-project --api-key sk-... --no-viz
```

---

## 📋 What You Get

| Output | Description |
|--------|-------------|
| `graphify-out/graph.json` | Persistent knowledge graph (load in any tool) |
| `graphify-out/GRAPH_REPORT.md` | Human-readable audit report |
| `graphify-out/graph.html` | Interactive local data map |
| `graphify-out/obsidian/` | Open as Obsidian vault for browsing |
| `graphify-out/graph.svg` | Visual graph (with `--svg`) |
| `graphify-out/graph.graphml` | For Gephi/yEd (with `--graphml`) |
| `graphify-out/cypher.txt` | Neo4j import script (with `--neo4j`) |

---

## 🔑 Two Modes of Operation

### Mode 1: Code-Only (No API Key) ✅
**Works for everyone — no credentials needed**

```bash
chatgpt-graphify ./my-project --no-viz
```

- Analyzes: Python, JavaScript, TypeScript, Java, Go, Rust, C++, C#, Ruby, Kotlin, Scala, PHP, C
- Extracts: Classes, functions, methods, imports, calls, inheritance
- Builds: Graph with communities, god nodes, surprising connections
- **Token savings: ~94% (18x reduction)** vs reading all files

### Mode 2: Full Analysis (With API Key) 🔑
**Adds document/PDF/image understanding**

```bash
export OPENAI_API_KEY="sk-..."
chatgpt-graphify ./my-project --no-viz
```

- Everything in Mode 1 **PLUS**:
- Markdown docs, READMEs, architecture docs
- PDF papers, design documents
- Images/diagrams (architecture charts, ER diagrams)
- Semantic relationships across code + docs

---

## 🎯 Common Commands

### Full Pipeline Options

```bash
# Basic pipeline
chatgpt-graphify ./my-project

# Deep extraction (more INFERRED edges)
chatgpt-graphify ./my-project --deep

# Incremental update (only changed files)
chatgpt-graphify ./my-project --update

# Re-cluster existing graph only
chatgpt-graphify ./my-project --cluster-only

# Skip visualizations (faster)
chatgpt-graphify ./my-project --no-viz

# Export formats
chatgpt-graphify ./my-project --svg --graphml --neo4j
```

### Query Existing Graph

```bash
# Ask questions about your codebase
chatgpt-graphify query "how does authentication work"

# DFS traversal (deeper)
chatgpt-graphify query "what connects the API to the database" --dfs

# Token budget control
chatgpt-graphify query "explain the payment flow" --budget 5000
```

### Find Paths Between Concepts

```bash
# Shortest path between two concepts
chatgpt-graphify path "UserService" "Database"
```

### Explain a Specific Node

```bash
# Get details about a concept
chatgpt-graphify explain "HttpClient"
```

### Git Hooks (Auto-Update on Commit)

```bash
# Install post-commit hook
chatgpt-graphify hook install

# Check status
chatgpt-graphify hook status

# Remove hook
chatgpt-graphify hook uninstall
```

### MCP Server (For AI Assistants)

```bash
# Start MCP stdio server (requires Python 3.10+)
chatgpt-graphify ./my-project --mcp
```

---

## 📊 Understanding the Output

### Interactive local data map

Run the normal pipeline without `--no-viz`, then either:

1. In the desktop app, click **Open data map** after analysis completes.
2. Open `graphify-out/graph.html` inside the folder you analyzed.

The map shows the user's own extracted nodes and edges. Click a node to see its source file, type, community, and neighbors. Use search to find a concept and the community legend to focus the view.

This is a local file created inside that user's installation output folder. Graphify does not publish it or send it to other users. The viewer is rendered with built-in browser SVG and JavaScript only; it does not load a CDN, remote script, font, stylesheet, or graph service.

### GRAPH_REPORT.md Sections

| Section | What It Tells You |
|---------|-------------------|
| **Corpus Summary** | File counts, word counts, sensitive files skipped |
| **God Nodes** | Highly connected hubs (potential refactoring targets) |
| **Surprising Connections** | Cross-module links you might not expect |
| **Suggested Questions** | Good starting points for exploration |
| **Communities** | Natural module boundaries |

### Query Output Format

```
Traversal: BFS depth=3 | Start: ['auth', 'login'] | 46 nodes found

NODE auth [src=auth.py loc=L10 community=0]
NODE login [src=auth.py loc=L25 community=0]
EDGE auth --calls [EXTRACTED]--> login
EDGE login --calls [INFERRED]--> validate_token
```

**Confidence Levels:**
- `EXTRACTED` — Directly found in code (100% confidence)
- `INFERRED` — Reasonable deduction (70-90% confidence)
- `AMBIGUOUS` — Weak signal (30-50% confidence)

---

## 🏢 For Organizations

### Team Without API Keys
```bash
# Everyone can run this
chatgpt-graphify ./repo --no-viz
# Shares: graph.json, GRAPH_REPORT.md, obsidian vault
```

### Team With API Keys
```bash
# Add to shell profile or CI/CD
export OPENAI_API_KEY="sk-..."
chatgpt-graphify ./repo --no-viz
```

### CI/CD Integration

```yaml
# .github/workflows/graph.yml
name: Update Knowledge Graph
on:
  push:
    branches: [main]
jobs:
  graph:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.9' }
      - run: pip install chatgpt-graphify
      - run: chatgpt-graphify . --no-viz
      - uses: actions/upload-artifact@v4
        with:
          name: knowledge-graph
          path: graphify-out/
```

### Sharing with ChatGPT Web/Desktop Users

Just share these files — they work standalone:
- `GRAPH_REPORT.md` → Paste into ChatGPT for analysis
- `graph.json` → Load in any graph tool
- `graph.svg` → Open in browser
- `obsidian/` folder → Open as Obsidian vault

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for semantic extraction | None |
| `OPENAI_MODEL` | Model to use | `gpt-4o` |

### Model Options

```bash
# Use cheaper model
chatgpt-graphify ./my-project --model gpt-4o-mini

# Use latest model
chatgpt-graphify ./my-project --model gpt-4o
```

---

## 🐛 Troubleshooting

### "No OpenAI API key provided"
```
⚠ No OpenAI API key provided - skipping semantic extraction on 4 non-code files
  Set OPENAI_API_KEY env var or use --api-key to enable document/PDF/image analysis
```
**Fix:** This is a warning, not an error. Code analysis still works. Add API key for full features.

### "Graph file not found"
```
error: Graph file not found: graphify-out/graph.json
```
**Fix:** Run the full pipeline first, or specify correct path:
```bash
chatgpt-graphify query "question"  # runs in current dir
# or
cd /path/to/project && chatgpt-graphify query "question"
```

### "Not in a git repository"
```
Not in a git repository.
```
**Fix:** Run `git init` first, or run hook commands from a git repo root.

### Tree-sitter Language Errors
```
error: Incompatible Language version 15. Must be between 13 and 14
```
**Fix:** This is a known tree-sitter version mismatch. The file is skipped; other languages work fine.

### MCP Server Won't Start
```
ModuleNotFoundError: No module named 'mcp'
```
**Fix:** MCP requires Python 3.10+. Upgrade Python or use the CLI instead.

---

## 📈 Token Savings Benchmark

Run on your codebase to see actual savings:

```bash
chatgpt-graphify ./my-project --no-viz
# Look for "token reduction benchmark" in output
```

Typical results:
| Codebase Size | Reduction |
|---------------|-----------|
| Small (<50 files) | 10-20x |
| Medium (50-500) | 20-50x |
| Large (500+) | 50-100x+ |

---

## 🔗 Useful Links

- **Source**: https://github.com/your-org/chatgpt-graphify
- **Issues**: https://github.com/your-org/chatgpt-graphify/issues
- **Original graphify**: https://github.com/your-org/graphify

---

## 📝 License

MIT License — Use freely in your organization.

---

*Built as a ChatGPT-compatible alternative to graphify (Claude Code skill)*
