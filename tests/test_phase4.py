#!/usr/bin/env python3
"""
Targeted tests for enhanced BibTeX Phase 4 workflows.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from enhanced_database import EnhancedLiteratureDatabase


def seed_database(db: EnhancedLiteratureDatabase):
    """Create a small realistic fixture library."""
    db.add_document(
        doc_key="10.1000/alpha",
        title="Catalytic Protein Engineering for MOF Reactors",
        year=2024,
        venue="Nature Catalysis",
        doi="10.1000/alpha",
        pdf_path="/papers/alpha.pdf",
        note_path="/papers/My_Collection.bib",
        tags=["mof", "enzyme", "catalysis"],
        bibtex_key="Alpha2024",
        authors=["Smith, Jane", "Lee, Aaron"],
    )
    db.add_chunk(
        "10.1000/alpha",
        "note",
        "MOF scaffolds improve catalytic stability for enzyme cascades.",
        {"paragraph_start": 1},
        0,
    )
    db.add_chunk(
        "10.1000/alpha",
        "pdf",
        "The paper studies catalytic stability in protein-loaded MOF reactors.",
        {"page_start": 1, "page_end": 2},
        0,
    )

    db.add_document(
        doc_key="beta_2023",
        title="MOF Reactors for Multienzyme Cascades",
        year=2023,
        venue="Nature Catalysis",
        doi=None,
        pdf_path="/papers/beta.pdf",
        note_path="/papers/My_Collection.bib",
        tags=["mof", "multienzyme"],
        bibtex_key="Beta2023",
        authors=["Smith, Jane", "Patel, Mira"],
    )
    db.add_chunk(
        "beta_2023",
        "note",
        "Multienzyme cascades inside MOF reactors increase product yield.",
        {"paragraph_start": 1},
        0,
    )

    db.add_document(
        doc_key="gamma_2022",
        title="Transformer Models for Literature Mining",
        year=2022,
        venue="Bioinformatics",
        doi=None,
        pdf_path="",
        note_path="/papers/My_Collection.bib",
        tags=["nlp", "literature-mining"],
        bibtex_key="Gamma2022",
        authors=["Nguyen, Linh"],
    )
    db.add_chunk(
        "gamma_2022",
        "note",
        "Transformer encoders help mine literature corpora.",
        {"paragraph_start": 1},
        0,
    )


def test_phase4_database_features():
    """Test browsing, citation, related-doc, and note-history features."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "phase4.db"
        db = EnhancedLiteratureDatabase(str(db_path))
        seed_database(db)

        search_results = db.search_chunks("mof", filters={"source_type": "note"}, k=5)
        assert len(search_results) >= 2, "Expected multiple MOF search hits"
        assert search_results[0]["source_type"] == "note"

        filtered_docs = db.list_documents(filters={"venue": "Nature", "author": "Smith"}, limit=10)
        assert len(filtered_docs) == 2, "Venue + author filtering should return two docs"

        citation = db.get_citation("10.1000/alpha", style="apa")
        assert citation is not None, "Citation lookup should succeed"
        assert "Nature Catalysis" in citation["citation"]
        assert "https://doi.org/10.1000/alpha" in citation["citation"]

        bibtex = db.get_citation("10.1000/alpha", style="bibtex")
        assert bibtex is not None and "@article{Alpha2024" in bibtex["citation"]

        related = db.find_related_documents("10.1000/alpha", limit=5)
        assert related, "Should find related documents"
        assert related[0]["doc_key"] == "beta_2023", "Most related paper should share venue/authors/tags"

        original_note = db.get_note_content("10.1000/alpha")
        assert original_note and "catalytic stability" in original_note

        updated = db.update_note_content(
            "10.1000/alpha",
            "Updated note content for catalytic protein engineering.",
        )
        assert updated, "Note update should succeed"

        updated_note = db.get_note_content("10.1000/alpha")
        assert updated_note == "Updated note content for catalytic protein engineering."

        history = db.get_note_edit_history("10.1000/alpha")
        assert len(history) == 1, "Expected a single note edit history entry"
        assert "catalytic stability" in history[0]["old_content"]

        stats = db.get_stats()
        assert stats["documents"] == 3
        assert stats["duplicates"] == 0


def main():
    """Run the Phase 4 tests as a standalone script."""
    print("Running Phase 4 tests...\n")
    try:
        test_phase4_database_features()
        print("✅ Phase 4 tests passed!")
        return 0
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
