#!/usr/bin/env python3
"""
Enhanced MCP Server for Literature Knowledge Base.

Phase 3 adds duplicate detection, incremental refresh, and note history.
Phase 4 adds document browsing, citation export, and related-paper discovery.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from enhanced_bibtex_ingestion import EnhancedBibTeXIngester
from enhanced_database import EnhancedLiteratureDatabase
from mcp.server import Server
from mcp.types import TextContent, Tool


class EnhancedLiteratureMCPServer:
    """Enhanced MCP server with Phase 3 and Phase 4 features."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.db = EnhancedLiteratureDatabase(self.config["index_path"])
        self.server = Server("literature-kb-enhanced")
        self._setup_tools()

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        defaults = {
            "pdf_root": "/home/azurin/.openclaw/workspace/project/Yang_Document/LIB_ROOT",
            "bibtex_path": "/home/azurin/.openclaw/workspace/project/Yang_Document/My_Collection.bib",
            "index_path": "/home/azurin/.openclaw/workspace/project/Yang_Document/Literature/kb/index.sqlite",
            "max_pdf_mb": 200,
            "chunking": {"pdf_chunk_chars": 2000, "note_chunk_chars": 1500},
        }

        if config_path and Path(config_path).exists():
            import yaml

            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f) or {}
                defaults.update(user_config)

        return defaults

    def _text(self, payload: Any) -> List[TextContent]:
        """Return a JSON payload as MCP text content."""
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, indent=2)
        return [TextContent(type="text", text=text)]

    def _setup_tools(self):
        """Set up MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="kb_search",
                    description="Search the literature knowledge base",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "k": {
                                "type": "integer",
                                "description": "Number of results",
                                "default": 10,
                            },
                            "filters": {
                                "type": "object",
                                "description": "Optional filters (year, venue, source_type)",
                                "default": {},
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="kb_get_document",
                    description="Get document metadata by key",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            }
                        },
                        "required": ["doc_key"],
                    },
                ),
                Tool(
                    name="kb_get_note",
                    description="Get note content for a document",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            }
                        },
                        "required": ["doc_key"],
                    },
                ),
                Tool(
                    name="kb_get_pdf_text",
                    description="Extract text from PDF pages",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            },
                            "page_range": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "integer"},
                                    "end": {"type": "integer"},
                                },
                                "description": "Page range to extract",
                            },
                        },
                        "required": ["doc_key"],
                    },
                ),
                Tool(
                    name="kb_update_note",
                    description="Update note content for a document (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            },
                            "content": {
                                "type": "string",
                                "description": "New note content",
                            },
                        },
                        "required": ["doc_key", "content"],
                    },
                ),
                Tool(
                    name="kb_get_note_history",
                    description="Get edit history for a document's notes (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            }
                        },
                        "required": ["doc_key"],
                    },
                ),
                Tool(
                    name="kb_find_duplicates",
                    description="Find detected duplicate entries (Phase 3)",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="kb_check_duplicate",
                    description="Check if a paper is already in the database (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doi": {"type": "string", "description": "DOI to check"},
                            "title": {
                                "type": "string",
                                "description": "Title to check (optional)",
                            },
                            "year": {
                                "type": "integer",
                                "description": "Year to check (optional)",
                            },
                        },
                        "required": ["doi"],
                    },
                ),
                Tool(
                    name="kb_refresh",
                    description="Refresh the index with incremental update (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "full_refresh": {
                                "type": "boolean",
                                "description": "Force full refresh",
                                "default": False,
                            },
                            "include_duplicates": {
                                "type": "boolean",
                                "description": "Include suspected duplicates",
                                "default": False,
                            },
                        },
                    },
                ),
                Tool(
                    name="kb_list_documents",
                    description="Browse the indexed library by metadata filters (Phase 4)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "filters": {
                                "type": "object",
                                "description": "Optional filters (year, venue, author, tag, title_contains, has_pdf)",
                                "default": {},
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of documents to return",
                                "default": 20,
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Pagination offset",
                                "default": 0,
                            },
                        },
                    },
                ),
                Tool(
                    name="kb_get_citation",
                    description="Format a paper citation for writing workflows (Phase 4)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            },
                            "style": {
                                "type": "string",
                                "description": "Citation style: apa, short, or bibtex",
                                "default": "apa",
                            },
                        },
                        "required": ["doc_key"],
                    },
                ),
                Tool(
                    name="kb_find_related",
                    description="Find related papers using shared metadata (Phase 4)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of related papers to return",
                                "default": 10,
                            },
                        },
                        "required": ["doc_key"],
                    },
                ),
                Tool(
                    name="kb_stats",
                    description="Get database statistics",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            if name == "kb_search":
                return await self._handle_search(arguments)
            if name == "kb_get_document":
                return await self._handle_get_document(arguments)
            if name == "kb_get_note":
                return await self._handle_get_note(arguments)
            if name == "kb_get_pdf_text":
                return await self._handle_get_pdf_text(arguments)
            if name == "kb_update_note":
                return await self._handle_update_note(arguments)
            if name == "kb_get_note_history":
                return await self._handle_get_note_history(arguments)
            if name == "kb_find_duplicates":
                return await self._handle_find_duplicates(arguments)
            if name == "kb_check_duplicate":
                return await self._handle_check_duplicate(arguments)
            if name == "kb_refresh":
                return await self._handle_refresh(arguments)
            if name == "kb_list_documents":
                return await self._handle_list_documents(arguments)
            if name == "kb_get_citation":
                return await self._handle_get_citation(arguments)
            if name == "kb_find_related":
                return await self._handle_find_related(arguments)
            if name == "kb_stats":
                return await self._handle_stats(arguments)
            return self._text({"error": f"Unknown tool: {name}"})

    async def _handle_search(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_search tool."""
        query = arguments.get("query", "")
        filters = arguments.get("filters", {})
        k = arguments.get("k", 10)
        results = self.db.search_chunks(query, filters, k)

        return self._text(
            {
                "hits": [
                    {
                        "doc_key": result["doc_key"],
                        "title": result["title"],
                        "year": result["year"],
                        "venue": result["venue"],
                        "doi": result["doi"],
                        "citation": self.db.get_citation(result["doc_key"], style="short")["citation"],
                        "source_type": result["source_type"],
                        "score": result["score"],
                        "snippet": result["snippet"][:500] + "..."
                        if len(result["snippet"]) > 500
                        else result["snippet"],
                        "locator": result["locator"],
                        "pdf_path": result["pdf_path"],
                        "note_path": result["note_path"],
                    }
                    for result in results
                ]
            }
        )

    async def _handle_get_document(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_document tool."""
        doc = self.db.get_document(arguments.get("doc_key", ""))
        return self._text(doc or {"error": "Document not found"})

    async def _handle_get_note(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_note tool."""
        doc_key = arguments.get("doc_key", "")
        note_content = self.db.get_note_content(doc_key)
        if note_content:
            return self._text({"doc_key": doc_key, "content": note_content})
        return self._text({"error": "No notes found for this document"})

    async def _handle_get_pdf_text(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_pdf_text tool."""
        import fitz

        doc_key = arguments.get("doc_key", "")
        page_range = arguments.get("page_range", {})
        start_page = page_range.get("start", 1)
        end_page = page_range.get("end", 1)

        doc = self.db.get_document(doc_key)
        if not doc or not doc.get("pdf_path"):
            return self._text({"error": "PDF not found for this document"})

        pdf_path = Path(doc["pdf_path"])
        if not pdf_path.exists():
            return self._text({"error": f"PDF file not found: {pdf_path}"})

        try:
            pdf_doc = fitz.open(pdf_path)
            pages = []
            for page_num in range(start_page - 1, min(end_page, len(pdf_doc))):
                page = pdf_doc[page_num]
                pages.append({"page": page_num + 1, "text": page.get_text()})
            pdf_doc.close()
            return self._text({"doc_key": doc_key, "pdf_path": str(pdf_path), "pages": pages})
        except Exception as e:
            return self._text({"error": str(e)})

    async def _handle_update_note(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_update_note tool (Phase 3)."""
        doc_key = arguments.get("doc_key", "")
        content = arguments.get("content", "")
        success = self.db.update_note_content(doc_key, content)
        if success:
            return self._text(
                {"success": True, "doc_key": doc_key, "message": "Note updated successfully"}
            )
        return self._text({"success": False, "doc_key": doc_key, "error": "Failed to update note"})

    async def _handle_get_note_history(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_note_history tool (Phase 3)."""
        doc_key = arguments.get("doc_key", "")
        history = self.db.get_note_edit_history(doc_key)
        return self._text(
            {
                "doc_key": doc_key,
                "edit_count": len(history),
                "edits": [
                    {
                        "edited_at": edit["edited_at"],
                        "old_content_preview": (
                            edit["old_content"][:200] + "..."
                            if edit["old_content"] and len(edit["old_content"]) > 200
                            else edit["old_content"]
                        ),
                        "new_content_preview": (
                            edit["new_content"][:200] + "..."
                            if edit["new_content"] and len(edit["new_content"]) > 200
                            else edit["new_content"]
                        ),
                    }
                    for edit in history
                ],
            }
        )

    async def _handle_find_duplicates(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_find_duplicates tool (Phase 3)."""
        duplicates = self.db.get_duplicates()
        return self._text(
            {
                "duplicate_count": len(duplicates),
                "duplicates": [
                    {
                        "canonical_doc_key": dup["canonical_doc_key"],
                        "canonical_title": dup.get("canonical_title", "Unknown"),
                        "duplicate_doc_key": dup["duplicate_doc_key"],
                        "duplicate_title": dup.get("duplicate_title", "Unknown"),
                        "reason": dup["duplicate_source"],
                        "detected_at": dup["detected_at"],
                    }
                    for dup in duplicates[:20]
                ],
            }
        )

    async def _handle_check_duplicate(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_check_duplicate tool (Phase 3)."""
        doi = arguments.get("doi", "")
        title = arguments.get("title", "")
        year = arguments.get("year")
        existing = self.db.find_duplicate_by_doi(doi)

        if not existing and title:
            potential = self.db.find_duplicates_by_title_year(title, year)
            if potential:
                existing = potential[0]

        if existing:
            return self._text(
                {
                    "is_duplicate": True,
                    "existing_document": {
                        "doc_key": existing["doc_key"],
                        "title": existing["title"],
                        "year": existing["year"],
                        "doi": existing.get("doi"),
                    },
                }
            )
        return self._text({"is_duplicate": False, "message": "No duplicate found"})

    async def _handle_refresh(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_refresh tool."""
        full_refresh = arguments.get("full_refresh", False)
        include_duplicates = arguments.get("include_duplicates", False)
        ingester = EnhancedBibTeXIngester(
            self.db,
            pdf_root=self.config["pdf_root"],
            bibtex_path=self.config["bibtex_path"],
            pdf_chunk_size=self.config["chunking"]["pdf_chunk_chars"],
            note_chunk_size=self.config["chunking"]["note_chunk_chars"],
        )
        stats = ingester.scan_and_ingest(
            incremental=not full_refresh, skip_duplicates=not include_duplicates
        )
        return self._text(
            {
                "indexed": stats["indexed"],
                "failed": stats["failed"],
                "skipped": stats["skipped"],
                "duplicates_detected": stats["duplicates_detected"],
                "pdfs_matched": stats["pdf_matched"],
            }
        )

    async def _handle_list_documents(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_list_documents tool (Phase 4)."""
        filters = arguments.get("filters", {})
        limit = arguments.get("limit", 20)
        offset = arguments.get("offset", 0)
        documents = self.db.list_documents(filters=filters, limit=limit, offset=offset)
        return self._text(
            {
                "count": len(documents),
                "limit": limit,
                "offset": offset,
                "documents": documents,
            }
        )

    async def _handle_get_citation(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_citation tool (Phase 4)."""
        doc_key = arguments.get("doc_key", "")
        style = arguments.get("style", "apa")
        citation = self.db.get_citation(doc_key, style=style)
        return self._text(citation or {"error": "Document not found"})

    async def _handle_find_related(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_find_related tool (Phase 4)."""
        doc_key = arguments.get("doc_key", "")
        limit = arguments.get("limit", 10)
        document = self.db.get_document(doc_key)
        if not document:
            return self._text({"error": "Document not found"})

        related = self.db.find_related_documents(doc_key, limit=limit)
        return self._text(
            {
                "doc_key": doc_key,
                "title": document["title"],
                "related_count": len(related),
                "related": related,
            }
        )

    async def _handle_stats(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_stats tool."""
        return self._text(self.db.get_stats())

    async def run(self):
        """Run the MCP server."""
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced Literature Knowledge Base MCP Server (Phase 4)"
    )
    parser.add_argument("--config", "-c", help="Path to config file")
    args = parser.parse_args()

    server = EnhancedLiteratureMCPServer(config_path=args.config)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
