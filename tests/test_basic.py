#!/usr/bin/env python3
"""
Basic tests for Literature Knowledge Base.
"""

import sys
import tempfile
import shutil
from pathlib import Path

# Add mcp_server to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'mcp_server'))

from database import LiteratureDatabase


def test_database():
    """Test database operations."""
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = LiteratureDatabase(str(db_path))
        
        # Test adding document
        success = db.add_document(
            doc_key="test_paper_2023",
            title="Test Paper",
            year=2023,
            venue="Test Venue",
            doi="10.1234/test",
            pdf_path="/path/to/test.pdf",
            note_path="/path/to/test.mendeley.md",
            tags=["test", "example"]
        )
        assert success, "Failed to add document"
        
        # Test retrieving document
        doc = db.get_document("test_paper_2023")
        assert doc is not None, "Failed to retrieve document"
        assert doc['title'] == "Test Paper"
        assert doc['year'] == 2023
        
        # Test adding chunks
        db.add_chunk(
            doc_key="test_paper_2023",
            source_type="note",
            text="This is a test note about the paper.",
            locator={"page": 1},
            chunk_index=0
        )
        
        db.add_chunk(
            doc_key="test_paper_2023",
            source_type="pdf",
            text="This is extracted text from the PDF.",
            locator={"page_start": 1, "page_end": 2},
            chunk_index=0
        )
        
        # Test search
        results = db.search_chunks("test note", k=10)
        assert len(results) > 0, "Search returned no results"
        assert results[0]['source_type'] == 'note'
        
        # Test stats
        stats = db.get_stats()
        assert stats['documents'] == 1
        assert stats['chunks'] == 2
        
        print("✓ All database tests passed!")
        return True


def test_note_parser():
    """Test note file parsing."""
    from ingestion import NoteParser
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        note_path = Path(tmpdir) / "test.mendeley.md"
        
        # Create test note with YAML front matter
        note_content = """---
title: "Test Paper Title"
year: 2023
venue: "Nature"
doi: "10.1234/test"
pdf_path: "/path/to/paper.pdf"
tags: ["machine learning", "neuroscience"]
---

[Page 1] Highlight: This is an important finding.

[Page 2] Note: This relates to previous work.

Summary: The paper presents...
"""
        note_path.write_text(note_content)
        
        parser = NoteParser()
        metadata, body = parser.parse(note_path)
        
        assert metadata.title == "Test Paper Title"
        assert metadata.year == 2023
        assert metadata.venue == "Nature"
        assert metadata.doi == "10.1234/test"
        assert metadata.pdf_path == "/path/to/paper.pdf"
        assert "machine learning" in metadata.tags
        
        print("✓ Note parser tests passed!")
        return True


def main():
    """Run all tests."""
    print("Running Literature Knowledge Base tests...\n")
    
    try:
        test_database()
        test_note_parser()
        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
