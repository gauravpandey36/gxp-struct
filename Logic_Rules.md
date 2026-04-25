# Logic Rules Manifest

This file is the human-readable companion to [`examples/Deviation_SOP.gxp`](examples/Deviation_SOP.gxp). It enumerates every rule the deterministic engine can fire, the SOP section that authorizes it, the rule_id used in code, and the answer the engine returns.

If you are evaluating GxP-Struct for adoption, **read this file first**. It is the entire decision surface of the AI system, in one document.

---

## Reading the manifest

Every rule has four parts:

| Field | Meaning |
|---|---|
| **Rule ID** | Stable identifier referenced in audit logs and code (e.g., `R-5.2-DEFAULT_L1`) |
| **Source** | The SOP section the rule cites |
| **Trigger** | The intent / phrase pattern that fires the rule |
| **Determined output** | The exact string the engine returns, plus structured metadata for downstream systems |

A rule that cannot cite a SOP section does not fire. That is the contract.

---

## Hierarchy of Power

When two rules could both fire, the engine resolves them by precedence:

```
1. L2 Trigger        (Sterility / Falsified Data / CPP)        — highest, OVERRIDE: TRUE
2. Close Reference   (Close Reference Deviations always L1)
3. Default           (Item not in Attachment 4 → Level 1)
4. Quality Override  (QM may reclassify L1 → L2)               — manual escalation path
```

Within timelines, exceptions, and responsibilities, rules are mutually exclusive (no precedence conflict possible).

---

## 1.0 Responsibility Rules

### `R-3.0-QUALITY_APPROVER`
- **Source:** SOP § 3.0 — Responsibilities
- **Trigger:** Queries naming the *Quality Approver* role
- **Determined output:** "Quality Approver: Sole authority for final leveling approval and disposition oversight (per SOP § 3.0)."
- **Metadata:** `{ role: "quality approver", authority: "SOLE", deterministic: true }`
- **Linked to:** `@RULE:RESP_001` in the `.gxp` file.

### `R-3.0-DEVIATION_OWNER`
- **Source:** SOP § 3.0
- **Trigger:** Queries naming the *Deviation Owner* role
- **Determined output:** "Deviation Owner: Accountable for containment, impact assessment, and risk-based leveling (per SOP § 3.0)."
- **Linked to:** `@RULE:RESP_003`.

### `R-3.0-ORIGINATOR`
- **Source:** SOP § 3.0
- **Trigger:** Queries naming the *Originator* role
- **Determined output:** "Originator: Evaluation and initiation of the record in GEMS within 2 business days (per SOP § 3.0)."
- **Linked to:** `@RULE:RESP_002`.

---

## 2.0 Initiation & Containment Rules

### `R-5.1-CLOCK_START`
- **Source:** SOP § 5.1 — Initiation and Containment
- **Trigger:** Queries about initiation, clock-start, or discovery
- **Determined output:** "The record must be initiated within 2 business days of discovery, with impacted lot numbers populated (SOP § 5.1)."
- **Metadata:** `{ initiation_clock_business_days: 2, deterministic: true }`
- **Linked to:** `@TIMELINE:INITIATION_CLOCK`.

### `R-5.1-LANG_DEFAULT`
- **Source:** SOP § 5.1
- **Trigger:** Language-related queries with no country mentioned
- **Determined output:** "All records must be in English. The only exemption is Austria BioLife centers (SOP § 5.1)."
- **Linked to:** `@EXCEPTION:LANG_DEFAULT`.

### `R-5.1-LANG_EXEMPTION`
- **Source:** SOP § 5.1
- **Trigger:** Queries mentioning Austria or BioLife
- **Determined output:** "Records at the Austria BioLife centers are exempt from the English-only requirement (SOP § 5.1). All other sites must record in English."
- **Metadata:** `{ exempt_country: "austria", default_language: "English" }`
- **Linked to:** `@EXCEPTION:LANG_01`.

---

## 3.0 Classification Rules (Risk-Based Leveling)

### `R-5.2-L2_TRIGGER` *(highest precedence)*
- **Source:** SOP § 5.2 — Risk-Based Leveling
- **Trigger:** Query mentions critical process parameter / CPP / sterility / falsified data / data integrity
- **Determined output:** "Level 2 (mandatory). Per SOP § 5.2, deviations involving \<trigger\> are always Level 2 regardless of frequency."
- **Metadata:** `{ level: "L2", trigger: "<sterility|falsified data|critical process parameters>", deterministic: true }`
- **Linked to:** `@LOGIC:L2_TRIGGER` with `OVERRIDE: TRUE`.

### `R-5.2-DEFAULT_L1`
- **Source:** SOP § 5.2
- **Trigger:** Classification query for an item NOT in Attachment 4
- **Determined output:** "Level 1 (default). Per SOP § 5.2, if a deviation is not listed in Attachment 4 (Investigation – CAPA Reference List), it is classified as Level 1 by default. Quality Management may re-classify to Level 2 based on evaluation."
- **Metadata:** `{ level: "L1", override_path: "Quality Management" }`
- **Linked to:** `@LOGIC:DEFAULT`.
- **Note:** The runtime `ATTACHMENT_4_REFERENCE_LIST` should be populated under change control. Until populated, the rule conservatively returns Level 1, which is the SOP's own default.

### `R-5.2-CLOSE_REF` *(reserved)*
- **Source:** SOP § 5.2
- **Trigger:** Query mentions a Close Reference Deviation
- **Determined output:** "Level 1 (mandatory by SOP § 5.2 — Close Reference Deviations are always Level 1)."
- **Linked to:** `@LOGIC:CLOSE_REF` with `MANDATORY: TRUE`.

---

## 4.0 Performance Timeline Rules

### `R-5.3-LEVEL_1_COMPLETION`
- **Source:** SOP § 5.3 — Performance Timelines
- **Trigger:** Queries about Level 1 deadline / completion
- **Determined output:** "Level 1 Completion: 30 calendar days from initiation (per SOP § 5.3)."
- **Metadata:** `{ event: "level 1 completion", deadline: "30 calendar days from initiation" }`
- **Linked to:** `@TIMELINE:L1_COMPLETION`.

### `R-5.3-LEVEL_2_INVESTIGATION`
- **Source:** SOP § 5.3
- **Trigger:** Queries about Level 2 investigation deadline
- **Determined output:** "Level 2 Investigation: 60 calendar days from initiation (per SOP § 5.3)."
- **Linked to:** `@TIMELINE:L2_INVESTIGATION`.

### `R-5.3-CAPA_EXECUTION`
- **Source:** SOP § 5.3
- **Trigger:** Queries about CAPA execution / due / deadline
- **Determined output:** "CAPA Execution: 60 calendar days from investigation approval (per SOP § 5.3)."
- **Linked to:** `@TIMELINE:CAPA_EXECUTION`.

---

## 5.0 Scope Guardrails

These are not "rules" in the question-answering sense but are evaluated by the gatekeeper before any rule fires.

### `G-2.0-SCOPE_EXCLUSION`
- **Source:** SOP § 2.0 — Scope
- **Trigger:** Query is about an entity in `@SCOPE:EXCLUDED_FROM` (Preclinical research, Environmental / Utility Monitoring Excursions)
- **Determined output:** "This is out of scope per SOP § 2.0. The Deviation and CAPA Management System does not apply to \<excluded entity\>. Refer to the appropriate SOP."
- **Linked to:** `@SCOPE:EXCLUDED_FROM`.

### `G-2.0-PROHIBITED`
- **Source:** SOP § 2.0
- **Trigger:** Query proposes a Planned Deviation
- **Determined output:** "Planned deviations are strictly prohibited per SOP § 2.0. Escalate to Quality Management."
- **Linked to:** `@SCOPE:PROHIBITED`.

---

## What the engine refuses to do

GxP-Struct deliberately does not fire a rule for these patterns; they fall through to RAG with a strict refusal-to-speculate prompt:

- Open-ended scope summaries that aren't a yes/no exclusion check.
- Investigation methodology questions ("which root-cause analysis tool should we use?") — these depend on judgment, not rule.
- Reference document content ("what does SOP-QA-005 say about change control?") — handled by the referenced SOP's own `.gxp` file in a multi-archetype future release.

If retrieval comes back empty for a fall-through question, the system returns: **"Not addressed in the SOP. Escalate to Quality Approver."**

---

## Rule precedence test cases

Each row below is a query that exercises the precedence stack. All ten pass deterministically in the golden suite.

| # | Query | Rule that fires |
|---|---|---|
| 1 | When must I initiate a record after discovery? | `R-5.1-CLOCK_START` |
| 2 | Deviation not in Attachment 4 — what level? | `R-5.2-DEFAULT_L1` |
| 3 | Sterility breach during fill — what level? | `R-5.2-L2_TRIGGER` |
| 4 | Operator falsified records — what level? | `R-5.2-L2_TRIGGER` |
| 5 | CPP excursion — what level? | `R-5.2-L2_TRIGGER` |
| 6 | What is the deadline for Level 2 investigation? | `R-5.3-LEVEL_2_INVESTIGATION` |
| 7 | How many days for CAPA execution? | `R-5.3-CAPA_EXECUTION` |
| 8 | Do Austria BioLife records have to be in English? | `R-5.1-LANG_EXEMPTION` |
| 9 | Who is the Quality Approver? | `R-3.0-QUALITY_APPROVER` |
| 10 | What's excluded from this SOP? | *(no rule — defers to RAG, retrieves § 2.0)* |

The full harness is in [`validation_test.py`](validation_test.py).
