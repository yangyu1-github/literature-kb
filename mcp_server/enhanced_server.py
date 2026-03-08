#!/usr/bin/env python3
"""
Enhanced MCP Server for Literature Knowledge Base (Phase 3).
Exposes tools for searching, retrieving, and editing literature.
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import our modules
from enhanced_database import EnhancedLiteratureDatabase
from enhanced_bibtex_ingestion import EnhancedBibTeXIngester

# MCP SDK
from mcp.server import Server
from mcp.types import Tool, TextContent


class EnhancedLiteratureMCPServer:
    """Enhanced MCP server with Phase 3 features."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self.db = EnhancedLiteratureDatabase(self.config['index_path'])
        self.server = Server("literature-kb-enhanced")
        
        self._setup_tools()
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        defaults = {
            'pdf_root': '/home/azurin/.openclaw/workspace/project/Yang_Document/LIB_ROOT',
            'bibtex_path': '/home/azurin/.openclaw/workspace/project/Yang_Document/My_Collection.bib',
            'index_path': '/home/azurin/.openclaw/workspace/project/Yang_Document/Literature/kb/index.sqlite',
            'max_pdf_mb': 200,
            'chunking': {
                'pdf_chunk_chars': 2000,
                'note_chunk_chars': 1500
            }
        }
        
        if config_path and Path(config_path).exists():
            import yaml
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                defaults.update(user_config)
        
        return defaults
    
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
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "k": {
                                "type": "integer",
                                "description": "Number of results",
                                "default": 10
                            },
                            "filters": {
                                "type": "object",
                                "description": "Optional filters (year, venue, source_type)",
                                "default": {}
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="kb_get_document",
                    description="Get document metadata by key",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI"
                            }
                        },
                        "required": ["doc_key"]
                    }
                ),
                Tool(
                    name="kb_get_note",
                    description="Get note content for a document",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI"
                            }
                        },
                        "required": ["doc_key"]
                    }
                ),
                Tool(
                    name="kb_get_pdf_text",
                    description="Extract text from PDF pages",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI"
                            },
                            "page_range": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "integer"},
                                    "end": {"type": "integer"}
                                },
                                "description": "Page range to extract"
                            }
                        },
                        "required": ["doc_key"]
                    }
                ),
                Tool(
                    name="kb_update_note",
                    description="Update note content for a document (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI"
                            },
                            "content": {
                                "type": "string",
                                "description": "New note content"
                            }
                        },
                        "required": ["doc_key", "content"]
                    }
                ),
                Tool(
                    name="kb_get_note_history",
                    description="Get edit history for a document's notes (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key or DOI"
                            }
                        },
                        "required": ["doc_key"]
                    }
                ),
                Tool(
                    name="kb_find_duplicates",
                    description="Find detected duplicate entries (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="kb_check_duplicate",
                    description="Check if a paper is already in the database (Phase 3)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doi": {
                                "type": "string",
                                "description": "DOI to check"
                            },
                            "title": {
                                "type": "string",
                                "description": "Title to check (optional)"
                            },
                            "year": {
                                "type": "integer",
                                "description": "Year to check (optional)"
                            }
                        },
                        "required": ["doi"]
                    }
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
                                "default": False
                            },
                            "include_duplicates": {
                                "type": "boolean",
                                "description": "Include suspected duplicates",
                                "default": False
                            }
                        }
                    }
                ),
                Tool(
                    name="kb_stats",
                    description="Get database statistics",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            if name == "kb_search":
                return await self._handle_search(arguments)
            elif name == "kb_get_document":
                return await self._handle_get_document(arguments)
            elif name == "kb_get_note":
                return await self._handle_get_note(arguments)
            elif name == "kb_get_pdf_text":
                return await self._handle_get_pdf_text(arguments)
            elif name == "kb_update_note":
                return await self._handle_update_note(arguments)
            elif name == "kb_get_note_history":
                return await self._handle_get_note_history(arguments)
            elif name == "kb_find_duplicates":
                return await self._handle_find_duplicates(arguments)
            elif name == "kb_check_duplicate":
                return await self._handle_check_duplicate(arguments)
            elif name == "kb_refresh":
                return await self._handle_refresh(arguments)
            elif name == "kb_stats":
                return await self._handle_stats(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    async def _handle_search(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_search tool."""
        query = arguments.get('query', '')
        filters = arguments.get('filters', {})
        k = arguments.get('k', 10)
        
        results = self.db.search_chunks(query, filters, k)
        
        formatted = {
            "hits": [
                {
                    "doc_key": r['doc_key'],
                    "title": r['title'],
                    "year": r['year'],
                    "venue": r['venue'],
                    "doi": r['doi'],
                    "source_type": r['source_type'],
                    "score": r['score'],
                    "snippet": r['snippet'][:500] + "..." if len(r['snippet']) > 500 else r['snippet'],
                    "locator": r['locator'],
                    "pdf_path": r['pdf_path'],
                    "note_path": r['note_path']
                }
                for r in results
            ]
        }
        
        return [TextContent(type="text", text=json.dumps(formatted, indent=2))]
    
    async def _handle_get_document(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_document tool."""
        doc_key = arguments.get('doc_key', '')
        doc = self.db.get_document(doc_key)
        
        if doc:
            return [TextContent(type="text", text=json.dumps(doc, indent=2))]
        else:
            return [TextContent(type="text", text=json.dumps({"error": "Document not found"}))]
    
    async def _handle_get_note(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_note tool."""
        doc_key = arguments.get('doc_key', '')
        
        # Get note chunks from database
        import sqlite3
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.execute(
                'SELECT content FROM chunks WHERE doc_key = ? AND source_type = "note" ORDER BY chunk_index',
                (doc_key,)
            )
            chunks = [row[0] for row in cursor.fetchall()]
        
        if chunks:
            content = '\n\n'.join(chunks)
            return [TextContent(type="text", content)]
        else:
            return [TextContent(type="text", text="No notes found for this document")]
    
    async def _handle_get_pdf_text(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_pdf_text tool."""
        import fitz
        
        doc_key = arguments.get('doc_key', '')
        page_range = arguments.get('page_range', {})
        start_page = page_range.get('start', 1)
        end_page = page_range.get('end', 1)
        
        doc = self.db.get_document(doc_key)
        if not doc or not doc.get('pdf_path'):
            return [TextContent(type="text", text=json.dumps({"error": "PDF not found for this document"}))]
        
        pdf_path = Path(doc['pdf_path'])
        if not pdf_path.exists():
            return [TextContent(type="text", text=json.dumps({"error": f"PDF file not found: {pdf_path}"}))]
        
        try:
            pdf_doc = fitz.open(pdf_path)
            pages = []
            
            for page_num in range(start_page - 1, min(end_page, len(pdf_doc))):
                page = pdf_doc[page_num]
                pages.append({
                    "page": page_num + 1,
                    "text": page.get_text()
                })
            
            pdf_doc.close()
            
            result = {
                "doc_key": doc_key,
                "pdf_path": str(pdf_path),
                "pages": pages
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    
    async def _handle_update_note(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_update_note tool (Phase 3)."""
        doc_key = arguments.get('doc_key', '')
        content = arguments.get('content', '')
        
        success = self.db.update_note_content(doc_key, content)
        
        if success:
            result = {
                "success": True,
                "doc_key": doc_key,
                "message": "Note updated successfully"
            }
        else:
            result = {
                "success": False,
                "doc_key": doc_key,
                "error": "Failed to update note"
            }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async def _handle_get_note_history(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_note_history tool (Phase 3)."""
        doc_key = arguments.get('doc_key', '')
        
        history = self.db.get_note_edit_history(doc_key)
        
        formatted = {
            "doc_key": doc_key,
            "edit_count": len(history),
            "edits": [
                {
                    "edited_at": h['edited_at'],
                    "old_content_preview": h['old_content'][:200] + "..." if h['old_content'] and len(h['old_content']) > 200 else h['old_content'],
                    "new_content_preview": h['new_content'][:200] + "..." if h['new_content'] and len(h['new_content']) > 200 else h['new_content']
                }
                for h in history
            ]
        }
        
        return [TextContent(type="text", text=json.dumps(formatted, indent=2))]
    
    async def _handle_find_duplicates(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_find_duplicates tool (Phase 3)."""
        duplicates = self.db.get_duplicates()
        
        formatted = {
            "duplicate_count": len(duplicates),
            "duplicates": [
                {
                    "canonical_doc_key": d['canonical_doc_key'],
                    "canonical_title": d.get('canonical_title', 'Unknown'),
                    "duplicate_doc_key": d['duplicate_doc_key'],
                    "duplicate_title": d.get('duplicate_title', 'Unknown'),
                    "reason": d['duplicate_source'],
                    "detected_at": d['detected_at']
                }
                for d in duplicates[:20]  # Limit to 20
            ]
        }
        
        return [TextContent(type="text", text=json.dumps(formatted, indent=2))]
    
    async def _handle_check_duplicate(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_check_duplicate tool (Phase 3)."""
        doi = arguments.get('doi', '')
        title = arguments.get('title', '')
        year = arguments.get('year')
        
        # Check by DOI
        existing = self.db.find_duplicate_by_doi(doi)
        
        if not existing and title:
            # Check by title + year
            potential = self.db.find_duplicates_by_title_year(title, year)
            if potential:
                existing = potential[0]
        
        if existing:
            result = {
                "is_duplicate": True,
                "existing_document": {
                    "doc_key": existing['doc_key'],
                    "title": existing['title'],
                    "year": existing['year'],
                    "doi": existing.get('doi')
                }
            }
        else:
            result = {
                "is_duplicate": False,
                "message": "No duplicate found"
            }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async def _handle_refresh(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_refresh tool with Phase 3 enhancements."""
        full_refresh = arguments.get('full_refresh', False)
        include_duplicates = arguments.get('include_duplicates', False)
        
        # Create ingester
        ingester = EnhancedBibTeXIngester(
            self.db,
            pdf_root=self.config['pdf_root'],
            bibtex_path=self.config['bibtex_path'],
            pdf_chunk_size=self.config['chunking']['pdf_chunk_chars'],
            note_chunk_size=self.config['chunking']['note_chunk_chars']
        )
        
        stats = ingester.scan_and_ingest(
            incremental=not full_refresh,
            skip_duplicates=not include_duplicates
        )
        
        result = {
            "indexed": stats['indexed'],
            "failed": stats['failed'],
            "skipped": stats['skipped'],
            "duplicates_detected": stats['duplicates_detected'],
            "pdfs_matched": stats['pdf_matched']
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async def _handle_stats(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_stats tool."""
        stats = self.db.get_stats()
        
        return [TextContent(type="text", text=json.dumps(stats, indent=2))]
    
    async def run(self):
        """Run the MCP server."""
        from mcp.server.stdio import stdio_server
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Literature Knowledge Base MCP Server (Phase 3)")
    parser.add_argument("--config", "-c", help="Path to config file")
    args = parser.parse_args()
    
    server = EnhancedLiteratureMCPServer(config_path=args.config)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
