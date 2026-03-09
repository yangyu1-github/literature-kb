#!/usr/bin/env python3
"""
MCP Server for Literature Knowledge Base.
Exposes tools for searching and retrieving literature.
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import our modules
from database import LiteratureDatabase
from ingestion import LibraryIngester
from bibtex_ingestion import BibTeXIngester

# MCP SDK
from mcp.server import Server
from mcp.types import Tool, TextContent


class LiteratureMCPServer:
    """MCP server for literature knowledge base."""
    
    def __init__(self, config_path: Optional[str] = None, enable_semantic: bool = True):
        self.config = self._load_config(config_path)
        self.db = LiteratureDatabase(self.config['index_path'])
        self.server = Server("literature-kb")
        
        # Phase 2: Semantic search
        self.enable_semantic = enable_semantic
        self.hybrid_searcher = None
        self.vector_store = None
        self.embedding_generator = None
        
        if enable_semantic:
            self._init_semantic_search()
        
        self._setup_tools()
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        defaults = {
            'pdf_root': '/home/azurin/Documents/Papers',
            'notes_root': '/home/azurin/Documents/Notes',
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
    
    def _init_semantic_search(self):
        """Initialize semantic search components."""
        try:
            from semantic_search import VectorStore, EmbeddingGenerator, HybridSearcher
            
            # Get vector store path from config or default
            vector_path = self.config.get('vector_path', 
                str(Path(self.config['index_path']).parent / 'chroma'))
            
            self.vector_store = VectorStore(vector_path)
            self.embedding_generator = EmbeddingGenerator(
                model_name=self.config.get('embedding_model')
            )
            
            # Create hybrid searcher with configurable semantic weight
            semantic_weight = self.config.get('semantic_weight', 0.5)
            self.hybrid_searcher = HybridSearcher(
                self.db, self.vector_store, self.embedding_generator,
                semantic_weight=semantic_weight
            )
            
            print(f"Semantic search enabled (weight: {semantic_weight})")
            print(f"  Vector store: {vector_path}")
            print(f"  Embeddings: {self.vector_store.count()} chunks indexed")
            
        except ImportError as e:
            print(f"Warning: Could not enable semantic search: {e}")
            self.enable_semantic = False
            self.hybrid_searcher = None
    
    def _setup_tools(self):
        """Register MCP tools."""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="kb_search",
                    description="Search the literature knowledge base for relevant passages",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query text"
                            },
                            "filters": {
                                "type": "object",
                                "properties": {
                                    "year": {"type": "integer"},
                                    "venue": {"type": "string"},
                                    "source_type": {"type": "string", "enum": ["pdf", "note"]}
                                }
                            },
                            "k": {
                                "type": "integer",
                                "default": 20,
                                "description": "Number of results to return"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="kb_get_document",
                    description="Get document metadata and file paths",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key (DOI or derived key)"
                            }
                        },
                        "required": ["doc_key"]
                    }
                ),
                Tool(
                    name="kb_get_note",
                    description="Get full note content for a document",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key"
                            },
                            "range": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "integer"},
                                    "end": {"type": "integer"}
                                }
                            }
                        },
                        "required": ["doc_key"]
                    }
                ),
                Tool(
                    name="kb_get_pdf_text",
                    description="Get extracted PDF text for specific pages",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_key": {
                                "type": "string",
                                "description": "Document key"
                            },
                            "page_range": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "integer"},
                                    "end": {"type": "integer"}
                                },
                                "required": ["start", "end"]
                            }
                        },
                        "required": ["doc_key", "page_range"]
                    }
                ),
                Tool(
                    name="kb_refresh",
                    description="Refresh the knowledge base index",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "scan": {
                                "type": "object",
                                "properties": {
                                    "pdf_root": {"type": "string"},
                                    "notes_root": {"type": "string"}
                                }
                            }
                        }
                    }
                ),
                Tool(
                    name="kb_stats",
                    description="Get knowledge base statistics",
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
            elif name == "kb_refresh":
                return await self._handle_refresh(arguments)
            elif name == "kb_stats":
                return await self._handle_stats(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    async def _handle_search(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_search tool with optional hybrid search."""
        query = arguments.get('query', '')
        filters = arguments.get('filters', {})
        k = arguments.get('k', 20)
        use_semantic = arguments.get('semantic', self.enable_semantic)
        
        # Use hybrid search if enabled and requested
        if use_semantic and self.hybrid_searcher:
            results = self.hybrid_searcher.search(query, filters, k=k)
            
            formatted = {
                "hits": [
                    {
                        "doc_key": r['doc_key'],
                        "title": r['title'],
                        "year": r['year'],
                        "venue": r['venue'],
                        "doi": r['doi'],
                        "source_type": r['source_type'],
                        "hybrid_score": round(r['hybrid_score'], 4),
                        "bm25_score": round(r['bm25_score'], 4),
                        "semantic_score": round(r['semantic_score'], 4),
                        "snippet": r['snippet'][:500] + "..." if len(r['snippet']) > 500 else r['snippet'],
                        "locator": r['locator'],
                        "pdf_path": r['pdf_path'],
                        "note_path": r['note_path']
                    }
                    for r in results
                ]
            }
        else:
            # Fall back to BM25 only
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
        note_content = self.db.get_note_content(doc_key)
        
        if note_content:
            # Handle range if specified
            range_spec = arguments.get('range', {})
            if 'start' in range_spec and 'end' in range_spec:
                start = range_spec['start']
                end = range_spec['end']
                note_content = note_content[start:end]
            
            return [TextContent(type="text", text=note_content)]
        else:
            return [TextContent(type="text", text="Note not found or no note available for this document")]
    
    async def _handle_get_pdf_text(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_get_pdf_text tool."""
        import fitz
        
        doc_key = arguments.get('doc_key', '')
        page_range = arguments.get('page_range', {})
        start_page = page_range.get('start', 1)
        end_page = page_range.get('end', 1)
        
        doc = self.db.get_document(doc_key)
        if not doc or not doc['pdf_path']:
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
    
    async def _handle_refresh(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_refresh tool with optional semantic indexing."""
        scan_config = arguments.get('scan', {})
        
        pdf_root = scan_config.get('pdf_root', self.config['pdf_root'])
        
        # Check if using BibTeX mode
        if 'bibtex_path' in self.config:
            bibtex_path = scan_config.get('bibtex_path', self.config['bibtex_path'])
            
            ingester = BibTeXIngester(
                self.db,
                pdf_root=pdf_root,
                bibtex_path=bibtex_path,
                pdf_chunk_size=self.config['chunking']['pdf_chunk_chars'],
                note_chunk_size=self.config['chunking']['note_chunk_chars']
            )
        else:
            # Deprecated legacy Markdown-note mode
            notes_root = scan_config.get('notes_root', self.config['notes_root'])
            
            if self.enable_semantic and self.hybrid_searcher:
                from semantic_search import SemanticIngester
                
                ingester = SemanticIngester(
                    self.db,
                    self.vector_store,
                    self.embedding_generator,
                    pdf_root=pdf_root,
                    notes_root=notes_root,
                    pdf_chunk_size=self.config['chunking']['pdf_chunk_chars'],
                    note_chunk_size=self.config['chunking']['note_chunk_chars']
                )
            else:
                ingester = LibraryIngester(
                    self.db,
                    pdf_root=pdf_root,
                    notes_root=notes_root,
                    pdf_chunk_size=self.config['chunking']['pdf_chunk_chars'],
                    note_chunk_size=self.config['chunking']['note_chunk_chars']
                )
        
        stats = ingester.scan_and_ingest()
        
        result = {
            "indexed": stats['indexed'],
            "failed": stats['failed'],
            "skipped": stats['skipped']
        }
        
        if self.enable_semantic and hasattr(self, 'vector_store') and self.vector_store:
            result['vector_chunks'] = self.vector_store.count()
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async def _handle_stats(self, arguments: Dict) -> List[TextContent]:
        """Handle kb_stats tool."""
        stats = self.db.get_stats()
        
        if self.enable_semantic and self.vector_store:
            stats['vector_chunks'] = self.vector_store.count()
        
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
    
    parser = argparse.ArgumentParser(description="Literature Knowledge Base MCP Server")
    parser.add_argument("--config", "-c", help="Path to config file")
    parser.add_argument("--no-semantic", action="store_true", 
                       help="Disable semantic search (BM25 only)")
    args = parser.parse_args()
    
    server = LiteratureMCPServer(config_path=args.config, 
                                 enable_semantic=not args.no_semantic)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
