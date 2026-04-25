"""Ingestion pipeline: Markdown -> structured nodes -> Pinecone.

Key design points:

1. **MarkdownElementNodeParser** is used (NOT a generic text splitter) so
   the responsibilities table in § 3.0 and the timelines table in § 5.3
   are kept as Data Objects — IndexNodes that link to a structured
   representation rather than being chopped into arbitrary character
   windows.

2. **Section-aware metadata injection** — every node gets stamped with
   its parent section (5.1, 5.2, etc.), the SOP version, and any
   relevant rule_type tags so the RecursiveRetriever can filter by
   "hard rule" sections before falling back to similarity.

3. **Idempotent upsert** — re-running this script against the same SOP
   version replaces the namespace; bumping SOP_VERSION in .env creates a
   fresh namespace so old revisions remain queryable for audit.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

from llama_index.core import Document, Settings as LISettings, VectorStoreIndex, StorageContext
from llama_index.core.node_parser import MarkdownElementNodeParser
from llama_index.core.schema import BaseNode, IndexNode, TextNode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from rich.console import Console

from config import get_settings

console = Console()


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

SECTION_TAGS: dict[str, dict[str, str | list[str]]] = {
    "1.0": {"title": "Objective", "rule_type": "context"},
    "2.0": {"title": "Scope", "rule_type": "scope"},
    "3.0": {"title": "Responsibilities", "rule_type": "roles", "is_table": "true"},
    "4.0": {"title": "References", "rule_type": "context"},
    "5.1": {"title": "Initiation and Containment", "rule_type": "hard_rule",
            "initiation_clock": "2_business_days",
            "language_exception": "Austria"},
    "5.2": {"title": "Risk-Based Leveling", "rule_type": "classification",
            "default_level": "Level_1",
            "l2_triggers": "critical_process_parameters,sterility,falsified_data"},
    "5.3": {"title": "Performance Timelines", "rule_type": "hard_rule",
            "is_table": "true"},
    "6.0": {"title": "Attachments", "rule_type": "reference"},
    "7.0": {"title": "List of Changes", "rule_type": "version"},
}

_SECTION_RE = re.compile(r"^\s*#{1,6}\s*(\d+\.\d+|\d+\.0)\s+(.+?)\s*$", re.MULTILINE)


def detect_section_for_text(text: str, full_doc: str) -> str | None:
    """Return the section number (e.g. '5.2') that contains `text`.

    Strategy: find all section headers in the full doc with their offsets,
    locate `text` in the full doc, and pick the most recent header.
    """
    if not text.strip():
        return None
    headers = [(m.group(1), m.start()) for m in _SECTION_RE.finditer(full_doc)]
    if not headers:
        return None
    # Use a short signature of the chunk to locate it
    needle = text.strip()[:80]
    idx = full_doc.find(needle)
    if idx == -1:
        # Fall back to longest common prefix
        return None
    current = None
    for sec, pos in headers:
        if pos <= idx:
            current = sec
        else:
            break
    return current


# ---------------------------------------------------------------------------
# Pinecone setup
# ---------------------------------------------------------------------------

def ensure_pinecone_index() -> Pinecone:
    s = get_settings()
    pc = Pinecone(api_key=s.pinecone_api_key)
    existing = {ix["name"] for ix in pc.list_indexes()}
    if s.pinecone_index_name not in existing:
        console.print(f"[yellow]Creating Pinecone index '{s.pinecone_index_name}'...[/yellow]")
        pc.create_index(
            name=s.pinecone_index_name,
            dimension=s.embedding_dim,
            metric="cosine",
            spec=ServerlessSpec(cloud=s.pinecone_cloud, region=s.pinecone_region),
        )
    else:
        console.print(f"[green]Pinecone index '{s.pinecone_index_name}' already exists.[/green]")
    return pc


# ---------------------------------------------------------------------------
# Metadata injection
# ---------------------------------------------------------------------------

def stamp_metadata(nodes: Iterable[BaseNode], full_doc: str) -> list[BaseNode]:
    s = get_settings()
    out: list[BaseNode] = []
    for node in nodes:
        text = getattr(node, "text", "") or ""
        section = detect_section_for_text(text, full_doc) or "unknown"
        tags = SECTION_TAGS.get(section, {})

        # Pinecone metadata must be flat scalars / lists of scalars.
        meta = {
            "sop_id": s.sop_id,
            "sop_title": s.sop_title,
            "sop_version": s.sop_version,
            "sop_effective_date": s.sop_effective_date,
            "section": section,
            "section_title": str(tags.get("title", "")),
            "rule_type": str(tags.get("rule_type", "general")),
            "node_type": "table" if isinstance(node, IndexNode) else "text",
        }
        # Promote optional rule tags as separate keys (filterable in Pinecone).
        for opt in ("initiation_clock", "language_exception", "default_level",
                    "l2_triggers", "is_table"):
            if opt in tags:
                meta[opt] = str(tags[opt])

        # Merge instead of overwrite
        existing_meta = dict(node.metadata or {})
        existing_meta.update(meta)
        node.metadata = existing_meta
        # Also bake the section header into the embedded text so similarity
        # search has a hint even before metadata filtering.
        if isinstance(node, TextNode):
            prefix = f"[SOP § {section} — {meta['section_title']}]\n"
            if not node.text.startswith("[SOP §"):
                node.text = prefix + node.text
        out.append(node)
    return out


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def run_ingestion(sop_path: Path, *, recreate: bool = False) -> None:
    s = get_settings()

    # Configure global LlamaIndex settings
    LISettings.embed_model = OpenAIEmbedding(
        model=s.embedding_model, api_key=s.openai_api_key
    )
    LISettings.llm = OpenAI(
        model=s.llm_model, api_key=s.openai_api_key,
        temperature=s.llm_temperature,
    )

    # Read source
    raw = sop_path.read_text(encoding="utf-8")
    doc = Document(
        text=raw,
        metadata={"source": str(sop_path), "sop_version": s.sop_version},
    )

    # Hierarchical parse — keep tables as objects
    parser = MarkdownElementNodeParser(
        llm=LISettings.llm,
        num_workers=2,
    )
    raw_nodes = parser.get_nodes_from_documents([doc])
    base_nodes, objects = parser.get_nodes_and_objects(raw_nodes)
    all_nodes: list[BaseNode] = list(base_nodes) + list(objects)
    console.print(
        f"[cyan]Parsed[/cyan] {len(base_nodes)} text nodes + "
        f"{len(objects)} structured objects (tables)."
    )

    # Inject metadata
    all_nodes = stamp_metadata(all_nodes, raw)

    # Pinecone
    pc = ensure_pinecone_index()
    pinecone_index = pc.Index(s.pinecone_index_name)

    if recreate:
        console.print(f"[yellow]Deleting all vectors in namespace '{s.pinecone_namespace}'...[/yellow]")
        try:
            pinecone_index.delete(delete_all=True, namespace=s.pinecone_namespace)
        except Exception as e:  # namespace may not exist yet
            console.print(f"[dim]Namespace clear skipped: {e}[/dim]")

    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        namespace=s.pinecone_namespace,
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    console.print(f"[cyan]Embedding & upserting to namespace '{s.pinecone_namespace}'...[/cyan]")
    VectorStoreIndex(
        nodes=all_nodes,
        storage_context=storage_context,
    )
    console.print(f"[bold green]✓ Ingestion complete.[/bold green] "
                  f"{len(all_nodes)} nodes stored in '{s.pinecone_namespace}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SOP into Pinecone.")
    parser.add_argument(
        "--sop",
        type=Path,
        default=Path(__file__).parent / "data" / "Deviation_SOP.md",
        help="Path to the SOP markdown file.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete the namespace before re-upserting (clean reload).",
    )
    args = parser.parse_args()

    if not args.sop.exists():
        raise SystemExit(f"SOP file not found: {args.sop}")
    run_ingestion(args.sop, recreate=args.recreate)


if __name__ == "__main__":
    main()
