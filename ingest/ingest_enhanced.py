#!/usr/bin/env python3
"""
Enhanced standalone ingestion script with Phase 3 features.
Usage: python ingest_enhanced.py [--config config.yaml] [--full-refresh] [--include-duplicates]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'mcp_server'))

from enhanced_database import EnhancedLiteratureDatabase
from enhanced_bibtex_ingestion import EnhancedBibTeXIngester
import yaml


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced literature ingestion with duplicate detection and incremental refresh"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config.yaml file"
    )
    parser.add_argument(
        "--full-refresh", "-f",
        action="store_true",
        help="Force full refresh (ignore incremental check)"
    )
    parser.add_argument(
        "--include-duplicates", "-d",
        action="store_true",
        help="Include suspected duplicates (don't skip them)"
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Show database statistics after ingestion"
    )
    parser.add_argument(
        "--show-duplicates",
        action="store_true",
        help="Show detected duplicates after ingestion"
    )
    
    args = parser.parse_args()
    
    # Load config
    config = {
        'pdf_root': '/home/azurin/.openclaw/workspace/project/Yang_Document/LIB_ROOT',
        'bibtex_path': '/home/azurin/.openclaw/workspace/project/Yang_Document/My_Collection.bib',
        'index_path': str(Path(__file__).parent.parent / 'kb' / 'index.sqlite'),
        'chunking': {
            'pdf_chunk_chars': 2000,
            'note_chunk_chars': 1500
        }
    }
    
    if Path(args.config).exists():
        user_config = load_config(args.config)
        config.update(user_config)
    
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
    db = EnhancedLiteratureDatabase(config['index_path'])
    
    # Create ingester
    ingester = EnhancedBibTeXIngester(
        db,
        pdf_root=config['pdf_root'],
        bibtex_path=config['bibtex_path'],
        pdf_chunk_size=config['chunking']['pdf_chunk_chars'],
        note_chunk_size=config['chunking']['note_chunk_chars']
    )
    
    # Run ingestion
    print(f"\nParsing BibTeX: {config['bibtex_path']}")
    print(f"Looking for PDFs in: {config['pdf_root']}")
    print(f"Incremental mode: {'disabled' if args.full_refresh else 'enabled'}")
    print(f"Duplicate skipping: {'disabled' if args.include_duplicates else 'enabled'}")
    print()
    
    stats = ingester.scan_and_ingest(
        incremental=not args.full_refresh,
        skip_duplicates=not args.include_duplicates
    )
    
    if args.stats:
        db_stats = db.get_stats()
        print(f"\nDatabase statistics:")
        print(f"  Documents: {db_stats['documents']}")
        print(f"  Total chunks: {db_stats['chunks']}")
        print(f"  PDF chunks: {db_stats['pdf_chunks']}")
        print(f"  Note chunks: {db_stats['note_chunks']}")
        print(f"  Duplicates detected: {db_stats['duplicates']}")
    
    if args.show_duplicates:
        duplicates = db.get_duplicates()
        if duplicates:
            print(f"\nDetected duplicates ({len(duplicates)}):")
            for dup in duplicates[:10]:  # Show first 10
                print(f"  - {dup.get('duplicate_title', 'Unknown')[:60]}...")
                print(f"    (matches: {dup.get('canonical_title', 'Unknown')[:50]}...)")
                print(f"    Reason: {dup.get('duplicate_source', 'unknown')}")
        else:
            print("\nNo duplicates detected.")
    
    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
