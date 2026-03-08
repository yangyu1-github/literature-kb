-- Literature Knowledge Base Schema
-- SQLite with FTS5 for full-text search

-- Main documents table
CREATE TABLE IF NOT EXISTS documents (
    doc_key TEXT PRIMARY KEY,  -- DOI or normalized(title+year+venue)
    title TEXT NOT NULL,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    pdf_path TEXT NOT NULL,
    note_path TEXT,
    tags TEXT,  -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-text search index for documents metadata
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    venue,
    content='documents',
    content_rowid='rowid'
);

-- Content chunks table (both PDF and note chunks)
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_key TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('pdf', 'note')),
    text TEXT NOT NULL,
    locator TEXT,  -- JSON: page range for PDFs, section/offset for notes
    chunk_index INTEGER,  -- ordering within document
    FOREIGN KEY (doc_key) REFERENCES documents(doc_key) ON DELETE CASCADE
);

-- Full-text search index for chunks
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='chunk_id'
);

-- Triggers to keep FTS indexes in sync
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, venue)
    VALUES (new.rowid, new.title, new.venue);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, venue)
    VALUES ('delete', old.rowid, old.title, old.venue);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, venue)
    VALUES ('delete', old.rowid, old.title, old.venue);
    INSERT INTO documents_fts(rowid, title, venue)
    VALUES (new.rowid, new.title, new.venue);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text)
    VALUES (new.chunk_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text)
    VALUES ('delete', old.chunk_id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text)
    VALUES ('delete', old.chunk_id, old.text);
    INSERT INTO chunks_fts(rowid, text)
    VALUES (new.chunk_id, new.text);
END;

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_chunks_doc_key ON chunks(doc_key);
CREATE INDEX IF NOT EXISTS idx_chunks_source_type ON chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_venue ON documents(venue);
