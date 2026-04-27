"""
Hybrid BM25 + Vector Retrieval with Reciprocal Rank Fusion (RRF).

Combines sparse (BM25) and dense (Pinecone vector) retrieval for improved
recall and precision on pharmaceutical compliance documents. Results are
merged using RRF scoring to produce a single ranked list.

Author: Gourav Pandey
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single retrieved document chunk with scoring metadata."""

    chunk_id: str
    text: str
    score: float
    source: str  # 'bm25', 'vector', or 'hybrid'
    metadata: dict[str, Any] = field(default_factory=dict)


class BM25Index:
    """BM25 sparse index over a corpus of text chunks."""

    def __init__(self, corpus: list[dict[str, Any]]) -> None:
        """
        Initialize BM25 index from a corpus of chunk dictionaries.

        Args:
            corpus: List of dicts with at least 'chunk_id' and 'text' keys.
        """
        self._corpus = corpus
        tokenized = [self._tokenize(doc["text"]) for doc in corpus]
        self._index = BM25Okapi(tokenized)
        logger.info("BM25 index built with %d documents", len(corpus))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace tokenizer with lowercasing and punctuation removal."""
        import re

        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return text.split()

    def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        """
        Search the BM25 index.

        Args:
            query: The search query string.
            top_k: Number of top results to return.

        Returns:
            List of RetrievedChunk objects ranked by BM25 score.
        """
        tokenized_query = self._tokenize(query)
        scores = self._index.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                doc = self._corpus[idx]
                results.append(
                    RetrievedChunk(
                        chunk_id=doc["chunk_id"],
                        text=doc["text"],
                        score=float(scores[idx]),
                        source="bm25",
                        metadata=doc.get("metadata", {}),
                    )
                )
        return results


class VectorRetriever:
    """Dense vector retrieval using Pinecone."""

    def __init__(
        self,
        index_name: str,
        api_key: str,
        environment: str = "us-east-1",
        namespace: str = "",
    ) -> None:
        """
        Initialize the Pinecone vector retriever.

        Args:
            index_name: Name of the Pinecone index.
            api_key: Pinecone API key.
            environment: Pinecone environment/region.
            namespace: Optional namespace within the index.
        """
        from pinecone import Pinecone

        self._pc = Pinecone(api_key=api_key)
        self._index = self._pc.Index(index_name)
        self._namespace = namespace
        logger.info("Pinecone vector retriever connected to index '%s'", index_name)

    def _get_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding for the given text using OpenAI.

        Args:
            text: Input text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        import openai

        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        """
        Search Pinecone for similar vectors.

        Args:
            query: The search query string.
            top_k: Number of top results to return.

        Returns:
            List of RetrievedChunk objects ranked by cosine similarity.
        """
        embedding = self._get_embedding(query)
        results = self._index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True,
            namespace=self._namespace,
        )

        chunks = []
        for match in results.get("matches", []):
            metadata = match.get("metadata", {})
            chunks.append(
                RetrievedChunk(
                    chunk_id=match["id"],
                    text=metadata.get("text", ""),
                    score=float(match["score"]),
                    source="vector",
                    metadata=metadata,
                )
            )
        return chunks


class HybridRetriever:
    """
    Hybrid retriever combining BM25 and vector search with Reciprocal Rank Fusion.

    RRF formula: score(d) = sum(1 / (k + rank_i(d))) for each retriever i
    where k is a constant (default 60) that controls rank saturation.
    """

    def __init__(
        self,
        bm25_index: BM25Index,
        vector_retriever: VectorRetriever,
        rrf_k: int = 60,
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
    ) -> None:
        """
        Initialize the hybrid retriever.

        Args:
            bm25_index: Pre-built BM25 index.
            vector_retriever: Configured Pinecone retriever.
            rrf_k: RRF constant (higher = less rank-sensitive). Default 60.
            bm25_weight: Weight multiplier for BM25 RRF scores.
            vector_weight: Weight multiplier for vector RRF scores.
        """
        self._bm25 = bm25_index
        self._vector = vector_retriever
        self._rrf_k = rrf_k
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight

    def _compute_rrf_scores(
        self,
        bm25_results: list[RetrievedChunk],
        vector_results: list[RetrievedChunk],
    ) -> dict[str, float]:
        """
        Compute RRF scores for all retrieved chunks.

        Args:
            bm25_results: Ranked results from BM25.
            vector_results: Ranked results from vector search.

        Returns:
            Dictionary mapping chunk_id to combined RRF score.
        """
        rrf_scores: dict[str, float] = {}

        for rank, chunk in enumerate(bm25_results, start=1):
            score = self._bm25_weight * (1.0 / (self._rrf_k + rank))
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + score

        for rank, chunk in enumerate(vector_results, start=1):
            score = self._vector_weight * (1.0 / (self._rrf_k + rank))
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + score

        return rrf_scores

    def search(
        self,
        query: str,
        top_k: int = 10,
        bm25_candidates: int = 20,
        vector_candidates: int = 20,
    ) -> list[RetrievedChunk]:
        """
        Perform hybrid search combining BM25 and vector retrieval.

        Args:
            query: The search query string.
            top_k: Number of final results to return.
            bm25_candidates: Number of candidates from BM25.
            vector_candidates: Number of candidates from vector search.

        Returns:
            List of RetrievedChunk objects ranked by RRF score.
        """
        logger.info("Hybrid search for: '%s'", query[:80])

        bm25_results = self._bm25.search(query, top_k=bm25_candidates)
        logger.debug("BM25 returned %d candidates", len(bm25_results))

        vector_results = self._vector.search(query, top_k=vector_candidates)
        logger.debug("Vector search returned %d candidates", len(vector_results))

        rrf_scores = self._compute_rrf_scores(bm25_results, vector_results)

        # Build a lookup of chunk data from both result sets
        chunk_lookup: dict[str, RetrievedChunk] = {}
        for chunk in bm25_results + vector_results:
            if chunk.chunk_id not in chunk_lookup:
                chunk_lookup[chunk.chunk_id] = chunk

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        results = []
        for chunk_id in sorted_ids[:top_k]:
            base_chunk = chunk_lookup[chunk_id]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=base_chunk.text,
                    score=rrf_scores[chunk_id],
                    source="hybrid",
                    metadata={
                        **base_chunk.metadata,
                        "rrf_score": rrf_scores[chunk_id],
                        "in_bm25": any(c.chunk_id == chunk_id for c in bm25_results),
                        "in_vector": any(c.chunk_id == chunk_id for c in vector_results),
                    },
                )
            )

        logger.info(
            "Hybrid search returned %d results (from %d unique candidates)",
            len(results),
            len(rrf_scores),
        )
        return results


def create_hybrid_retriever(
    corpus: list[dict[str, Any]],
    pinecone_index: str,
    pinecone_api_key: str,
    pinecone_environment: str = "us-east-1",
    rrf_k: int = 60,
    bm25_weight: float = 1.0,
    vector_weight: float = 1.0,
) -> HybridRetriever:
    """
    Factory function to create a fully configured HybridRetriever.

    Args:
        corpus: List of chunk dicts with 'chunk_id' and 'text' keys.
        pinecone_index: Name of the Pinecone index.
        pinecone_api_key: Pinecone API key.
        pinecone_environment: Pinecone environment/region.
        rrf_k: RRF constant.
        bm25_weight: BM25 score weight.
        vector_weight: Vector score weight.

    Returns:
        Configured HybridRetriever instance.
    """
    bm25_index = BM25Index(corpus)
    vector_retriever = VectorRetriever(
        index_name=pinecone_index,
        api_key=pinecone_api_key,
        environment=pinecone_environment,
    )
    return HybridRetriever(
        bm25_index=bm25_index,
        vector_retriever=vector_retriever,
        rrf_k=rrf_k,
        bm25_weight=bm25_weight,
        vector_weight=vector_weight,
    )
