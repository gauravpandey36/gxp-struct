# Implementation Guide

Developer-facing reference for the Python implementation. If you are evaluating GxP-Struct for adoption, start with the [README](../README.md) and [SCHEMA_SPEC](SCHEMA_SPEC.md). This document is for the engineer who will run, extend, or integrate the reference implementation.

---

## Architecture

```
                  ┌──────────────┐
   user query ──▶ │ rules.py     │ ──── deterministic answer ──┐
                  │  intent      │      (rule_engine source)    │
                  │  + hard rule │                              ▼
                  └──────┬───────┘                       ┌──────────────┐
                         │  miss                         │ audit.py     │
                         ▼                               │  JSONL log   │
                  ┌──────────────┐    Pinecone           └──────────────┘
                  │ retriever.py │ ◀─── (cosine sim +           ▲
                  │  Recursive   │      metadata filters)       │
                  │  Retriever   │                              │
                  └──────┬───────┘                              │
                         ▼                                      │
                  ┌──────────────┐                              │
                  │ GPT-4o       │ ── grounded, cited answer ───┘
                  │ (templated)  │      (rag source)
                  └──────────────┘
```

## Files

| File | Purpose |
|---|---|
| `config.py` | Loads `.env`, exposes typed `Settings`. |
| `audit.py` | Append-only JSONL log of every query (21 CFR Part 11 friendly). |
| `rules.py` | Intent detection + deterministic rules. **Runs before the LLM.** |
| `parser_gxp.py` | Parses `.gxp` files into rule tables. |
| `ingest.py` | `MarkdownElementNodeParser` → metadata-tagged nodes → Pinecone. |
| `retriever.py` | `RecursiveRetriever` so table IndexNodes resolve to real values. |
| `query.py` | CLI entrypoint. Rule-check → retrieve → synthesize. |
| `validation_test.py` | Golden Q&A harness. Run with `--rules-only` for a no-API smoke test. |
| `examples/Deviation_SOP.gxp` | The machine-readable SOP — canonical schema example. |
| `data/Deviation_SOP.md` | Source SOP, Rev 1.0 — the prose human-readable original. |
| `audit/queries.jsonl` | Audit trail (created on first run). |

## Setup

```bash
cd gxp-struct
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Fill in OPENAI_API_KEY and PINECONE_API_KEY
```

## Smoke test (no API calls)

This validates the rule engine — the part that *replaces* the LLM for hard rules.

```bash
python validation_test.py --rules-only
```

Expected: 10/10 PASS.

## Parse the `.gxp` file

To verify the schema parser independently:

```bash
python parser_gxp.py examples/Deviation_SOP.gxp --print
```

This prints the parsed rule table — the same table the rule engine consumes at runtime.

## Ingest the SOP

```bash
python ingest.py --recreate
```

This will:
1. Create the Pinecone index `gxp-struct` with cosine similarity (3072 dim) if missing.
2. Parse `data/Deviation_SOP.md` with `MarkdownElementNodeParser` so the responsibilities table (§ 3.0) and timelines table (§ 5.3) are stored as structured Data Objects, not flattened text.
3. Stamp every node with metadata (sop_version, section, rule_type, `initiation_clock`, `language_exception`, `default_level`, etc.).
4. Upsert into namespace `gxp-struct-v1`.

## Ask questions

```bash
python query.py "What is the deadline for Level 2 investigation?"
python query.py "An operator falsified data — what level?"
python query.py "Do Austria records need to be in English?"
python query.py --json "What is excluded from the SOP scope?"
```

Each response is tagged with its source — `DETERMINISTIC` (rule fired, LLM not called) or `RAG` (retriever + LLM with grounded synthesis).

## Full validation (RAG path included)

After ingestion completes:

```bash
python validation_test.py
```

This runs all 10 golden cases including the open-ended scope question that is *expected* to fall through to RAG. Use this as the regression bar before any change.

## GxP / compliance notes

- **Audit trail.** Every query writes one JSONL line to `audit/queries.jsonl` including the SOP version it was answered against, the model, the intent, the rule that fired (if any), the retrieved chunks, and the final answer. Designed for 21 CFR Part 11 / Annex 11 expectations. In production, mount this path on a write-once volume and tail it to your eQMS.
- **SOP versioning.** `SOP_VERSION` in `.env` is stamped on every chunk *and* every audit record. To onboard a new revision, bump the version, change `PINECONE_NAMESPACE` to `gxp-struct-v<n>`, and re-run `ingest.py --recreate`. Old namespaces remain queryable for historical audits.
- **Attachment 4.** The default-to-Level-1 rule depends on a controlled reference list. Populate `ATTACHMENT_4_REFERENCE_LIST` in `rules.py` from the controlled artifact under change control, OR populate it from the `.gxp` file via `@ATTACHMENT` references. Until then, the rule conservatively returns Level 1 (with a citation back to § 5.2) for any item not in the list — which is the SOP's own default.
- **No silent fallback.** If retrieval comes back empty, the LLM is instructed to reply *"Not addressed in the SOP. Escalate to Quality Approver."* — never to invent.
- **Temperature 0.** Generation is deterministic-as-possible.

## Hierarchy of Power

When the same question could plausibly be answered two ways, the rule engine wins. Examples:

| Question | Mechanism | Why |
|---|---|---|
| "Initiation deadline?" | Rule (§ 5.1) | Hard SOP requirement, no ambiguity. |
| "What level if not in Attachment 4?" | Rule (§ 5.2) | Default classification is a hard rule. |
| "Sterility breach — level?" | Rule (§ 5.2) | L2 trigger is mandatory. |
| "Level 2 investigation deadline?" | Rule (§ 5.3) | Timeline table — verbatim values only. |
| "What's excluded from the SOP scope?" | RAG (§ 2.0) | Open-ended; LLM synthesizes from retrieved chunk. |

## Extending the engine

To add a new rule family:

1. Add the tag to [SCHEMA_SPEC.md](SCHEMA_SPEC.md) § 4.
2. Add a parser branch in `parser_gxp.py`.
3. Add a rule function in `rules.py` (returning a `RuleResult`).
4. Add an intent in `Intent` enum and a regex in `_INTENT_PATTERNS`.
5. Add a dispatch line in `evaluate()`.
6. Add golden test cases.
7. Update [Logic_Rules.md](../Logic_Rules.md).

The framework intentionally keeps these in lockstep — new rule families that aren't reflected in all six places aren't really part of the framework.

## Roadmap

1. `parser_gxp.py` becomes the single source of truth (rules.py reads its lookup tables from the parsed `.gxp`, not from Python literals). v0.1 ships with both for safety; v0.2 will eliminate the duplicated tables.
2. Bridge Agent — LLM-assisted authoring tool that proposes a `.gxp` from a prose SOP for SME review. Single biggest reduction in adoption friction.
3. `--validate-citations` flag that re-checks every quoted excerpt actually exists in the indexed SOP (defense against quote drift).
4. Annex 11 / Part 11 self-test that proves audit log immutability.
5. Multi-SOP support — per-SOP namespace, per-question SOP routing, cross-SOP `@REFERENCE` linkage.
