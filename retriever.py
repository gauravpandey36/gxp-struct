"""RecursiveRetriever wired to the Pinecone-backed index.

Why RecursiveRetriever instead of a plain vector retriever?

The MarkdownElementNodeParser produces two kinds of nodes:
  - TextNodes  for prose paragraphs.
  - IndexNodes for tables (e.g. § 5.3 timelines, § 3.0 responsibilities).

An IndexNode is a *pointer* to its underlying structured representation.
A plain retriever returns the pointer, leaving the LLM to chase references.
RecursiveRetriever resolves those pointers automatically and returns the
actual table content alongside any matched text — that's the difference
between "the SOP mentions a timelines table" and "Level 2 Investigation: 60
calendar days from initiation."

We also expose `retrieve_with_section_filter()` for the rare cases where
the query engine wants to constrain results to a specific section number
(e.g. only § 5.2 chunks for a classification refinement question).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llama_index.core import Settings as LISettings, VectorStoreIndex
from llama_index.core.retrievers import RecursiveRetriever
from llama_index.core.schema import IndexNode, NodeWithScore
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone

from config import get_settings


@dataclass
class RetrievedChunk:
    """A flat representation suitable for audit logging."""
    node_id: str
    score: float
    section: str
    section_title: str
    rule_type: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "score": self.score,
            "section": self.section,
            "section_title": self.section_title,
            "rule_type": self.rule_type,
            "text_preview": self.text[:300],
        }


def _configure_models() -> None:
    s = get_settings()
    LISettings.embed_model = OpenAIEmbedding(
        model=s.embedding_model, api_key=s.openai_api_key
    )
    LISettings.llm = OpenAI(
        model=s.llm_model, api_key=s.openai_api_key,
        temperature=s.llm_temperature,
    )


def build_index() -> VectorStoreIndex:
    """Re-attach to the existing Pinecone namespace as a queryable index."""
    _configure_models()
    s = get_settings()
    pc = Pinecone(api_key=s.pinecone_api_key)
    pinecone_index = pc.Index(s.pinecone_index_name)
    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        namespace=s.pinecone_namespace,
    )
    return VectorStoreIndex.from_vector_store(vector_store=vector_store)


def build_recursive_retriever(
    *,
    similarity_top_k: int = 6,
    section_filter: str | None = None,
) -> RecursiveRetriever:
    """Build a RecursiveRetriever. If `section_filter` is set, restrict
    similarity search to chunks tagged with that section number.
    """
    index = build_index()

    filters = None
    if section_filter:
        filters = MetadataFilters(filters=[
            MetadataFilter(key="section", value=section_filter)
        ])

    base_retriever = index.as_retriever(
        similarity_top_k=similarity_top_k,
        filters=filters,
    )

    # The recursive retriever resolves IndexNode references.
    return RecursiveRetriever(
        "vector",
        retriever_dict={"vector": base_retriever},
        verbose=False,
    )


def flatten(nodes: list[NodeWithScore]) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for nws in nodes:
        n = nws.node
        meta = n.metadata or {}
        # Skip unresolved IndexNode pointers — the recursive retriever
        # should have replaced them, but be defensive.
        if isinstance(n, IndexNode) and not getattr(n, "text", ""):
            continue
        out.append(RetrievedChunk(
            node_id=n.node_id,
            score=float(nws.score or 0.0),
            section=str(meta.get("section", "unknown")),
            section_title=str(meta.get("section_title", "")),
            rule_type=str(meta.get("rule_type", "general")),
            text=getattr(n, "text", "") or "",
        ))
    return out
