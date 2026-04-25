# Contributing to GxP-Struct

Thank you for your interest in extending the standard. The value of GxP-Struct depends on it being adopted across companies, and that depends on contributions from people who actually run regulated operations.

## Two ways to contribute

### 1. Extend the schema with a new SOP archetype

Pharma has roughly 10–15 document archetypes (SOPs, Protocols, Test Methods, Work Instructions, Job Aids, Specifications, Protocol Reports, Validation Plans, Master Batch Records, Change Controls, …). v0.1 ships with one (Deviation & CAPA Management). Adding a new archetype is the most valuable contribution.

A complete archetype contribution includes:

1. **A canonical `.gxp` example** in `examples/` covering the new archetype, using only tags defined in [docs/SCHEMA_SPEC.md](docs/SCHEMA_SPEC.md) — or proposing new tags with rationale.
2. **An extension to `Logic_Rules.md`** documenting every rule the archetype introduces, with the SOP section it cites and the rule_id used in code.
3. **Golden test cases** added to `validation_test.py` covering both deterministic and RAG paths for the new archetype.
4. **A short note in `docs/RESEARCH_FINDINGS.md`** documenting any head-to-head test you ran.

If your contribution introduces new tag types or modifies the schema, also update [docs/SCHEMA_SPEC.md](docs/SCHEMA_SPEC.md) with rationale and propose a schema version bump.

### 2. Improve the reference implementation

The Python reference implementation in this repo is intentionally small and readable. Contributions that keep it that way are welcome:

- New retriever strategies (hybrid search, re-rankers).
- Better `.gxp` parser robustness or tooling (linter, formatter).
- Adapters for additional eQMS systems (Veeva Vault, Documentum, MasterControl).
- Multilingual grounding (the "vernacular validation" use case).

## Pull request checklist

Before opening a PR:

- [ ] `python validation_test.py --rules-only` passes.
- [ ] If you touched the schema, both `docs/SCHEMA_SPEC.md` and `Logic_Rules.md` are updated.
- [ ] New tags follow the existing style (`@FAMILY:RULE_ID { KEY: VALUE, ... }`).
- [ ] No company-specific or proprietary content. Examples must be derived from public reference SOPs or fully synthetic content.

## What we will not merge

- Changes that introduce silent fallbacks (the system answering when no rule fires *and* no relevant chunk is retrieved). The framework's contract is "say *not addressed in SOP* rather than guess."
- Changes that drop the audit log for performance. The audit log is non-negotiable.
- Code that calls an external LLM for what is fundamentally a deterministic check.

## Governance

For now, governance is benevolent-dictator (the original author). If the project reaches a critical mass of cross-company adoption, governance will move to a steering committee with rotating seats representing the major archetypes. That's a problem we'd love to have.

## Code of conduct

Be civil, be precise, be direct. Pharma quality work attracts people who say what they mean — that's a feature, not a bug. We don't need a long document to enumerate it.

## Questions?

Open an issue with the `question` label, or start a discussion in the repository's Discussions tab.
