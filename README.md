# Local Literature Knowledge Base for OpenClaw (BibTeX-First, Phase 4) via MCP

> A local BibTeX-first literature knowledge base that indexes PDFs and Mendeley-exported notes from the `annote` field into a searchable local SQLite/MCP service. Phase 4 adds research-workflow tools for browsing the library, exporting citations, and finding related papers.

**Current Status (2026-03-09):** ✅ **Phase 4 Expanded** | 5,798 papers indexed | 12,489 chunks | 37 MB database | Enhanced MCP server ready

**Phase 3 Features:**
- 🔍 Duplicate detection by DOI/title
- 📝 Incremental refresh (skip unchanged files)
- ✏️ Note editing with history tracking
- 🛠️ Enhanced MCP tools

**Phase 4 Features:**
- 📚 Library browsing by year, venue, author, tag, or title
- 📖 Citation export in `apa`, `short`, or `bibtex` formats
- 🔗 Related-paper discovery from shared metadata

## Quick Start

```bash
# 1. Install dependencies
cd /home/azurin/.openclaw/workspace/project/Yang_Document/Literature
source venv/bin/activate  # or: python3 -m venv venv && source venv/bin/activate

pip install -r requirements.txt

# 2. Configuration is already set up in config.yaml
# - PDFs: /home/azurin/.openclaw/workspace/project/Yang_Document/LIB_ROOT
# - BibTeX: /home/azurin/.openclaw/workspace/project/Yang_Document/My_Collection.bib

# 3. Run ingestion to build the index
python ingest/ingest_bibtex.py --config config.yaml --stats

# 4. Start the MCP server (for OpenClaw integration)
python mcp_server/server.py --config config.yaml
```

## What This Is

A local knowledge base for your research literature. It indexes your PDF papers alongside your BibTeX-based reading notes (stored in Mendeley's `annote` field), making them searchable through OpenClaw via MCP (Model Context Protocol).

**Key features:**
- 🔍 **BM25 keyword search** - Fast full-text search across all indexed content
- 📝 **BibTeX note integration** - Extracts annotations from the `annote` field
- 📄 **PDF text extraction** - Indexes full text from locally available PDFs
- 📚 **Large library support** - Successfully tested with 6,000+ paper entries
- 🏷️ **Rich metadata** - Year, venue, DOI, authors from BibTeX
- 🔒 **Completely local** - No cloud services, all data stays on your machine
- ⚡ **MCP integration** - Query directly from OpenClaw

## How It Works

### 1. Data Sources

This system is designed for Mendeley users who store their library as:

- **PDFs**: Stored in a local directory (e.g., `LIB_ROOT/2026/Journal/Author - Year - Title.pdf`)
- **BibTeX file**: Exported from Mendeley with annotations in the `annote` field

Example BibTeX entry:
```bibtex
@article{Sharip2026,
annote = {multienzyme immobilization on MOF
etched to include enzyme
synthesis of violacein},
author = {Sharip, Ainur and ...},
journal = {bioRxiv},
title = {{Hierarchically engineered multi-enzyme nanoreactors...}},
year = {2026}
}
```

### 2. Library Structure

Your PDFs should be organized as:
```
LIB_ROOT/
├── 2026/
│   ├── Journal of Inorganic Biochemistry/
│   │   └── Author et al. - 2026 - Title.pdf
│   ├── Nature/
│   │   └── Author et al. - 2026 - Title.pdf
│   └── ...
└── ...
```

### 3. Ingestion Pipeline

The `ingest_bibtex.py` script:
- Parses your BibTeX file (supports 6,000+ entries)
- Extracts metadata (title, year, venue, authors, DOI)
- Extracts notes from the `annote` field
- Finds matching PDFs by filename/title similarity
- Chunks content for efficient search
- Stores everything in a local SQLite database with FTS5 full-text indexing

### 4. Search & Retrieval

Once indexed, you can:
- Search for concepts across your entire library (notes + PDFs)
- Retrieve specific annotations or PDF pages
- Get document metadata (year, venue, authors, DOI)
- Access your research notes directly from OpenClaw

## MCP Tools

The server exposes these tools to OpenClaw:

| Tool | Purpose |
|------|---------|
| `kb_search` | Full-text search with filters |
| `kb_get_document` | Get document metadata |
| `kb_get_note` | Retrieve full note content |
| `kb_get_pdf_text` | Extract specific PDF pages |
| `kb_refresh` | Update the index |
| `kb_list_documents` | Browse the library by metadata |
| `kb_get_citation` | Format a citation for a paper |
| `kb_find_related` | Find related papers |
| `kb_stats` | Show database statistics |

### Example: kb_search (with hybrid scoring)

**Input:**
```json
{
  "query": "transformer architecture",
  "filters": {"year": 2017},
  "k": 10,
  "semantic": true
}
```

**Output:**
```json
{
  "hits": [
    {
      "doc_key": "attention_is_all_you_need_2017",
      "title": "Attention Is All You Need",
      "year": 2017,
      "venue": "NeurIPS",
      "source_type": "note",
      "hybrid_score": 0.8923,
      "bm25_score": 0.8234,
      "semantic_score": 0.9612,
      "snippet": "[Page 1] Summary: Introduces the Transformer architecture...",
      "locator": {"page": 1},
      "pdf_path": "/home/.../Attention Is All You Need.pdf",
      "note_path": "/home/.../My_Collection.bib"
    }
  ]
}
```

The `hybrid_score` combines BM25 (keyword) and semantic similarity. You can also see individual scores to understand why results are ranked.

## Project Structure

```
Literature/
├── README.md                       # This file
├── config.yaml                     # Your configuration (PDF + BibTeX paths)
├── config.example.yaml             # Configuration template
├── requirements.txt                # Python dependencies
├── IMPLEMENTATION.md               # Technical implementation details
├── schema/
│   └── 001_initial.sql             # Database schema (SQLite + FTS5)
├── mcp_server/
│   ├── database.py                 # Database operations
│   ├── enhanced_database.py        # **Phase 4: Enhanced database with browse/citation/related docs**
│   ├── bibtex_ingestion.py         # BibTeX ingestion
│   ├── enhanced_bibtex_ingestion.py # **Phase 3: Enhanced with duplicate detection**
│   ├── ingestion.py                # Deprecated legacy Markdown-note ingestion
│   ├── server.py                   # MCP server
│   └── enhanced_server.py          # **Phase 4: Enhanced MCP server with workflow tools**
├── ingest/
│   ├── ingest_bibtex.py            # Standalone CLI for BibTeX
│   ├── ingest_enhanced.py          # **Phase 3: Enhanced CLI with all features**
│   └── ingest.py                   # Deprecated legacy Markdown-note CLI
└── tests/
    ├── test_basic.py               # Unit tests
    ├── test_semantic.py            # Semantic search tests
    └── test_phase4.py              # Browse/citation/related-doc tests
```

## Deprecation Note

The Markdown note workflow (`ingest/ingest.py`, `mcp_server/ingestion.py`, and related helpers) is deprecated. The supported path for this repository is BibTeX ingestion from `My_Collection.bib` with notes read from the `annote` field.

## Configuration

Your `config.yaml` is already set up:

```yaml
# Root directory containing your PDF library
pdf_root: "/home/azurin/.openclaw/workspace/project/Yang_Document/LIB_ROOT"

# Path to your BibTeX file with annotations
bibtex_path: "/home/azurin/.openclaw/workspace/project/Yang_Document/My_Collection.bib"

# Path to the SQLite database
index_path: "/home/azurin/.openclaw/workspace/project/Yang_Document/Literature/kb/index.sqlite"

# Text chunking settings
chunking:
  pdf_chunk_chars: 2000    # Characters per PDF chunk
  note_chunk_chars: 1500   # Characters per note chunk
```

## Usage Examples

### Initial Indexing

```bash
# Index your entire BibTeX library
python ingest/ingest_bibtex.py --config config.yaml --stats

# Output:
# Parsing BibTeX file: /home/azurin/.../My_Collection.bib
# Found 6047 entries to ingest
# Indexed: Widatalla et al. - 2025 - Sidechain conditioning... (0 note chunks, 1 abstract chunks, 0 PDF chunks)
# Indexed: Sharip et al. - 2026 - Hierarchically engineered... (1 note chunks, 0 abstract chunks, 0 PDF chunks)
# ...
# ==================================================
# Ingestion complete!
#   Indexed: 5798
#   Failed: 0
#   Skipped: 0
#
# Database statistics:
#   Documents: 5798
#   Total chunks: 12489
#   PDF chunks: 2552
#   Note chunks: 9937
```

### Running the MCP Server

```bash
# Start the server (stdio mode for MCP)
python mcp_server/server.py --config config.yaml

# The server will listen for MCP requests from OpenClaw
```

### Phase 3: Enhanced Ingestion with Duplicate Detection

```bash
# Use the enhanced ingester with Phase 3 features
python ingest/ingest_enhanced.py --config config.yaml --stats

# Force full refresh (ignore incremental check)
python ingest/ingest_enhanced.py --config config.yaml --full-refresh

# Include suspected duplicates (don't skip them)
python ingest/ingest_enhanced.py --config config.yaml --include-duplicates

# Show detected duplicates after ingestion
python ingest/ingest_enhanced.py --config config.yaml --show-duplicates
```

### Running the Enhanced MCP Server

```bash
# Start the enhanced server with new tools
python mcp_server/enhanced_server.py --config config.yaml
```

### Enhanced MCP Tools

| Tool | Purpose |
|------|---------|
| `kb_search` | Full-text search with filters |
| `kb_get_document` | Get document metadata |
| `kb_get_note` | Retrieve note content |
| `kb_get_pdf_text` | Extract PDF pages |
| `kb_update_note` | **Update note content** (with history) |
| `kb_get_note_history` | **View note edit history** |
| `kb_find_duplicates` | **List detected duplicates** |
| `kb_check_duplicate` | **Check if paper exists** by DOI |
| `kb_refresh` | **Incremental refresh** |
| `kb_list_documents` | **Browse documents** by metadata filters |
| `kb_get_citation` | **Export citations** for writing workflows |
| `kb_find_related` | **Find related papers** from shared metadata |
| `kb_stats` | Show database statistics |

### Phase 4 Workflow Examples

```json
{"tool":"kb_list_documents","arguments":{"filters":{"venue":"Nature Catalysis","year":2024},"limit":20}}
```

```json
{"tool":"kb_get_citation","arguments":{"doc_key":"10.1000/alpha","style":"apa"}}
```

```json
{"tool":"kb_find_related","arguments":{"doc_key":"10.1000/alpha","limit":5}}
```

### Testing Search

```python
from mcp_server.database import LiteratureDatabase

db = LiteratureDatabase("kb/index.sqlite")

# Search for papers about transformers
results = db.search_chunks("transformer attention", k=5)

for hit in results:
    print(f"{hit['title']} ({hit['year']})")
    print(f"  Source: {hit['source_type']}")
    print(f"  Snippet: {hit['snippet'][:200]}...")
    print()
```

## Architecture

### Database Schema

- **documents**: Metadata for each paper (title, year, venue, DOI, authors, paths)
- **chunks**: Searchable text chunks from PDFs and notes
- **FTS5 virtual tables**: Full-text search indexes

### Ingestion Flow (BibTeX Mode)

1. Parse BibTeX file and extract all entries
2. Extract metadata (title, year, venue, authors, DOI)
3. Extract notes from the `annote` field
4. Find corresponding PDFs by filename matching
5. Chunk note content (by paragraphs) and PDF text (by pages)
6. Store in SQLite with FTS5 indexing

### Search Flow

1. Query FTS5 index for matching chunks
2. Join with documents table for metadata
3. Return ranked results with snippets and locators
4. OpenClaw can then fetch full notes or PDF pages as needed

## Roadmap

### Phase 1 ✅ (Complete)
- SQLite + FTS5 keyword search
- PDF text extraction
- MCP server with core tools

### Phase 2 ✅ (Complete - BibTeX Support)
- **BibTeX ingestion**: Parse Mendeley exports with `annote` field
- Large library support (tested with 6,000+ entries)
- PDF matching by filename/title similarity
- Abstract fallback when no annotations present

### Phase 3 ✅ (Complete - Enhanced Features)
- **Duplicate detection**: Automatic detection by DOI and title/year matching
- **Incremental refresh**: Only re-index when BibTeX file changes
- **Note editing**: Update notes via MCP with edit history tracking
- **Enhanced MCP tools**: New tools for duplicate checking and note management

### Phase 4 ✅ (Complete - Research Workflow Tools)
- **Library browsing**: Filter documents by year, venue, author, tag, or title
- **Citation export**: Format citations as `apa`, `short`, or `bibtex`
- **Related-paper discovery**: Rank nearby papers from shared metadata

### Phase 5 (Future)
- Stronger hybrid ranking across the enhanced server path
- File watching for automatic refresh
- Web interface for browsing library

## Requirements

- Python 3.10+
- Dependencies: `pyyaml`, `pymupdf`, `mcp`
- Storage: ~6MB per 1000 papers (SQLite with FTS5)
- RAM: Minimal (~50MB for ingestion, scales with library size)

## License

MIT - Use it, modify it, make it yours.

## Contributing

This is a personal tool that grew out of a need. If you find it useful and want to improve it, feel free to fork and modify. The architecture is designed to be extended without breaking existing functionality.
