"""
Database module for Literature Knowledge Base.
Handles SQLite connections, schema initialization, and basic CRUD operations.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class LiteratureDatabase:
    """Manages the SQLite database for literature indexing."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database with schema."""
        schema_path = Path(__file__).parent.parent / "schema" / "001_initial.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        with self._get_connection() as conn:
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())
    
    def add_document(self, doc_key: str, title: str, year: Optional[int],
                     venue: Optional[str], doi: Optional[str],
                     pdf_path: str, note_path: Optional[str],
                     tags: Optional[List[str]] = None) -> bool:
        """Add or update a document."""
        with self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO documents (doc_key, title, year, venue, doi, 
                                         pdf_path, note_path, tags, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(doc_key) DO UPDATE SET
                        title=excluded.title,
                        year=excluded.year,
                        venue=excluded.venue,
                        doi=excluded.doi,
                        pdf_path=excluded.pdf_path,
                        note_path=excluded.note_path,
                        tags=excluded.tags,
                        updated_at=CURRENT_TIMESTAMP
                """, (doc_key, title, year, venue, doi, pdf_path, note_path,
                      json.dumps(tags) if tags else None))
                return True
            except sqlite3.Error as e:
                print(f"Error adding document {doc_key}: {e}")
                return False
    
    def add_chunk(self, doc_key: str, source_type: str, text: str,
                  locator: Dict[str, Any], chunk_index: int) -> bool:
        """Add a content chunk."""
        with self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO chunks (doc_key, source_type, text, locator, chunk_index)
                    VALUES (?, ?, ?, ?, ?)
                """, (doc_key, source_type, text, json.dumps(locator), chunk_index))
                return True
            except sqlite3.Error as e:
                print(f"Error adding chunk for {doc_key}: {e}")
                return False
    
    def search_chunks(self, query: str, filters: Optional[Dict] = None,
                      k: int = 20) -> List[Dict]:
        """Search chunks using FTS5."""
        with self._get_connection() as conn:
            # Build the query with filters
            where_clauses = ["c.doc_key = d.doc_key"]
            params = []
            
            if filters:
                if 'year' in filters:
                    where_clauses.append("d.year = ?")
                    params.append(filters['year'])
                if 'venue' in filters:
                    where_clauses.append("d.venue = ?")
                    params.append(filters['venue'])
                if 'source_type' in filters:
                    where_clauses.append("c.source_type = ?")
                    params.append(filters['source_type'])
            
            # FTS5 query
            sql = f"""
                SELECT 
                    c.chunk_id,
                    c.doc_key,
                    c.source_type,
                    c.text,
                    c.locator,
                    c.chunk_index,
                    d.title,
                    d.year,
                    d.venue,
                    d.doi,
                    d.pdf_path,
                    d.note_path,
                    d.tags,
                    rank as score
                FROM chunks c
                JOIN documents d ON c.doc_key = d.doc_key
                JOIN chunks_fts f ON c.chunk_id = f.rowid
                WHERE {' AND '.join(where_clauses)}
                    AND chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            params.extend([query, k])
            
            cursor = conn.execute(sql, params)
            results = []
            for row in cursor.fetchall():
                results.append({
                    'chunk_id': row['chunk_id'],
                    'doc_key': row['doc_key'],
                    'title': row['title'],
                    'year': row['year'],
                    'venue': row['venue'],
                    'doi': row['doi'],
                    'source_type': row['source_type'],
                    'score': row['score'],
                    'snippet': row['text'],
                    'locator': json.loads(row['locator']) if row['locator'] else {},
                    'pdf_path': row['pdf_path'],
                    'note_path': row['note_path'],
                    'tags': json.loads(row['tags']) if row['tags'] else []
                })
            return results
    
    def get_document(self, doc_key: str) -> Optional[Dict]:
        """Get document metadata."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM documents WHERE doc_key = ?", (doc_key,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'doc_key': row['doc_key'],
                    'title': row['title'],
                    'year': row['year'],
                    'venue': row['venue'],
                    'doi': row['doi'],
                    'pdf_path': row['pdf_path'],
                    'note_path': row['note_path'],
                    'tags': json.loads(row['tags']) if row['tags'] else [],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
            return None
    
    def get_note_content(self, doc_key: str) -> Optional[str]:
        """Get full note content for a document."""
        doc = self.get_document(doc_key)
        if doc and doc['note_path'] and Path(doc['note_path']).exists():
            with open(doc['note_path'], 'r', encoding='utf-8') as f:
                return f.read()
        return None
    
    def delete_document(self, doc_key: str) -> bool:
        """Delete a document and all its chunks."""
        with self._get_connection() as conn:
            try:
                conn.execute("DELETE FROM documents WHERE doc_key = ?", (doc_key,))
                return True
            except sqlite3.Error as e:
                print(f"Error deleting document {doc_key}: {e}")
                return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with self._get_connection() as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            pdf_chunks = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE source_type = 'pdf'"
            ).fetchone()[0]
            note_chunks = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE source_type = 'note'"
            ).fetchone()[0]
            return {
                'documents': doc_count,
                'chunks': chunk_count,
                'pdf_chunks': pdf_chunks,
                'note_chunks': note_chunks
            }
