"""Parser for `.gxp` machine-readable SOP files.

The schema is documented in docs/SCHEMA_SPEC.md. In one paragraph:

    A .gxp file begins with [SYSTEM_RULE_START] and ends with
    [SYSTEM_RULE_END]. Between those markers, header fields appear as
    `KEY: VALUE` lines and rules appear as one-line declarations of the
    form `@TAG_FAMILY:RULE_ID { KEY: VALUE, ... }`. Section headers
    `# 1.0 NAME` are organizational only.

This parser is intentionally small and dependency-free. It produces a
typed `ParsedGxp` object that other modules can consume without ever
touching the file format. If the parser rejects a file, the rest of
the system never sees it — that's the validation contract.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data shape
# ---------------------------------------------------------------------------

@dataclass
class GxpRule:
    family: str          # e.g. "RULE", "TIMELINE", "LOGIC", "EXCEPTION", ...
    rule_id: str         # e.g. "RESP_001", "L2_TRIGGER"
    fields: dict[str, Any]
    line_no: int


@dataclass
class ParsedGxp:
    sop_id: str = ""
    sop_version: str = ""
    sop_effective_date: str = ""
    title: str = ""
    archetype: str = ""
    jurisdiction: str = ""
    human_doc: str = ""
    rules: list[GxpRule] = field(default_factory=list)

    def by_family(self, family: str) -> list[GxpRule]:
        return [r for r in self.rules if r.family.upper() == family.upper()]

    def find(self, family: str, rule_id: str) -> GxpRule | None:
        for r in self.rules:
            if r.family.upper() == family.upper() and r.rule_id == rule_id:
                return r
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class GxpParseError(ValueError):
    """Raised when a .gxp file violates the schema."""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HEADER_KEYS = {
    "SOP_ID": "sop_id",
    "REV": "sop_version",
    "EFFECTIVE": "sop_effective_date",
    "TITLE": "title",
    "ARCHETYPE": "archetype",
    "JURISDICTION": "jurisdiction",
    "HUMAN_DOC": "human_doc",
}

_RULE_LINE = re.compile(
    r"^@(?P<family>[A-Z_]+):(?P<rule_id>[A-Z0-9_]+)\s*\{(?P<body>.*)\}\s*$"
)
_SECTION_HEADER = re.compile(r"^#\s*\d+\.\d+")  # `# 1.0 ACCESS_CONTROL` etc.


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        # Array of double-quoted strings.
        inner = raw[1:-1].strip()
        if not inner:
            return []
        out = []
        for item in re.findall(r'"([^"]*)"|\b(TRUE|FALSE)\b|(-?\d+)', inner):
            s, b, n = item
            if s != "":
                out.append(s)
            elif b:
                out.append(b == "TRUE")
            elif n:
                out.append(int(n))
        return out
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw in {"TRUE", "FALSE"}:
        return raw == "TRUE"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    # Fallback: bare token (e.g. for SOP_ID values without quotes)
    return raw


def _split_pipe_header(line: str, parsed: ParsedGxp) -> None:
    """Header line of the form `SOP_ID: ... | REV: ... | EFFECTIVE: ...`."""
    parts = [p.strip() for p in line.split("|")]
    for part in parts:
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        k = k.strip().upper()
        v = v.strip()
        if k in _HEADER_KEYS:
            setattr(parsed, _HEADER_KEYS[k], v)


def _split_kv_body(body: str) -> dict[str, Any]:
    """Split `KEY: VALUE, KEY: ["a", "b"], KEY: TRUE` into a dict."""
    fields: dict[str, Any] = {}
    # Walk character-by-character to respect bracketed arrays and quoted strings.
    i = 0
    key = ""
    state = "key"
    buf = ""
    depth = 0
    in_quote = False
    while i < len(body):
        ch = body[i]
        if state == "key":
            if ch == ":":
                state = "value"
                buf = ""
            elif ch == ",":
                # stray comma — ignore
                key = ""
            else:
                key += ch
        else:  # state == "value"
            if in_quote:
                buf += ch
                if ch == '"':
                    in_quote = False
            elif ch == '"':
                buf += ch
                in_quote = True
            elif ch == "[":
                buf += ch
                depth += 1
            elif ch == "]":
                buf += ch
                depth -= 1
            elif ch == "," and depth == 0:
                fields[key.strip().upper()] = _parse_value(buf)
                key = ""
                buf = ""
                state = "key"
            else:
                buf += ch
        i += 1
    if key.strip():
        fields[key.strip().upper()] = _parse_value(buf)
    return fields


def parse(text: str, *, source: str = "<string>") -> ParsedGxp:
    if "[SYSTEM_RULE_START]" not in text or "[SYSTEM_RULE_END]" not in text:
        raise GxpParseError(
            f"{source}: missing [SYSTEM_RULE_START] / [SYSTEM_RULE_END] markers."
        )
    start = text.index("[SYSTEM_RULE_START]") + len("[SYSTEM_RULE_START]")
    end = text.index("[SYSTEM_RULE_END]")
    body = text[start:end]

    parsed = ParsedGxp()
    seen: set[tuple[str, str]] = set()

    for lineno, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if not _SECTION_HEADER.match(line):
                # comments / unrecognized headers are tolerated but ignored
                pass
            continue
        if line.startswith("@"):
            m = _RULE_LINE.match(line)
            if not m:
                raise GxpParseError(
                    f"{source}:{lineno}: malformed rule line: {line!r}"
                )
            family = m.group("family")
            rule_id = m.group("rule_id")
            fields = _split_kv_body(m.group("body"))
            if "SOURCE_SECTION" not in fields:
                raise GxpParseError(
                    f"{source}:{lineno}: rule @{family}:{rule_id} is missing required SOURCE_SECTION."
                )
            key = (family.upper(), rule_id)
            if key in seen:
                raise GxpParseError(
                    f"{source}:{lineno}: duplicate rule id @{family}:{rule_id}."
                )
            seen.add(key)
            parsed.rules.append(GxpRule(
                family=family,
                rule_id=rule_id,
                fields=fields,
                line_no=lineno,
            ))
            continue
        # Header lines outside any tag
        if "|" in line and "SOP_ID" in line.upper():
            _split_pipe_header(line, parsed)
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip().upper()
            v = v.strip()
            if k in _HEADER_KEYS:
                setattr(parsed, _HEADER_KEYS[k], v)
            continue
        # otherwise: ignore
    if not parsed.sop_id:
        raise GxpParseError(f"{source}: SOP_ID header is required.")
    if not parsed.sop_version:
        raise GxpParseError(f"{source}: REV header is required.")
    if not parsed.sop_effective_date:
        raise GxpParseError(f"{source}: EFFECTIVE header is required.")
    return parsed


def parse_file(path: str | Path) -> ParsedGxp:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"), source=str(p))


# ---------------------------------------------------------------------------
# Conformance summary helpers
# ---------------------------------------------------------------------------

def summary(parsed: ParsedGxp) -> dict[str, Any]:
    families: dict[str, int] = {}
    for r in parsed.rules:
        families[r.family] = families.get(r.family, 0) + 1
    return {
        "sop_id": parsed.sop_id,
        "sop_version": parsed.sop_version,
        "sop_effective_date": parsed.sop_effective_date,
        "title": parsed.title,
        "archetype": parsed.archetype,
        "jurisdiction": parsed.jurisdiction,
        "rule_count": len(parsed.rules),
        "by_family": families,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Parse a .gxp machine-readable SOP file.")
    ap.add_argument("path", help="Path to the .gxp file.")
    ap.add_argument("--print", action="store_true",
                    help="Print the full parsed structure as JSON.")
    args = ap.parse_args()

    parsed = parse_file(args.path)
    if args.print:
        print(json.dumps(parsed.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(summary(parsed), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
