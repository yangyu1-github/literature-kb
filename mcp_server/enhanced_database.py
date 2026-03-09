"""
Enhanced database operations for the BibTeX-first literature knowledge base.

Phase 3 adds duplicate detection, incremental refresh tracking, and note edit
history. Phase 4 adds browsing, citation export, and related-document lookup.
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class EnhancedLiteratureDatabase:
    """Extended database class with Phase 3 and Phase 4 features."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database with schema including Phase 3 tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                '''
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

                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_key TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('pdf', 'note')),
                    content TEXT NOT NULL,
                    locator TEXT,
                    chunk_index INTEGER,
                    FOREIGN KEY (doc_key) REFERENCES documents(doc_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ingestion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('bibtex', 'pdf')),
                    last_modified TIMESTAMP,
                    entry_count INTEGER,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS duplicates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_doc_key TEXT NOT NULL,
                    duplicate_doc_key TEXT NOT NULL,
                    duplicate_source TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (canonical_doc_key) REFERENCES documents(doc_key),
                    FOREIGN KEY (duplicate_doc_key) REFERENCES documents(doc_key)
                );

                CREATE TABLE IF NOT EXISTS note_edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_key TEXT NOT NULL,
                    old_content TEXT,
                    new_content TEXT,
                    edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (doc_key) REFERENCES documents(doc_key) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_doc_key ON chunks(doc_key);
                CREATE INDEX IF NOT EXISTS idx_chunks_source_type ON chunks(source_type);
                CREATE INDEX IF NOT EXISTS idx_documents_doi ON documents(doi);
                CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
                CREATE INDEX IF NOT EXISTS idx_documents_venue ON documents(venue);
                CREATE INDEX IF NOT EXISTS idx_ingestion_log_path ON ingestion_log(source_path);
                '''
            )

            # Keep the FTS table in external-content mode so delete/update triggers work.
            fts_row = conn.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table' AND name = 'chunks_fts'
                """
            ).fetchone()
            fts_sql = fts_row[0] if fts_row else ""
            if "content='chunks'" not in fts_sql and 'content="chunks"' not in fts_sql:
                conn.execute("DROP TRIGGER IF EXISTS chunks_ai")
                conn.execute("DROP TRIGGER IF EXISTS chunks_ad")
                conn.execute("DROP TRIGGER IF EXISTS chunks_au")
                conn.execute("DROP TABLE IF EXISTS chunks_fts")
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE chunks_fts USING fts5(
                        content,
                        content='chunks',
                        content_rowid='id'
                    )
                    """
                )

            conn.executescript(
                '''
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
                END;

                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
                END;

                CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
                    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
                END;
                '''
            )
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")

    def _row_to_document(self, row: sqlite3.Row) -> Dict:
        """Convert a sqlite row into a document dict with decoded JSON fields."""
        result = dict(row)
        if result.get("tags"):
            result["tags"] = json.loads(result["tags"])
        else:
            result["tags"] = []
        if result.get("authors"):
            result["authors"] = json.loads(result["authors"])
        else:
            result["authors"] = []
        return result

    def add_document(
        self,
        doc_key: str,
        title: str,
        year: Optional[int] = None,
        venue: Optional[str] = None,
        doi: Optional[str] = None,
        pdf_path: str = "",
        note_path: str = "",
        tags: Optional[List[str]] = None,
        bibtex_key: Optional[str] = None,
        authors: Optional[List[str]] = None,
    ) -> bool:
        """Add or update a document."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO documents
                    (doc_key, title, year, venue, doi, pdf_path, note_path, tags,
                     updated_at, bibtex_key, authors)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                    ON CONFLICT(doc_key) DO UPDATE SET
                        title=excluded.title,
                        year=excluded.year,
                        venue=excluded.venue,
                        doi=excluded.doi,
                        pdf_path=excluded.pdf_path,
                        note_path=excluded.note_path,
                        tags=excluded.tags,
                        updated_at=CURRENT_TIMESTAMP,
                        bibtex_key=excluded.bibtex_key,
                        authors=excluded.authors
                    ''',
                    (
                        doc_key,
                        title,
                        year,
                        venue,
                        doi,
                        pdf_path,
                        note_path,
                        json.dumps(tags) if tags else None,
                        bibtex_key,
                        json.dumps(authors) if authors else None,
                    ),
                )
            return True
        except sqlite3.Error as e:
            print(f"Error adding document {doc_key}: {e}")
            return False

    def add_chunk(
        self,
        doc_key: str,
        source_type: str,
        content: str,
        locator: Optional[Dict] = None,
        chunk_index: int = 0,
    ):
        """Add a content chunk to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO chunks (doc_key, source_type, content, locator, chunk_index)
                    VALUES (?, ?, ?, ?, ?)
                    ''',
                    (
                        doc_key,
                        source_type,
                        content,
                        json.dumps(locator) if locator else None,
                        chunk_index,
                    ),
                )
        except sqlite3.Error as e:
            print(f"Error adding chunk for {doc_key}: {e}")

    def find_duplicate_by_doi(self, doi: str) -> Optional[Dict]:
        """Check if a document with this DOI already exists."""
        if not doi:
            return None

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM documents WHERE doi = ?",
                (doi,),
            ).fetchone()
            return self._row_to_document(row) if row else None

    def find_duplicates_by_title_year(self, title: str, year: Optional[int]) -> List[Dict]:
        """Find potential duplicates by title similarity and year."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            normalized_title = title.lower().strip()
            query = """
                SELECT * FROM documents
                WHERE (LOWER(title) = ? OR LOWER(title) LIKE ?)
            """
            params = [normalized_title, f"%{normalized_title}%"]

            if year:
                query += " AND year = ?"
                params.append(year)

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_document(row) for row in rows]

    def record_duplicate(
        self, canonical_doc_key: str, duplicate_doc_key: str, duplicate_source: str = "doi_match"
    ):
        """Record a detected duplicate."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO duplicates (canonical_doc_key, duplicate_doc_key, duplicate_source)
                    VALUES (?, ?, ?)
                    ''',
                    (canonical_doc_key, duplicate_doc_key, duplicate_source),
                )
        except sqlite3.Error as e:
            print(f"Error recording duplicate: {e}")

    def get_duplicates(self) -> List[Dict]:
        """Get all detected duplicates."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                '''
                SELECT d.*,
                       c.title AS canonical_title,
                       dup.title AS duplicate_title
                FROM duplicates d
                JOIN documents c ON d.canonical_doc_key = c.doc_key
                JOIN documents dup ON d.duplicate_doc_key = dup.doc_key
                ORDER BY d.detected_at DESC
                '''
            ).fetchall()
            return [dict(row) for row in rows]

    def record_ingestion(
        self, source_path: str, source_type: str, last_modified: Optional[datetime], entry_count: int
    ):
        """Record ingestion event for incremental refresh tracking."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO ingestion_log (source_path, source_type, last_modified, entry_count)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (source_path, source_type, last_modified, entry_count),
                )
        except sqlite3.Error as e:
            print(f"Error recording ingestion: {e}")

    def get_last_ingestion(self, source_path: str) -> Optional[Dict]:
        """Get the last ingestion record for a source."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                '''
                SELECT * FROM ingestion_log
                WHERE source_path = ?
                ORDER BY ingested_at DESC
                LIMIT 1
                ''',
                (source_path,),
            ).fetchone()
            return dict(row) if row else None

    def needs_refresh(self, source_path: str, current_modified: datetime) -> bool:
        """Check if a source needs refresh based on modification time."""
        last = self.get_last_ingestion(source_path)
        if not last:
            return True

        last_modified = last.get("last_modified")
        if last_modified and current_modified > datetime.fromisoformat(last_modified):
            return True

        return False

    def update_note_content(self, doc_key: str, new_content: str) -> bool:
        """Update note content for a document and record edit history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    '''
                    SELECT content
                    FROM chunks
                    WHERE doc_key = ? AND source_type = "note"
                    ORDER BY chunk_index
                    ''',
                    (doc_key,),
                )
                old_content = "\n\n".join(row[0] for row in cursor.fetchall())

                conn.execute(
                    '''
                    INSERT INTO note_edits (doc_key, old_content, new_content)
                    VALUES (?, ?, ?)
                    ''',
                    (doc_key, old_content, new_content),
                )

                conn.execute(
                    'DELETE FROM chunks WHERE doc_key = ? AND source_type = "note"',
                    (doc_key,),
                )
                conn.execute(
                    '''
                    INSERT INTO chunks (doc_key, source_type, content, chunk_index)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (doc_key, "note", new_content, 0),
                )
                conn.execute(
                    "UPDATE documents SET updated_at = CURRENT_TIMESTAMP WHERE doc_key = ?",
                    (doc_key,),
                )

            return True
        except sqlite3.Error as e:
            print(f"Error updating note for {doc_key}: {e}")
            return False

    def get_note_edit_history(self, doc_key: str) -> List[Dict]:
        """Get edit history for a document's notes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                '''
                SELECT * FROM note_edits
                WHERE doc_key = ?
                ORDER BY edited_at DESC
                ''',
                (doc_key,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_note_content(self, doc_key: str) -> Optional[str]:
        """Return the full concatenated note content for a document."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                '''
                SELECT content
                FROM chunks
                WHERE doc_key = ? AND source_type = "note"
                ORDER BY chunk_index
                ''',
                (doc_key,),
            )
            parts = [row[0] for row in cursor.fetchall()]
            return "\n\n".join(parts) if parts else None

    def search_chunks(self, query: str, filters: Optional[Dict] = None, k: int = 10) -> List[Dict]:
        """Search for chunks matching the query."""
        filters = filters or {}

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = '''
                SELECT
                    d.doc_key,
                    d.title,
                    d.year,
                    d.venue,
                    d.doi,
                    d.pdf_path,
                    d.note_path,
                    d.tags,
                    d.authors,
                    c.id AS chunk_id,
                    c.source_type,
                    c.content AS snippet,
                    c.locator,
                    bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.id
                JOIN documents d ON c.doc_key = d.doc_key
                WHERE chunks_fts MATCH ?
            '''
            params = [query]

            if "year" in filters:
                sql += " AND d.year = ?"
                params.append(filters["year"])
            if "venue" in filters:
                sql += " AND d.venue LIKE ?"
                params.append(f'%{filters["venue"]}%')
            if "source_type" in filters:
                sql += " AND c.source_type = ?"
                params.append(filters["source_type"])

            sql += " ORDER BY score LIMIT ?"
            params.append(k)

            rows = conn.execute(sql, params).fetchall()
            results = []
            for row in rows:
                result = dict(row)
                result["locator"] = json.loads(result["locator"]) if result.get("locator") else {}
                result["tags"] = json.loads(result["tags"]) if result.get("tags") else []
                result["authors"] = json.loads(result["authors"]) if result.get("authors") else []
                results.append(result)
            return results

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with sqlite3.connect(self.db_path) as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            pdf_chunks = conn.execute(
                'SELECT COUNT(*) FROM chunks WHERE source_type = "pdf"'
            ).fetchone()[0]
            note_chunks = conn.execute(
                'SELECT COUNT(*) FROM chunks WHERE source_type = "note"'
            ).fetchone()[0]
            duplicate_count = conn.execute("SELECT COUNT(*) FROM duplicates").fetchone()[0]

            return {
                "documents": doc_count,
                "chunks": chunk_count,
                "pdf_chunks": pdf_chunks,
                "note_chunks": note_chunks,
                "duplicates": duplicate_count,
            }

    def get_document(self, doc_key: str) -> Optional[Dict]:
        """Get a document by key."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM documents WHERE doc_key = ?",
                (doc_key,),
            ).fetchone()
            return self._row_to_document(row) if row else None

    def list_documents(
        self, filters: Optional[Dict] = None, limit: int = 20, offset: int = 0
    ) -> List[Dict]:
        """Browse documents with optional metadata filters."""
        filters = filters or {}
        sql = "SELECT * FROM documents WHERE 1=1"
        params: List = []

        if "year" in filters:
            sql += " AND year = ?"
            params.append(filters["year"])
        if "venue" in filters:
            sql += " AND venue LIKE ?"
            params.append(f'%{filters["venue"]}%')
        if "has_pdf" in filters:
            if filters["has_pdf"]:
                sql += " AND pdf_path IS NOT NULL AND pdf_path != ''"
            else:
                sql += " AND (pdf_path IS NULL OR pdf_path = '')"
        if "title_contains" in filters:
            sql += " AND title LIKE ?"
            params.append(f'%{filters["title_contains"]}%')

        sql += " ORDER BY COALESCE(year, 0) DESC, title ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            docs = [self._row_to_document(row) for row in conn.execute(sql, params).fetchall()]

        author_filter = filters.get("author")
        tag_filter = filters.get("tag")
        if author_filter:
            needle = author_filter.lower()
            docs = [
                doc
                for doc in docs
                if any(needle in author.lower() for author in doc.get("authors", []))
            ]
        if tag_filter:
            needle = tag_filter.lower()
            docs = [
                doc
                for doc in docs
                if any(needle == tag.lower() or needle in tag.lower() for tag in doc.get("tags", []))
            ]

        return docs

    def get_citation(self, doc_key: str, style: str = "apa") -> Optional[Dict]:
        """Format a document citation for assistant workflows."""
        doc = self.get_document(doc_key)
        if not doc:
            return None

        style = (style or "apa").lower()
        if style == "bibtex":
            citation_text = self._format_bibtex(doc)
        elif style == "short":
            citation_text = self._format_short_citation(doc)
        else:
            citation_text = self._format_apa_citation(doc)

        return {
            "doc_key": doc["doc_key"],
            "style": style,
            "citation": citation_text,
            "title": doc["title"],
            "year": doc.get("year"),
            "doi": doc.get("doi"),
        }

    def _format_short_citation(self, doc: Dict) -> str:
        """Return a concise citation string."""
        author_part = self._format_author_list(doc.get("authors", []), short=True)
        year_part = str(doc["year"]) if doc.get("year") else "n.d."
        venue_part = doc.get("venue") or "Unknown venue"
        return f"{author_part} ({year_part}). {doc['title']}. {venue_part}."

    def _format_apa_citation(self, doc: Dict) -> str:
        """Return a lightweight APA-style citation."""
        author_part = self._format_author_list(doc.get("authors", []), short=False)
        year_part = str(doc["year"]) if doc.get("year") else "n.d."
        venue_part = doc.get("venue") or "Unknown venue"
        citation = f"{author_part} ({year_part}). {doc['title']}. {venue_part}."
        if doc.get("doi"):
            citation += f" https://doi.org/{doc['doi']}"
        return citation

    def _format_bibtex(self, doc: Dict) -> str:
        """Return a minimal BibTeX reconstruction from stored metadata."""
        entry_type = "article" if doc.get("venue") else "misc"
        bibtex_key = doc.get("bibtex_key") or doc["doc_key"]
        lines = [f"@{entry_type}{{{bibtex_key},"]
        lines.append(f"  title = {{{doc['title']}}},")
        if doc.get("authors"):
            lines.append(f"  author = {{{' and '.join(doc['authors'])}}},")
        if doc.get("venue"):
            lines.append(f"  journal = {{{doc['venue']}}},")
        if doc.get("year"):
            lines.append(f"  year = {{{doc['year']}}},")
        if doc.get("doi"):
            lines.append(f"  doi = {{{doc['doi']}}},")
        lines.append("}")
        return "\n".join(lines)

    def _format_author_list(self, authors: List[str], short: bool) -> str:
        """Format authors for citations."""
        if not authors:
            return "Unknown author"

        formatted = [self._format_person_name(name, short=short) for name in authors[:8]]
        if len(formatted) == 1:
            return formatted[0]
        if len(formatted) == 2:
            return f"{formatted[0]} & {formatted[1]}"
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"

    def _format_person_name(self, name: str, short: bool) -> str:
        """Format a single name."""
        name = " ".join(name.split())
        if "," in name:
            last, first = [part.strip() for part in name.split(",", 1)]
            if short:
                return last
            initials = " ".join(f"{part[0]}." for part in first.split() if part)
            return f"{last}, {initials}".strip()

        parts = name.split()
        if not parts:
            return "Unknown"
        last = parts[-1]
        if short:
            return last
        initials = " ".join(f"{part[0]}." for part in parts[:-1] if part)
        return f"{last}, {initials}".strip()

    def find_related_documents(self, doc_key: str, limit: int = 10) -> List[Dict]:
        """Find related documents using shared metadata heuristics."""
        target = self.get_document(doc_key)
        if not target:
            return []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM documents WHERE doc_key != ?",
                (doc_key,),
            ).fetchall()
            candidates = [self._row_to_document(row) for row in rows]

        target_authors = {author.lower() for author in target.get("authors", [])}
        target_tags = {tag.lower() for tag in target.get("tags", [])}
        target_tokens = self._tokenize_title(target.get("title", ""))

        ranked = []
        for candidate in candidates:
            score = 0.0
            reasons = []

            candidate_authors = {author.lower() for author in candidate.get("authors", [])}
            shared_authors = target_authors & candidate_authors
            if shared_authors:
                shared_score = 2.0 * len(shared_authors)
                score += shared_score
                reasons.append(f"shared authors: {', '.join(sorted(shared_authors))}")

            candidate_tags = {tag.lower() for tag in candidate.get("tags", [])}
            shared_tags = target_tags & candidate_tags
            if shared_tags:
                tag_score = 1.5 * len(shared_tags)
                score += tag_score
                reasons.append(f"shared tags: {', '.join(sorted(shared_tags))}")

            if target.get("venue") and candidate.get("venue") == target.get("venue"):
                score += 1.5
                reasons.append(f"same venue: {target['venue']}")

            if target.get("year") and candidate.get("year"):
                year_gap = abs(candidate["year"] - target["year"])
                if year_gap == 0:
                    score += 1.0
                    reasons.append("same year")
                elif year_gap == 1:
                    score += 0.5
                    reasons.append("adjacent year")

            candidate_tokens = self._tokenize_title(candidate.get("title", ""))
            shared_tokens = target_tokens & candidate_tokens
            if shared_tokens:
                title_score = min(2.0, len(shared_tokens) * 0.4)
                score += title_score
                reasons.append(
                    "title overlap: " + ", ".join(sorted(list(shared_tokens))[:5])
                )

            if score > 0:
                ranked.append(
                    {
                        "doc_key": candidate["doc_key"],
                        "title": candidate["title"],
                        "year": candidate.get("year"),
                        "venue": candidate.get("venue"),
                        "doi": candidate.get("doi"),
                        "score": round(score, 3),
                        "reasons": reasons,
                    }
                )

        ranked.sort(key=lambda item: (-item["score"], item["title"].lower()))
        return ranked[:limit]

    def _tokenize_title(self, title: str) -> set:
        """Tokenize a title into lowercase content words."""
        tokens = re.findall(r"\w+", title.lower())
        stopwords = {"the", "and", "for", "with", "from", "into", "using", "via", "of", "a", "an"}
        return {token for token in tokens if token not in stopwords and len(token) > 2}
