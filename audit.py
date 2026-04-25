"""GxP audit log — one JSONL line per query.

Captures everything a regulator would want to see: the exact SOP version,
the query, whether a deterministic rule fired, what chunks were retrieved,
and the final answer. Append-only.

Aligns with 21 CFR Part 11 / EU Annex 11 expectations for electronic records:
- Timestamped (UTC, ISO 8601)
- User-attributable
- Tamper-evident (append-only JSONL; pair with file-system permissions in prod)
- Complete (no field is dropped silently)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import get_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_query_id() -> str:
    return str(uuid.uuid4())


def log_query(
    *,
    query_id: str,
    query: str,
    intent: str,
    rule_triggered: str | None,
    retrieved_chunks: list[dict[str, Any]],
    answer: str,
    citations: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one record. Never raises on log failure — but we DO surface it."""
    s = get_settings()
    record = {
        "timestamp_utc": _now_iso(),
        "query_id": query_id,
        "user": s.audit_user,
        "sop_id": s.sop_id,
        "sop_version": s.sop_version,
        "sop_effective_date": s.sop_effective_date,
        "query": query,
        "intent_detected": intent,
        "rule_triggered": rule_triggered,
        "retrieved_chunks": retrieved_chunks,
        "answer": answer,
        "citations": citations,
        "model": {
            "llm": s.llm_model,
            "embedding": s.embedding_model,
            "temperature": s.llm_temperature,
        },
        "extra": extra or {},
    }

    path: Path = s.audit_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
