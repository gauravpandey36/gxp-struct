"""End-user query CLI.

Order of operations on every query (the Hierarchy of Power):
    1. Audit log: open record with a fresh query_id.
    2. Rules engine: deterministic pre-LLM check (rules.evaluate).
       - If a rule fires, return its answer + citations. LLM is never called.
    3. Recursive retriever: pull the most relevant chunks (with table
       resolution) from Pinecone.
    4. LLM synthesis: GPT-4o composes a grounded answer from those chunks
       with strict instructions to cite section numbers and refuse to
       speculate.
    5. Audit log: close record with everything captured.

Run:
    python query.py "What is the deadline for Level 2 investigation?"
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

from llama_index.core import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import get_response_synthesizer
from rich.console import Console
from rich.panel import Panel

import audit
import rules
from retriever import build_recursive_retriever, flatten

console = Console()


SYSTEM_PROMPT = PromptTemplate(
    """You are a GxP-compliance assistant grounded ONLY in the SOP excerpts below.

STRICT RULES:
  1. Answer using the excerpts only. If the excerpts do not contain the answer,
     reply exactly: "Not addressed in the SOP. Escalate to Quality Approver."
  2. Cite the SOP section number for every factual claim, e.g. (§ 5.2).
  3. Do NOT infer, generalize, or fill gaps from external knowledge.
  4. Quote table values verbatim where applicable.
  5. State the SOP version you relied on at the end of the answer.

SOP excerpts:
---------------------
{context_str}
---------------------

Question: {query_str}

Answer:"""
)


@dataclass
class Answer:
    query: str
    intent: str
    answer: str
    source: str  # "rule_engine" | "rag" | "fallback"
    citations: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    rule_id: str | None
    query_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "answer": self.answer,
            "source": self.source,
            "citations": self.citations,
            "retrieved_chunks": self.retrieved_chunks,
            "rule_id": self.rule_id,
            "query_id": self.query_id,
        }


def _format_citation_for_audit(c: rules.Citation) -> dict[str, Any]:
    return c.to_dict()


def _rag_answer(query: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Fall-through path: hit the recursive retriever + LLM."""
    retriever = build_recursive_retriever(similarity_top_k=6)
    nodes = retriever.retrieve(query)
    chunks = flatten(nodes)

    if not chunks:
        return (
            "Not addressed in the SOP. Escalate to Quality Approver.",
            [],
            [],
        )

    synthesizer = get_response_synthesizer(
        text_qa_template=SYSTEM_PROMPT,
        response_mode="compact",
    )
    engine = RetrieverQueryEngine(retriever=retriever, response_synthesizer=synthesizer)
    response = engine.query(query)

    answer_text = str(response).strip()
    citations = [
        {
            "sop_section": c.section,
            "sop_section_title": c.section_title,
            "node_id": c.node_id,
            "score": c.score,
        }
        for c in chunks
    ]
    return answer_text, citations, [c.to_dict() for c in chunks]


def answer_query(query: str, *, use_rag_fallback: bool = True) -> Answer:
    query_id = audit.new_query_id()

    # Stage 1: deterministic rule engine
    rule_result = rules.evaluate(query)
    if rule_result.fired:
        ans = Answer(
            query=query,
            intent=rule_result.intent.value,
            answer=rule_result.answer,
            source="rule_engine",
            citations=[_format_citation_for_audit(c) for c in rule_result.citations],
            retrieved_chunks=[],
            rule_id=rule_result.rule_id,
            query_id=query_id,
        )
        audit.log_query(
            query_id=query_id,
            query=query,
            intent=rule_result.intent.value,
            rule_triggered=rule_result.rule_id,
            retrieved_chunks=[],
            answer=ans.answer,
            citations=ans.citations,
            extra={"rule_metadata": rule_result.metadata},
        )
        return ans

    # Stage 2: fall through to RAG
    if not use_rag_fallback:
        ans = Answer(
            query=query,
            intent=rule_result.intent.value,
            answer="No deterministic rule matched and RAG fallback is disabled.",
            source="fallback",
            citations=[],
            retrieved_chunks=[],
            rule_id=None,
            query_id=query_id,
        )
        audit.log_query(
            query_id=query_id, query=query, intent=rule_result.intent.value,
            rule_triggered=None, retrieved_chunks=[], answer=ans.answer,
            citations=[],
        )
        return ans

    answer_text, citations, retrieved = _rag_answer(query)
    ans = Answer(
        query=query,
        intent=rule_result.intent.value,
        answer=answer_text,
        source="rag",
        citations=citations,
        retrieved_chunks=retrieved,
        rule_id=None,
        query_id=query_id,
    )
    audit.log_query(
        query_id=query_id,
        query=query,
        intent=rule_result.intent.value,
        rule_triggered=None,
        retrieved_chunks=retrieved,
        answer=answer_text,
        citations=citations,
    )
    return ans


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_human(ans: Answer) -> None:
    badge = {
        "rule_engine": "[bold green]DETERMINISTIC[/bold green]",
        "rag":         "[bold cyan]RAG[/bold cyan]",
        "fallback":    "[bold red]FALLBACK[/bold red]",
    }.get(ans.source, ans.source)

    console.print(Panel.fit(
        f"{badge}  intent=[yellow]{ans.intent}[/yellow]  "
        f"rule_id=[magenta]{ans.rule_id or '—'}[/magenta]\n\n"
        f"{ans.answer}",
        title=f"Q: {ans.query}",
        border_style="blue",
    ))
    if ans.citations:
        console.print("[dim]Citations:[/dim]")
        for c in ans.citations:
            sec = c.get("sop_section", "?")
            title = c.get("sop_section_title", "")
            console.print(f"  • § {sec} {title}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query GxP-Struct.")
    parser.add_argument("query", nargs="?", help="The question. If omitted, reads stdin.")
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    parser.add_argument("--no-rag", action="store_true",
                        help="Disable RAG fallback — only use the rule engine.")
    args = parser.parse_args()

    q = args.query or sys.stdin.read().strip()
    if not q:
        raise SystemExit("No query provided.")

    ans = answer_query(q, use_rag_fallback=not args.no_rag)

    if args.json:
        print(json.dumps(ans.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_human(ans)


if __name__ == "__main__":
    main()
