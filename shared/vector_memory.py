"""
Pluggable Vector Memory Store for Long-Term Agent Recall

Provides semantic memory across sessions using vector embeddings.
Backend and embedding provider are fully configurable via environment variables —
no code changes required to switch providers.

Supported Vector Store Backends:
  - in_memory      : Numpy cosine similarity (default, zero dependencies)
  - chromadb       : ChromaDB local/server (pip install chromadb)
  - pinecone       : Pinecone cloud (pip install pinecone-client)
  - qdrant         : Qdrant local/cloud (pip install qdrant-client)
  - weaviate       : Weaviate local/cloud (pip install weaviate-client)
  - pgvector       : PostgreSQL + pgvector (pip install psycopg2-binary pgvector)
  - redis          : Redis with vector search (pip install redis)
  ── AWS Cloud-Native ──
  - opensearch_aws : Amazon OpenSearch Service k-NN (pip install opensearch-py requests-aws4auth)
                     Uses SigV4 (existing AWS credentials) or basic auth.
                     This is the AWS-native equivalent of a managed vector database.
  ── Azure Cloud-Native ──
  - azure_ai_search: Azure AI Search HNSW vector fields (pip install azure-search-documents)
                     Supports hybrid search (vector + BM25) and Managed Identity auth.
  - azure_cosmos   : Azure Cosmos DB DiskANN vector search (pip install azure-cosmos)
                     Stores embeddings alongside item data; partition key = session_id.
                     Recommended for apps already using Cosmos DB for session/conversation state.

Supported Embedding Providers:
  - bedrock           : AWS Bedrock Titan Embeddings (default, uses existing AWS creds)
  - openai            : OpenAI text-embedding-3-small (pip install openai)
  - sentence_transformers : Local model (pip install sentence-transformers)
  - none              : No embeddings (disables semantic search, keyword fallback)

Environment Variables:
  VECTOR_MEMORY_ENABLED        = true/false (default: false)
  VECTOR_MEMORY_BACKEND        = in_memory|chromadb|pinecone|qdrant|weaviate|pgvector|redis
                                 |opensearch_aws|azure_ai_search|azure_cosmos
  VECTOR_MEMORY_EMBEDDING      = bedrock|openai|sentence_transformers|none
  VECTOR_MEMORY_COLLECTION     = collection name (default: a2a_memories)
  VECTOR_MEMORY_TOP_K          = number of results to return (default: 5)
  VECTOR_MEMORY_SCORE_THRESHOLD= minimum similarity score 0.0-1.0 (default: 0.3)
  VECTOR_MEMORY_MAX_ENTRIES    = max per-session entries (default: 1000)

  # ChromaDB
  CHROMA_HOST          = localhost
  CHROMA_PORT          = 8000
  CHROMA_PERSIST_PATH  = ./chroma_data

  # Pinecone
  PINECONE_API_KEY     = pc-...
  PINECONE_ENVIRONMENT = us-east-1
  PINECONE_INDEX_NAME  = a2a-memories

  # Qdrant
  QDRANT_HOST     = localhost
  QDRANT_PORT     = 6333
  QDRANT_API_KEY  = (optional, for cloud)
  QDRANT_URL      = https://... (optional, overrides host/port)

  # Weaviate
  WEAVIATE_URL     = http://localhost:8080
  WEAVIATE_API_KEY = (optional, for cloud)

  # PGVector
  PGVECTOR_CONNECTION_STRING = postgresql://user:pass@host:5432/dbname

  # Redis
  REDIS_URL = redis://localhost:6379

  # OpenAI embeddings
  OPENAI_API_KEY   = sk-...
  OPENAI_EMBED_MODEL = text-embedding-3-small

  # Bedrock embeddings
  BEDROCK_EMBED_MODEL = amazon.titan-embed-text-v1
  BEDROCK_REGION      = us-east-1

  # Sentence Transformers
  ST_MODEL_NAME = all-MiniLM-L6-v2
"""

import os
import json
import logging
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

class VectorBackend(Enum):
    IN_MEMORY        = "in_memory"
    CHROMADB         = "chromadb"
    PINECONE         = "pinecone"
    QDRANT           = "qdrant"
    WEAVIATE         = "weaviate"
    PGVECTOR         = "pgvector"
    REDIS            = "redis"
    # ── AWS Cloud-Native ──
    OPENSEARCH_AWS   = "opensearch_aws"   # Amazon OpenSearch Service (managed k-NN)
    # ── Azure Cloud-Native ──
    AZURE_AI_SEARCH  = "azure_ai_search"  # Azure AI Search (HNSW vector fields)
    AZURE_COSMOS     = "azure_cosmos"     # Azure Cosmos DB (DiskANN vector search)


class EmbeddingProvider(Enum):
    BEDROCK               = "bedrock"
    OPENAI                = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    NONE                  = "none"


@dataclass
class MemoryEntry:
    """A single memory record stored in the vector store."""
    id: str
    session_id: str
    text: str                          # The text that was embedded
    metadata: Dict[str, Any]           # task, result, workflow_id, timestamp, etc.
    embedding: Optional[List[float]] = None
    score: float = 0.0                 # populated during search results


# ─────────────────────────────────────────────────────────────────────────────
# Embedding Providers
# ─────────────────────────────────────────────────────────────────────────────

class BaseEmbedder:
    """Base class for embedding providers."""

    def embed(self, text: str) -> Optional[List[float]]:
        raise NotImplementedError

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        return [self.embed(t) for t in texts]


class BedrockEmbedder(BaseEmbedder):
    """AWS Bedrock Titan Embeddings — uses existing AWS credentials."""

    def __init__(self, model_id: str = None, region: str = None):
        self.model_id = model_id or os.getenv("BEDROCK_EMBED_MODEL", "amazon.titan-embed-text-v1")
        self.region   = region   or os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))
        self._client  = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client("bedrock-runtime", region_name=self.region)
            except Exception as e:
                logger.error(f"[VectorMemory] Bedrock client init failed: {e}")
        return self._client

    def embed(self, text: str) -> Optional[List[float]]:
        client = self._get_client()
        if client is None:
            return None
        try:
            body = json.dumps({"inputText": text[:8192]})  # Titan max ~8k chars
            response = client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=body
            )
            result = json.loads(response["body"].read())
            return result.get("embedding")
        except Exception as e:
            logger.error(f"[VectorMemory] Bedrock embed error: {e}")
            return None


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI embeddings."""

    def __init__(self, model: str = None, api_key: str = None):
        self.model   = model   or os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                logger.error("[VectorMemory] openai package not installed. Run: pip install openai")
        return self._client

    def embed(self, text: str) -> Optional[List[float]]:
        client = self._get_client()
        if client is None:
            return None
        try:
            response = client.embeddings.create(model=self.model, input=text[:8192])
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"[VectorMemory] OpenAI embed error: {e}")
            return None


class SentenceTransformerEmbedder(BaseEmbedder):
    """Local sentence-transformers model (fully offline)."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv("ST_MODEL_NAME", "all-MiniLM-L6-v2")
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"[VectorMemory] Loaded local model: {self.model_name}")
            except ImportError:
                logger.error("[VectorMemory] sentence-transformers not installed. Run: pip install sentence-transformers")
        return self._model

    def embed(self, text: str) -> Optional[List[float]]:
        model = self._get_model()
        if model is None:
            return None
        try:
            return model.encode(text).tolist()
        except Exception as e:
            logger.error(f"[VectorMemory] SentenceTransformer embed error: {e}")
            return None


class NullEmbedder(BaseEmbedder):
    """No-op embedder — vector memory operates in keyword-only mode."""

    def embed(self, text: str) -> Optional[List[float]]:
        return None


def _make_embedder(provider: EmbeddingProvider) -> BaseEmbedder:
    if provider == EmbeddingProvider.BEDROCK:
        return BedrockEmbedder()
    elif provider == EmbeddingProvider.OPENAI:
        return OpenAIEmbedder()
    elif provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
        return SentenceTransformerEmbedder()
    else:
        return NullEmbedder()


# ─────────────────────────────────────────────────────────────────────────────
# Vector Store Backends
# ─────────────────────────────────────────────────────────────────────────────

class BaseVectorStore(ABC):
    """Abstract vector store interface."""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> bool:
        """Store a memory entry. Returns True on success."""

    @abstractmethod
    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        """Semantic or keyword search. Returns top_k results."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> int:
        """Delete all entries for a session. Returns count deleted."""

    @abstractmethod
    async def count(self, session_id: Optional[str] = None) -> int:
        """Count entries, optionally filtered by session."""


# ── In-Memory (NumPy cosine similarity) ──────────────────────────────────────

class InMemoryVectorStore(BaseVectorStore):
    """
    In-process vector store using numpy cosine similarity.
    No external dependencies. Suitable for dev/test and single-process deployments.
    Data is NOT persisted across restarts unless a persist_path is configured.
    """

    def __init__(self, persist_path: Optional[str] = None, max_entries: int = 10000):
        self._entries: List[MemoryEntry] = []
        self._persist_path = persist_path or os.getenv("VECTOR_MEMORY_PERSIST_PATH", "")
        self._max_entries = max_entries
        if self._persist_path:
            self._load_from_disk()

    def _load_from_disk(self):
        try:
            import pickle
            path = self._persist_path
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._entries = pickle.load(f)
                logger.info(f"[VectorMemory] Loaded {len(self._entries)} entries from {path}")
        except Exception as e:
            logger.warning(f"[VectorMemory] Could not load from disk: {e}")

    def _save_to_disk(self):
        if not self._persist_path:
            return
        try:
            import pickle, os
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True) if os.path.dirname(self._persist_path) else None
            with open(self._persist_path, "wb") as f:
                pickle.dump(self._entries, f)
        except Exception as e:
            logger.warning(f"[VectorMemory] Could not save to disk: {e}")

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        try:
            import math
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(x * x for x in b))
            if mag_a == 0 or mag_b == 0:
                return 0.0
            return dot / (mag_a * mag_b)
        except Exception:
            return 0.0

    async def store(self, entry: MemoryEntry) -> bool:
        # Enforce max entries per-store (evict oldest first)
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
        self._entries.append(entry)
        self._save_to_disk()
        return True

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        candidates = [e for e in self._entries if session_id is None or e.session_id == session_id]

        if query_embedding is not None:
            scored = []
            for e in candidates:
                if e.embedding:
                    s = self._cosine(query_embedding, e.embedding)
                    scored.append((s, e))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for s, e in scored[:top_k]:
                if s >= score_threshold:
                    e.score = s
                    results.append(e)
            return results

        # Keyword fallback (no embeddings)
        words = set(query_text.lower().split())
        scored = []
        for e in candidates:
            text_words = set(e.text.lower().split())
            overlap = len(words & text_words)
            if overlap > 0:
                scored.append((overlap, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    async def delete_session(self, session_id: str) -> int:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.session_id != session_id]
        deleted = before - len(self._entries)
        self._save_to_disk()
        return deleted

    async def count(self, session_id: Optional[str] = None) -> int:
        if session_id:
            return sum(1 for e in self._entries if e.session_id == session_id)
        return len(self._entries)


# ── ChromaDB ─────────────────────────────────────────────────────────────────

class ChromaDBVectorStore(BaseVectorStore):
    """ChromaDB-backed vector store (local or server mode)."""

    def __init__(self, collection_name: str = "a2a_memories"):
        self._collection_name = collection_name
        self._client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
            host = os.getenv("CHROMA_HOST", "localhost")
            port = int(os.getenv("CHROMA_PORT", "8000"))
            persist_path = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")

            if os.getenv("CHROMA_HOST"):
                self._client = chromadb.HttpClient(host=host, port=port)
            else:
                self._client = chromadb.PersistentClient(path=persist_path)

            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            return self._collection
        except ImportError:
            logger.error("[VectorMemory] chromadb not installed. Run: pip install chromadb")
            return None
        except Exception as e:
            logger.error(f"[VectorMemory] ChromaDB init error: {e}")
            return None

    async def store(self, entry: MemoryEntry) -> bool:
        col = self._get_collection()
        if col is None:
            return False
        try:
            kwargs: Dict[str, Any] = {
                "ids": [entry.id],
                "documents": [entry.text],
                "metadatas": [{**entry.metadata, "session_id": entry.session_id}],
            }
            if entry.embedding:
                kwargs["embeddings"] = [entry.embedding]
            col.upsert(**kwargs)
            return True
        except Exception as e:
            logger.error(f"[VectorMemory] ChromaDB store error: {e}")
            return False

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        col = self._get_collection()
        if col is None:
            return []
        try:
            where = {"session_id": session_id} if session_id else None
            kwargs: Dict[str, Any] = {"n_results": top_k, "include": ["documents", "metadatas", "distances"]}
            if where:
                kwargs["where"] = where
            if query_embedding:
                kwargs["query_embeddings"] = [query_embedding]
            else:
                kwargs["query_texts"] = [query_text]

            results = col.query(**kwargs)
            entries = []
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i]
                dist = results["distances"][0][i]
                score = 1.0 - dist  # ChromaDB cosine distance → similarity
                if score >= score_threshold:
                    entries.append(MemoryEntry(
                        id=results["ids"][0][i],
                        session_id=meta.get("session_id", ""),
                        text=doc,
                        metadata=meta,
                        score=score
                    ))
            return entries
        except Exception as e:
            logger.error(f"[VectorMemory] ChromaDB search error: {e}")
            return []

    async def delete_session(self, session_id: str) -> int:
        col = self._get_collection()
        if col is None:
            return 0
        try:
            existing = col.get(where={"session_id": session_id})
            ids = existing.get("ids", [])
            if ids:
                col.delete(ids=ids)
            return len(ids)
        except Exception as e:
            logger.error(f"[VectorMemory] ChromaDB delete error: {e}")
            return 0

    async def count(self, session_id: Optional[str] = None) -> int:
        col = self._get_collection()
        if col is None:
            return 0
        try:
            if session_id:
                return col.count(where={"session_id": session_id})
            return col.count()
        except Exception:
            return 0


# ── Qdrant ────────────────────────────────────────────────────────────────────

class QdrantVectorStore(BaseVectorStore):
    """Qdrant-backed vector store (local or cloud)."""

    def __init__(self, collection_name: str = "a2a_memories", vector_size: int = 1536):
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance

            url     = os.getenv("QDRANT_URL", "")
            host    = os.getenv("QDRANT_HOST", "localhost")
            port    = int(os.getenv("QDRANT_PORT", "6333"))
            api_key = os.getenv("QDRANT_API_KEY", "")

            if url:
                self._client = QdrantClient(url=url, api_key=api_key or None)
            else:
                self._client = QdrantClient(host=host, port=port, api_key=api_key or None)

            # Ensure collection exists
            existing = [c.name for c in self._client.get_collections().collections]
            if self._collection_name not in existing:
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(size=self._vector_size, distance=Distance.COSINE)
                )
            return self._client
        except ImportError:
            logger.error("[VectorMemory] qdrant-client not installed. Run: pip install qdrant-client")
            return None
        except Exception as e:
            logger.error(f"[VectorMemory] Qdrant init error: {e}")
            return None

    async def store(self, entry: MemoryEntry) -> bool:
        client = self._get_client()
        if client is None or not entry.embedding:
            return False
        try:
            from qdrant_client.models import PointStruct
            client.upsert(
                collection_name=self._collection_name,
                points=[PointStruct(
                    id=hashlib.md5(entry.id.encode()).hexdigest()[:16],  # Qdrant needs numeric/UUID
                    vector=entry.embedding,
                    payload={**entry.metadata, "session_id": entry.session_id, "text": entry.text, "_id": entry.id}
                )]
            )
            return True
        except Exception as e:
            logger.error(f"[VectorMemory] Qdrant store error: {e}")
            return False

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        client = self._get_client()
        if client is None or query_embedding is None:
            return []
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = None
            if session_id:
                query_filter = Filter(must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))])

            results = client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold
            )
            entries = []
            for r in results:
                payload = r.payload or {}
                entries.append(MemoryEntry(
                    id=payload.get("_id", str(r.id)),
                    session_id=payload.get("session_id", ""),
                    text=payload.get("text", ""),
                    metadata=payload,
                    score=r.score
                ))
            return entries
        except Exception as e:
            logger.error(f"[VectorMemory] Qdrant search error: {e}")
            return []

    async def delete_session(self, session_id: str) -> int:
        client = self._get_client()
        if client is None:
            return 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))])
            )
            return -1  # Count not easily available
        except Exception as e:
            logger.error(f"[VectorMemory] Qdrant delete error: {e}")
            return 0

    async def count(self, session_id: Optional[str] = None) -> int:
        client = self._get_client()
        if client is None:
            return 0
        try:
            if session_id:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                return client.count(
                    collection_name=self._collection_name,
                    count_filter=Filter(must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))])
                ).count
            return client.get_collection(self._collection_name).points_count
        except Exception:
            return 0


# ── Pinecone ──────────────────────────────────────────────────────────────────

class PineconeVectorStore(BaseVectorStore):
    """Pinecone cloud vector store."""

    def __init__(self, index_name: str = None):
        self._index_name = index_name or os.getenv("PINECONE_INDEX_NAME", "a2a-memories")
        self._index = None

    def _get_index(self):
        if self._index is not None:
            return self._index
        try:
            from pinecone import Pinecone
            api_key = os.getenv("PINECONE_API_KEY", "")
            pc = Pinecone(api_key=api_key)
            self._index = pc.Index(self._index_name)
            return self._index
        except ImportError:
            logger.error("[VectorMemory] pinecone-client not installed. Run: pip install pinecone-client")
            return None
        except Exception as e:
            logger.error(f"[VectorMemory] Pinecone init error: {e}")
            return None

    async def store(self, entry: MemoryEntry) -> bool:
        index = self._get_index()
        if index is None or not entry.embedding:
            return False
        try:
            index.upsert(vectors=[{
                "id": entry.id,
                "values": entry.embedding,
                "metadata": {**entry.metadata, "session_id": entry.session_id, "text": entry.text[:1000]}
            }])
            return True
        except Exception as e:
            logger.error(f"[VectorMemory] Pinecone store error: {e}")
            return False

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        index = self._get_index()
        if index is None or query_embedding is None:
            return []
        try:
            filter_dict = {"session_id": {"$eq": session_id}} if session_id else None
            results = index.query(
                vector=query_embedding,
                top_k=top_k,
                filter=filter_dict,
                include_metadata=True
            )
            entries = []
            for match in results.matches:
                if match.score >= score_threshold:
                    meta = match.metadata or {}
                    entries.append(MemoryEntry(
                        id=match.id,
                        session_id=meta.get("session_id", ""),
                        text=meta.get("text", ""),
                        metadata=meta,
                        score=match.score
                    ))
            return entries
        except Exception as e:
            logger.error(f"[VectorMemory] Pinecone search error: {e}")
            return []

    async def delete_session(self, session_id: str) -> int:
        index = self._get_index()
        if index is None:
            return 0
        try:
            index.delete(filter={"session_id": {"$eq": session_id}})
            return -1
        except Exception as e:
            logger.error(f"[VectorMemory] Pinecone delete error: {e}")
            return 0

    async def count(self, session_id: Optional[str] = None) -> int:
        index = self._get_index()
        if index is None:
            return 0
        try:
            stats = index.describe_index_stats()
            return stats.total_vector_count
        except Exception:
            return 0


# ── AWS OpenSearch Service ────────────────────────────────────────────────────

class OpenSearchAWSVectorStore(BaseVectorStore):
    """
    Amazon OpenSearch Service vector store (AWS-native).

    Uses the k-NN plugin (HNSW or IVF) available on all managed OpenSearch
    domains ≥ 2.9 and on OpenSearch Serverless.

    Authentication options:
      - AWS SigV4 (recommended): set OPENSEARCH_SERVICE=es or aoss,
        uses existing boto3 credentials automatically.
      - Basic auth: OPENSEARCH_USER + OPENSEARCH_PASSWORD.

    Required packages: pip install opensearch-py requests-aws4auth

    Environment Variables:
      OPENSEARCH_HOST          Endpoint URL (no trailing slash)
                               e.g. https://xxx.us-east-1.es.amazonaws.com
      OPENSEARCH_SERVICE       es (Elasticsearch compat) | aoss (Serverless)
                               default: es
      OPENSEARCH_REGION        AWS region (default: AWS_REGION env var)
      OPENSEARCH_INDEX         Index name (default: collection arg)
      OPENSEARCH_VECTOR_DIM    Embedding dimension (default: 1536)
      OPENSEARCH_USER          Basic-auth username (skip if using SigV4)
      OPENSEARCH_PASSWORD      Basic-auth password (skip if using SigV4)
    """

    def __init__(self, index_name: str = "a2a_memories", vector_dim: int = 1536):
        self._index   = os.getenv("OPENSEARCH_INDEX", index_name)
        self._dim     = int(os.getenv("OPENSEARCH_VECTOR_DIM", str(vector_dim)))
        self._client  = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
            import boto3

            host     = os.getenv("OPENSEARCH_HOST", "").rstrip("/")
            service  = os.getenv("OPENSEARCH_SERVICE", "es")
            region   = os.getenv("OPENSEARCH_REGION", os.getenv("AWS_REGION", "us-east-1"))
            user     = os.getenv("OPENSEARCH_USER", "")
            password = os.getenv("OPENSEARCH_PASSWORD", "")

            if not host:
                logger.error("[VectorMemory] OPENSEARCH_HOST not set")
                return None

            if user and password:
                # Basic auth
                self._client = OpenSearch(
                    hosts=[host],
                    http_auth=(user, password),
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection
                )
            else:
                # AWS SigV4 — reuses existing boto3 credentials (IAM role / env vars)
                credentials = boto3.Session().get_credentials()
                auth = AWSV4SignerAuth(credentials, region, service)
                self._client = OpenSearch(
                    hosts=[host],
                    http_auth=auth,
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection
                )

            # Create index with knn_vector mapping if it doesn't exist
            if not self._client.indices.exists(index=self._index):
                self._client.indices.create(index=self._index, body={
                    "settings": {"index": {"knn": True}},
                    "mappings": {"properties": {
                        "embedding":   {"type": "knn_vector", "dimension": self._dim,
                                        "method": {"name": "hnsw", "space_type": "cosinesimil",
                                                   "engine": "nmslib",
                                                   "parameters": {"ef_construction": 128, "m": 24}}},
                        "text":        {"type": "text"},
                        "session_id":  {"type": "keyword"},
                        "workflow_id": {"type": "keyword"},
                        "timestamp":   {"type": "date", "format": "strict_date_optional_time||epoch_millis"}
                    }}
                })
                logger.info(f"[VectorMemory] Created OpenSearch index: {self._index}")
            return self._client
        except ImportError:
            logger.error("[VectorMemory] opensearch-py not installed. Run: pip install opensearch-py requests-aws4auth")
            return None
        except Exception as e:
            logger.error(f"[VectorMemory] OpenSearch init error: {e}")
            return None

    async def store(self, entry: MemoryEntry) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            body = {
                "text":       entry.text,
                "session_id": entry.session_id,
                **{k: v for k, v in entry.metadata.items() if isinstance(v, (str, int, float, bool))}
            }
            if entry.embedding:
                body["embedding"] = entry.embedding
            client.index(index=self._index, id=entry.id, body=body)
            return True
        except Exception as e:
            logger.error(f"[VectorMemory] OpenSearch store error: {e}")
            return False

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        client = self._get_client()
        if client is None:
            return []
        try:
            if query_embedding:
                knn_query: Dict[str, Any] = {
                    "knn": {"embedding": {"vector": query_embedding, "k": top_k}}
                }
                if session_id:
                    knn_query = {"bool": {"must": [knn_query,
                        {"term": {"session_id": session_id}}]}}
                body = {"size": top_k, "query": knn_query}
            else:
                body = {"size": top_k, "query": {"match": {"text": query_text}}}
                if session_id:
                    body["query"] = {"bool": {"must": [{"match": {"text": query_text}},
                        {"term": {"session_id": session_id}}]}}

            response = client.search(index=self._index, body=body)
            entries = []
            for hit in response["hits"]["hits"]:
                score = hit["_score"] or 0.0
                if score >= score_threshold:
                    src = hit["_source"]
                    entries.append(MemoryEntry(
                        id=hit["_id"],
                        session_id=src.get("session_id", ""),
                        text=src.get("text", ""),
                        metadata=src,
                        score=score
                    ))
            return entries
        except Exception as e:
            logger.error(f"[VectorMemory] OpenSearch search error: {e}")
            return []

    async def delete_session(self, session_id: str) -> int:
        client = self._get_client()
        if client is None:
            return 0
        try:
            response = client.delete_by_query(
                index=self._index,
                body={"query": {"term": {"session_id": session_id}}}
            )
            return response.get("deleted", 0)
        except Exception as e:
            logger.error(f"[VectorMemory] OpenSearch delete error: {e}")
            return 0

    async def count(self, session_id: Optional[str] = None) -> int:
        client = self._get_client()
        if client is None:
            return 0
        try:
            q = {"term": {"session_id": session_id}} if session_id else {"match_all": {}}
            r = client.count(index=self._index, body={"query": q})
            return r.get("count", 0)
        except Exception:
            return 0


# ── Azure AI Search ───────────────────────────────────────────────────────────

class AzureAISearchVectorStore(BaseVectorStore):
    """
    Azure AI Search (formerly Cognitive Search) vector store.

    Uses HNSW vector fields for fast approximate nearest-neighbour search.
    Supports hybrid search (vector + BM25 keyword) automatically.
    Works with any tier (Basic+) that has vector search enabled.

    Required packages: pip install azure-search-documents

    Environment Variables:
      AZURE_SEARCH_ENDPOINT     https://<service>.search.windows.net
      AZURE_SEARCH_API_KEY      Admin or query key
      AZURE_SEARCH_INDEX        Index name (default: collection arg)
      AZURE_SEARCH_API_VERSION  REST API version (default: 2024-02-01)
      AZURE_SEARCH_VECTOR_DIM   Embedding dimension (default: 1536)

    Authentication note:
      Managed Identity (passwordless) is also supported — omit
      AZURE_SEARCH_API_KEY and set AZURE_CLIENT_ID / AZURE_TENANT_ID /
      AZURE_CLIENT_SECRET for DefaultAzureCredential.
    """

    def __init__(self, index_name: str = "a2a-memories", vector_dim: int = 1536):
        self._index_name = os.getenv("AZURE_SEARCH_INDEX", index_name)
        self._dim        = int(os.getenv("AZURE_SEARCH_VECTOR_DIM", str(vector_dim)))
        self._client     = None
        self._admin      = None

    def _get_clients(self):
        if self._client is not None:
            return self._client, self._admin
        try:
            from azure.search.documents import SearchClient
            from azure.search.documents.indexes import SearchIndexClient
            from azure.search.documents.indexes.models import (
                SearchIndex, SimpleField, SearchFieldDataType, SearchableField,
                SearchField, VectorSearch, HnswAlgorithmConfiguration,
                VectorSearchProfile
            )

            endpoint   = os.getenv("AZURE_SEARCH_ENDPOINT", "")
            api_key    = os.getenv("AZURE_SEARCH_API_KEY", "")

            if not endpoint:
                logger.error("[VectorMemory] AZURE_SEARCH_ENDPOINT not set")
                return None, None

            if api_key:
                from azure.core.credentials import AzureKeyCredential
                credential = AzureKeyCredential(api_key)
            else:
                from azure.identity import DefaultAzureCredential
                credential = DefaultAzureCredential()

            self._admin  = SearchIndexClient(endpoint=endpoint, credential=credential)
            self._client = SearchClient(endpoint=endpoint,
                                        index_name=self._index_name,
                                        credential=credential)

            # Create index if it doesn't exist
            existing = [i.name for i in self._admin.list_indexes()]
            if self._index_name not in existing:
                fields = [
                    SimpleField(name="id",         type=SearchFieldDataType.String, key=True),
                    SimpleField(name="session_id", type=SearchFieldDataType.String, filterable=True),
                    SimpleField(name="workflow_id",type=SearchFieldDataType.String, filterable=True),
                    SimpleField(name="timestamp",  type=SearchFieldDataType.String, filterable=True),
                    SearchableField(name="text"),
                    SearchField(
                        name="embedding",
                        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                        searchable=True,
                        vector_search_dimensions=self._dim,
                        vector_search_profile_name="hnsw_profile"
                    )
                ]
                vs = VectorSearch(
                    algorithms=[HnswAlgorithmConfiguration(name="hnsw_algo")],
                    profiles=[VectorSearchProfile(name="hnsw_profile",
                                                  algorithm_configuration_name="hnsw_algo")]
                )
                self._admin.create_index(SearchIndex(
                    name=self._index_name, fields=fields, vector_search=vs
                ))
                logger.info(f"[VectorMemory] Created Azure AI Search index: {self._index_name}")
            return self._client, self._admin
        except ImportError:
            logger.error("[VectorMemory] azure-search-documents not installed. Run: pip install azure-search-documents")
            return None, None
        except Exception as e:
            logger.error(f"[VectorMemory] Azure AI Search init error: {e}")
            return None, None

    async def store(self, entry: MemoryEntry) -> bool:
        client, _ = self._get_clients()
        if client is None:
            return False
        try:
            doc = {
                "id":          entry.id,
                "session_id":  entry.session_id,
                "text":        entry.text,
                "workflow_id": entry.metadata.get("workflow_id", ""),
                "timestamp":   entry.metadata.get("timestamp", ""),
            }
            if entry.embedding:
                doc["embedding"] = entry.embedding
            client.upload_documents(documents=[doc])
            return True
        except Exception as e:
            logger.error(f"[VectorMemory] Azure AI Search store error: {e}")
            return False

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        client, _ = self._get_clients()
        if client is None:
            return []
        try:
            from azure.search.documents.models import VectorizedQuery

            filter_expr = f"session_id eq '{session_id}'" if session_id else None
            vector_queries = None
            if query_embedding:
                vector_queries = [VectorizedQuery(
                    vector=query_embedding,
                    k_nearest_neighbors=top_k,
                    fields="embedding"
                )]

            results = client.search(
                search_text=query_text if not query_embedding else None,
                vector_queries=vector_queries,
                filter=filter_expr,
                top=top_k,
                select=["id", "session_id", "text", "workflow_id", "timestamp"]
            )
            entries = []
            for r in results:
                score = r.get("@search.score", 0.0)
                if score >= score_threshold:
                    entries.append(MemoryEntry(
                        id=r["id"],
                        session_id=r.get("session_id", ""),
                        text=r.get("text", ""),
                        metadata={"workflow_id": r.get("workflow_id", ""),
                                  "timestamp":   r.get("timestamp", "")},
                        score=score
                    ))
            return entries
        except Exception as e:
            logger.error(f"[VectorMemory] Azure AI Search search error: {e}")
            return []

    async def delete_session(self, session_id: str) -> int:
        client, _ = self._get_clients()
        if client is None:
            return 0
        try:
            # Fetch IDs first, then delete
            hits = client.search(search_text="*",
                                 filter=f"session_id eq '{session_id}'",
                                 select=["id"])
            ids = [{"id": h["id"]} for h in hits]
            if ids:
                client.delete_documents(documents=ids)
            return len(ids)
        except Exception as e:
            logger.error(f"[VectorMemory] Azure AI Search delete error: {e}")
            return 0

    async def count(self, session_id: Optional[str] = None) -> int:
        client, _ = self._get_clients()
        if client is None:
            return 0
        try:
            filter_expr = f"session_id eq '{session_id}'" if session_id else None
            results = client.search(search_text="*", filter=filter_expr,
                                    include_total_count=True, top=0)
            return results.get_count() or 0
        except Exception:
            return 0


# ── Azure Cosmos DB (vector search / DiskANN) ────────────────────────────────

class AzureCosmosDBVectorStore(BaseVectorStore):
    """
    Azure Cosmos DB for NoSQL vector store (DiskANN algorithm).

    Cosmos DB vector search is fully integrated — embeddings are stored
    alongside the item data in the same container, enabling single-read
    retrieval of memory + metadata. Ideal for applications already using
    Cosmos DB for session/conversation state.

    Recommended for: chat history, user context, RAG patterns, multi-tenant
    agent memory isolation (partition key = session_id).

    Required packages: pip install azure-cosmos

    Environment Variables:
      COSMOS_ENDPOINT            https://<account>.documents.azure.com:443/
      COSMOS_KEY                 Primary or secondary account key
                                 (skip for Managed Identity / Entra ID)
      COSMOS_DATABASE            Database name  (default: a2a_agent_memory)
      COSMOS_CONTAINER           Container name (default: collection arg)
      COSMOS_VECTOR_DIM          Embedding dimension (default: 1536)
      COSMOS_VECTOR_POLICY       flat | diskANN (default: diskANN)

    Passwordless auth:
      Omit COSMOS_KEY.  Set AZURE_CLIENT_ID / AZURE_TENANT_ID /
      AZURE_CLIENT_SECRET (or use Managed Identity) — DefaultAzureCredential
      is used automatically.

    Partition key:
      /session_id  — ensures data locality per session and prevents hot
      partitions as recommended by Cosmos DB best practices.
    """

    def __init__(self, container_name: str = "a2a_memories", vector_dim: int = 1536):
        self._database_name   = os.getenv("COSMOS_DATABASE", "a2a_agent_memory")
        self._container_name  = os.getenv("COSMOS_CONTAINER", container_name)
        self._dim             = int(os.getenv("COSMOS_VECTOR_DIM", str(vector_dim)))
        self._policy          = os.getenv("COSMOS_VECTOR_POLICY", "diskANN")
        self._container       = None

    def _get_container(self):
        if self._container is not None:
            return self._container
        try:
            from azure.cosmos import CosmosClient, PartitionKey

            endpoint = os.getenv("COSMOS_ENDPOINT", "")
            key      = os.getenv("COSMOS_KEY", "")

            if not endpoint:
                logger.error("[VectorMemory] COSMOS_ENDPOINT not set")
                return None

            if key:
                client = CosmosClient(url=endpoint, credential=key)
            else:
                from azure.identity import DefaultAzureCredential
                client = CosmosClient(url=endpoint, credential=DefaultAzureCredential())

            db = client.create_database_if_not_exists(id=self._database_name)

            # Vector embedding policy (DiskANN for scalable ANN search)
            vector_embedding_policy = {
                "vectorEmbeddings": [{
                    "path": "/embedding",
                    "dataType": "float32",
                    "distanceFunction": "cosine",
                    "dimensions": self._dim
                }]
            }
            indexing_policy = {
                "includedPaths": [{"path": "/*"}],
                "excludedPaths": [{"path": "/embedding/*"}],
                "vectorIndexes": [{
                    "path": "/embedding",
                    "type": self._policy  # diskANN or flat
                }]
            }

            self._container = db.create_container_if_not_exists(
                id=self._container_name,
                partition_key=PartitionKey(path="/session_id"),
                indexing_policy=indexing_policy,
                vector_embedding_policy=vector_embedding_policy
            )
            logger.info(f"[VectorMemory] Cosmos DB container ready: {self._container_name} "
                        f"(policy={self._policy})")
            return self._container
        except ImportError:
            logger.error("[VectorMemory] azure-cosmos not installed. Run: pip install azure-cosmos")
            return None
        except Exception as e:
            logger.error(f"[VectorMemory] Cosmos DB init error: {e}")
            return None

    async def store(self, entry: MemoryEntry) -> bool:
        container = self._get_container()
        if container is None:
            return False
        try:
            doc = {
                "id":          entry.id,
                "session_id":  entry.session_id,
                "text":        entry.text,
                **{k: v for k, v in entry.metadata.items() if isinstance(v, (str, int, float, bool, list))}
            }
            if entry.embedding:
                doc["embedding"] = entry.embedding
            container.upsert_item(body=doc)
            return True
        except Exception as e:
            logger.error(f"[VectorMemory] Cosmos DB store error: {e}")
            return False

    async def search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[MemoryEntry]:
        container = self._get_container()
        if container is None:
            return []
        try:
            if query_embedding:
                # Cosmos DB vector search query (VectorDistance function)
                if session_id:
                    query = (
                        f"SELECT TOP {top_k} c.id, c.session_id, c.text, c.workflow_id, "
                        f"c.timestamp, c.task, c.result, "
                        f"VectorDistance(c.embedding, @embedding) AS score "
                        f"FROM c WHERE c.session_id = @session_id "
                        f"ORDER BY VectorDistance(c.embedding, @embedding)"
                    )
                    params = [{"name": "@embedding", "value": query_embedding},
                              {"name": "@session_id", "value": session_id}]
                else:
                    query = (
                        f"SELECT TOP {top_k} c.id, c.session_id, c.text, c.workflow_id, "
                        f"c.timestamp, c.task, c.result, "
                        f"VectorDistance(c.embedding, @embedding) AS score "
                        f"FROM c ORDER BY VectorDistance(c.embedding, @embedding)"
                    )
                    params = [{"name": "@embedding", "value": query_embedding}]

                items = list(container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=(session_id is None)
                ))
            else:
                # Keyword fallback via CONTAINS
                if session_id:
                    query = (f"SELECT TOP {top_k} * FROM c "
                             f"WHERE c.session_id = @session_id "
                             f"AND CONTAINS(LOWER(c.text), @kw)")
                    params = [{"name": "@session_id", "value": session_id},
                              {"name": "@kw", "value": query_text.lower()[:50]}]
                else:
                    query = (f"SELECT TOP {top_k} * FROM c "
                             f"WHERE CONTAINS(LOWER(c.text), @kw)")
                    params = [{"name": "@kw", "value": query_text.lower()[:50]}]
                items = list(container.query_items(query=query, parameters=params,
                                                   enable_cross_partition_query=True))

            entries = []
            for item in items:
                # Cosmos VectorDistance returns distance (lower = closer); convert
                raw_score = item.pop("score", None)
                score = (1.0 - float(raw_score)) if raw_score is not None else 1.0
                if score >= score_threshold:
                    entries.append(MemoryEntry(
                        id=item.get("id", ""),
                        session_id=item.get("session_id", ""),
                        text=item.get("text", ""),
                        metadata=item,
                        score=score
                    ))
            return entries
        except Exception as e:
            logger.error(f"[VectorMemory] Cosmos DB search error: {e}")
            return []

    async def delete_session(self, session_id: str) -> int:
        container = self._get_container()
        if container is None:
            return 0
        try:
            items = list(container.query_items(
                query="SELECT c.id, c.session_id FROM c WHERE c.session_id = @sid",
                parameters=[{"name": "@sid", "value": session_id}]
            ))
            for item in items:
                container.delete_item(item=item["id"], partition_key=session_id)
            return len(items)
        except Exception as e:
            logger.error(f"[VectorMemory] Cosmos DB delete error: {e}")
            return 0

    async def count(self, session_id: Optional[str] = None) -> int:
        container = self._get_container()
        if container is None:
            return 0
        try:
            if session_id:
                q = "SELECT VALUE COUNT(1) FROM c WHERE c.session_id = @sid"
                p = [{"name": "@sid", "value": session_id}]
                result = list(container.query_items(query=q, parameters=p))
            else:
                q = "SELECT VALUE COUNT(1) FROM c"
                result = list(container.query_items(
                    query=q, enable_cross_partition_query=True
                ))
            return result[0] if result else 0
        except Exception:
            return 0


# ─────────────────────────────────────────────────────────────────────────────
# Factory functions
# ─────────────────────────────────────────────────────────────────────────────

def _make_store(backend: VectorBackend, collection: str, max_entries: int) -> BaseVectorStore:
    if backend == VectorBackend.CHROMADB:
        return ChromaDBVectorStore(collection_name=collection)
    elif backend == VectorBackend.QDRANT:
        return QdrantVectorStore(collection_name=collection)
    elif backend == VectorBackend.PINECONE:
        return PineconeVectorStore(index_name=collection)
    elif backend == VectorBackend.OPENSEARCH_AWS:
        return OpenSearchAWSVectorStore(index_name=collection)
    elif backend == VectorBackend.AZURE_AI_SEARCH:
        return AzureAISearchVectorStore(index_name=collection)
    elif backend == VectorBackend.AZURE_COSMOS:
        return AzureCosmosDBVectorStore(container_name=collection)
    else:
        persist_path = os.getenv("VECTOR_MEMORY_PERSIST_PATH", "")
        return InMemoryVectorStore(persist_path=persist_path or None, max_entries=max_entries)


# ─────────────────────────────────────────────────────────────────────────────
# Main VectorMemoryStore facade
# ─────────────────────────────────────────────────────────────────────────────

class VectorMemoryStore:
    """
    High-level facade over the pluggable vector store backend.
    
    This is the class used by the Orchestrator and other services.
    
    Usage:
        from shared.vector_memory import get_vector_memory
        
        vm = get_vector_memory()
        
        # Store a memory
        await vm.remember(
            session_id="sess_123",
            text="User asked about cloud providers. Recommended AWS for scale.",
            metadata={"task": "cloud comparison", "workflow_id": "wf_456"}
        )
        
        # Recall relevant memories
        memories = await vm.recall(
            query="Which cloud provider is best for machine learning?",
            session_id=None,  # None = search globally, or pass session_id to scope
            top_k=5
        )
        for m in memories:
            print(f"[{m.score:.2f}] {m.text}")
    """

    def __init__(
        self,
        enabled: bool = False,
        backend: VectorBackend = VectorBackend.IN_MEMORY,
        embedding_provider: EmbeddingProvider = EmbeddingProvider.BEDROCK,
        collection: str = "a2a_memories",
        top_k: int = 5,
        score_threshold: float = 0.3,
        max_entries: int = 1000
    ):
        self.enabled = enabled
        self._backend_type = backend
        self._embedding_provider = embedding_provider
        self._collection = collection
        self._top_k = top_k
        self._score_threshold = score_threshold

        if enabled:
            self._embedder = _make_embedder(embedding_provider)
            self._store    = _make_store(backend, collection, max_entries)
            logger.info(
                f"[VectorMemory] Initialized — backend={backend.value}, "
                f"embedder={embedding_provider.value}, collection={collection}"
            )
        else:
            self._embedder = NullEmbedder()
            self._store    = InMemoryVectorStore(max_entries=0)
            logger.debug("[VectorMemory] Disabled — all operations are no-ops")

    # ── Public API ─────────────────────────────────────────────────────────────

    async def remember(
        self,
        session_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store a memory entry.
        
        Args:
            session_id: The session this memory belongs to.
            text:       The text to embed and store (task + summary is ideal).
            metadata:   Extra fields: task, result, workflow_id, timestamp, agent, etc.
        
        Returns True on success, False if disabled or error.
        """
        if not self.enabled or not text:
            return False
        try:
            entry_id   = hashlib.sha256(f"{session_id}:{text}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:32]
            embedding  = self._embedder.embed(text)
            meta       = metadata or {}
            meta.setdefault("timestamp", datetime.utcnow().isoformat())
            entry = MemoryEntry(
                id=entry_id,
                session_id=session_id,
                text=text,
                metadata=meta,
                embedding=embedding
            )
            ok = await self._store.store(entry)
            if ok:
                logger.debug(f"[VectorMemory] Stored memory for session={session_id} (embed={'yes' if embedding else 'no'})")
            return ok
        except Exception as e:
            logger.error(f"[VectorMemory] remember() error: {e}")
            return False

    async def recall(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None
    ) -> List[MemoryEntry]:
        """
        Retrieve semantically relevant memories.
        
        Args:
            query:          Natural-language query to search for.
            session_id:     Scope search to a session (None = global search).
            top_k:          Number of results (uses configured default if None).
            score_threshold: Minimum similarity (uses configured default if None).
        
        Returns:
            List of MemoryEntry sorted by descending relevance score.
        """
        if not self.enabled or not query:
            return []
        try:
            k         = top_k          if top_k is not None          else self._top_k
            threshold = score_threshold if score_threshold is not None else self._score_threshold
            embedding = self._embedder.embed(query)
            return await self._store.search(
                query_embedding=embedding,
                query_text=query,
                session_id=session_id,
                top_k=k,
                score_threshold=threshold
            )
        except Exception as e:
            logger.error(f"[VectorMemory] recall() error: {e}")
            return []

    async def forget_session(self, session_id: str) -> int:
        """Delete all memories for a session. Returns count deleted."""
        if not self.enabled:
            return 0
        return await self._store.delete_session(session_id)

    async def count(self, session_id: Optional[str] = None) -> int:
        """Count stored memories."""
        if not self.enabled:
            return 0
        return await self._store.count(session_id)

    def format_for_context(self, memories: List[MemoryEntry], max_chars: int = 2000) -> str:
        """
        Format recalled memories as a context string for prompt injection.
        
        Returns an empty string if no memories, otherwise a formatted block
        suitable for insertion into an agent prompt.
        """
        if not memories:
            return ""
        lines = ["--- RELEVANT LONG-TERM MEMORIES ---"]
        chars = 0
        for m in memories:
            task    = m.metadata.get("task", m.text[:120])
            result  = m.metadata.get("result_summary", m.metadata.get("result", ""))
            ts      = m.metadata.get("timestamp", "")[:10]
            score   = f"{m.score:.2f}" if m.score else ""
            line    = f"[{ts}] Task: {task}\n  Result: {str(result)[:400]}\n  (relevance: {score})"
            chars  += len(line)
            if chars > max_chars:
                break
            lines.append(line)
        return "\n".join(lines)

    @property
    def backend(self) -> str:
        return self._backend_type.value

    @property
    def is_enabled(self) -> bool:
        return self.enabled


# ─────────────────────────────────────────────────────────────────────────────
# Singleton factory
# ─────────────────────────────────────────────────────────────────────────────

_vector_memory_instance: Optional[VectorMemoryStore] = None


def get_vector_memory(config=None) -> VectorMemoryStore:
    """
    Get (or lazily create) the singleton VectorMemoryStore.
    
    Reads configuration from a VectorMemoryConfig object if provided,
    otherwise falls back to environment variables directly.
    
    Call once at service startup and reuse throughout.
    """
    global _vector_memory_instance
    if _vector_memory_instance is not None:
        return _vector_memory_instance

    if config is not None:
        # Config object provided (from ConfigManager)
        enabled            = config.enabled
        backend_str        = config.backend
        embedding_str      = config.embedding_provider
        collection         = config.collection_name
        top_k              = config.top_k
        score_threshold    = config.score_threshold
        max_entries        = config.max_entries
    else:
        # Fall back to reading env vars directly
        enabled            = os.getenv("VECTOR_MEMORY_ENABLED", "false").lower() == "true"
        backend_str        = os.getenv("VECTOR_MEMORY_BACKEND", "in_memory")
        embedding_str      = os.getenv("VECTOR_MEMORY_EMBEDDING", "bedrock")
        collection         = os.getenv("VECTOR_MEMORY_COLLECTION", "a2a_memories")
        top_k              = int(os.getenv("VECTOR_MEMORY_TOP_K", "5"))
        score_threshold    = float(os.getenv("VECTOR_MEMORY_SCORE_THRESHOLD", "0.3"))
        max_entries        = int(os.getenv("VECTOR_MEMORY_MAX_ENTRIES", "1000"))

    try:
        backend   = VectorBackend(backend_str)
    except ValueError:
        logger.warning(f"[VectorMemory] Unknown backend '{backend_str}', falling back to in_memory")
        backend   = VectorBackend.IN_MEMORY

    try:
        embedding = EmbeddingProvider(embedding_str)
    except ValueError:
        logger.warning(f"[VectorMemory] Unknown embedding provider '{embedding_str}', falling back to bedrock")
        embedding = EmbeddingProvider.BEDROCK

    _vector_memory_instance = VectorMemoryStore(
        enabled=enabled,
        backend=backend,
        embedding_provider=embedding,
        collection=collection,
        top_k=top_k,
        score_threshold=score_threshold,
        max_entries=max_entries
    )
    return _vector_memory_instance


def reset_vector_memory():
    """Reset the singleton (useful for testing or config reload)."""
    global _vector_memory_instance
    _vector_memory_instance = None
