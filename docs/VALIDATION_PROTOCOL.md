# Validation Protocol — 21 CFR Part 11 / EU GMP Annex 11 Alignment

This document maps GxP-Struct's design decisions to the specific regulatory expectations of 21 CFR Part 11 (US FDA) and EU GMP Annex 11. It is not a substitute for a company's own validation package — adopters must execute their own Computer System Validation (CSV). It is the architectural evidence that supports such a package.

---

## 1. Scope

The framework is designed to support, not replace, validated-state operations. The deterministic rule layer is amenable to traditional functional testing; the RAG fallback layer requires the standard CSV considerations for AI/ML systems plus the additional controls described below.

---

## 2. 21 CFR Part 11 mapping

### § 11.10 — Controls for closed systems

| Requirement | GxP-Struct provision |
|---|---|
| **(a) Validation of systems to ensure accuracy** | The deterministic layer is testable as a pure function. The golden test suite in `validation_test.py` is the OQ artifact. |
| **(b) Ability to generate accurate copies of records** | Audit log is plain JSONL, machine- and human-readable. Records are exportable byte-for-byte. |
| **(c) Protection of records to enable accurate retrieval** | Audit records carry explicit `sop_version`, `sop_effective_date`, and `query_id`. Implementation guidance: place the audit log on a write-once / append-only volume. |
| **(d) Limiting system access to authorized individuals** | Implementation responsibility — adopters configure access via their existing IAM. The framework records `audit_user` on every entry. |
| **(e) Use of secure, computer-generated, time-stamped audit trails** | Every query produces one audit record with UTC ISO-8601 timestamp, query_id (UUID), user, model identifiers, and the retrieved context. |
| **(f) Use of operational system checks** | The intent router enforces a hierarchy of power before any answer is generated. Rules cannot fire without a `SOURCE_SECTION`. |
| **(g) Use of authority checks** | Responsibility rules (`@RULE` family) are enforceable — the framework can refuse an answer when the asking role lacks authority for the asked-about action. |
| **(h) Use of device checks** | Implementation responsibility — applies to upstream / downstream integrations. |
| **(i) Determination that persons who develop, maintain, or use systems have appropriate education, training, and experience** | Process responsibility, not architectural. |
| **(j) Establishment of and adherence to written policies that hold individuals accountable** | Process responsibility. |
| **(k) Use of appropriate controls over systems documentation** | The schema specification ([SCHEMA_SPEC.md](SCHEMA_SPEC.md)) is versioned. The `.gxp` files reference a schema version. |

### § 11.50 — Signature manifestations

The framework does not generate electronic signatures itself; it consumes the SOP version that has been signed in the eQMS. Audit records can reference the eQMS signature record by `SOP_ID` and `SOP_VERSION`.

### § 11.70 — Signature/record linking

Every audit record is bound to a specific `sop_version` and `sop_effective_date`, which themselves are bound to the eQMS signature record on the SOP. This linkage is structural, not editorial — there is no path to produce an answer without the binding.

---

## 3. EU GMP Annex 11 mapping

### § 4 — Validation

| Requirement | GxP-Struct provision |
|---|---|
| **§ 4.1 Validation documentation and reports should cover the relevant steps of the life cycle** | The schema is the User Requirements artifact. The reference implementation is the System artifact. The golden test suite is the OQ artifact. |
| **§ 4.5 An up to date listing of all relevant systems and their GMP functionality (inventory) should be available** | Adopter responsibility — register the GxP-Struct deployment in your validated-system inventory. |
| **§ 4.7 Specifications should be reviewed for accuracy and approved before incorporation** | The `.gxp` file goes through the same change-control as the prose SOP. The framework does not author rules — only the SME does. |

### § 5 — Data

| Requirement | GxP-Struct provision |
|---|---|
| **Data should be checked for accuracy** | Rules execute deterministically. The same input always produces the same output, modulo the explicit ATTACHMENT_4_REFERENCE_LIST (which is itself controlled). |
| **Data integrity (ALCOA+)** | Audit log is **A**ttributable (user), **L**egible (JSONL), **C**ontemporaneous (UTC timestamp), **O**riginal (append-only), **A**ccurate (no transformation), and **C**omplete, **C**onsistent, **E**nduring, **A**vailable when stored on appropriate media. |

### § 7 — Data Storage

The audit log format is a fixed schema (see § 5 below). Format changes require a version bump and migration plan.

### § 9 — Audit Trails

> *"Consideration should be given, based on a risk assessment, to building into the system the creation of a record of all GMP-relevant changes and deletions (a system generated 'audit trail'). For change or deletion of GMP-relevant data the reason should be documented."*

Every interaction is auditable. The `extra` field on each audit record allows deployment-specific context (the asking user's role, the workflow they were in, the eQMS document state) to be added without breaking the schema.

### § 10 — Change and Configuration Management

> *"Any changes to a computerised system including system configurations should only be made in a controlled manner in accordance with a defined procedure."*

Changes to a `.gxp` file follow the same change-control as the prose SOP. Changes to the framework code follow standard CSV change-control. The schema specification declares which kinds of changes are breaking vs non-breaking.

---

## 4. Audit log schema

Every query produces exactly one record in `audit/queries.jsonl`. Schema:

```json
{
  "timestamp_utc": "2026-04-25T18:23:11.482Z",
  "query_id": "f4e2d6a8-...",
  "user": "string (from AUDIT_USER)",
  "sop_id": "SOP-DEV-001",
  "sop_version": "1.0",
  "sop_effective_date": "2026-04-25",
  "query": "What is the deadline for Level 2 investigation?",
  "intent_detected": "timeline",
  "rule_triggered": "R-5.3-LEVEL_2_INVESTIGATION",
  "retrieved_chunks": [],
  "answer": "Level 2 Investigation: 60 calendar days from initiation (per SOP § 5.3).",
  "citations": [
    { "sop_section": "5.3", "sop_section_title": "Performance Timelines", ... }
  ],
  "model": {
    "llm": "gpt-4o",
    "embedding": "text-embedding-3-large",
    "temperature": 0.0
  },
  "extra": {
    "rule_metadata": { "event": "level 2 investigation", "deadline": "60 calendar days from initiation", "deterministic": true }
  }
}
```

For RAG-path queries, `rule_triggered` is `null` and `retrieved_chunks` contains the retrieved evidence with scores. For deterministic queries, `retrieved_chunks` is empty and `rule_triggered` names the rule.

---

## 5. Risk assessment summary

| Risk | Mitigation |
|---|---|
| LLM hallucinates a critical SOP value (deadline, classification) | Hard rules execute deterministically; LLM is never asked these questions. |
| Retrieval misses the relevant chunk | Strict refusal-to-speculate prompt: "Not addressed in the SOP. Escalate to Quality Approver." |
| `.gxp` drifts from prose SOP | Change-control discipline (see [ADOPTION_GUIDE.md](ADOPTION_GUIDE.md) Phase 3). The `SOP_VERSION` and `EFFECTIVE` in the `.gxp` header must match the prose SOP. |
| Audit log tampering | Append-only file mode; deployment on write-once volume; cryptographic hash chaining is a planned v0.2 enhancement. |
| Old SOP version answered against | Audit log records the exact SOP version on every record, retroactively detectable. Recommended: stamp `SOP_VERSION` from the eQMS API at every restart, fail if it doesn't match the loaded `.gxp`. |
| Unauthorized rule modification | `.gxp` files are stored under the same access controls as the prose SOP in the eQMS. Any modification is itself a change-control event. |

---

## 6. Open compliance items for adopters

The framework provides the architecture; adopters must execute against their own environment. Specifically:

- **Performance Qualification (PQ)** — adopters run the golden suite against their own SOPs and document results.
- **User access management** — wire `AUDIT_USER` to your IdP / SSO.
- **Backup and recovery** — the audit log is the system of record for AI interactions; back it up at the same cadence as your other validated records.
- **Periodic review** — review the audit log at the same cadence as your other validated systems (typically annually).
- **Retirement** — when a SOP is retired, the corresponding `.gxp` should be marked obsolete in your eQMS but retained for the same retention period as the prose SOP.

---

## 7. Acknowledgment

This document represents the framework's design intent. It is not legal or regulatory advice. Adopters should engage their own Compliance / CSV / QA functions before deploying GxP-Struct in a regulated environment.
