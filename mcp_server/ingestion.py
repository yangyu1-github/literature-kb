"""
Deprecated ingestion pipeline for the legacy Markdown-note workflow.
Scans PDF and note directories, extracts content, and indexes into database.
"""

import re
import yaml
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass


@dataclass
class NoteMetadata:
    """Parsed note file metadata."""
    title: str
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    pdf_path: Optional[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class NoteParser:
    """Parse legacy Markdown note files with YAML front matter."""
    
    @staticmethod
    def parse(note_path: Path) -> Tuple[NoteMetadata, str]:
        """Parse a note file and return metadata + content."""
        content = note_path.read_text(encoding='utf-8')
        
        # Try to extract YAML front matter
        front_matter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        
        metadata = NoteMetadata(title=note_path.stem.replace('.mendeley', ''))
        body = content
        
        if front_matter_match:
            try:
                yaml_content = front_matter_match.group(1)
                data = yaml.safe_load(yaml_content) or {}
                
                metadata.title = data.get('title', metadata.title)
                metadata.year = data.get('year')
                metadata.venue = data.get('venue')
                metadata.doi = data.get('doi')
                metadata.pdf_path = data.get('pdf_path')
                metadata.tags = data.get('tags', [])
                
                body = content[front_matter_match.end():]
            except yaml.YAMLError as e:
                print(f"Warning: Could not parse YAML front matter in {note_path}: {e}")
        
        return metadata, body


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
    """Chunk note files into searchable segments."""
    
    def __init__(self, chunk_size: int = 1500):
        self.chunk_size = chunk_size
    
    def chunk(self, content: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Chunk note content by paragraphs or fixed size.
        Returns list of (text, locator) tuples.
        """
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
            
            # Check for page markers like [Page X]
            page_match = re.match(r'\[Page\s+(\d+)\]', para)
            if page_match:
                page_num = int(page_match.group(1))
            else:
                page_num = None
            
            # If adding this paragraph would exceed chunk size, save current chunk
            if current_length + para_length > self.chunk_size and current_chunk:
                chunk_text = '\n\n'.join(current_chunk)
                locator = {
                    'offset_start': current_start_offset,
                    'offset_end': current_start_offset + current_length,
                    'paragraph_start': i - len(current_chunk) + 1,
                    'paragraph_end': i,
                    'page': page_num
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


class LibraryIngester:
    """Main ingester for the deprecated Markdown-note workflow."""
    
    def __init__(self, db, pdf_root: str, notes_root: str,
                 pdf_chunk_size: int = 2000, note_chunk_size: int = 1500):
        self.db = db
        self.pdf_root = Path(pdf_root)
        self.notes_root = Path(notes_root)
        self.pdf_extractor = PDFExtractor(chunk_size=pdf_chunk_size)
        self.note_chunker = NoteChunker(chunk_size=note_chunk_size)
        self.note_parser = NoteParser()
    
    def _derive_doc_key(self, title: str, year: Optional[int], 
                        venue: Optional[str]) -> str:
        """Generate a stable document key."""
        # Normalize title
        normalized = re.sub(r'[^\w\s]', '', title.lower())
        normalized = re.sub(r'\s+', '_', normalized.strip())
        
        # Add year and venue if available
        parts = [normalized]
        if year:
            parts.append(str(year))
        if venue:
            venue_norm = re.sub(r'[^\w\s]', '', venue.lower())
            parts.append(re.sub(r'\s+', '_', venue_norm.strip()))
        
        return '_'.join(parts)
    
    def _find_pdf_for_note(self, note_path: Path, metadata: NoteMetadata) -> Optional[Path]:
        """Find corresponding PDF for a note file."""
        # If metadata has explicit pdf_path, use it
        if metadata.pdf_path and Path(metadata.pdf_path).exists():
            return Path(metadata.pdf_path)
        
        # Try to find PDF with same name in parallel structure
        rel_path = note_path.relative_to(self.notes_root)
        pdf_name = note_path.stem.replace('.mendeley', '') + '.pdf'
        pdf_path = self.pdf_root / rel_path.parent / pdf_name
        
        if pdf_path.exists():
            return pdf_path
        
        # Try without the .mendeley suffix
        pdf_name = note_path.stem + '.pdf'
        pdf_path = self.pdf_root / rel_path.parent / pdf_name
        
        if pdf_path.exists():
            return pdf_path
        
        return None
    
    def ingest_note(self, note_path: Path) -> bool:
        """Ingest a single note file and its corresponding PDF."""
        try:
            # Parse note
            metadata, content = self.note_parser.parse(note_path)
            
            # Find corresponding PDF
            pdf_path = self._find_pdf_for_note(note_path, metadata)
            if not pdf_path:
                print(f"Warning: No PDF found for note {note_path}")
                # Still index the note without PDF
                pdf_path_str = None
            else:
                pdf_path_str = str(pdf_path.absolute())
            
            # Generate doc_key
            doc_key = metadata.doi if metadata.doi else self._derive_doc_key(
                metadata.title, metadata.year, metadata.venue
            )
            
            # Add document to database
            success = self.db.add_document(
                doc_key=doc_key,
                title=metadata.title,
                year=metadata.year,
                venue=metadata.venue,
                doi=metadata.doi,
                pdf_path=pdf_path_str or "",
                note_path=str(note_path.absolute()),
                tags=metadata.tags
            )
            
            if not success:
                return False
            
            # Index note chunks
            note_chunks = self.note_chunker.chunk(content)
            for i, (chunk_text, locator) in enumerate(note_chunks):
                self.db.add_chunk(doc_key, 'note', chunk_text, locator, i)
            
            # Index PDF chunks if available
            if pdf_path:
                pdf_chunks = self.pdf_extractor.extract(pdf_path)
                for i, (chunk_text, locator) in enumerate(pdf_chunks):
                    self.db.add_chunk(doc_key, 'pdf', chunk_text, locator, i)
            
            print(f"Indexed: {metadata.title} ({len(note_chunks)} note chunks, {len(pdf_chunks) if pdf_path else 0} PDF chunks)")
            return True
            
        except Exception as e:
            print(f"Error ingesting {note_path}: {e}")
            return False
    
    def scan_and_ingest(self) -> Dict[str, int]:
        """Scan notes directory and ingest all files."""
        stats = {'indexed': 0, 'failed': 0, 'skipped': 0}
        
        if not self.notes_root.exists():
            print(f"Notes root does not exist: {self.notes_root}")
            return stats
        
        # Find all .mendeley.md files
        note_files = list(self.notes_root.rglob('*.mendeley.md'))
        
        print(f"Found {len(note_files)} note files to ingest")
        
        for note_path in note_files:
            if self.ingest_note(note_path):
                stats['indexed'] += 1
            else:
                stats['failed'] += 1
        
        return stats
    
    def refresh(self) -> Dict[str, int]:
        """Refresh index - remove deleted, add new, update modified."""
        # TODO: Implement incremental refresh with file modification times
        # For now, just do a full re-scan
        return self.scan_and_ingest()
