"""Golden Q&A validation harness.

Two modes:

  python validation_test.py --rules-only
      Runs the rule engine against the golden set with NO API calls.
      This is the fast smoke test — proves the deterministic layer works.

  python validation_test.py
      Full run: rule engine + RAG fallback. Requires OPENAI_API_KEY and
      a populated Pinecone namespace.

The harness asserts on:
  - The answer's *source* (rule_engine vs rag) — proves we're not letting
    the LLM speculate on questions that have a hard answer.
  - For deterministic answers, the *rule_id* and key facts.
  - For RAG answers, the citation set must contain the expected section.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable

from rich.console import Console
from rich.table import Table

import rules

console = Console()


@dataclass
class Case:
    name: str
    query: str
    expected_source: str            # "rule_engine" or "rag"
    expected_rule_id: str | None
    expected_section: str | None    # used for RAG cases
    expected_substrings: list[str]  # all must appear in answer (case-insensitive)


GOLDEN: list[Case] = [
    # --- Deterministic / rule-engine cases ---
    Case(
        name="Initiation clock",
        query="When must I initiate a deviation record after discovery?",
        expected_source="rule_engine",
        expected_rule_id="R-5.1-CLOCK_START",
        expected_section="5.1",
        expected_substrings=["2 business days", "5.1"],
    ),
    Case(
        name="Default classification (not in Attachment 4)",
        query="A new type of deviation occurred that is not listed in Attachment 4. What level is it?",
        expected_source="rule_engine",
        expected_rule_id="R-5.2-DEFAULT_L1",
        expected_section="5.2",
        expected_substrings=["Level 1", "Attachment 4"],
    ),
    Case(
        name="L2 trigger — sterility",
        query="A sterility breach occurred during fill. What level should this be classified as?",
        expected_source="rule_engine",
        expected_rule_id="R-5.2-L2_TRIGGER",
        expected_section="5.2",
        expected_substrings=["Level 2", "sterility"],
    ),
    Case(
        name="L2 trigger — falsified data",
        query="An operator falsified batch records. Classification?",
        expected_source="rule_engine",
        expected_rule_id="R-5.2-L2_TRIGGER",
        expected_section="5.2",
        expected_substrings=["Level 2", "falsif"],
    ),
    Case(
        name="L2 trigger — critical process parameter",
        query="The deviation involved a critical process parameter excursion. What level?",
        expected_source="rule_engine",
        expected_rule_id="R-5.2-L2_TRIGGER",
        expected_section="5.2",
        expected_substrings=["Level 2"],
    ),
    Case(
        name="Timeline — Level 2 Investigation",
        query="What is the deadline for Level 2 Investigation?",
        expected_source="rule_engine",
        expected_rule_id="R-5.3-LEVEL_2_INVESTIGATION",
        expected_section="5.3",
        expected_substrings=["60", "calendar days"],
    ),
    Case(
        name="Timeline — CAPA Execution",
        query="How many days do I have for CAPA Execution?",
        expected_source="rule_engine",
        expected_rule_id="R-5.3-CAPA_EXECUTION",
        expected_section="5.3",
        expected_substrings=["60", "investigation approval"],
    ),
    Case(
        name="Language — Austria exemption",
        query="Do records at our Austria BioLife site have to be in English?",
        expected_source="rule_engine",
        expected_rule_id="R-5.1-LANG_EXEMPTION",
        expected_section="5.1",
        expected_substrings=["Austria", "exempt"],
    ),
    Case(
        name="Responsibility — Quality Approver",
        query="Who is the Quality Approver and what do they do?",
        expected_source="rule_engine",
        expected_rule_id="R-3.0-QUALITY_APPROVER",
        expected_section="3.0",
        expected_substrings=["final leveling", "disposition"],
    ),
    # --- RAG fall-through case (no deterministic rule should fire) ---
    Case(
        name="Open-ended scope question (RAG path)",
        query="What activities are excluded from the scope of this SOP?",
        expected_source="rag",
        expected_rule_id=None,
        expected_section="2.0",
        expected_substrings=["Preclinical", "Environmental"],
    ),
]


def _check_substrings(answer: str, expected: list[str]) -> tuple[bool, list[str]]:
    a = answer.lower()
    missing = [s for s in expected if s.lower() not in a]
    return (not missing), missing


def _run_rules_only(case: Case) -> tuple[bool, str, dict]:
    result = rules.evaluate(case.query)
    info: dict = {
        "fired": result.fired,
        "rule_id": result.rule_id or None,
        "intent": result.intent.value,
        "answer": result.answer,
    }
    if case.expected_source == "rule_engine":
        if not result.fired:
            return False, f"expected rule to fire, got miss (intent={result.intent.value})", info
        if case.expected_rule_id and result.rule_id != case.expected_rule_id:
            return False, f"rule_id mismatch: {result.rule_id} != {case.expected_rule_id}", info
        ok, missing = _check_substrings(result.answer, case.expected_substrings)
        if not ok:
            return False, f"answer missing substrings: {missing}", info
        return True, "ok", info
    else:
        # RAG path — in rules-only mode, the correct outcome is a miss.
        if result.fired:
            return False, f"unexpected rule fired ({result.rule_id})", info
        return True, "ok (rule correctly deferred to RAG)", info


def _run_full(case: Case) -> tuple[bool, str, dict]:
    # Lazy import — only needed for full mode.
    from query import answer_query  # type: ignore
    ans = answer_query(case.query)
    info = {
        "source": ans.source,
        "rule_id": ans.rule_id,
        "intent": ans.intent,
        "answer": ans.answer,
    }
    if ans.source != case.expected_source:
        return False, f"source mismatch: {ans.source} != {case.expected_source}", info
    if case.expected_source == "rule_engine":
        if case.expected_rule_id and ans.rule_id != case.expected_rule_id:
            return False, f"rule_id mismatch: {ans.rule_id} != {case.expected_rule_id}", info
    ok, missing = _check_substrings(ans.answer, case.expected_substrings)
    if not ok:
        return False, f"answer missing substrings: {missing}", info
    if case.expected_source == "rag" and case.expected_section:
        sections = {c.get("sop_section") for c in ans.citations}
        if case.expected_section not in sections:
            return False, f"expected section {case.expected_section} not in citations {sections}", info
    return True, "ok", info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-only", action="store_true",
                        help="Skip RAG path; test rule engine only (no API calls).")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    runner: Callable[[Case], tuple[bool, str, dict]] = (
        _run_rules_only if args.rules_only else _run_full
    )

    table = Table(title=f"GxP-Struct validation ({'rules-only' if args.rules_only else 'full'})")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Case")
    table.add_column("Result")
    table.add_column("Detail", overflow="fold")

    passed = 0
    for i, case in enumerate(GOLDEN, 1):
        ok, msg, info = runner(case)
        status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        detail = msg
        if args.verbose:
            detail += f"\n  intent={info.get('intent')} rule_id={info.get('rule_id')}"
            detail += f"\n  answer={info.get('answer','')[:200]}"
        table.add_row(str(i), case.name, status, detail)
        if ok:
            passed += 1

    console.print(table)
    total = len(GOLDEN)
    console.print(f"\n[bold]{passed}/{total} passed[/bold]")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
