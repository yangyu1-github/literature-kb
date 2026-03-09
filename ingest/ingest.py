#!/usr/bin/env python3
"""
Deprecated standalone ingestion script for the legacy Markdown-note workflow.
Usage: python ingest.py [--config config.yaml] [--pdf-root PATH] [--notes-root PATH]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'mcp_server'))

from database import LiteratureDatabase
from ingestion import LibraryIngester
import yaml


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Deprecated: ingest literature from legacy Markdown notes into the knowledge base"
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
        "--stats", "-s",
        action="store_true",
        help="Show database statistics after ingestion"
    )
    
    args = parser.parse_args()

    print("DEPRECATED: this CLI targets the legacy Markdown-note workflow.")
    print("Use `python ingest/ingest_bibtex.py --config config.yaml --stats` for the supported BibTeX workflow.\n")
    
    # Load config or use defaults
    config = {
        'pdf_root': '/home/azurin/Documents/Papers',
        'notes_root': '/home/azurin/Documents/Notes',
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
    if args.notes_root:
        config['notes_root'] = args.notes_root
    if args.index_path:
        config['index_path'] = args.index_path
    
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
    
    # Create ingester
    ingester = LibraryIngester(
        db,
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
