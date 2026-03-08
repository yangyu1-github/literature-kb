"""
Semantic search module for Literature Knowledge Base.
Adds embedding-based retrieval using sentence-transformers and ChromaDB.
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import json

# Lazy imports - only load when needed
def get_sentence_transformer():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer

def get_chromadb():
    import chromadb
    return chromadb


class EmbeddingGenerator:
    """Generate embeddings for text chunks using sentence-transformers."""
    
    # Lightweight model good for academic/scientific text
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None
    
    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None:
            SentenceTransformer = get_sentence_transformer()
            print(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""
        return self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    
    def encode_single(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        return self.model.encode(text, show_progress_bar=False, convert_to_numpy=True)


class VectorStore:
    """ChromaDB wrapper for storing and searching embeddings."""
    
    COLLECTION_NAME = "literature_chunks"
    
    def __init__(self, persist_directory: str):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.parent.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
    
    @property
    def client(self):
        """Lazy load ChromaDB client."""
        if self._client is None:
            chromadb = get_chromadb()
            self._client = chromadb.PersistentClient(path=str(self.persist_directory))
        return self._client
    
    @property
    def collection(self):
        """Lazy load collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
        return self._collection
    
    def add_chunks(self, chunk_ids: List[str], texts: List[str], 
                   embeddings: np.ndarray, metadatas: List[Dict[str, Any]]):
        """Add chunks with embeddings to the vector store."""
        # Convert embeddings to list for ChromaDB
        embeddings_list = embeddings.tolist() if isinstance(embeddings, np.ndarray) else embeddings
        
        self.collection.add(
            ids=chunk_ids,
            documents=texts,
            embeddings=embeddings_list,
            metadatas=metadatas
        )
    
    def search(self, query_embedding: np.ndarray, k: int = 20,
               filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Search for similar chunks."""
        query_embedding_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding
        
        # Build where clause for filters
        where_clause = None
        if filters:
            conditions = []
            if 'source_type' in filters:
                conditions.append({"source_type": filters['source_type']})
            if 'year' in filters:
                conditions.append({"year": filters['year']})
            if 'venue' in filters:
                conditions.append({"venue": filters['venue']})
            
            if len(conditions) == 1:
                where_clause = conditions[0]
            elif len(conditions) > 1:
                where_clause = {"$and": conditions}
        
        results = self.collection.query(
            query_embeddings=[query_embedding_list],
            n_results=k,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        hits = []
        if results['ids'] and len(results['ids'][0]) > 0:
            for i in range(len(results['ids'][0])):
                # Convert cosine distance to similarity score (1 - distance)
                similarity = 1 - results['distances'][0][i]
                hits.append({
                    'chunk_id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'semantic_score': similarity
                })
        
        return hits
    
    def delete_by_doc_key(self, doc_key: str):
        """Delete all chunks for a document."""
        self.collection.delete(where={"doc_key": doc_key})
    
    def count(self) -> int:
        """Get total number of chunks."""
        return self.collection.count()
    
    def reset(self):
        """Clear all data."""
        self.client.delete_collection(self.COLLECTION_NAME)
        self._collection = None


class HybridSearcher:
    """Combine BM25 (keyword) and semantic search with hybrid scoring."""
    
    def __init__(self, db, vector_store: VectorStore, 
                 embedding_generator: EmbeddingGenerator,
                 semantic_weight: float = 0.5):
        """
        Initialize hybrid searcher.
        
        Args:
            db: LiteratureDatabase instance for BM25 search
            vector_store: VectorStore instance for semantic search
            embedding_generator: EmbeddingGenerator instance
            semantic_weight: Weight for semantic score (0-1). 
                           0 = BM25 only, 1 = semantic only, 0.5 = equal weight
        """
        self.db = db
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.semantic_weight = semantic_weight
    
    def search(self, query: str, filters: Optional[Dict] = None,
               k: int = 20, k_bm25: int = 50, k_semantic: int = 50) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining BM25 and semantic similarity.
        
        Args:
            query: Search query
            filters: Optional filters (year, venue, source_type)
            k: Number of final results to return
            k_bm25: Number of BM25 candidates to retrieve
            k_semantic: Number of semantic candidates to retrieve
        
        Returns:
            Ranked list of results with hybrid scores
        """
        # Get BM25 results
        bm25_results = self.db.search_chunks(query, filters, k=k_bm25)
        
        # Get semantic results
        query_embedding = self.embedding_generator.encode_single(query)
        semantic_results = self.vector_store.search(query_embedding, k=k_semantic, filters=filters)
        
        # Combine and score
        combined = self._combine_results(bm25_results, semantic_results)
        
        # Sort by hybrid score and return top k
        combined.sort(key=lambda x: x['hybrid_score'], reverse=True)
        return combined[:k]
    
    def _combine_results(self, bm25_results: List[Dict], 
                         semantic_results: List[Dict]) -> List[Dict]:
        """Combine BM25 and semantic results with hybrid scoring."""
        # Normalize scores to 0-1 range
        bm25_scores = [r.get('score', 0) for r in bm25_results]
        semantic_scores = [r['semantic_score'] for r in semantic_results]
        
        if bm25_scores:
            bm25_min, bm25_max = min(bm25_scores), max(bm25_scores)
            bm25_range = bm25_max - bm25_min if bm25_max > bm25_min else 1
        else:
            bm25_min, bm25_range = 0, 1
        
        # Build result map by chunk_id
        result_map = {}
        
        # Process BM25 results
        for r in bm25_results:
            chunk_id = str(r.get('chunk_id', r.get('doc_key', '')))
            normalized_bm25 = (r.get('score', 0) - bm25_min) / bm25_range if bm25_range > 0 else 0
            
            result_map[chunk_id] = {
                'chunk_id': chunk_id,
                'doc_key': r.get('doc_key', ''),
                'title': r.get('title', ''),
                'year': r.get('year'),
                'venue': r.get('venue', ''),
                'doi': r.get('doi', ''),
                'source_type': r.get('source_type', ''),
                'snippet': r.get('snippet', r.get('text', '')),
                'locator': r.get('locator', {}),
                'pdf_path': r.get('pdf_path', ''),
                'note_path': r.get('note_path', ''),
                'tags': r.get('tags', []),
                'bm25_score': normalized_bm25,
                'semantic_score': 0.0
            }
        
        # Process semantic results
        for r in semantic_results:
            chunk_id = r['chunk_id']
            
            if chunk_id in result_map:
                # Update existing entry
                result_map[chunk_id]['semantic_score'] = r['semantic_score']
            else:
                # Create new entry
                meta = r['metadata']
                result_map[chunk_id] = {
                    'chunk_id': chunk_id,
                    'doc_key': meta.get('doc_key', ''),
                    'title': meta.get('title', ''),
                    'year': meta.get('year'),
                    'venue': meta.get('venue', ''),
                    'doi': meta.get('doi', ''),
                    'source_type': meta.get('source_type', ''),
                    'snippet': r['text'],
                    'locator': json.loads(meta.get('locator', '{}')),
                    'pdf_path': meta.get('pdf_path', ''),
                    'note_path': meta.get('note_path', ''),
                    'tags': json.loads(meta.get('tags', '[]')) if meta.get('tags') else [],
                    'bm25_score': 0.0,
                    'semantic_score': r['semantic_score']
                }
        
        # Calculate hybrid scores
        w = self.semantic_weight
        for item in result_map.values():
            item['hybrid_score'] = (1 - w) * item['bm25_score'] + w * item['semantic_score']
        
        return list(result_map.values())


class SemanticIngester:
    """Extended ingester that generates embeddings for semantic search."""
    
    def __init__(self, db, vector_store: VectorStore,
                 embedding_generator: EmbeddingGenerator,
                 pdf_root: str, notes_root: str,
                 pdf_chunk_size: int = 2000, note_chunk_size: int = 1500):
        from ingestion import LibraryIngester
        
        self.base_ingester = LibraryIngester(
            db, pdf_root, notes_root, pdf_chunk_size, note_chunk_size
        )
        self.db = db
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
    
    def ingest_note(self, note_path: Path) -> bool:
        """Ingest a note with embeddings."""
        # First do base ingestion
        success = self.base_ingester.ingest_note(note_path)
        if not success:
            return False
        
        # Get the document key
        from ingestion import NoteParser
        metadata, content = NoteParser().parse(note_path)
        
        import re
        normalized = re.sub(r'[^\w\s]', '', metadata.title.lower())
        normalized = re.sub(r'\s+', '_', normalized.strip())
        doc_key = metadata.doi if metadata.doi else normalized
        
        # Generate embeddings for note chunks
        # Get chunks from database
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT chunk_id, text, locator FROM chunks WHERE doc_key = ? AND source_type = 'note'",
            (doc_key,)
        )
        
        chunks = cursor.fetchall()
        conn.close()
        
        if chunks:
            texts = [c['text'] for c in chunks]
            embeddings = self.embedding_generator.encode(texts)
            
            chunk_ids = [str(c['chunk_id']) for c in chunks]
            metadatas = []
            for c in chunks:
                metadatas.append({
                    'doc_key': doc_key,
                    'title': metadata.title,
                    'year': metadata.year,
                    'venue': metadata.venue,
                    'doi': metadata.doi,
                    'source_type': 'note',
                    'locator': c['locator'],
                    'pdf_path': str(self.base_ingester._find_pdf_for_note(note_path, metadata)) if self.base_ingester._find_pdf_for_note(note_path, metadata) else '',
                    'note_path': str(note_path.absolute()),
                    'tags': json.dumps(metadata.tags)
                })
            
            self.vector_store.add_chunks(chunk_ids, texts, embeddings, metadatas)
        
        return True
    
    def scan_and_ingest(self) -> Dict[str, int]:
        """Scan and ingest with embeddings."""
        stats = self.base_ingester.scan_and_ingest()
        
        # After base ingestion, generate embeddings for PDF chunks too
        # This is done in batches for efficiency
        print("\nGenerating embeddings for semantic search...")
        
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        
        # Get all PDF chunks without embeddings
        cursor = conn.execute("""
            SELECT c.chunk_id, c.doc_key, c.text, c.locator, 
                   d.title, d.year, d.venue, d.doi, d.pdf_path, d.note_path, d.tags
            FROM chunks c
            JOIN documents d ON c.doc_key = d.doc_key
            WHERE c.source_type = 'pdf'
        """)
        
        pdf_chunks = cursor.fetchall()
        conn.close()
        
        if pdf_chunks:
            # Process in batches
            batch_size = 32
            for i in range(0, len(pdf_chunks), batch_size):
                batch = pdf_chunks[i:i+batch_size]
                texts = [c['text'] for c in batch]
                embeddings = self.embedding_generator.encode(texts)
                
                chunk_ids = [str(c['chunk_id']) for c in batch]
                metadatas = []
                for c in batch:
                    metadatas.append({
                        'doc_key': c['doc_key'],
                        'title': c['title'],
                        'year': c['year'],
                        'venue': c['venue'],
                        'doi': c['doi'],
                        'source_type': 'pdf',
                        'locator': c['locator'],
                        'pdf_path': c['pdf_path'],
                        'note_path': c['note_path'],
                        'tags': c['tags'] or '[]'
                    })
                
                self.vector_store.add_chunks(chunk_ids, texts, embeddings, metadatas)
                print(f"  Embedded {min(i+batch_size, len(pdf_chunks))}/{len(pdf_chunks)} PDF chunks")
        
        print(f"Semantic index complete: {self.vector_store.count()} chunks with embeddings")
        return stats
