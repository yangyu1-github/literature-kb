#!/usr/bin/env python3
"""
Tests for Phase 2: Semantic search functionality.
"""

import sys
import tempfile
import shutil
from pathlib import Path

# Add mcp_server to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'mcp_server'))

from database import LiteratureDatabase
from semantic_search import EmbeddingGenerator, VectorStore, HybridSearcher
import numpy as np


def test_embedding_generator():
    """Test embedding generation."""
    print("Testing embedding generator...")
    
    generator = EmbeddingGenerator()
    
    # Test single encoding
    text = "This is a test sentence about machine learning."
    embedding = generator.encode_single(text)
    
    assert isinstance(embedding, np.ndarray), "Embedding should be numpy array"
    assert embedding.ndim == 1, "Embedding should be 1D vector"
    assert embedding.shape[0] > 0, "Embedding should have dimensions"
    
    # Test batch encoding
    texts = [
        "Machine learning is fascinating.",
        "Deep learning uses neural networks.",
        "Natural language processing is a subfield."
    ]
    embeddings = generator.encode(texts)
    
    assert embeddings.shape[0] == 3, "Should have 3 embeddings"
    assert embeddings.shape[1] == embedding.shape[0], "All embeddings should have same dimension"
    
    print("✓ Embedding generator tests passed!")
    return True


def test_vector_store():
    """Test vector store operations."""
    print("Testing vector store...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(tmpdir)
        
        # Test adding chunks
        chunk_ids = ["chunk_1", "chunk_2", "chunk_3"]
        texts = [
            "Machine learning algorithms learn from data.",
            "Neural networks are inspired by the brain.",
            "Transformers revolutionized NLP."
        ]
        
        # Create fake embeddings (in practice, use EmbeddingGenerator)
        embeddings = np.random.rand(3, 384).astype(np.float32)
        
        metadatas = [
            {"doc_key": "doc1", "title": "ML Basics", "source_type": "note"},
            {"doc_key": "doc2", "title": "Neural Nets", "source_type": "pdf"},
            {"doc_key": "doc3", "title": "Transformers", "source_type": "note"}
        ]
        
        store.add_chunks(chunk_ids, texts, embeddings, metadatas)
        
        # Test count
        assert store.count() == 3, f"Expected 3 chunks, got {store.count()}"
        
        # Test search
        query_embedding = embeddings[0]  # Use first embedding as query
        results = store.search(query_embedding, k=2)
        
        assert len(results) == 2, "Should return 2 results"
        assert results[0]['chunk_id'] == "chunk_1", "First result should be most similar"
        assert 'semantic_score' in results[0], "Results should have semantic_score"
        
        print("✓ Vector store tests passed!")
        return True


def test_hybrid_search():
    """Test hybrid search combining BM25 and semantic."""
    print("Testing hybrid search...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        vector_path = Path(tmpdir) / "chroma"
        
        # Setup
        db = LiteratureDatabase(str(db_path))
        vector_store = VectorStore(str(vector_path))
        embedding_generator = EmbeddingGenerator()
        
        # Add test documents
        db.add_document(
            doc_key="ml_intro",
            title="Introduction to Machine Learning",
            year=2023,
            venue="Tutorial",
            doi=None,
            pdf_path="/path/to/ml.pdf",
            note_path="/path/to/ml.md",
            tags=["ml", "tutorial"]
        )
        
        db.add_document(
            doc_key="nlp_survey",
            title="Natural Language Processing Survey",
            year=2023,
            venue="Survey",
            doi=None,
            pdf_path="/path/to/nlp.pdf",
            note_path="/path/to/nlp.md",
            tags=["nlp", "survey"]
        )
        
        # Add chunks
        ml_text = "Machine learning is a subset of artificial intelligence."
        nlp_text = "Natural language processing enables computers to understand text."
        
        db.add_chunk("ml_intro", "note", ml_text, {"page": 1}, 0)
        db.add_chunk("nlp_survey", "note", nlp_text, {"page": 1}, 0)
        
        # Add to vector store
        embeddings = embedding_generator.encode([ml_text, nlp_text])
        vector_store.add_chunks(
            ["1", "2"],
            [ml_text, nlp_text],
            embeddings,
            [
                {"doc_key": "ml_intro", "title": "Introduction to Machine Learning", "source_type": "note"},
                {"doc_key": "nlp_survey", "title": "Natural Language Processing Survey", "source_type": "note"}
            ]
        )
        
        # Test hybrid search
        searcher = HybridSearcher(db, vector_store, embedding_generator, semantic_weight=0.5)
        results = searcher.search("machine learning AI", k=5)
        
        assert len(results) > 0, "Should return results"
        assert 'hybrid_score' in results[0], "Results should have hybrid_score"
        assert 'bm25_score' in results[0], "Results should have bm25_score"
        assert 'semantic_score' in results[0], "Results should have semantic_score"
        
        print("✓ Hybrid search tests passed!")
        return True


def main():
    """Run all Phase 2 tests."""
    print("Running Phase 2 (Semantic Search) tests...\n")
    
    try:
        test_embedding_generator()
        test_vector_store()
        test_hybrid_search()
        print("\n✅ All Phase 2 tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
