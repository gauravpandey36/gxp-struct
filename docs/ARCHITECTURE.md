# GxP-Struct: System Architecture

## Table of Contents

1. [System Design Overview](#system-design-overview)
2. [The Fourth Translation Concept](#the-fourth-translation-concept)
3. [Component Descriptions](#component-descriptions)
4. [Data Flow](#data-flow)
5. [Key Design Decisions](#key-design-decisions)
6. [Integration Points](#integration-points)

---

## System Design Overview

GxP-Struct employs a **three-tier deterministic architecture** that fundamentally diverges from conventional RAG systems. Where standard RAG retrieves context and feeds it directly to an LLM (hoping for accurate output), GxP-Struct interposes a deterministic rules layer that enforces compliance correctness before any response reaches the user.

```
+================================================================+
|                     GxP-Struct System                           |
|================================================================|
|                                                                 |
|  +-----------+     +-------------+     +-------------------+    |
|  |  Tier 1   |     |   Tier 2    |     |     Tier 3        |    |
|  |  Bridge   | --> |   Intent    | --> |  Deterministic    |    |
|  |  Agent    |     |   Router    |     |  Strategist       |    |
|  +-----------+     +-------------+     +-------------------+    |
|       |                  |                      |               |
|       v                  v                      v               |
|  NLU + Context    Classification +      Rule Enforcement +      |
|  Extraction       Query Decomp.        Citation Binding         |
|                                                                 |
+================================================================+
```

The system is designed for **pharmaceutical GxP environments** where a wrong answer is not merely unhelpful -- it can lead to regulatory violations, product recalls, or patient safety incidents.

---

## The Fourth Translation Concept

Pharmaceutical documentation traditionally undergoes three translations:

1. **Scientific to Regulatory** -- Lab findings become regulatory submissions
2. **Regulatory to Operational** -- Approved specifications become SOPs
3. **Operational to Training** -- SOPs become employee training materials

GxP-Struct introduces a **Fourth Translation**:

4. **Operational to Machine-Readable** -- SOPs become structured decision engines that AI agents consume with zero ambiguity

This insight drives the entire architecture: AI agents are treated as a new class of "employee" that requires its own validated document format. The system does not ask an LLM to interpret compliance rules; it converts those rules into deterministic logic that the LLM cannot override.

---

## Component Descriptions

### Tier 1: Bridge Agent

**File:** `query.py`

The Bridge Agent serves as the natural language interface between the user and the system. Its responsibilities include:

- Receiving free-text queries from users
- Performing initial natural language understanding
- Extracting key entities (document references, hold times, process steps)
- Normalizing terminology to canonical GxP vocabulary
- Passing structured query representations to the Intent Router

The Bridge Agent does not make compliance decisions. It translates human intent into machine-processable query structures.

### Tier 2: Intent Router

**File:** `retriever.py`

The Intent Router classifies the incoming query and determines the retrieval strategy:

- **Hard Rule Query** -- Routes to the deterministic rules engine when the question maps to a defined compliance boundary (e.g., maximum hold times, temperature ranges, required approvals)
- **Soft Guidance Query** -- Routes to vector retrieval when the question seeks general process guidance or contextual information
- **Hybrid Query** -- Engages both retrieval paths and merges results

The router uses a classification layer that examines query structure, entity types, and keyword signals to make routing decisions.

### Tier 3: Deterministic Strategist

**Files:** `rules.py`, `parser_gxp.py`

The Deterministic Strategist is the core innovation of GxP-Struct. It operates in two modes:

- **Rule Mode** -- For hard compliance rules, the strategist bypasses the LLM entirely and returns the deterministic answer from the parsed rule set, with exact citations
- **Merge Mode** -- For hybrid queries, it takes vector-retrieved context and applies rule constraints as guardrails, preventing the LLM from generating answers that contradict established compliance boundaries

### Supporting Components

| Component | File | Role |
|---|---|---|
| **SOP Parser** | `parser_gxp.py` | Converts SOP documents into structured rule trees and searchable chunks |
| **Audit Logger** | `audit.py` | Writes append-only JSONL records for every query, retrieval, and response |
| **Configuration** | `config.py` | Manages environment settings, model parameters, and index paths |
| **Validation Suite** | `validation_test.py` | Regression tests against known-correct Q&A pairs |

---

## Data Flow

### Document Ingestion Pipeline

```
+-------------+     +--------------+     +---------------+     +------------+
| Raw SOP     | --> | parser_gxp   | --> | Chunked +     | --> | Vector     |
| Documents   |     | .py          |     | Structured    |     | Index      |
| (.pdf/.docx)|     |              |     | Rules         |     | (ChromaDB) |
+-------------+     +--------------+     +-------+-------+     +------------+
                                                 |
                                                 v
                                         +-------+-------+
                                         | Rules         |
                                         | Registry      |
                                         | (rules.py)    |
                                         +---------------+
```

### Query Execution Pipeline

```
User Query
    |
    v
[Bridge Agent] ---> NLU extraction ---> Structured Query
    |
    v
[Intent Router] ---> Classification
    |
    +---> Hard Rule? ---> [Rules Engine] ---> Deterministic Answer
    |
    +---> Soft Query? ---> [Vector Retrieval] ---> LLM Generation
    |
    +---> Hybrid? ---> [Vector + Rules] ---> Constrained Generation
    |
    v
[Deterministic Strategist] ---> Merge + Validate
    |
    v
[Audit Logger] ---> JSONL Record
    |
    v
Validated Response + Citations
```

### Audit Record Structure

Each query produces an append-only JSONL record:

```json
{
  "timestamp": "2026-04-26T14:30:00Z",
  "query_id": "uuid-v4",
  "user_query": "What is the hold time for Buffer A?",
  "intent_class": "hard_rule",
  "retrieval_path": "deterministic",
  "source_documents": ["SOP-2024-001 Section 4.3.2"],
  "response": "Buffer A has a maximum hold time of 24 hours at 2-8C.",
  "citation_chain": ["SOP-2024-001:4.3.2:para:2"],
  "confidence": 1.0,
  "latency_ms": 142
}
```

---

## Key Design Decisions

### 1. Deterministic Rules Over Probabilistic Generation

**Decision:** Hard compliance rules are never generated by the LLM. They are returned directly from a parsed, validated rule set.

**Rationale:** In pharmaceutical manufacturing, a hold time of "24 hours" versus "48 hours" is not a matter of interpretation -- it is a regulatory boundary. LLMs can produce plausible but incorrect values. The rules engine eliminates this category of failure entirely.

### 2. Append-Only Audit Logging

**Decision:** All system interactions are recorded in append-only JSONL format with no update or delete operations.

**Rationale:** FDA 21 CFR Part 11 and EU Annex 11 require complete audit trails for electronic records in regulated environments. Append-only logging ensures that no historical record can be retroactively modified.

### 3. Three-Tier Separation

**Decision:** The system separates natural language understanding (Tier 1), intent classification (Tier 2), and compliance enforcement (Tier 3) into distinct components.

**Rationale:** This separation enables independent testing and validation of each layer. The rules engine can be validated against known-correct answers without involving the LLM. The LLM can be swapped or upgraded without affecting compliance logic.

### 4. Citation-First Response Design

**Decision:** Every response must include traceable citations to source document sections before it is returned to the user.

**Rationale:** Regulatory auditors require evidence that AI-generated guidance traces to approved source documents. Unattributed answers are inadmissible in GxP contexts.

---

## Integration Points

### Current Integrations

| Integration | Protocol | Purpose |
|---|---|---|
| OpenAI API | REST / HTTPS | Embedding generation and LLM completion |
| ChromaDB | Python SDK | Vector storage and similarity search |
| GitHub Actions | YAML workflow | CI/CD smoke testing |

### Planned Integrations

| Integration | Protocol | Purpose |
|---|---|---|
| BM25 Index | Python (rank-bm25) | Keyword-based retrieval for hybrid search |
| Cross-Encoder | Python (sentence-transformers) | Re-ranking for precision improvement |
| RAGAS | Python SDK | Automated evaluation pipeline |
| Langfuse | REST / SDK | Observability and cost tracking |
| Document Management System | REST API | Automated SOP ingestion from enterprise DMS |

### API Surface (Planned)

```
POST /api/v1/query
  Body: { "question": "string", "context": "optional string" }
  Response: { "answer": "string", "citations": [], "confidence": float }

GET /api/v1/health
  Response: { "status": "ok", "index_size": int, "rules_count": int }

GET /api/v1/audit?from=<timestamp>&to=<timestamp>
  Response: { "records": [...] }
```

---

*For usage instructions, see [README.md](README.md).*
