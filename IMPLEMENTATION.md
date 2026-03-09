# Literature Knowledge Base - BibTeX Implementation Summary

## What Was Built

A BibTeX-first implementation of the Literature Knowledge Base with the following components.

The current repository now includes a Phase 4 expansion on top of the enhanced BibTeX path: document browsing, citation export, and related-paper discovery for research workflows.

The older Markdown note ingestion path remains in the repository for reference, but it is deprecated and no longer the recommended workflow.

### Project Structure
```
Literature/
├── README.md                    # Updated with quick start guide
├── config.example.yaml          # Configuration template
├── requirements.txt             # Python dependencies
├── schema/
│   └── 001_initial.sql         # SQLite + FTS5 schema
├── mcp_server/
│   ├── database.py             # Database operations
│   ├── bibtex_ingestion.py     # BibTeX parsing, PDF matching, and indexing
│   └── server.py               # MCP server with tools
├── ingest/
│   └── ingest_bibtex.py        # Standalone BibTeX ingestion script
└── tests/
    └── test_basic.py           # Basic unit tests
```

### Features Implemented

1. **Database Layer** (`database.py`)
   - SQLite with FTS5 full-text search
   - Documents table with metadata
   - Chunks table for searchable content
   - Automatic FTS index synchronization via triggers
   - CRUD operations for documents and chunks

2. **Ingestion Pipeline** (`bibtex_ingestion.py`)
   - BibTeXParser: Parses Mendeley-exported BibTeX entries
   - PDFExtractor: Uses PyMuPDF to extract text with page locators
   - NoteChunker: Chunks `annote` content by paragraphs
   - BibTeXIngester: Orchestrates parsing, PDF matching, and indexing

3. **MCP Server** (`server.py`)
   - `kb_search`: Full-text search with filters
   - `kb_get_document`: Retrieve document metadata
   - `kb_get_note`: Get full note content
   - `kb_get_pdf_text`: Extract PDF pages
   - `kb_refresh`: Re-scan and update index
   - `kb_stats`: Get database statistics

4. **Configuration**
   - YAML config for PDF root, BibTeX path, database path, and chunking settings
   - Command-line overrides for all paths

### Next Steps to Use

1. **Install dependencies** (when pip is available):
   ```bash
   pip install pyyaml pymupdf
   ```

2. **Set up your library structure**:
   ```
   ~/Documents/Papers/2023/Nature/Some Paper Title.pdf
   ~/Documents/My_Collection.bib
   ```

3. **Export your library as BibTeX from Mendeley**:
   - Ensure the export includes metadata such as title, year, venue, DOI, authors
   - Notes should be present in the `annote` field when available

4. **Run ingestion**:
   ```bash
   python ingest/ingest_bibtex.py --config config.yaml --stats
   ```

5. **Start MCP server** (for OpenClaw integration):
   ```bash
   python mcp_server/server.py
   ```

### Architecture Decisions

- **SQLite + FTS5**: Lightweight, no external services needed
- **BibTeX as source of truth**: Metadata and notes come from one export
- **Filename/title matching**: Locates local PDFs without changing the library layout
- **Page locators**: Enables precise citations

### Future Enhancements (Phase 2+)

- Semantic search with embeddings
- Hybrid scoring (BM25 + semantic)
- Incremental refresh with file modification times
- Better PDF extraction for complex layouts
- Note editing via MCP tools
