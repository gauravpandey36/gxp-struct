"""Central configuration. Loads .env and exposes typed constants.

Every other module imports from here so the SOP version, namespace, and
model choices are tracked in exactly one place — important for GxP
change control.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Missing required env var: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


@dataclass(frozen=True)
class Settings:
    # OpenAI
    openai_api_key: str
    embedding_model: str
    embedding_dim: int
    llm_model: str
    llm_temperature: float

    # Pinecone
    pinecone_api_key: str
    pinecone_index_name: str
    pinecone_namespace: str
    pinecone_cloud: str
    pinecone_region: str

    # SOP provenance — stamped onto every chunk
    sop_id: str
    sop_title: str
    sop_version: str
    sop_effective_date: str

    # Audit
    audit_log_path: Path
    audit_user: str

    # Paths
    sop_markdown_path: Path


def load_settings() -> Settings:
    audit_path = Path(os.getenv("AUDIT_LOG_PATH", "./audit/queries.jsonl"))
    if not audit_path.is_absolute():
        audit_path = PROJECT_ROOT / audit_path

    return Settings(
        openai_api_key=_require("OPENAI_API_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "3072")),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        pinecone_api_key=_require("PINECONE_API_KEY"),
        pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "gxp-struct"),
        pinecone_namespace=os.getenv("PINECONE_NAMESPACE", "gxp-struct-v1"),
        pinecone_cloud=os.getenv("PINECONE_CLOUD", "aws"),
        pinecone_region=os.getenv("PINECONE_REGION", "us-east-1"),
        sop_id=os.getenv("SOP_ID", "SOP-DEV-001"),
        sop_title=os.getenv("SOP_TITLE", "Deviation and CAPA Management System"),
        sop_version=os.getenv("SOP_VERSION", "1.0"),
        sop_effective_date=os.getenv("SOP_EFFECTIVE_DATE", "2026-04-25"),
        audit_log_path=audit_path,
        audit_user=os.getenv("AUDIT_USER", "system"),
    )


SETTINGS = load_settings() if os.getenv("OPENAI_API_KEY") else None  # lazy: don't crash on import in tests


def get_settings() -> Settings:
    """Resolve settings on demand so unit tests can monkeypatch env."""
    global SETTINGS
    if SETTINGS is None:
        SETTINGS = load_settings()
    return SETTINGS
