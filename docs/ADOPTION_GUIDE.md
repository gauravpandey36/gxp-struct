# Adoption Guide — 90-day Playbook

A practical playbook for QA, Technical Operations, or Digital QA leaders bringing GxP-Struct into a regulated environment. Designed for organizations using Veeva Vault QualityDocs, OpenText Documentum, or MasterControl as their eQMS, but the steps generalize.

---

## Why this matters

If your AI strategy depends on RAG over your SOP library, you have a validation problem you can't solve with a bigger model. The SOP author cannot validate that the AI will return Level 1 every time the rule says Level 1; they can only hope. GxP-Struct lets the SOP author validate the *rule definition* once, and that rule then executes deterministically every time.

The adoption cost is bounded — authors continue to write SOPs the way they always have. Each SOP gains a small companion file (`.gxp`) authored by the same SME alongside the prose document.

---

## Pre-work (Week 0)

Before kicking off, line up:

| Stakeholder | Role |
|---|---|
| QA Lead (sponsor) | Owns the validation strategy and the change-control process |
| One SOP Author (champion) | Authors the first `.gxp` files; the practical face of the adoption |
| eQMS Admin | Wires the `.gxp` artifact into the SOP lifecycle (effective-date sync, audit trail) |
| AI / Data Engineer | Stands up the reference implementation; integrates with internal RAG |
| Compliance / CSV Lead | Drafts the Validation Plan against the framework |

If any of these is missing, find them before Day 1. The framework is not implementable by IT alone.

---

## Phase 1 — Pilot (Days 1–30)

**Goal:** prove the framework on a single, representative SOP. No production traffic.

### Day 1–5 — Pick the right SOP

Criteria for the pilot SOP:

- Has at least three rule families represented (responsibilities, timelines, classifications, exemptions). The Deviation & CAPA SOP shipped as the reference example fits this perfectly — that's why it was chosen.
- Owned by an enthusiastic SME. The first `.gxp` is the hardest one; you need someone who wants to do it.
- Currently a high-traffic question source for any existing AI / search / chatbot system. You'll have anecdotes to compare against.

Avoid for the pilot: highly technical methods (Test Method, Specification) — those are great for v0.3 but the schema doesn't yet have the right tag families for them.

### Day 5–15 — Author the first `.gxp`

The SME and the AI Engineer co-author. The SME provides the rules; the engineer encodes them in schema syntax and runs the parser to verify. Expect 4–8 hours of total effort across the two roles for a representative SOP.

Validation checklist for the `.gxp`:

- [ ] Every `@RULE`, `@LOGIC`, `@TIMELINE`, `@EXCEPTION` cites a `SOURCE_SECTION`.
- [ ] The SME has reviewed every rule against the prose SOP and signed off.
- [ ] `python parser_gxp.py examples/<your_sop>.gxp` runs without error.
- [ ] `python validation_test.py --rules-only` passes against newly-authored golden test cases.

### Day 15–25 — Stand up the reference implementation

Internal infrastructure:

- Deploy the Python reference implementation behind your firewall. The repo is < 1500 lines of Python; treat it as a starter codebase, not a finished product.
- Configure the audit log to write to your immutable storage tier (Veeva Vault eRecord, S3 Object Lock, internal write-once volume). 21 CFR Part 11 expects tamper-evident records.
- Wire `SOP_VERSION` and the `.gxp` file path to your eQMS via API. When a new revision goes effective, the new `.gxp` and `SOP_VERSION` must propagate without manual intervention.

### Day 25–30 — Pilot evaluation

Run the golden test suite. Run a freeform "stress test" with 30 questions from the SME's experience of where the existing system has been wrong. Document the head-to-head comparison in your internal validation report — this is the artifact that justifies expanding the program.

---

## Phase 2 — Expansion (Days 30–60)

**Goal:** prove it scales beyond one SOP.

### Day 30–45 — Add 4–6 more SOPs

Pick SOPs from the same archetype (Deviation/CAPA family) so you don't have to extend the schema yet. Examples: Out-of-Specification, Out-of-Trend, Atypical Result.

Process per SOP:
- 4–8 SME hours
- 2–4 engineer hours
- Validation report addendum
- Golden test cases added to the harness

### Day 45–55 — Integrate with your existing tools

If you have an internal chatbot or knowledge assistant, plumb GxP-Struct in as an upstream layer. The integration pattern is:

```
existing chatbot → /gxp/ask → returns deterministic answer if a rule fires,
                              otherwise existing chatbot continues
```

This is non-invasive — it only changes the existing system's behavior on questions where a rule fires, and makes those questions safer. Everything else continues unchanged.

### Day 55–60 — First steering committee review

Invite Quality, Tech Ops, Digital QA, and Compliance leadership. Present the head-to-head data. Decide: do we expand to a second archetype (e.g., Change Control) and bump to schema v0.2?

---

## Phase 3 — Validation & Production (Days 60–90)

**Goal:** move from pilot to validated state for at least one workflow.

### Day 60–75 — Computer System Validation

Build the validation package. Required documents:

- **Validation Plan** — what is being validated, against what requirements (21 CFR Part 11, Annex 11, internal SOPs).
- **User Requirements Specification** — the rule families the system supports, derived from this repo's [SCHEMA_SPEC.md](SCHEMA_SPEC.md).
- **Functional Specification** — what the system does, with traceability to the URS.
- **Test Protocols** — IQ (installation), OQ (operational), PQ (performance). The OQ protocol can use the golden test suite directly.
- **Validation Report** — execution evidence and sign-off.

GxP-Struct's design helps here: the deterministic layer is testable as a pure function, which OQ-style protocols handle gracefully. The RAG layer needs the standard caveats around model versioning and prompt fingerprinting.

### Day 75–85 — Change-control integration

Wire the `.gxp` file into the same change-control process that governs the prose SOP:

- Author drafts the prose SOP and the `.gxp` companion together.
- Reviewer reviews both.
- QA approves both.
- On effective date, both publish atomically.
- The audit log automatically picks up the new `SOP_VERSION`.

This is the most-overlooked step. If your `.gxp` file drifts from your prose SOP, the framework's validation guarantee is broken. The change-control discipline is what keeps them aligned.

### Day 85–90 — Production cutover

For one specific workflow (e.g., "deviation initiation help in our internal chatbot"), enable GxP-Struct in production. Monitor:

- The audit log — every interaction recorded, available for retrospective review.
- User feedback — the deterministic answers should be wrong less often than before.
- Latency — rule-fired answers are < 50ms; RAG-fallback answers retain LLM latency.

---

## Common questions

**Q: Does this require us to rewrite our SOPs?**
No. The prose SOP is unchanged. The `.gxp` is a small companion file authored alongside it.

**Q: Who owns the `.gxp` — Quality or IT?**
Quality. The SME who owns the prose SOP also owns the `.gxp`. IT helps with the syntax during pilot but the long-term steady state is SME ownership. Treat the `.gxp` as a controlled artifact like any other SOP attachment.

**Q: How do we audit a `.gxp`-driven answer?**
The audit log captures every query: the SOP version, the rule_id that fired, the retrieved chunks (if any), the final answer, and the model identifiers. The format is documented in [VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md) and is suitable for 21 CFR Part 11 / Annex 11 audit trail expectations.

**Q: What if our SOP doesn't fit the existing tag families?**
Open an issue with a representative SOP excerpt. Most missing tag families are obvious extensions (`@CALIBRATION`, `@SAFETY_LIMIT`) and we'd rather have them in the schema than have you fork. See [CONTRIBUTING.md](../CONTRIBUTING.md).

**Q: Will this work with our LLM provider / on-prem model?**
The deterministic layer is provider-agnostic — it never calls an LLM. The RAG fallback layer currently uses OpenAI in the reference implementation but is pluggable; any model with a LlamaIndex integration works. If you need on-prem, swap in a self-hosted model and an open-source embedding (BGE, E5).

**Q: What about Veeva's own AI agents?**
Veeva's agents operate inside Vault. GxP-Struct is the open standard for *what they read*. The two are complementary — Veeva provides the secure agent runtime, GxP-Struct provides the validated language those agents consume. We expect the integration story to formalize as the schema reaches v1.0.

---

## Red flags that mean stop

If during the pilot any of these happens, pause and review:

- The SME cannot reach consensus on what a rule says. The rule is ambiguous in the prose SOP; the framework cannot fix that — the prose SOP needs revision first.
- The change-control process won't accept the `.gxp` as a controlled artifact. Without that, drift between prose and `.gxp` will eventually cause an incident.
- The Compliance / CSV team objects to the audit log format. Resolve the format with them before scaling — it's much harder to change later.

These are organizational issues, not technical ones, and the framework cannot work around them.

---

## Success metrics

A reasonable bar at end-of-Day-90:

- One SOP archetype fully covered, 4–8 SOPs encoded.
- 100% of golden-suite questions answered deterministically with citations.
- One production workflow live with audit trail.
- A signed Validation Report.
- A second archetype scoped for the next quarter.

If you hit those, you have built something defensible to a regulator and useful to your operators. That is the bar.
