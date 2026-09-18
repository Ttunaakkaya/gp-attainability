"""A recorded validation hash must be the hash of the bytes on disk."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module", params=["validate_m4", "validate_m5"])
def validation_script(request):
    directory = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location(
            f"{request.param}_writer_test", directory / f"{request.param}.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(directory))


def test_returned_hash_matches_the_written_bytes(validation_script, tmp_path, monkeypatch):
    # Emulate Windows text mode on every platform, so a return to write_text fails in CI too.
    def crlf_write_text(self, data, encoding=None, errors=None, newline=None):
        with self.open("w", encoding=encoding, errors=errors, newline="\r\n") as stream:
            return stream.write(data)

    monkeypatch.setattr(Path, "write_text", crlf_write_text)
    path = tmp_path / "validation.json"
    digest = validation_script.write_json(path, {"records": [{"value": 1.5}], "complete": True})
    payload = path.read_bytes()
    assert digest == hashlib.sha256(payload).hexdigest()
    assert b"\r" not in payload
