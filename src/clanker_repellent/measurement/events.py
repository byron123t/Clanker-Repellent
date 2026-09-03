"""Small append-only structured event log for experiment observability."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_text(value: str) -> str:
    output = value
    for pattern in SECRET_PATTERNS:
        output = pattern.sub("[REDACTED]", output)
    return output


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def compact_usage(usage: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(usage, dict):
        return None
    completion_details = usage.get("completion_tokens_details") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": prompt_details.get("cached_tokens"),
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


class EventLogger:
    """Writes compact JSONL metadata; prompts and response bodies are deliberately excluded."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.session_id = uuid.uuid4().hex[:12]
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, trial_id: Optional[str] = None, **fields: Any) -> None:
        record: Dict[str, Any] = {
            "event_schema": "1.0",
            "timestamp_utc": utc_now(),
            "run_id": self.run_id,
            "session_id": self.session_id,
            "event": event,
        }
        if trial_id is not None:
            record["trial_id"] = trial_id
        record.update(_sanitize(fields))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
