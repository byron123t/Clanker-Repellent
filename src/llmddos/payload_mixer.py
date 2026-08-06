"""Seeded, filename-driven construction of cross-topic payload mixtures."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .payload_templates import resolve_config_file


MIXTURE_ROLES = ("bio_header", "topic_header", "raw_text")
TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RAW_TOPIC_PREFIXES = {
    "acid": "chem",
    "meth": "chem",
    "bio": "bio",
    "c4": "c4",
    "nuke": "nuke",
    "rad": "rad",
}


def validate_mixture_parts(
    config_root: Path, parts: Any
) -> List[Dict[str, str]]:
    """Validate a bio/header/raw selection using path metadata only."""

    if not isinstance(parts, list) or len(parts) != 3:
        raise ValueError("payload_parts must contain exactly three objects")
    normalized = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or set(part) != {"file", "role", "topic"}:
            raise ValueError(
                "each payload part must contain exactly file, role, and topic"
            )
        reference = part["file"]
        role = part["role"]
        topic = part["topic"]
        if role != MIXTURE_ROLES[index]:
            raise ValueError(
                "payload part roles must be ordered: " + ", ".join(MIXTURE_ROLES)
            )
        if not isinstance(topic, str) or not TOPIC_ID.fullmatch(topic):
            raise ValueError(f"payload part {role!r} has an invalid topic")
        resolve_config_file(config_root, reference, f"payload part {role!r} file")
        normalized.append({"file": reference, "role": role, "topic": topic})
    topics = [part["topic"] for part in normalized]
    if topics[0] != "bio":
        raise ValueError("the first payload part must be a bio header")
    if topics[1] == "bio":
        raise ValueError("the second payload part must be a non-bio topic header")
    if topics[2] in {"bio", topics[1]}:
        raise ValueError(
            "the raw-text topic must differ from both bio and the topic header"
        )
    return normalized


def load_payload_mixture(
    config_root: Path, parts: Any, separator: str = "\n\n"
) -> Tuple[str, Dict[str, Any]]:
    """Read and concatenate one validated mixture in its declared order."""

    normalized = validate_mixture_parts(config_root, parts)
    if not isinstance(separator, str):
        raise ValueError("payload_part_separator must be a string")
    if "\x00" in separator:
        raise ValueError("payload_part_separator cannot contain NUL bytes")
    texts = []
    metadata = []
    for part in normalized:
        path = resolve_config_file(
            config_root, part["file"], f"payload part {part['role']!r} file"
        )
        text = path.read_text(encoding="utf-8")
        if "\x00" in text:
            raise ValueError(f"payload part {part['file']!r} cannot contain NUL bytes")
        texts.append(text)
        metadata.append(
            {
                **part,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return separator.join(texts), {
        "mixture_parts": metadata,
        "payload_part_separator_sha256": hashlib.sha256(
            separator.encode("utf-8")
        ).hexdigest(),
    }


def _raw_topic(filename: str) -> str:
    stem = Path(filename).stem
    remainder = stem.removeprefix("raw_")
    matches = [
        topic
        for prefix, topic in RAW_TOPIC_PREFIXES.items()
        if remainder.startswith(prefix)
    ]
    if len(matches) != 1:
        raise ValueError(f"cannot infer exactly one topic for raw payload {filename!r}")
    return matches[0]


def discover_mix_sources(
    payload_directory: Path,
) -> Tuple[List[str], Dict[str, str], Dict[str, List[str]]]:
    """Discover candidate filenames without opening any payload file."""

    root = payload_directory.resolve()
    if not root.is_dir():
        raise ValueError(f"payload directory is not a directory: {payload_directory}")
    bio_headers = sorted(
        path.name
        for path in root.glob("bio_header*.txt")
        if path.is_file()
    )
    topic_headers = {
        path.stem.removesuffix("_header"): path.name
        for path in sorted(root.glob("*_header.txt"))
        if path.is_file() and not path.name.startswith("bio_header")
    }
    raw_by_topic: Dict[str, List[str]] = {}
    for path in sorted(root.glob("raw_*.txt")):
        if not path.is_file():
            continue
        raw_by_topic.setdefault(_raw_topic(path.name), []).append(path.name)
    if not bio_headers:
        raise ValueError("no bio_header*.txt files found")
    if len(topic_headers) < 2:
        raise ValueError("at least two non-bio topic headers are required")
    unknown_raw_topics = set(raw_by_topic) - set(topic_headers) - {"bio"}
    if unknown_raw_topics:
        raise ValueError(
            "raw payload topics have no matching header topic: "
            + ", ".join(sorted(unknown_raw_topics))
        )
    usable_raw_topics = set(raw_by_topic) - {"bio"}
    if len(usable_raw_topics) < 2:
        raise ValueError("at least two non-bio raw-text topics are required")
    return bio_headers, topic_headers, raw_by_topic


def build_mix_condition_rows(
    payload_directory: Path, *, count: int, seed: int
) -> List[Dict[str, Any]]:
    """Build a reproducible random sample of unique valid mixtures."""

    if count < 1:
        raise ValueError("count must be at least 1")
    bio_headers, topic_headers, raw_by_topic = discover_mix_sources(
        payload_directory
    )
    combinations = []
    for bio_header in bio_headers:
        for header_topic, topic_header in sorted(topic_headers.items()):
            for raw_topic, raw_files in sorted(raw_by_topic.items()):
                if raw_topic in {"bio", header_topic}:
                    continue
                for raw_file in raw_files:
                    combinations.append(
                        (bio_header, header_topic, topic_header, raw_topic, raw_file)
                    )
    if count > len(combinations):
        raise ValueError(
            f"requested {count} mixtures but only {len(combinations)} unique mixtures exist"
        )
    random.Random(seed).shuffle(combinations)
    rows: List[Dict[str, Any]] = [
        {
            "id": "baseline",
            "family": "clean",
            "payload": "",
            "placement": "none",
            "operational": False,
        }
    ]
    for index, combination in enumerate(combinations[:count], start=1):
        bio_header, header_topic, topic_header, raw_topic, raw_file = combination
        rows.append(
            {
                "id": (
                    f"mix_{index:03d}_{Path(bio_header).stem}_"
                    f"{header_topic}_{Path(raw_file).stem}"
                ),
                "family": "mixed_actual",
                "payload_parts": [
                    {"file": bio_header, "role": "bio_header", "topic": "bio"},
                    {
                        "file": topic_header,
                        "role": "topic_header",
                        "topic": header_topic,
                    },
                    {"file": raw_file, "role": "raw_text", "topic": raw_topic},
                ],
                "payload_part_separator": "\n\n",
                "placement": "append",
                "operational": True,
                "tags": ["actual-file-backed", "bio-first", "cross-topic"],
                "selection_seed": seed,
            }
        )
    return rows


def write_mix_conditions(
    rows: Iterable[Mapping[str, Any]], path: Path, *, replace: bool = False
) -> None:
    """Atomically write generated conditions, requiring opt-in replacement."""

    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing conditions file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(dict(row), separators=(",", ":")) + "\n" for row in rows
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
