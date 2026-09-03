"""Experiment execution and durable JSONL recording."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .events import EventLogger, compact_usage, fingerprint, redact_text
from .metrics import classify_response
from ..inference.prompts import PROMPT_VERSION, build_messages
from ..inference.provider import OpenAICompatibleProvider


def trial_id(
    model: str,
    case_id: str,
    condition_id: str,
    prompt_mode: str,
    repeat: int,
    request_hash: str = "",
    temperature: float = 0.0,
    max_tokens: int = 300,
) -> str:
    raw = "|".join(
        (
            model,
            case_id,
            condition_id,
            prompt_mode,
            str(repeat),
            request_hash,
            str(temperature),
            str(max_tokens),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_trials(
    models: Sequence[str],
    cases: Sequence[Dict[str, Any]],
    conditions: Sequence[Dict[str, Any]],
    prompt_modes: Sequence[str],
    repeats: int,
    seed: int,
) -> List[Tuple[str, Dict[str, Any], Dict[str, Any], str, int]]:
    trials = [
        (model, case, condition, prompt_mode, repeat)
        for model in models
        for case in cases
        for condition in conditions
        for prompt_mode in prompt_modes
        for repeat in range(repeats)
    ]
    random.Random(seed).shuffle(trials)
    return trials


def load_completed(path: Path) -> set:
    if not path.exists():
        return set()
    completed = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("status") == "ok":
                    completed.add(row["trial_id"])
    return completed


def run_trials(
    provider: OpenAICompatibleProvider,
    output_path: Path,
    models: Sequence[str],
    cases: Sequence[Dict[str, Any]],
    conditions: Sequence[Dict[str, Any]],
    prompt_modes: Sequence[str],
    repeats: int = 1,
    seed: int = 20260802,
    max_tokens: int = 300,
    temperature: float = 0.0,
    limit: Optional[int] = None,
    run_id: Optional[str] = None,
    max_consecutive_errors: int = 3,
    event_log_path: Optional[Path] = None,
) -> Dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    effective_run_id = run_id or output_path.stem
    event_logger = EventLogger(event_log_path, effective_run_id) if event_log_path else None
    completed = load_completed(output_path)
    trials = make_trials(models, cases, conditions, prompt_modes, repeats, seed)
    if limit is not None:
        trials = trials[:limit]
    counts = {
        "planned": len(trials),
        "completed": 0,
        "skipped": 0,
        "errors": 0,
        "terminated_early": 0,
    }
    consecutive_errors = 0
    if event_logger:
        event_logger.emit(
            "run_started",
            planned_trials=len(trials),
            models=list(models),
            prompt_modes=list(prompt_modes),
            repeats=repeats,
            seed=seed,
            max_tokens=max_tokens,
            temperature=temperature,
            output_file=output_path.name,
        )
    with output_path.open("a", encoding="utf-8") as handle:
        for model, case, condition, prompt_mode, repeat in trials:
            messages = build_messages(case, condition, prompt_mode)
            request_hash = hashlib.sha256(
                json.dumps(messages, sort_keys=True).encode("utf-8")
            ).hexdigest()
            current_id = trial_id(
                model,
                case["id"],
                condition["id"],
                prompt_mode,
                repeat,
                request_hash=request_hash,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if current_id in completed:
                counts["skipped"] += 1
                if event_logger:
                    event_logger.emit("trial_skipped", trial_id=current_id, reason="already_completed")
                continue
            if event_logger:
                system_content = next(
                    (message["content"] for message in messages if message["role"] == "system"), ""
                )
                user_content = next(
                    (message["content"] for message in reversed(messages) if message["role"] == "user"), ""
                )
                event_logger.emit(
                    "trial_started",
                    trial_id=current_id,
                    model=model,
                    case_id=case["id"],
                    condition_id=condition["id"],
                    condition_family=condition["family"],
                    prompt_mode=prompt_mode,
                    repeat=repeat,
                    request_hash=request_hash,
                    prompt_characters=sum(len(message["content"]) for message in messages),
                    payload_characters=len(condition["payload"]),
                    payload_placement=condition["placement"],
                    payload_declared_operational=bool(condition.get("operational", False)),
                    payload_verified_in_prompt=(
                        condition["payload"] in user_content
                        if condition["payload"]
                        else None
                    ),
                    system_role_present=bool(system_content),
                    document_frame_present="Document:" in user_content,
                    appendix_frame_present="[APPENDIX]" in user_content,
                    hardened_provenance_instruction=prompt_mode == "hardened",
                )
            base = {
                "schema_version": "1.0",
                "prompt_version": PROMPT_VERSION,
                "run_id": effective_run_id,
                "trial_id": current_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "case_id": case["id"],
                "condition_id": condition["id"],
                "condition_family": condition["family"],
                "prompt_mode": prompt_mode,
                "repeat": repeat,
                "messages": messages,
                "expected_terms": case["expected_terms"],
                "sampling": {"temperature": temperature, "max_tokens": max_tokens},
                "request_hash": request_hash,
                "system_wrapper_hash": hashlib.sha256(
                    next(
                        (message["content"] for message in messages if message["role"] == "system"), ""
                    ).encode("utf-8")
                ).hexdigest(),
                "condition_payload_hash": hashlib.sha256(
                    condition["payload"].encode("utf-8")
                ).hexdigest(),
            }
            try:
                result = provider.complete(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if event_logger:
                    event_logger.emit(
                        "provider_succeeded",
                        trial_id=current_id,
                        latency_ms=result["latency_ms"],
                        finish_reason=result["finish_reason"],
                        usage=compact_usage(result["usage"]),
                        response_characters=len(result["response_text"]),
                        structured_refusal_present=bool(result.get("provider_refusal")),
                        resolved_model=result.get("resolved_model"),
                        service_tier=result.get("service_tier"),
                    )
                base.update(result)
                base["metrics"] = classify_response(
                    result["response_text"],
                    case["expected_terms"],
                    provider_refusal=result.get("provider_refusal") or "",
                )
                base["status"] = "ok"
                if event_logger:
                    event_logger.emit(
                        "trial_scored",
                        trial_id=current_id,
                        outcome=base["metrics"]["outcome"],
                        task_success=base["metrics"]["task_success"],
                        refusal=base["metrics"]["refusal"],
                        attack_success=base["metrics"]["attack_success"],
                        schema_valid=base["metrics"]["schema_valid"],
                        refusal_match_count=len(base["metrics"]["refusal_matches"]),
                        expected_term_hit_count=len(base["metrics"]["expected_term_hits"]),
                    )
                counts["completed"] += 1
                consecutive_errors = 0
            except Exception as exc:  # Preserve failures without conflating them with refusals.
                base["status"] = "error"
                base["error_type"] = type(exc).__name__
                base["error_message"] = redact_text(str(exc))[:500]
                counts["errors"] += 1
                consecutive_errors += 1
                if event_logger:
                    event_logger.emit(
                        "provider_failed",
                        trial_id=current_id,
                        error_type=type(exc).__name__,
                        status_code=getattr(exc, "status_code", None),
                        error_fingerprint=fingerprint(str(exc)),
                        consecutive_errors=consecutive_errors,
                    )
            handle.write(json.dumps(base, ensure_ascii=False) + "\n")
            handle.flush()
            if consecutive_errors >= max_consecutive_errors:
                counts["terminated_early"] = 1
                if event_logger:
                    event_logger.emit(
                        "run_stopped",
                        trial_id=current_id,
                        reason="max_consecutive_errors",
                        consecutive_errors=consecutive_errors,
                    )
                break
    if event_logger:
        event_logger.emit("run_finished", **counts)
    return counts


def read_results(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
