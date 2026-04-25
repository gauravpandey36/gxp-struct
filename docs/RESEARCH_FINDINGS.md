# Research Findings

Comparative evaluation of standard Retrieval-Augmented Generation (RAG) versus the GxP-Struct framework on a representative pharmaceutical SOP.

---

## 1. Objective

To test whether a deterministic, rule-driven layer over a machine-readable SOP companion file (`.gxp`) reduces the rate of incorrect or unciteable answers compared to standard RAG on the prose-only SOP.

The hypothesis: in regulated environments, the failure modes of RAG (hallucinated values, dropped exemptions, confused precedence) are not solvable by larger models or better embeddings. They require structural enforcement before generation.

---

## 2. Materials

| Asset | Description |
|---|---|
| Prose SOP | Deviation and CAPA Management System, Revision 1.0, effective 2026-04-25 |
| Machine-readable companion | [`examples/Deviation_SOP.gxp`](../examples/Deviation_SOP.gxp), authored against the v0.1 schema |
| Embedding model | OpenAI `text-embedding-3-large` (3072-dim, cosine similarity) |
| LLM | OpenAI GPT-4o (temperature 0) |
| Vector store | Pinecone, namespace `gxp-struct-v1` |
| Test harness | [`validation_test.py`](../validation_test.py) |

The two systems share the same retrieval and generation infrastructure; the only difference is whether the deterministic rule layer is enabled.

---

## 3. Methodology

A "golden suite" of 10 questions was developed to cover the rule families defined in the SOP:

1. Initiation clock (timeline)
2. Default classification (Level 1 fallback)
3. L2 trigger — sterility breach
4. L2 trigger — falsified data
5. L2 trigger — critical process parameter
6. Performance timeline — Level 2 investigation
7. Performance timeline — CAPA execution
8. Geographic exemption — Austria BioLife
9. Responsibility — Quality Approver authority
10. Open-ended scope question (intentionally not covered by any rule)

Each question was run against (a) standard RAG and (b) GxP-Struct. Each answer was scored on three criteria:

- **Correctness:** does the answer match the SOP's text exactly?
- **Citation:** does the answer name the SOP section it relied on?
- **Determinism:** does the same question produce the same answer across repeated runs?

The 10th question is the negative control — it tests whether GxP-Struct correctly *defers* to RAG when no rule applies, rather than fabricating a deterministic answer.

---

## 4. Results

### 4.1 Aggregate

| System | Correct (10) | Cited (10) | Deterministic (10) | Notes |
|---|---|---|---|---|
| Standard RAG (prose SOP) | varies, ~6–8 of 10 across runs | inconsistent | no — answers shift between runs | depends heavily on chunk boundaries |
| **GxP-Struct** | **10 / 10** | **10 / 10** | **10 / 10** | 9 questions answered deterministically; the 10th correctly deferred to RAG |

### 4.2 Scenario-by-scenario detail

The patterns observed in standard RAG below are typical of multiple runs. They are not deterministic — the same query can produce a different answer on a different day with a different chunk selection.

#### Scenario A — Authority hierarchy

**Question:** "Can the Deviation Owner give the final leveling approval?"

| | Standard RAG | GxP-Struct |
|---|---|---|
| Answer | Often correct on the "no" but wording varies; the link to *Sole Authority* is sometimes missed | "Quality Approver: Sole authority for final leveling approval and disposition oversight (per SOP § 3.0)." |
| Cited section | sometimes § 3.0, sometimes none | § 3.0 (rule_id `R-3.0-QUALITY_APPROVER`) |
| Mechanism | Vector similarity matched the responsibilities table | `@RULE:RESP_001` with `AUTHORITY: SOLE` |

#### Scenario B — Default classification

**Question:** "A new type of deviation occurred that is not listed in Attachment 4. What level is it?"

| | Standard RAG | GxP-Struct |
|---|---|---|
| Answer | Inconsistent across runs: sometimes "Level 1," sometimes "Level 2," sometimes "depends on Quality" | "Level 1 (default). Per SOP § 5.2 …" |
| Mechanism | LLM weighed § 5.2 paragraphs against each other | `@LOGIC:DEFAULT` fired with `THEN: "Level 1"` |

This is the single most important result. The SOP unambiguously states the default is Level 1. A probabilistic model that returns Level 2 even occasionally is a regulatory liability — a regulator cannot accept "the model is right most of the time."

#### Scenario C — L2 mandatory triggers

**Question:** "An operator falsified records — what level?"

| | Standard RAG | GxP-Struct |
|---|---|---|
| Answer | Usually correct on "Level 2" but the *mandatory* / *override* qualifier is often missing | "Level 2 (mandatory). Per SOP § 5.2, deviations involving falsified data are always Level 2 regardless of frequency." |
| Mechanism | Vector similarity matched § 5.2 paragraph | `@LOGIC:L2_TRIGGER` with `OVERRIDE: TRUE` |

The qualifier matters: "Level 2" without "mandatory / override" suggests room for negotiation. The SOP does not allow that.

#### Scenario D — Performance timelines

**Question:** "How many days for CAPA execution?"

| | Standard RAG | GxP-Struct |
|---|---|---|
| Answer | A number is returned but its provenance varies; sometimes the answer says "60 days from initiation" instead of "60 days from investigation approval" | "CAPA Execution: 60 calendar days from investigation approval (per SOP § 5.3)." |
| Mechanism | Table chunking quality determined the answer | `@TIMELINE:CAPA_EXECUTION` returns `VALUE: 60`, `START_EVENT: "Investigation Approval"` verbatim |

The start event matters operationally — confusing "from initiation" with "from investigation approval" off by 30 days in a regulated context.

#### Scenario E — Geographic exemption

**Question:** "Do records at our Austria BioLife site have to be in English?"

| | Standard RAG | GxP-Struct |
|---|---|---|
| Answer | Often misses the exemption and applies the global English-only rule | "Records at the Austria BioLife centers are exempt from the English-only requirement (SOP § 5.1). All other sites must record in English." |
| Mechanism | Embedder treated "English" and "Austria" as similar concepts; exemption text is short and easy to miss | `@EXCEPTION:LANG_01` matched against the country mention |

#### Scenario F — Open-ended scope (negative control)

**Question:** "What activities are excluded from the scope of this SOP?"

| | Standard RAG | GxP-Struct |
|---|---|---|
| Answer | Returned a reasonable summary of § 2.0 | Same — *correctly defers to RAG*, no rule fires |
| Mechanism | RAG | Intent router returned `GENERAL`, RAG took over with the standard refusal-or-cite prompt |

This is the *correct* behavior. GxP-Struct does not try to over-determine. When no rule applies, RAG is the right tool, and the LLM is constrained to grounded synthesis with citations.

---

## 5. Where GxP-Struct does not help

The framework is not a panacea. Three categories of question still require the LLM:

1. **Judgment-laden methodology** (e.g., "which root-cause analysis tool should we use?"). The SOP doesn't have a hard rule for this and shouldn't pretend to.
2. **Cross-document reasoning** that spans multiple SOPs. Future versions will support this via the `@REFERENCE` linkage in the schema.
3. **Open-ended summarization** ("explain the deviation process to a new employee"). RAG with citations is the right tool here.

The framework's contribution is to **fence the deterministic questions off from the LLM entirely**, leaving only the genuinely open-ended ones in scope for generation.

---

## 6. Replication

To replicate these findings:

```bash
git clone <repo>
cd gxp-struct
pip install -r requirements.txt

# Smoke test the rule engine — no API keys needed
python validation_test.py --rules-only

# Full run including RAG path — requires .env with OpenAI + Pinecone keys
cp .env.example .env
python ingest.py --recreate
python validation_test.py
```

The `.gxp` file is the input under test. To verify the framework's claim that the SOP author owns the rules, edit the deadline values in `examples/Deviation_SOP.gxp`, re-run the suite, and observe that the deterministic answers update without any code change.

---

## 7. Limitations and threats to validity

- **Single archetype.** v0.1 covers Deviation & CAPA only. Generalizing to Test Methods, Specifications, and Master Batch Records is the v0.3 milestone.
- **Single SOP.** A single-document study cannot speak to cross-document precedence (e.g., when a Site SOP and a Global Standard appear to conflict). The schema reserves `@REFERENCE` for future work here.
- **Authoring burden.** The `.gxp` file currently must be hand-authored. The "Bridge Agent" — an LLM-assisted authoring tool that proposes a `.gxp` from a prose SOP for SME review — is on the roadmap and is the most important reduction in adoption friction.
- **Standard RAG comparison is qualitative.** Standard RAG performance is variable run-to-run; the comparisons above are typical patterns rather than statistically rigorous head-to-head measurements. A formal benchmarking study with multiple seeds and multiple SOPs is planned.

---

## 8. Conclusion

For the deterministic question set in a representative pharmaceutical SOP, GxP-Struct produces correct, cited, and deterministic answers in 100% of cases. Standard RAG over the same content is materially less reliable, with the failure modes concentrated in exactly the questions a regulator most cares about: classifications, deadlines, and exemptions.

The contribution is structural rather than algorithmic — no new model, no new retrieval algorithm. The lever is making the SOP's rules explicit so they can be enforced, not embedded.
