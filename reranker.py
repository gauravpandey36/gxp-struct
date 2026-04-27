"""
Cross-encoder re-ranker for pharmaceutical document retrieval.

Uses a cross-encoder model (ms-marco-MiniLM-L-6-v2) to re-rank candidate
chunks from the hybrid retriever by computing pairwise relevance scores
between the query and each candidate.

Author: Gourav Pandey
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# Default cross-encoder model for re-ranking
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass
class RankedChunk:
    """A chunk with both retrieval and re-ranking scores."""

    chunk_id: str
    text: str
    retrieval_score: float
    rerank_score: float
    rank: int
    metadata: dict


class Reranker:
    """
    Cross-encoder re-ranker that scores query-document pairs for relevance.

    The cross-encoder processes the full (query, document) pair jointly,
    producing more accurate relevance scores than bi-encoder similarity
    at the cost of higher latency. Best used on a small candidate set
    (10-50 chunks) pre-filtered by the hybrid retriever.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        max_length: int = 512,
        batch_size: int = 32,
    ) -> None:
        """
        Initialize the cross-encoder re-ranker.

        Args:
            model_name: HuggingFace model name for the cross-encoder.
            device: Device to run inference on ('cpu', 'cuda', or None for auto).
            max_length: Maximum token length for input pairs.
            batch_size: Batch size for inference.
        """
        self._model_name = model_name
        self._batch_size = batch_size
        self._max_length = max_length

        logger.info("Loading cross-encoder model: %s", model_name)
        start = time.time()
        self._model = CrossEncoder(
            model_name,
            max_length=max_length,
            device=device,
        )
        elapsed = time.time() - start
        logger.info("Cross-encoder loaded in %.2fs", elapsed)

    def rerank(
        self,
        query: str,
        chunks: list,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
    ) -> list[RankedChunk]:
        """
        Re-rank candidate chunks by cross-encoder relevance score.

        Args:
            query: The user query.
            chunks: List of RetrievedChunk objects from the hybrid retriever.
            top_k: Number of top results to return after re-ranking.
            score_threshold: Optional minimum score to include a chunk.
                If set, chunks below this threshold are dropped even if
                within top_k.

        Returns:
            List of RankedChunk objects sorted by rerank_score descending.
        """
        if not chunks:
            logger.warning("Reranker received empty chunk list")
            return []

        logger.info(
            "Re-ranking %d chunks for query: '%s'",
            len(chunks),
            query[:80],
        )
        start = time.time()

        # Build query-document pairs
        pairs = [(query, chunk.text) for chunk in chunks]

        # Score all pairs
        scores = self._model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )

        # Pair scores with chunks and sort
        scored = list(zip(chunks, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        # Apply threshold filter if specified
        if score_threshold is not None:
            scored = [(c, s) for c, s in scored if s >= score_threshold]

        # Build ranked results
        results = []
        for rank, (chunk, score) in enumerate(scored[:top_k], start=1):
            results.append(
                RankedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    retrieval_score=chunk.score,
                    rerank_score=float(score),
                    rank=rank,
                    metadata=getattr(chunk, "metadata", {}),
                )
            )

        elapsed = time.time() - start
        logger.info(
            "Re-ranking complete: %d -> %d chunks in %.3fs",
            len(chunks),
            len(results),
            elapsed,
        )
        return results

    def score_single(self, query: str, document: str) -> float:
        """
        Score a single query-document pair.

        Useful for evaluating individual documents or for integration
        with other pipelines.

        Args:
            query: The query text.
            document: The document text.

        Returns:
            Relevance score as a float.
        """
        scores = self._model.predict(
            [(query, document)],
            show_progress_bar=False,
        )
        return float(scores[0])


class RetrieveAndRerank:
    """
    End-to-end retrieve-then-rerank pipeline.

    Combines the hybrid retriever with the cross-encoder re-ranker into
    a single callable interface. First retrieves a broad candidate set,
    then re-ranks for precision.
    """

    def __init__(
        self,
        retriever,
        reranker: Reranker,
        retrieval_candidates: int = 30,
        final_top_k: int = 5,
        score_threshold: Optional[float] = None,
    ) -> None:
        """
        Initialize the retrieve-and-rerank pipeline.

        Args:
            retriever: A HybridRetriever (or any retriever with a search method).
            reranker: A Reranker instance.
            retrieval_candidates: Number of candidates to fetch from retriever.
            final_top_k: Number of results after re-ranking.
            score_threshold: Minimum re-rank score to include.
        """
        self._retriever = retriever
        self._reranker = reranker
        self._retrieval_candidates = retrieval_candidates
        self._final_top_k = final_top_k
        self._score_threshold = score_threshold

    def search(self, query: str, top_k: Optional[int] = None) -> list[RankedChunk]:
        """
        Execute the full retrieve-and-rerank pipeline.

        Args:
            query: The search query.
            top_k: Override for final_top_k if provided.

        Returns:
            List of RankedChunk objects, re-ranked by cross-encoder.
        """
        k = top_k or self._final_top_k

        # Stage 1: Broad retrieval
        candidates = self._retriever.search(
            query,
            top_k=self._retrieval_candidates,
        )

        # Stage 2: Re-rank
        results = self._reranker.rerank(
            query=query,
            chunks=candidates,
            top_k=k,
            score_threshold=self._score_threshold,
        )

        return results
