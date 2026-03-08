#!/usr/bin/env python3
"""
Standalone ingestion script for Literature Knowledge Base (BibTeX version).
Usage: python ingest_bibtex.py [--config config.yaml] [--pdf-root PATH] [--bibtex PATH]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'mcp_server'))

from database import LiteratureDatabase
from bibtex_ingestion import BibTeXIngester
import yaml


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest literature library from BibTeX into knowledge base"
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
        "--bibtex",
        help="Path to BibTeX file with annotations"
    )
    parser.add_argument(
        "--index-path",
        help="Path to SQLite database file"
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Show database statistics after ingestion"
    )
    
    args = parser.parse_args()
    
    # Load config or use defaults
    config = {
        'pdf_root': '/home/azurin/.openclaw/workspace/project/Yang_Document/LIB_ROOT',
        'bibtex_path': '/home/azurin/.openclaw/workspace/project/Yang_Document/My_Collection.bib',
        'index_path': str(Path(__file__).parent / 'kb' / 'index.sqlite'),
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
    if args.bibtex:
        config['bibtex_path'] = args.bibtex
    if args.index_path:
        config['index_path'] = args.index_path
    
    # Validate paths
    pdf_root = Path(config['pdf_root'])
    bibtex_path = Path(config['bibtex_path'])
    
    if not pdf_root.exists():
        print(f"Warning: PDF root does not exist: {pdf_root}")
    if not bibtex_path.exists():
        print(f"Error: BibTeX file does not exist: {bibtex_path}")
        return 1
    
    # Initialize database
    print(f"Initializing database: {config['index_path']}")
    db = LiteratureDatabase(config['index_path'])
    
    # Create ingester
    ingester = BibTeXIngester(
        db,
        pdf_root=config['pdf_root'],
        bibtex_path=config['bibtex_path'],
        pdf_chunk_size=config['chunking']['pdf_chunk_chars'],
        note_chunk_size=config['chunking']['note_chunk_chars']
    )
    
    # Run ingestion
    print(f"\nParsing BibTeX: {config['bibtex_path']}")
    print(f"Looking for PDFs in: {config['pdf_root']}\n")
    
    stats = ingester.scan_and_ingest()
    
    print(f"\n{'='*50}")
    print("Ingestion complete!")
    print(f"  Indexed: {stats['indexed']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Skipped: {stats['skipped']}")
    
    if args.stats:
        db_stats = db.get_stats()
        print(f"\nDatabase statistics:")
        print(f"  Documents: {db_stats['documents']}")
        print(f"  Total chunks: {db_stats['chunks']}")
        print(f"  PDF chunks: {db_stats['pdf_chunks']}")
        print(f"  Note chunks: {db_stats['note_chunks']}")
    
    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
