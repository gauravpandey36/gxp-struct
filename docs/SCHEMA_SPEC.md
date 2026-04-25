# GxP-Struct Schema Specification

**Version:** 0.1.0
**Status:** Draft for community review
**License:** MIT (the schema, like the reference implementation, is openly licensed for adoption)

---

## 1. Purpose

This document defines the open standard for representing pharmaceutical Standard Operating Procedures (and adjacent regulated documents) in a machine-readable form suitable for deterministic rule execution by AI systems.

It is the **only** part of GxP-Struct that adopters strictly need to learn. Everything else — the Python reference implementation, the rule engine, the audit log format — is replaceable. The schema is the contract.

---

## 2. Design principles

The schema is designed against five non-negotiable principles:

1. **Authored, not inferred.** The subject-matter expert who writes the SOP is the only person who can write the `.gxp` companion. No AI infers rules from prose. This is the validation foundation.
2. **Cited, always.** Every rule names a `SOURCE_SECTION` in the parent SOP. A rule that cannot cite is an invalid rule.
3. **Flat, not nested.** Rules are a flat list of one-line declarations. Nested rules invite ambiguity and parser bugs. Cross-references between rules are by `RULE_ID`, not by structural nesting.
4. **Precedence is explicit.** Where two rules could fire, the document declares which wins (`OVERRIDE: TRUE`, `MANDATORY: TRUE`, `AUTHORITY: "SOLE"`). The engine does not infer precedence.
5. **Schema is versioned.** Breaking changes to the schema require a major version bump. Adopters can pin their `.gxp` files to a schema version.

---

## 3. File format

### 3.1 Container

A `.gxp` file is plain UTF-8 text. It begins with `[SYSTEM_RULE_START]` on its own line and ends with `[SYSTEM_RULE_END]` on its own line. Any text outside these markers is ignored by the parser.

```
[SYSTEM_RULE_START]
SOP_ID: <id> | REV: <version> | EFFECTIVE: <YYYY-MM-DD>
TITLE: <title>
ARCHETYPE: <archetype>
JURISDICTION: <Global|<region>>
HUMAN_DOC: <relative path to the prose SOP>

# <section number> <SECTION NAME>
@<TAG_FAMILY>:<RULE_ID> { <KEY>: <VALUE>, ... }
@<TAG_FAMILY>:<RULE_ID> { ... }

# <next section>
...
[SYSTEM_RULE_END]
```

### 3.2 Header fields

| Field | Required | Description |
|---|---|---|
| `SOP_ID` | yes | Stable identifier (matches eQMS document ID) |
| `REV` | yes | Revision number — must match the prose SOP exactly |
| `EFFECTIVE` | yes | Effective date in `YYYY-MM-DD` format |
| `TITLE` | yes | Document title — exact match to prose SOP |
| `ARCHETYPE` | yes | One of: `SOP`, `PROTOCOL`, `WORK_INSTRUCTION`, `JOB_AID`, `TEST_METHOD`, `SPECIFICATION`, `PROTOCOL_REPORT`, `VALIDATION_PLAN`, `MASTER_BATCH_RECORD`, `CHANGE_CONTROL` |
| `JURISDICTION` | yes | `Global` or a specific region/site identifier |
| `HUMAN_DOC` | recommended | Relative path to the prose document |

### 3.3 Section markers

Section markers are `# <section_number> <SECTION_NAME>` (Markdown H1). They organize the file by SOP section but are not parsed semantically — the `SOURCE_SECTION` field on each rule is what binds the rule to a SOP section.

### 3.4 Rule syntax

Each rule is one line:

```
@<TAG_FAMILY>:<RULE_ID> { <KEY>: <VALUE>, <KEY>: <VALUE>, ... }
```

Where:
- `<TAG_FAMILY>` is one of the canonical tag families (§ 4).
- `<RULE_ID>` is an uppercase, snake-cased identifier unique within its tag family (e.g., `RESP_001`, `L2_TRIGGER`).
- The body between `{` and `}` is a comma-separated list of `KEY: VALUE` pairs.
- Values are double-quoted strings, unquoted booleans (`TRUE`/`FALSE`), unquoted integers, or arrays in `[...]`.

---

## 4. Canonical tag families (v0.1)

### 4.1 `@RULE` — Responsibility / role rules

Defines who is authorized to perform an action. Used to enforce the "Hierarchy of Power" — when a query asks "can the Originator approve final leveling?" the engine traces the role to its action authority.

**Required keys:** `ROLE`, `ACTION`, `SOURCE_SECTION`
**Optional keys:** `AUTHORITY` (`SOLE` | `JOINT` | `DELEGATED`), `WINDOW` (timeline qualifier)

```
@RULE:RESP_001 { ROLE: "Quality Approver", AUTHORITY: "SOLE", ACTION: "Final Leveling Approval", SOURCE_SECTION: "3.0" }
```

### 4.2 `@TIMELINE` — Mandatory deadlines

Defines a hard deadline. The engine returns these verbatim when the user asks about a deadline.

**Required keys:** `VALUE` (integer), `UNIT` (`Calendar Days` | `Business Days` | `Hours`), `START_EVENT`, `SOURCE_SECTION`

```
@TIMELINE:L2_INVESTIGATION { VALUE: 60, UNIT: "Calendar Days", START_EVENT: "Initiation", SOURCE_SECTION: "5.3" }
```

### 4.3 `@LOGIC` — Classification / decision logic

Defines an `IF / THEN` rule that classifies an item. Used for risk-based leveling, default classifications, and mandatory triggers.

**Required keys:** `IF` (string or array), `THEN`, `SOURCE_SECTION`
**Optional keys:** `OVERRIDE: TRUE` (highest precedence), `MANDATORY: TRUE`, `AUTHORITY` (the role who can override the result)

```
@LOGIC:L2_TRIGGER { IF: ["Sterility", "Falsified Data", "CPP"], THEN: "Level 2", OVERRIDE: TRUE, SOURCE_SECTION: "5.2" }
@LOGIC:DEFAULT    { IF: "NOT in Attachment 4",                  THEN: "Level 1", AUTHORITY: "Quality Approver", SOURCE_SECTION: "5.2" }
```

### 4.4 `@EXCEPTION` — Conditional exemptions

Geographic, role-based, or material-based exemptions to a global rule.

**Required keys:** `REQUIREMENT`, `STATUS` (`EXEMPT` | `MANDATORY`), `SOURCE_SECTION`
**Optional keys:** `COUNTRY`, `SITE`, `ROLE`, `MATERIAL`

```
@EXCEPTION:LANG_01 { COUNTRY: "Austria", SITE: "BioLife", REQUIREMENT: "English", STATUS: "EXEMPT", SOURCE_SECTION: "5.1" }
```

### 4.5 `@SCOPE` — Scope guardrails

Inclusion / exclusion / prohibition declarations. Used by the scope gatekeeper before any rule fires — if a query is about an excluded entity, the engine refuses with a citation.

**Required keys:** depends on subtype. One of:
- `APPLIES_TO`: `ENTITIES: [...]`
- `EXCLUDED_FROM`: `ENTITIES: [...]`
- `PROHIBITED`: `ITEMS: [...]`, `STATUS`

```
@SCOPE:EXCLUDED_FROM { ENTITIES: ["Preclinical research", "Environmental Monitoring Excursions"], SOURCE_SECTION: "2.0" }
@SCOPE:PROHIBITED    { ITEMS: ["Planned Deviations"], STATUS: "STRICTLY PROHIBITED", SOURCE_SECTION: "2.0" }
```

### 4.6 `@REFERENCE` — Linked SOPs / standards

Documents this SOP depends on or references. Used to enable multi-document reasoning in future versions.

**Required keys:** `DOC_ID`, `TITLE`, `SOURCE_SECTION`

```
@REFERENCE:R_01 { DOC_ID: "SOP-QA-005", TITLE: "Quality Management Change Control System", SOURCE_SECTION: "4.0" }
```

### 4.7 `@ATTACHMENT` — Attachment registry

**Required keys:** `ID`, `TITLE`, `SOURCE_SECTION`
**Optional keys:** `ROLE` (a string declaring how the attachment is used by other rules, e.g., `REFERENCE_LIST_FOR_LOGIC:DEFAULT`)

```
@ATTACHMENT:A_04 { ID: "Attachment 4", TITLE: "Investigation - CAPA Reference List", SOURCE_SECTION: "6.0", ROLE: "REFERENCE_LIST_FOR_LOGIC:DEFAULT" }
```

### 4.8 `@REVISION` — Version history

**Required keys:** `VERSION`, `EFFECTIVE`, `SUMMARY`, `SOURCE_SECTION`

```
@REVISION:V_1_0 { VERSION: "1.0", EFFECTIVE: "2026-04-25", SUMMARY: "Initial Release", SOURCE_SECTION: "7.0" }
```

---

## 5. Precedence rules

When multiple rules could apply to a query, precedence is resolved as follows:

1. **`@SCOPE:EXCLUDED_FROM` and `@SCOPE:PROHIBITED`** evaluate first. If a query is about an excluded entity, the engine returns the scope refusal and stops.
2. **`@LOGIC` rules with `OVERRIDE: TRUE`** beat all other `@LOGIC` rules.
3. **`@LOGIC` rules with `MANDATORY: TRUE`** beat non-mandatory rules of the same type.
4. **`@EXCEPTION`** rules beat the corresponding default rule (e.g., `@EXCEPTION:LANG_01` beats `@EXCEPTION:LANG_DEFAULT` when the query mentions Austria).
5. Within the same precedence band, the first matching rule in document order wins.

The reference implementation enforces these explicitly; alternate implementations must match this precedence order to claim conformance.

---

## 6. Validation rules for `.gxp` files

A conforming parser MUST reject a `.gxp` file that:

- Lacks the `[SYSTEM_RULE_START]` / `[SYSTEM_RULE_END]` markers.
- Has any `@TAG` line without a `SOURCE_SECTION` field.
- Contains a duplicate `RULE_ID` within the same tag family.
- Contains a `@TIMELINE` with `VALUE` that isn't a positive integer.
- Has unbalanced `{` / `}` or `[` / `]`.
- References a tag family not listed in § 4 of this spec, unless the parser is in extension mode and the family is registered as an extension.

---

## 7. Extending the schema

Adding a new tag family is a non-breaking change as long as:

1. The new family is namespaced and clearly proposed (e.g., `@CALIBRATION`, `@SAFETY_LIMIT`).
2. A reference example is provided in `examples/`.
3. The reference implementation gains a parser for it.

Modifying an existing tag family (changing required keys, semantics) is a breaking change and requires a major schema version bump.

---

## 8. Conformance

A "GxP-Struct conformant" toolchain claims:

- It can parse a `.gxp` file written against this spec without modification.
- It enforces the precedence rules in § 5.
- It produces an audit record for every query that conforms to the audit schema (see [VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md)).

The Python reference implementation in this repository is the canonical conformance reference. Other implementations are welcome and encouraged.

---

## 9. Future schema extensions (v0.2+)

The following tag families are reserved for future versions:

- `@CPP` — Critical Process Parameters with target / range / action limits
- `@SAFETY_LIMIT` — Hard safety limits with associated alarm logic
- `@WORKFLOW_STATE` — Document lifecycle state (draft / in-review / approved / effective / obsolete)
- `@TRAINING` — Training assignments and competency requirements
- `@EQUIPMENT` — Equipment IDs the SOP applies to (with model numbers, serial numbers)

Contributions defining these tag families are welcome under the process in [CONTRIBUTING.md](../CONTRIBUTING.md).
