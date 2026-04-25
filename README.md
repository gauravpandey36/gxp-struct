<div align="center">

# GxP-Struct

### A machine-readable standard for pharmaceutical SOPs

**Deterministic. Auditable. Open-source. Built for the validated state.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Validation: 10/10](https://img.shields.io/badge/golden_suite-10%2F10-brightgreen.svg)](docs/RESEARCH_FINDINGS.md)
[![Schema: v0.1](https://img.shields.io/badge/schema-v0.1-orange.svg)](docs/SCHEMA_SPEC.md)
[![GxP](https://img.shields.io/badge/GxP-21_CFR_Part_11_aligned-purple.svg)](docs/VALIDATION_PROTOCOL.md)

</div>

---

## TL;DR

Standard RAG hallucinates. In pharmaceutical environments, hallucination means recalls, regulatory action, and patient harm — the cost of being wrong is asymmetric.

**GxP-Struct turns SOPs into a structure that AI can *execute* rather than *interpret***. Hard rules — classification levels, mandatory deadlines, geographic exemptions — bypass the LLM entirely. A deterministic rule engine answers them, cites the SOP section, and writes an immutable audit record. The LLM is invoked only for genuinely open-ended questions, and even then it is constrained to grounded synthesis with verbatim citations.

The reference implementation in this repo passes **10/10** on its golden test suite — every classification, timeline, and exemption answered with a SOP citation, no LLM creativity in the loop. See [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md) for the head-to-head results.

---

## The Problem

Retrieval-Augmented Generation (RAG) is the default pattern for putting an LLM on top of a corporate document corpus. It works passably for marketing FAQs and engineering wikis. It fails — sometimes catastrophically — in regulated environments. Three reasons:

1. **Tables get shredded.** Naïve chunking splits a responsibilities table down the middle, so the AI mixes a Quality Approver's authority with an Originator's role.
2. **Hierarchy of power is invisible.** RAG can't tell that a Job Aid contradicting an SOP must lose. To the embedder, both are just text.
3. **Defaults aren't enforceable.** The SOP says "if not in Attachment 4, classify as Level 1." A probabilistic model will sometimes say Level 1, sometimes Level 2 — and a regulator cannot accept "sometimes."

The fix is not a bigger model. The fix is upstream of the model: **make the document machine-readable, then enforce its rules deterministically before generation.**

---

## The Insight: Pharma documents are already structured

A pharmaceutical SOP is not free-form prose. It always has the same skeleton — Objective, Scope, Responsibilities, References, Procedure, Performance Timelines, Attachments, List of Changes. There are roughly 10–15 archetypes (SOPs, Protocols, Work Instructions, Job Aids, Test Methods, Specifications, Protocol Reports, Validation Plans, …) and every document of a given archetype follows the same skeleton.

That regularity is the asset standard RAG ignores. **GxP-Struct exploits it.**

---

## The Approach: The "Fourth Translation"

A pharmaceutical SOP is translated three times today:

1. English → Spanish for the Mexico site.
2. English → Mandarin for the Suzhou plant.
3. English → German for the Vienna BioLife center.

Each translation costs money because the *content* matters and the *form* is preserved exactly so a human in any language can execute the procedure identically.

**GxP-Struct introduces the fourth translation: English → Machine.**

The machine-readable version is the SOP's logic, extracted into a parseable rule format. It looks like this:

```
[SYSTEM_RULE_START]
SOP_ID: SOP-DEV-001 | REV: 1.0 | EFFECTIVE: 2026-04-25

# 1.0 ACCESS_CONTROL & RESPONSIBILITY
@RULE:RESP_001 { ROLE: "Quality Approver", AUTHORITY: "SOLE", ACTION: "Final Leveling Approval" }
@RULE:RESP_002 { ROLE: "Originator",       ACTION: "Initiation",            WINDOW: "2 Business Days" }

# 2.0 DETERMINISTIC_TIMELINES
@TIMELINE:L1_COMPLETION    { VALUE: 30, UNIT: "Calendar Days", START_EVENT: "Initiation" }
@TIMELINE:L2_INVESTIGATION { VALUE: 60, UNIT: "Calendar Days", START_EVENT: "Initiation" }
@TIMELINE:CAPA_EXECUTION   { VALUE: 60, UNIT: "Calendar Days", START_EVENT: "Investigation Approval" }

# 3.0 CLASSIFICATION_LOGIC (MANDATORY_PRECEDENCE)
@LOGIC:L2_TRIGGER { IF: ["Sterility", "Falsified Data", "CPP"], THEN: "Level 2", OVERRIDE: TRUE }
@LOGIC:DEFAULT    { IF: "NOT in Attachment 4",                  THEN: "Level 1", AUTHORITY: "Quality Approver" }
@LOGIC:CLOSE_REF  { IF: "Close Reference Deviation",            THEN: "Level 1", MANDATORY: TRUE }

# 4.0 GEOGRAPHIC_EXCEPTIONS
@EXCEPTION:LANG_01 { COUNTRY: "Austria", SITE: "BioLife", REQUIREMENT: "English", STATUS: "EXEMPT" }
[SYSTEM_RULE_END]
```

This is the canonical example shipped in [`examples/Deviation_SOP.gxp`](examples/Deviation_SOP.gxp). The SOP author owns it (they are the subject-matter expert); the AI consumes it without ambiguity.

---

## Three-Tier Architecture

```
                user query
                    │
                    ▼
        ┌───────────────────────┐
        │  Tier 1               │
        │  Intent Router        │   ← classifies as hard-rule vs open-ended
        └────┬──────────────┬───┘
             │              │
       hard rule        open-ended
             │              │
             ▼              ▼
    ┌────────────┐    ┌────────────┐
    │  Tier 2    │    │  Tier 3    │
    │  Rule      │    │  Grounded  │
    │  Engine    │    │  RAG (LLM) │
    │  (Python)  │    │  with      │
    │            │    │  citations │
    └─────┬──────┘    └──────┬─────┘
          │                  │
          └────────┬─────────┘
                   ▼
        ┌────────────────────┐
        │  Audit Log         │   ← every call: SOP version, rule fired,
        │  (JSONL, append)   │     retrieved chunks, final answer
        └────────────────────┘
                   │
                   ▼
              user answer
```

**Tier 1 — Intent Router.** Detects whether the question is about a hard rule (deadlines, classifications, exemptions, responsibilities) or a soft information request (scope, summary, reference).

**Tier 2 — Deterministic Rule Engine.** When a hard rule is detected, a rule executes against the parsed `.gxp` file and returns a cited answer without calling the LLM. This is where determinism lives.

**Tier 3 — Grounded RAG.** When no rule fires, the system retrieves the most relevant chunks (using `MarkdownElementNodeParser` so tables stay intact) and synthesizes an answer with strict instructions to cite the SOP section and refuse to speculate.

Audit logging is unconditional. Every query, regardless of which tier resolves it, produces one JSONL record with the SOP version, the rule that fired (if any), the retrieved chunks, and the final answer — designed for 21 CFR Part 11 / EU Annex 11 expectations.

---

## Evidence: Head-to-Head

The following scenarios were run against (a) standard RAG over the prose SOP and (b) GxP-Struct over the same content plus the `.gxp` machine-readable layer.

| Scenario | Question type | Standard RAG | GxP-Struct |
|---|---|---|---|
| Authority hierarchy ("Can the Deviation Owner approve final leveling?") | Authority logic | Reasonably correct on the "no" but couldn't link to the *Sole Authority* clause | Returns "Quality Approver — sole authority per § 3.0" deterministically with rule_id `R-3.0-QUALITY_APPROVER` |
| Default classification ("New deviation, not in Attachment 4 — what level?") | Mandatory default | Inconsistent: sometimes Level 1, sometimes Level 2 | Always Level 1 by rule `R-5.2-DEFAULT_L1`, cited to § 5.2 |
| L2 trigger ("Operator falsified records — what level?") | Mandatory override | Identified L2 by similarity but cannot guarantee it | Mandatory L2 by rule `R-5.2-L2_TRIGGER`, OVERRIDE=TRUE |
| Temporal logic ("Initiation deadline?") | Business vs calendar days | Frequently confuses business days with calendar days | Returns "2 business days" verbatim from `@RULE:RESP_002`, cited to § 5.1 |
| Performance timeline ("Level 2 investigation deadline?") | Mandatory deadline | Pulls a number; correctness varies with chunk boundaries | Returns "60 calendar days from initiation" from `@TIMELINE:L2_INVESTIGATION` |
| Geographic exception ("Austria BioLife — English required?") | Conditional exemption | Often misses the exemption and applies global rule | Returns the Austria exemption from `@EXCEPTION:LANG_01` with the rule explicitly named |

**Golden suite result: 10 / 10 on GxP-Struct, with deterministic rules covering 9 cases and one open-ended case correctly deferring to grounded RAG.**

Full methodology and replication instructions in [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md).

---

## Quick Start

```bash
git clone https://github.com/gauravpandey36/gxp-struct.git
cd gxp-struct

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Smoke test — no API keys needed
python validation_test.py --rules-only

# Full pipeline (requires OpenAI + Pinecone keys in .env)
cp .env.example .env   # then fill in keys
python ingest.py --recreate
python query.py "What is the deadline for Level 2 investigation?"
```

The smoke test exercises the deterministic layer only (no API calls), which is exactly the point: **the dangerous decisions in a regulated environment shouldn't depend on an external service being up**.

Full setup details in [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

---

## Adopt the Standard in Your Company

If you are a Quality, Technical Operations, or Digital QA leader evaluating this for adoption:

- Read [**docs/ADOPTION_GUIDE.md**](docs/ADOPTION_GUIDE.md) — a 90-day playbook for bringing GxP-Struct into a regulated environment, mapped to typical eQMS workflows (Veeva Vault, Documentum, MasterControl).
- Review [**docs/SCHEMA_SPEC.md**](docs/SCHEMA_SPEC.md) — the open standard. This is the only thing your authors need to learn. Once an SOP has a `.gxp` companion file, every downstream RAG system speaks the same language.
- Validate against [**docs/VALIDATION_PROTOCOL.md**](docs/VALIDATION_PROTOCOL.md) — the 21 CFR Part 11 / Annex 11 alignment checklist.

Cost of adoption is low. Authors continue to write SOPs the way they always have. The `.gxp` companion file is generated alongside (manually for now, automatically by the upcoming Bridge Agent) and is the source of truth for the AI layer.

---

## What's in this repo

```
gxp-struct/
├── README.md                     ← you are here
├── LICENSE                       MIT
├── CONTRIBUTING.md               how to extend the schema
├── CITATION.cff                  academic citation file
├── Logic_Rules.md                human-readable rule manifest
├── requirements.txt              Python dependencies
├── .env.example                  environment template
│
├── data/
│   └── Deviation_SOP.md          source SOP (Rev 1.0) — the human-readable original
│
├── examples/
│   └── Deviation_SOP.gxp         the machine-readable companion (the "Fourth Translation")
│
├── docs/
│   ├── SCHEMA_SPEC.md            the open standard — what other companies adopt
│   ├── RESEARCH_FINDINGS.md      head-to-head experimental results
│   ├── ADOPTION_GUIDE.md         90-day playbook for QA leaders
│   ├── IMPLEMENTATION.md         developer setup and architecture
│   └── VALIDATION_PROTOCOL.md    21 CFR Part 11 / Annex 11 alignment
│
├── rules.py                      deterministic rule engine
├── parser_gxp.py                 parser for the .gxp format
├── ingest.py                     SOP → Pinecone ingestion (table-aware)
├── retriever.py                  RecursiveRetriever wiring
├── query.py                      CLI entrypoint (rule-check → retrieve → synthesize)
├── audit.py                      append-only JSONL audit log
├── config.py                     central configuration
└── validation_test.py            golden Q&A harness
```

---

## Roadmap

| Version | Coverage | Status |
|---|---|---|
| **v0.1** (this release) | Deviation & CAPA Management archetype + reference implementation | Released |
| v0.2 | Change Control archetype + cross-archetype linking | Planned Q3 2026 |
| v0.3 | Eight more archetypes (Test Method, Specification, Protocol, Validation Plan, Work Instruction, Job Aid, Protocol Report, Master Batch Record) | Planned Q4 2026 |
| v1.0 | Cross-company validation harness + multilingual grounding | Planned 2027 |

Contributors who add new archetypes should follow the schema in [docs/SCHEMA_SPEC.md](docs/SCHEMA_SPEC.md) and submit a PR with: (1) one canonical `.gxp` example, (2) a `Logic_Rules.md` extension covering the new rule families, (3) golden test cases.

---

## Citing this work

A `CITATION.cff` is included for academic and professional citations. If you use GxP-Struct in research, internal validation reports, or regulatory submissions, please cite the repository.

---

## License

MIT. Take it. Fork it. Adopt it. Extend it. The only thing that's *not* freely sharable is the SOP content of any individual company — that stays where it always was. The schema, the rule grammar, and this reference implementation are open.

---

## Acknowledgments

Built from extended discussions with Claude (Anthropic) on what a "validated state" RAG architecture would actually look like in a GxP environment. The framing of the "Fourth Translation" — treating the AI agent as a first-class personnel role that needs its own validated language — emerged from those sessions.
