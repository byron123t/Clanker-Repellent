"""Minimal, dependency-free dotenv loading for local endpoint configuration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Mapping, Optional


_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_dotenv(path: Path) -> Dict[str, str]:
    """Load a strict KEY=VALUE file without mutating process environment."""

    if not path.is_file():
        return {}
    values: Dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _NAME.fullmatch(name):
            raise ValueError(f"{path}:{line_number}: invalid environment name")
        if name in values:
            raise ValueError(f"{path}:{line_number}: duplicate environment name {name}")
        value = raw_value.strip()
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"{path}:{line_number}: unterminated quoted value")
            value = value[1:-1]
        if "\x00" in value:
            raise ValueError(f"{path}:{line_number}: value cannot contain NUL")
        values[name] = value
    return values


def merged_environment(
    *,
    dotenv_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Merge dotenv defaults with an explicit or process environment override."""

    values = load_dotenv(dotenv_path) if dotenv_path is not None else {}
    values.update(dict(os.environ if environ is None else environ))
    return values
