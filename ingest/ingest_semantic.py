#!/usr/bin/env python3
"""
Semantic ingestion script for Literature Knowledge Base.
Builds both BM25 (SQLite FTS5) and semantic (ChromaDB) indexes.
Usage: python ingest_semantic.py [--config config.yaml] [--pdf-root PATH] [--notes-root PATH]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'mcp_server'))

from database import LiteratureDatabase
from semantic_search import SemanticIngester, VectorStore, EmbeddingGenerator
import yaml


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest literature library with semantic embeddings"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml file"
    )
    parser.add_argument(
        "--pdf-root",
        help="Root directory containing PDF files"
    )
    parser.add_argument(
        "--notes-root",
        help="Root directory containing note files (*.mendeley.md)"
    )
    parser.add_argument(
        "--index-path",
        help="Path to SQLite database file"
    )
    parser.add_argument(
        "--vector-path",
        help="Path to ChromaDB vector store"
    )
    parser.add_argument(
        "--model",
        help="Embedding model name (e.g., all-MiniLM-L6-v2)"
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Show database statistics after ingestion"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset vector store before ingestion"
    )
    
    args = parser.parse_args()
    
    # Load config or use defaults
    config = {
        'pdf_root': '/home/azurin/Documents/Papers',
        'notes_root': '/home/azurin/Documents/Notes',
        'index_path': str(Path(__file__).parent / 'kb' / 'index.sqlite'),
        'vector_path': str(Path(__file__).parent / 'kb' / 'chroma'),
        'semantic_search': {
            'embedding_model': 'all-MiniLM-L6-v2'
        },
        'chunking': {
            'pdf_chunk_chars': 2000,
            'note_chunk_chars': 1500
        }
    }
    
    if args.config:
        user_config = load_config(args.config)
        config.update(user_config)
    
    # Override with command line args
    if args.pdf_root:
        config['pdf_root'] = args.pdf_root
    if args.notes_root:
        config['notes_root'] = args.notes_root
    if args.index_path:
        config['index_path'] = args.index_path
    if args.vector_path:
        config['vector_path'] = args.vector_path
    if args.model:
        config['semantic_search']['embedding_model'] = args.model
    
    # Validate paths
    pdf_root = Path(config['pdf_root'])
    notes_root = Path(config['notes_root'])
    
    if not pdf_root.exists():
        print(f"Warning: PDF root does not exist: {pdf_root}")
    if not notes_root.exists():
        print(f"Warning: Notes root does not exist: {notes_root}")
    
    # Initialize database
    print(f"Initializing database: {config['index_path']}")
    db = LiteratureDatabase(config['index_path'])
    
    # Initialize vector store
    print(f"Initializing vector store: {config['vector_path']}")
    vector_store = VectorStore(config['vector_path'])
    
    if args.reset:
        print("Resetting vector store...")
        vector_store.reset()
    
    # Initialize embedding generator
    model_name = config['semantic_search'].get('embedding_model', 'all-MiniLM-L6-v2')
    print(f"Loading embedding model: {model_name}")
    embedding_generator = EmbeddingGenerator(model_name=model_name)
    
    # Create semantic ingester
    ingester = SemanticIngester(
        db,
        vector_store,
        embedding_generator,
        pdf_root=config['pdf_root'],
        notes_root=config['notes_root'],
        pdf_chunk_size=config['chunking']['pdf_chunk_chars'],
        note_chunk_size=config['chunking']['note_chunk_chars']
    )
    
    # Run ingestion
    print(f"\nScanning for notes in: {config['notes_root']}")
    print(f"Looking for PDFs in: {config['pdf_root']}\n")
    
    stats = ingester.scan_and_ingest()
    
    print(f"\n{'='*50}")
    print("Ingestion complete!")
    print(f"  Indexed documents: {stats['indexed']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Skipped: {stats['skipped']}")
    
    if args.stats:
        db_stats = db.get_stats()
        print(f"\nDatabase statistics:")
        print(f"  Documents: {db_stats['documents']}")
        print(f"  Total chunks: {db_stats['chunks']}")
        print(f"  PDF chunks: {db_stats['pdf_chunks']}")
        print(f"  Note chunks: {db_stats['note_chunks']}")
        print(f"  Vector embeddings: {vector_store.count()}")
    
    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
