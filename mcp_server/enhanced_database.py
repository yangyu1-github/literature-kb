"""
Enhanced database operations with duplicate detection and incremental refresh tracking.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class EnhancedLiteratureDatabase:
    """Extended database class with Phase 3 features."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema including Phase 3 tables."""
        with sqlite3.connect(self.db_path) as conn:
            # Original schema
            conn.executescript('''
                -- Documents table
                CREATE TABLE IF NOT EXISTS documents (
                    doc_key TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    year INTEGER,
                    venue TEXT,
                    doi TEXT UNIQUE,
                    pdf_path TEXT,
                    note_path TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    bibtex_key TEXT,
                    authors TEXT
                );
                
                -- Chunks table
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_key TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('pdf', 'note')),
                    content TEXT NOT NULL,
                    locator TEXT,
                    chunk_index INTEGER,
                    FOREIGN KEY (doc_key) REFERENCES documents(doc_key) ON DELETE CASCADE
                );
                
                -- FTS5 virtual table
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    content_rowid=id
                );
                
                -- Triggers to keep FTS index in sync
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
                END;
                
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
                END;
                
                -- Phase 3: Ingestion tracking for incremental refresh
                CREATE TABLE IF NOT EXISTS ingestion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('bibtex', 'pdf')),
                    last_modified TIMESTAMP,
                    entry_count INTEGER,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Phase 3: Duplicate tracking
                CREATE TABLE IF NOT EXISTS duplicates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_doc_key TEXT NOT NULL,
                    duplicate_doc_key TEXT NOT NULL,
                    duplicate_source TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (canonical_doc_key) REFERENCES documents(doc_key),
                    FOREIGN KEY (duplicate_doc_key) REFERENCES documents(doc_key)
                );
                
                -- Phase 3: Note edit history
                CREATE TABLE IF NOT EXISTS note_edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_key TEXT NOT NULL,
                    old_content TEXT,
                    new_content TEXT,
                    edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (doc_key) REFERENCES documents(doc_key) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_chunks_doc_key ON chunks(doc_key);
                CREATE INDEX IF NOT EXISTS idx_documents_doi ON documents(doi);
                CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
                CREATE INDEX IF NOT EXISTS idx_documents_venue ON documents(venue);
                CREATE INDEX IF NOT EXISTS idx_ingestion_log_path ON ingestion_log(source_path);
            ''')
    
    def add_document(self, doc_key: str, title: str, year: Optional[int] = None,
                     venue: Optional[str] = None, doi: Optional[str] = None,
                     pdf_path: str = "", note_path: str = "",
                     tags: Optional[List[str]] = None,
                     bibtex_key: Optional[str] = None,
                     authors: Optional[List[str]] = None) -> bool:
        """Add a document to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO documents 
                    (doc_key, title, year, venue, doi, pdf_path, note_path, tags, 
                     updated_at, bibtex_key, authors)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ''', (
                    doc_key, title, year, venue, doi, pdf_path, note_path,
                    json.dumps(tags) if tags else None,
                    bibtex_key,
                    json.dumps(authors) if authors else None
                ))
            return True
        except sqlite3.Error as e:
            print(f"Error adding document {doc_key}: {e}")
            return False
    
    def add_chunk(self, doc_key: str, source_type: str, content: str,
                  locator: Optional[Dict] = None, chunk_index: int = 0):
        """Add a content chunk to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO chunks (doc_key, source_type, content, locator, chunk_index)
                    VALUES (?, ?, ?, ?, ?)
                ''', (doc_key, source_type, content, json.dumps(locator) if locator else None, chunk_index))
        except sqlite3.Error as e:
            print(f"Error adding chunk for {doc_key}: {e}")
    
    def find_duplicate_by_doi(self, doi: str) -> Optional[Dict]:
        """Check if a document with this DOI already exists."""
        if not doi:
            return None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM documents WHERE doi = ?',
                (doi,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None
    
    def find_duplicates_by_title_year(self, title: str, year: Optional[int]) -> List[Dict]:
        """Find potential duplicates by title similarity and year."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Normalize title for comparison
            normalized_title = title.lower().strip()
            
            query = '''
                SELECT * FROM documents 
                WHERE LOWER(title) = ? OR LOWER(title) LIKE ?
            '''
            params = [normalized_title, f'%{normalized_title}%']
            
            if year:
                query += ' AND year = ?'
                params.append(year)
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def record_duplicate(self, canonical_doc_key: str, duplicate_doc_key: str,
                        duplicate_source: str = "doi_match"):
        """Record a detected duplicate."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO duplicates (canonical_doc_key, duplicate_doc_key, duplicate_source)
                    VALUES (?, ?, ?)
                ''', (canonical_doc_key, duplicate_doc_key, duplicate_source))
        except sqlite3.Error as e:
            print(f"Error recording duplicate: {e}")
    
    def get_duplicates(self) -> List[Dict]:
        """Get all detected duplicates."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT d.*, 
                       c.title as canonical_title,
                       dup.title as duplicate_title
                FROM duplicates d
                JOIN documents c ON d.canonical_doc_key = c.doc_key
                JOIN documents dup ON d.duplicate_doc_key = dup.doc_key
                ORDER BY d.detected_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def record_ingestion(self, source_path: str, source_type: str,
                        last_modified: Optional[datetime], entry_count: int):
        """Record ingestion event for incremental refresh tracking."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO ingestion_log (source_path, source_type, last_modified, entry_count)
                    VALUES (?, ?, ?, ?)
                ''', (source_path, source_type, last_modified, entry_count))
        except sqlite3.Error as e:
            print(f"Error recording ingestion: {e}")
    
    def get_last_ingestion(self, source_path: str) -> Optional[Dict]:
        """Get the last ingestion record for a source."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM ingestion_log 
                WHERE source_path = ?
                ORDER BY ingested_at DESC
                LIMIT 1
            ''', (source_path,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def needs_refresh(self, source_path: str, current_modified: datetime) -> bool:
        """Check if a source needs refresh based on modification time."""
        last = self.get_last_ingestion(source_path)
        if not last:
            return True
        
        last_modified = last.get('last_modified')
        if last_modified and current_modified > datetime.fromisoformat(last_modified):
            return True
        
        return False
    
    def update_note_content(self, doc_key: str, new_content: str) -> bool:
        """Update note content for a document (with history tracking)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Get current content
                cursor = conn.execute(
                    'SELECT content FROM chunks WHERE doc_key = ? AND source_type = "note" LIMIT 1',
                    (doc_key,)
                )
                old_chunk = cursor.fetchone()
                old_content = old_chunk[0] if old_chunk else ""
                
                # Record edit history
                conn.execute('''
                    INSERT INTO note_edits (doc_key, old_content, new_content)
                    VALUES (?, ?, ?)
                ''', (doc_key, old_content, new_content))
                
                # Delete old note chunks
                conn.execute(
                    'DELETE FROM chunks WHERE doc_key = ? AND source_type = "note"',
                    (doc_key,)
                )
                
                # Add new content as chunks
                # (This would need chunking logic - simplified here)
                conn.execute('''
                    INSERT INTO chunks (doc_key, source_type, content, chunk_index)
                    VALUES (?, ?, ?, ?)
                ''', (doc_key, 'note', new_content, 0))
                
                # Update document timestamp
                conn.execute('''
                    UPDATE documents SET updated_at = CURRENT_TIMESTAMP WHERE doc_key = ?
                ''', (doc_key,))
                
            return True
        except sqlite3.Error as e:
            print(f"Error updating note for {doc_key}: {e}")
            return False
    
    def get_note_edit_history(self, doc_key: str) -> List[Dict]:
        """Get edit history for a document's notes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM note_edits 
                WHERE doc_key = ?
                ORDER BY edited_at DESC
            ''', (doc_key,))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_chunks(self, query: str, filters: Optional[Dict] = None, k: int = 10) -> List[Dict]:
        """Search for chunks matching the query."""
        filters = filters or {}
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Build the query with FTS5
            sql = '''
                SELECT 
                    d.doc_key,
                    d.title,
                    d.year,
                    d.venue,
                    d.doi,
                    d.pdf_path,
                    d.note_path,
                    c.source_type,
                    c.content as snippet,
                    c.locator,
                    rank as score
                FROM chunks_fts fts
                JOIN chunks c ON fts.rowid = c.id
                JOIN documents d ON c.doc_key = d.doc_key
                WHERE chunks_fts MATCH ?
            '''
            params = [query]
            
            # Add filters
            if 'year' in filters:
                sql += ' AND d.year = ?'
                params.append(filters['year'])
            if 'venue' in filters:
                sql += ' AND d.venue LIKE ?'
                params.append(f'%{filters["venue"]}%')
            if 'source_type' in filters:
                sql += ' AND c.source_type = ?'
                params.append(filters['source_type'])
            
            sql += ' ORDER BY rank LIMIT ?'
            params.append(k)
            
            cursor = conn.execute(sql, params)
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get('locator'):
                    result['locator'] = json.loads(result['locator'])
                results.append(result)
            
            return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM documents')
            doc_count = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM chunks')
            chunk_count = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM chunks WHERE source_type = "pdf"')
            pdf_chunks = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM chunks WHERE source_type = "note"')
            note_chunks = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM duplicates')
            duplicate_count = cursor.fetchone()[0]
            
            return {
                'documents': doc_count,
                'chunks': chunk_count,
                'pdf_chunks': pdf_chunks,
                'note_chunks': note_chunks,
                'duplicates': duplicate_count
            }
    
    def get_document(self, doc_key: str) -> Optional[Dict]:
        """Get a document by key."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM documents WHERE doc_key = ?',
                (doc_key,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get('tags'):
                    result['tags'] = json.loads(result['tags'])
                if result.get('authors'):
                    result['authors'] = json.loads(result['authors'])
                return result
            return None
