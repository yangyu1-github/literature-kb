"""
Enhanced BibTeX ingestion with duplicate detection and incremental refresh.
"""

import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from dataclasses import dataclass

from bibtex_ingestion import BibTeXParser, BibEntry, PDFExtractor, NoteChunker
from enhanced_database import EnhancedLiteratureDatabase


class EnhancedBibTeXIngester:
    """Enhanced ingester with Phase 3 features."""
    
    def __init__(self, db: EnhancedLiteratureDatabase, pdf_root: str, 
                 bibtex_path: str, pdf_chunk_size: int = 2000, 
                 note_chunk_size: int = 1500):
        self.db = db
        self.pdf_root = Path(pdf_root)
        self.bibtex_path = Path(bibtex_path)
        self.pdf_extractor = PDFExtractor(chunk_size=pdf_chunk_size)
        self.note_chunker = NoteChunker(chunk_size=note_chunk_size)
        self.bibtex_parser = BibTeXParser()
        
        # Statistics
        self.stats = {
            'indexed': 0,
            'failed': 0,
            'skipped': 0,
            'duplicates_detected': 0,
            'pdf_matched': 0
        }
    
    def _derive_doc_key(self, entry: BibEntry) -> str:
        """Generate a stable document key from BibTeX entry."""
        if entry.doi:
            return entry.doi
        
        author_part = ""
        if entry.authors:
            first_author = entry.authors[0].split()[-1]
            author_part = re.sub(r'[^\w]', '', first_author.lower())
        
        year_part = str(entry.year) if entry.year else ""
        
        title_words = entry.title.split()[:3] if entry.title else []
        title_part = "_".join(re.sub(r'[^\w]', '', w.lower()) for w in title_words)
        
        parts = [p for p in [author_part, year_part, title_part] if p]
        return "_".join(parts) if parts else entry.key
    
    def _find_pdf_for_entry(self, entry: BibEntry) -> Optional[Path]:
        """Find corresponding PDF for a BibTeX entry."""
        if entry.file:
            pdf_match = re.search(r'[:\{]([^:}]+)\.pdf:pdf\}', entry.file)
            if pdf_match:
                file_path = pdf_match.group(1).replace('\\', '/')
                pdf_name = Path(file_path).name
                pdf_stem = Path(pdf_name).stem
                
                for pdf_file in self.pdf_root.rglob('*.pdf'):
                    if pdf_file.name == pdf_name or pdf_file.stem == pdf_stem:
                        return pdf_file
        
        if entry.title:
            title_normalized = re.sub(r'[^\w]', '', entry.title.lower())
            best_match = None
            best_score = 0
            
            for pdf_file in self.pdf_root.rglob('*.pdf'):
                pdf_name_normalized = re.sub(r'[^\w]', '', pdf_file.stem.lower())
                
                if title_normalized == pdf_name_normalized:
                    return pdf_file
                
                if title_normalized in pdf_name_normalized:
                    score = len(title_normalized) / len(pdf_name_normalized)
                elif pdf_name_normalized in title_normalized:
                    score = len(pdf_name_normalized) / len(title_normalized)
                else:
                    title_words = set(title_normalized.split())
                    pdf_words = set(pdf_name_normalized.split())
                    if title_words and pdf_words:
                        overlap = len(title_words & pdf_words)
                        score = overlap / max(len(title_words), len(pdf_words))
                    else:
                        score = 0
                
                if score > best_score and score > 0.5:
                    best_score = score
                    best_match = pdf_file
            
            if best_match:
                return best_match
        
        return None
    
    def _check_duplicate(self, entry: BibEntry) -> Tuple[bool, Optional[Dict], str]:
        """
        Check if entry is a duplicate.
        Returns: (is_duplicate, existing_doc, reason)
        """
        # Check by DOI first (most reliable)
        if entry.doi:
            existing = self.db.find_duplicate_by_doi(entry.doi)
            if existing:
                return True, existing, "doi_match"
        
        # Check by title + year
        if entry.title and entry.year:
            potential_dups = self.db.find_duplicates_by_title_year(entry.title, entry.year)
            if potential_dups:
                # If exact title match, it's a duplicate
                for dup in potential_dups:
                    if dup.get('title', '').lower().strip() == entry.title.lower().strip():
                        return True, dup, "title_year_match"
        
        return False, None, ""
    
    def ingest_entry(self, entry: BibEntry, skip_duplicates: bool = True) -> bool:
        """Ingest a single BibTeX entry with duplicate detection."""
        try:
            if not entry.title:
                print(f"Warning: Skipping entry {entry.key} - no title")
                self.stats['skipped'] += 1
                return False
            
            # Check for duplicates
            is_dup, existing, reason = self._check_duplicate(entry)
            if is_dup and skip_duplicates:
                print(f"  [DUPLICATE - {reason}] {entry.title[:60]}...")
                if existing:
                    self.db.record_duplicate(existing['doc_key'], 
                                           self._derive_doc_key(entry), reason)
                self.stats['duplicates_detected'] += 1
                self.stats['skipped'] += 1
                return False
            
            # Find corresponding PDF
            pdf_path = self._find_pdf_for_entry(entry)
            pdf_path_str = str(pdf_path.absolute()) if pdf_path else ""
            
            if pdf_path:
                self.stats['pdf_matched'] += 1
            else:
                print(f"  Warning: No PDF found for {entry.title[:50]}...")
            
            # Generate doc_key
            doc_key = self._derive_doc_key(entry)
            
            # Add document
            success = self.db.add_document(
                doc_key=doc_key,
                title=entry.title,
                year=entry.year,
                venue=entry.venue,
                doi=entry.doi,
                pdf_path=pdf_path_str,
                note_path=str(self.bibtex_path.absolute()),
                tags=entry.tags,
                bibtex_key=entry.key,
                authors=entry.authors
            )
            
            if not success:
                self.stats['failed'] += 1
                return False
            
            # Index annotation chunks
            note_chunks = []
            if entry.annote:
                note_chunks = self.note_chunker.chunk(entry.annote)
                for i, (chunk_text, locator) in enumerate(note_chunks):
                    self.db.add_chunk(doc_key, 'note', chunk_text, locator, i)
            
            # Index abstract if no annote
            abstract_chunks = []
            if entry.abstract and not entry.annote:
                abstract_chunks = self.note_chunker.chunk(entry.abstract)
                for i, (chunk_text, locator) in enumerate(abstract_chunks):
                    self.db.add_chunk(doc_key, 'note', chunk_text, locator, i)
            
            # Index PDF chunks
            pdf_chunks = []
            if pdf_path:
                pdf_chunks = self.pdf_extractor.extract(pdf_path)
                for i, (chunk_text, locator) in enumerate(pdf_chunks):
                    self.db.add_chunk(doc_key, 'pdf', chunk_text, locator, i)
            
            print(f"  Indexed: {entry.title[:60]}... ({len(note_chunks)} note, {len(abstract_chunks)} abstract, {len(pdf_chunks)} PDF chunks)")
            self.stats['indexed'] += 1
            return True
            
        except Exception as e:
            print(f"  Error ingesting {entry.key}: {e}")
            import traceback
            traceback.print_exc()
            self.stats['failed'] += 1
            return False
    
    def scan_and_ingest(self, incremental: bool = True, 
                       skip_duplicates: bool = True) -> Dict[str, int]:
        """
        Parse BibTeX file and ingest all entries.
        
        Args:
            incremental: If True, skip if BibTeX hasn't changed since last ingest
            skip_duplicates: If True, skip entries that appear to be duplicates
        """
        self.stats = {
            'indexed': 0,
            'failed': 0,
            'skipped': 0,
            'duplicates_detected': 0,
            'pdf_matched': 0
        }
        
        if not self.bibtex_path.exists():
            print(f"BibTeX file does not exist: {self.bibtex_path}")
            return self.stats
        
        # Check if incremental refresh is needed
        if incremental:
            current_modified = datetime.fromtimestamp(self.bibtex_path.stat().st_mtime)
            if not self.db.needs_refresh(str(self.bibtex_path.absolute()), current_modified):
                print(f"BibTeX file unchanged since last ingest. Skipping.")
                print(f"Last ingest: {self.db.get_last_ingestion(str(self.bibtex_path.absolute()))}")
                return self.stats
            print(f"BibTeX modified since last ingest. Proceeding with refresh...")
        
        # Parse BibTeX
        print(f"Parsing BibTeX file: {self.bibtex_path}")
        entries = self.bibtex_parser.parse(self.bibtex_path)
        print(f"Found {len(entries)} entries to ingest")
        print(f"Duplicate detection: {'enabled' if skip_duplicates else 'disabled'}")
        print()
        
        # Ingest entries
        for entry in entries:
            self.ingest_entry(entry, skip_duplicates=skip_duplicates)
        
        # Record ingestion
        current_modified = datetime.fromtimestamp(self.bibtex_path.stat().st_mtime)
        self.db.record_ingestion(
            str(self.bibtex_path.absolute()),
            'bibtex',
            current_modified,
            len(entries)
        )
        
        # Print summary
        print(f"\n{'='*60}")
        print("Ingestion Summary:")
        print(f"  Indexed: {self.stats['indexed']}")
        print(f"  Failed: {self.stats['failed']}")
        print(f"  Skipped: {self.stats['skipped']}")
        print(f"  Duplicates detected: {self.stats['duplicates_detected']}")
        print(f"  PDFs matched: {self.stats['pdf_matched']}")
        
        return self.stats
    
    def refresh(self, incremental: bool = True, 
                skip_duplicates: bool = True) -> Dict[str, int]:
        """Refresh index with optional incremental and duplicate detection."""
        return self.scan_and_ingest(incremental=incremental, 
                                   skip_duplicates=skip_duplicates)
