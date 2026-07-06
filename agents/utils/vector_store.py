"""
CivicMind -- Vector Store Interface
====================================
Local fallback: ChromaDB with persistent storage
Google Cloud swap-in: Replace ChromaVectorStore with a VertexAISearchStore
that uses the Vertex AI Search (Discovery Engine) API for grounded retrieval
with built-in citations.

IMPORTANT: ChromaDB is configured with persistent storage in data/chromadb/
so documents survive server restarts during the demo.
"""

import os
import hashlib
from pathlib import Path
from typing import Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


DATA_DIR = Path(__file__).parent.parent.parent / "data"
CHROMADB_DIR = DATA_DIR / "chromadb"
UNSTRUCTURED_DIR = DATA_DIR / "unstructured"


class VectorStoreInterface:
    """Abstract interface for document retrieval.

    Google Cloud swap-in:
        Replace with VertexAISearchStore that wraps the Discovery Engine API.
        The grounding_metadata in Vertex AI Search responses provides citations
        out of the box.
    """

    def add_document(self, doc_id: str, text: str, metadata: dict | None = None):
        raise NotImplementedError

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        raise NotImplementedError

    def document_count(self) -> int:
        raise NotImplementedError


class ChromaVectorStore(VectorStoreInterface):
    """ChromaDB-based vector store with PERSISTENT storage.

    Documents are stored on disk at data/chromadb/ so they survive
    server restarts without re-embedding.
    """

    def __init__(self, collection_name: str = "civic_documents"):
        if not CHROMADB_AVAILABLE:
            raise ImportError("chromadb is required. Install with: pip install chromadb")

        CHROMADB_DIR.mkdir(parents=True, exist_ok=True)

        # Persistent client — survives server restarts
        self.client = chromadb.PersistentClient(
            path=str(CHROMADB_DIR),
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_document(self, doc_id: str, text: str, metadata: dict | None = None):
        """Add a document to the vector store. Skips if doc_id already exists."""
        existing = self.collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            return  # Already indexed

        self.collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}]
        )

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        """Query the vector store and return results with citations.

        Returns list of dicts with keys: doc_id, text, metadata, distance
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=min(n_results, self.document_count() or 1)
        )

        output = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append({
                    "doc_id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })

        return output

    def document_count(self) -> int:
        """Return total number of documents in the collection."""
        return self.collection.count()


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def index_unstructured_documents(store: ChromaVectorStore) -> int:
    """Index all unstructured documents from the data directory.

    Chunks documents and adds them to the vector store.
    Returns the number of new documents indexed.
    """
    indexed = 0

    for subdir in ["complaints", "meeting_minutes", "news"]:
        dir_path = UNSTRUCTURED_DIR / subdir
        if not dir_path.exists():
            continue

        for file_path in sorted(dir_path.glob("*.txt")):
            text = file_path.read_text(encoding="utf-8")
            chunks = _chunk_text(text)

            for i, chunk in enumerate(chunks):
                doc_id = f"{subdir}/{file_path.stem}_chunk_{i}"

                # Check if already indexed (persistent store)
                existing = store.collection.get(ids=[doc_id])
                if existing and existing["ids"]:
                    continue

                store.add_document(
                    doc_id=doc_id,
                    text=chunk,
                    metadata={
                        "source": str(file_path.name),
                        "category": subdir,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                    }
                )
                indexed += 1

    return indexed


# Singleton
_store_instance = None

def get_vector_store() -> ChromaVectorStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = ChromaVectorStore()
        # Auto-index on first access
        count_before = _store_instance.document_count()
        if count_before == 0:
            new = index_unstructured_documents(_store_instance)
            print(f"[VectorStore] Indexed {new} document chunks (persistent at {CHROMADB_DIR})")
        else:
            print(f"[VectorStore] Loaded {count_before} document chunks from persistent store")
    return _store_instance
