"""Stable identifiers for immutable experiment artefacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


def canonical_digest(config: Mapping[str, Any]) -> str:
    """Hash a JSON-compatible resolved configuration deterministically."""

    payload = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not result:
        raise ValueError("identifier must contain at least one letter or digit")
    return result


def build_run_id(method: str, config_hash: str, seed: int, git_sha: str) -> str:
    """Build ``<method>-<hash8>-s<seed>-<sha7>`` without path-unsafe text."""

    if isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be non-negative")
    normalized_hash = config_hash.lower()
    normalized_sha = git_sha.lower()
    if re.fullmatch(r"[0-9a-f]{8,}", normalized_hash) is None:
        raise ValueError("config_hash must contain at least eight hexadecimal characters")
    if re.fullmatch(r"[0-9a-f]{7,}", normalized_sha) is None:
        raise ValueError("git_sha must contain at least seven hexadecimal characters")
    return f"{_slug(method)}-{normalized_hash[:8]}-s{seed}-{normalized_sha[:7]}"
