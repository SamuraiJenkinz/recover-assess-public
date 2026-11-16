"""Reusable audit of a ``run.jsonl`` (GRPH-07), stdlib only.

``audit_run_log`` reads a run log line by line and reports rule violations: a line that is
not a JSON object, a request line whose method is neither GET nor POST, a POST whose template
is not ``/$batch``, and any raw line that matches a secret pattern. A finding carries only a
line number and a rule name, never the matched text, so a failing audit cannot re-print the
secret it found. Phase 6 reuses it for the pilot-run log audit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["SECRET_PATTERNS", "AuditFinding", "audit_run_log"]

_BATCH_TEMPLATE: Final = "/$batch"
_ALLOWED_METHODS: Final = frozenset({"GET", "POST"})

# Case-insensitive; keyed by the rule name a finding reports. Every pattern is a regex
# description of a secret shape, not a secret-shaped literal.
SECRET_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "bearer": r"\bBearer\b",
        "jwt": r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        "signature": r"\bsig=",
        "tempauth": r"tempauth",
        "download_url": r"downloadurl",
        "api_key": r"api-?key",
        "access_token": r"access_token",
    }.items()
}


@dataclass(frozen=True)
class AuditFinding:
    """One rule violation: the 1-based line number and the rule's name. No excerpt."""

    line_number: int
    rule: str


def _request_findings(number: int, event: dict[str, object]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    method = event.get("method")
    if method not in _ALLOWED_METHODS:
        findings.append(AuditFinding(number, "method_not_get_or_post"))
    if method == "POST" and event.get("template") != _BATCH_TEMPLATE:
        findings.append(AuditFinding(number, "post_outside_batch"))
    return findings


def audit_run_log(path: Path) -> list[AuditFinding]:
    """Return every finding in the run log at ``path``; an empty list means the log is clean."""
    findings: list[AuditFinding] = []
    text = path.read_text(encoding="utf-8")
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        findings.extend(
            AuditFinding(number, f"secret_pattern_{name}")
            for name, pattern in SECRET_PATTERNS.items()
            if pattern.search(raw)
        )
        try:
            parsed = json.loads(raw)
        except ValueError:
            findings.append(AuditFinding(number, "unparseable_line"))
            continue
        if not isinstance(parsed, dict):
            findings.append(AuditFinding(number, "unparseable_line"))
            continue
        if parsed.get("event") == "request":
            findings.extend(_request_findings(number, parsed))
    return findings
