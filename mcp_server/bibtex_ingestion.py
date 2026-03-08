"""
BibTeX-based ingestion pipeline for Literature Knowledge Base.
Parses BibTeX files with 'annote' fields for notes instead of separate Markdown files.
"""

import re
import yaml
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class BibEntry:
    """Parsed BibTeX entry."""
    key: str
    entry_type: str
    title: str
    year: Optional[int] = None
    venue: Optional[str] = None  # journal, booktitle, etc.
    doi: Optional[str] = None
    authors: List[str] = None
    abstract: Optional[str] = None
    annote: Optional[str] = None  # Notes/annotations
    file: Optional[str] = None  # PDF file path from Mendeley
    tags: List[str] = None
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.tags is None:
            self.tags = []


class BibTeXParser:
    """Parse BibTeX files with support for 'annote' field."""
    
    @staticmethod
    def parse(bib_path: Path) -> List[BibEntry]:
        """Parse a BibTeX file and return list of entries."""
        content = bib_path.read_text(encoding='utf-8')
        entries = []
        
        # Find all entry blocks: @type{key, ... }
        # Use a simpler approach: split by @ and parse each entry
        parts = content.split('@')[1:]  # Skip empty first part
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Extract entry type and key
            match = re.match(r'(\w+)\s*\{\s*([^,\s]+)\s*,', part)
            if not match:
                continue
            
            entry_type = match.group(1).lower()
            key = match.group(2)
            
            # Extract fields
            fields = BibTeXParser._extract_fields(part[match.end():])
            
            # Build entry
            entry = BibEntry(
                key=key,
                entry_type=entry_type,
                title=fields.get('title', ''),
                year=BibTeXParser._parse_year(fields.get('year')),
                venue=fields.get('journal') or fields.get('booktitle') or fields.get('publisher'),
                doi=fields.get('doi'),
                authors=BibTeXParser._parse_authors(fields.get('author')),
                abstract=fields.get('abstract'),
                annote=fields.get('annote'),
                file=fields.get('file'),
                tags=BibTeXParser._parse_tags(fields.get('keywords'))
            )
            entries.append(entry)
        
        return entries
    
    @staticmethod
    def _extract_fields(body: str) -> Dict[str, str]:
        """Extract all fields from entry body."""
        fields = {}
        
        # Find field assignments: field = {value} or field = "value" or field = value
        pattern = r'(\w+)\s*=\s*'
        
        for match in re.finditer(pattern, body):
            field_name = match.group(1).lower()
            start = match.end()
            
            # Skip whitespace
            while start < len(body) and body[start] in ' \t\n\r':
                start += 1
            
            if start >= len(body):
                break
            
            # Determine value type
            if body[start] == '{':
                # Braced value - find matching closing brace
                brace_count = 1
                end = start + 1
                while brace_count > 0 and end < len(body):
                    if body[end] == '{':
                        brace_count += 1
                    elif body[end] == '}':
                        brace_count -= 1
                    end += 1
                value = body[start+1:end-1]
            elif body[start] == '"':
                # Quoted value - find closing quote (not escaped)
                end = start + 1
                while end < len(body):
                    if body[end] == '"' and body[end-1] != '\\':
                        break
                    end += 1
                value = body[start+1:end]
            else:
                # Unquoted value - find until comma or closing brace
                end_match = re.search(r'[,\}]', body[start:])
                if end_match:
                    end = start + end_match.start()
                    value = body[start:end].strip()
                else:
                    value = body[start:].strip()
            
            # Clean up value
            value = BibTeXParser._clean_value(value)
            if value:  # Only store non-empty values
                fields[field_name] = value
        
        return fields
    
    @staticmethod
    def _clean_value(value: str) -> str:
        """Clean up field value - remove extra braces, normalize whitespace."""
        # Remove outer braces if present
        while value.startswith('{') and value.endswith('}'):
            value = value[1:-1]
        
        # Remove LaTeX commands (simplified)
        value = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', value)
        value = re.sub(r'\\[a-zA-Z]+\s*', ' ', value)
        
        # Normalize whitespace
        value = ' '.join(value.split())
        
        # Handle escaped characters
        value = value.replace('\\{', '{').replace('\\}', '}')
        value = value.replace('\\"', '"').replace("\\'", "'")
        
        return value.strip()
    
    @staticmethod
    def _parse_year(year_str: Optional[str]) -> Optional[int]:
        """Parse year string to integer."""
        if not year_str:
            return None
        try:
            # Handle cases like "2026," or "2026}"
            year_str = re.sub(r'[^0-9]', '', year_str)
            return int(year_str) if year_str else None
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _parse_authors(author_str: Optional[str]) -> List[str]:
        """Parse author string into list of authors."""
        if not author_str:
            return []
        # Split by 'and'
        authors = [a.strip() for a in author_str.split(' and ')]
        return [a for a in authors if a]
    
    @staticmethod
    def _parse_tags(keywords_str: Optional[str]) -> List[str]:
        """Parse keywords string into list of tags."""
        if not keywords_str:
            return []
        # Split by comma
        tags = [t.strip() for t in keywords_str.split(',')]
        return [t for t in tags if t]


class PDFExtractor:
    """Extract text from PDF files."""
    
    def __init__(self, chunk_size: int = 2000):
        self.chunk_size = chunk_size
    
    def extract(self, pdf_path: Path) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Extract text from PDF and return chunks with page locators.
        Returns list of (text, locator) tuples.
        """
        chunks = []
        
        try:
            doc = fitz.open(pdf_path)
            current_chunk = []
            current_start_page = 0
            current_length = 0
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                if not text.strip():
                    continue
                
                # If adding this page would exceed chunk size, save current chunk
                if current_length + len(text) > self.chunk_size and current_chunk:
                    chunk_text = '\n'.join(current_chunk)
                    locator = {
                        'page_start': current_start_page + 1,  # 1-indexed
                        'page_end': page_num
                    }
                    chunks.append((chunk_text, locator))
                    current_chunk = [text]
                    current_start_page = page_num
                    current_length = len(text)
                else:
                    current_chunk.append(text)
                    current_length += len(text)
            
            # Don't forget the last chunk
            if current_chunk:
                chunk_text = '\n'.join(current_chunk)
                locator = {
                    'page_start': current_start_page + 1,
                    'page_end': len(doc)
                }
                chunks.append((chunk_text, locator))
            
            doc.close()
            
        except Exception as e:
            print(f"Error extracting PDF {pdf_path}: {e}")
        
        return chunks


class NoteChunker:
    """Chunk note content (from annote field) into searchable segments."""
    
    def __init__(self, chunk_size: int = 1500):
        self.chunk_size = chunk_size
    
    def chunk(self, content: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Chunk note content by paragraphs or fixed size.
        Returns list of (text, locator) tuples.
        """
        if not content:
            return []
        
        chunks = []
        paragraphs = content.split('\n\n')
        
        current_chunk = []
        current_length = 0
        current_start_offset = 0
        
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            
            para_length = len(para)
            
            # If adding this paragraph would exceed chunk size, save current chunk
            if current_length + para_length > self.chunk_size and current_chunk:
                chunk_text = '\n\n'.join(current_chunk)
                locator = {
                    'offset_start': current_start_offset,
                    'offset_end': current_start_offset + current_length,
                    'paragraph_start': i - len(current_chunk) + 1,
                    'paragraph_end': i
                }
                chunks.append((chunk_text, locator))
                current_chunk = [para]
                current_start_offset += current_length
                current_length = para_length
            else:
                current_chunk.append(para)
                current_length += para_length + 2  # +2 for '\n\n'
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            locator = {
                'offset_start': current_start_offset,
                'offset_end': current_start_offset + current_length,
                'paragraph_start': len(paragraphs) - len(current_chunk) + 1,
                'paragraph_end': len(paragraphs)
            }
            chunks.append((chunk_text, locator))
        
        return chunks


class BibTeXIngester:
    """Main ingestion orchestrator for BibTeX-based library."""
    
    def __init__(self, db, pdf_root: str, bibtex_path: str,
                 pdf_chunk_size: int = 2000, note_chunk_size: int = 1500):
        self.db = db
        self.pdf_root = Path(pdf_root)
        self.bibtex_path = Path(bibtex_path)
        self.pdf_extractor = PDFExtractor(chunk_size=pdf_chunk_size)
        self.note_chunker = NoteChunker(chunk_size=note_chunk_size)
        self.bibtex_parser = BibTeXParser()
    
    def _derive_doc_key(self, entry: BibEntry) -> str:
        """Generate a stable document key from BibTeX entry."""
        if entry.doi:
            return entry.doi
        
        # Use first author + year + first few words of title
        author_part = ""
        if entry.authors:
            first_author = entry.authors[0].split()[-1]  # Last name
            author_part = re.sub(r'[^\w]', '', first_author.lower())
        
        year_part = str(entry.year) if entry.year else ""
        
        # First 3 words of title
        title_words = entry.title.split()[:3] if entry.title else []
        title_part = "_".join(re.sub(r'[^\w]', '', w.lower()) for w in title_words)
        
        parts = [p for p in [author_part, year_part, title_part] if p]
        return "_".join(parts) if parts else entry.key
    
    def _find_pdf_for_entry(self, entry: BibEntry) -> Optional[Path]:
        """Find corresponding PDF for a BibTeX entry."""
        # First, try to parse the 'file' field from Mendeley
        if entry.file:
            # Mendeley format: {:path:pdf} or {:path:path2:pdf}
            # Handle both forward and backward slashes
            pdf_match = re.search(r'[:\{]([^:}]+)\.pdf:pdf\}', entry.file)
            if pdf_match:
                # Extract filename from path
                file_path = pdf_match.group(1).replace('\\', '/')
                pdf_name = Path(file_path).name
                pdf_stem = Path(pdf_name).stem
                
                # Search in pdf_root for this file
                for pdf_file in self.pdf_root.rglob('*.pdf'):
                    if pdf_file.name == pdf_name or pdf_file.stem == pdf_stem:
                        return pdf_file
        
        # Try to find by title similarity
        if entry.title:
            title_normalized = re.sub(r'[^\w]', '', entry.title.lower())
            best_match = None
            best_score = 0
            
            for pdf_file in self.pdf_root.rglob('*.pdf'):
                pdf_name_normalized = re.sub(r'[^\w]', '', pdf_file.stem.lower())
                
                # Calculate similarity score
                if title_normalized == pdf_name_normalized:
                    return pdf_file  # Exact match
                
                # Check if title is contained in filename or vice versa
                if title_normalized in pdf_name_normalized:
                    score = len(title_normalized) / len(pdf_name_normalized)
                elif pdf_name_normalized in title_normalized:
                    score = len(pdf_name_normalized) / len(title_normalized)
                else:
                    # Check word overlap
                    title_words = set(title_normalized.split())
                    pdf_words = set(pdf_name_normalized.split())
                    if title_words and pdf_words:
                        overlap = len(title_words & pdf_words)
                        score = overlap / max(len(title_words), len(pdf_words))
                    else:
                        score = 0
                
                if score > best_score and score > 0.5:  # Threshold for matching
                    best_score = score
                    best_match = pdf_file
            
            if best_match:
                return best_match
        
        return None
    
    def ingest_entry(self, entry: BibEntry) -> bool:
        """Ingest a single BibTeX entry and its corresponding PDF."""
        try:
            # Skip entries without title
            if not entry.title:
                print(f"Warning: Skipping entry {entry.key} - no title")
                return False
            
            # Find corresponding PDF
            pdf_path = self._find_pdf_for_entry(entry)
            pdf_path_str = str(pdf_path.absolute()) if pdf_path else ""
            
            if not pdf_path:
                print(f"Warning: No PDF found for {entry.title[:50]}...")
            
            # Generate doc_key
            doc_key = self._derive_doc_key(entry)
            
            # Add document to database
            success = self.db.add_document(
                doc_key=doc_key,
                title=entry.title,
                year=entry.year,
                venue=entry.venue,
                doi=entry.doi,
                pdf_path=pdf_path_str,
                note_path=str(self.bibtex_path.absolute()),  # Store bibtex path as note source
                tags=entry.tags
            )
            
            if not success:
                return False
            
            # Index annotation chunks (from annote field)
            if entry.annote:
                note_chunks = self.note_chunker.chunk(entry.annote)
                for i, (chunk_text, locator) in enumerate(note_chunks):
                    self.db.add_chunk(doc_key, 'note', chunk_text, locator, i)
            else:
                note_chunks = []
            
            # Index abstract as note chunks too (if no annote)
            if entry.abstract and not entry.annote:
                abstract_chunks = self.note_chunker.chunk(entry.abstract)
                for i, (chunk_text, locator) in enumerate(abstract_chunks):
                    self.db.add_chunk(doc_key, 'note', chunk_text, locator, i)
            else:
                abstract_chunks = []
            
            # Index PDF chunks if available
            pdf_chunks = []
            if pdf_path:
                pdf_chunks = self.pdf_extractor.extract(pdf_path)
                for i, (chunk_text, locator) in enumerate(pdf_chunks):
                    self.db.add_chunk(doc_key, 'pdf', chunk_text, locator, i)
            
            print(f"Indexed: {entry.title[:60]}... ({len(note_chunks)} note chunks, {len(abstract_chunks)} abstract chunks, {len(pdf_chunks)} PDF chunks)")
            return True
            
        except Exception as e:
            print(f"Error ingesting {entry.key}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def scan_and_ingest(self) -> Dict[str, int]:
        """Parse BibTeX file and ingest all entries."""
        stats = {'indexed': 0, 'failed': 0, 'skipped': 0}
        
        if not self.bibtex_path.exists():
            print(f"BibTeX file does not exist: {self.bibtex_path}")
            return stats
        
        if not self.pdf_root.exists():
            print(f"Warning: PDF root does not exist: {self.pdf_root}")
        
        # Parse BibTeX file
        print(f"Parsing BibTeX file: {self.bibtex_path}")
        entries = self.bibtex_parser.parse(self.bibtex_path)
        print(f"Found {len(entries)} entries to ingest")
        
        for entry in entries:
            if self.ingest_entry(entry):
                stats['indexed'] += 1
            else:
                stats['failed'] += 1
        
        return stats
    
    def refresh(self) -> Dict[str, int]:
        """Refresh index - re-parse and re-index everything."""
        # For BibTeX, we don't have file modification times easily
        # Just do a full re-scan
        return self.scan_and_ingest()
