"""Render the M5 figures for every paired run of a validation batch.

Every pair is drawn, not a selection, so no seed is picked after seeing its curves. The
results note shows seed 7, the development-pilot seed named before the batch ran.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from attain_sampling.sim.ecc2025_figures import render_ecc_pair, render_ecc_summary


def load(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rb") as stream:
        value = json.loads(stream.read())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a run record")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="validation batch directory")
    args = parser.parse_args()
    batch: Path = args.batch
    validation = json.loads((batch / "validation.json").read_text(encoding="utf-8"))
    destination = batch / "figures"
    written = [render_ecc_summary(validation, destination)]
    for row in validation["results"]:
        stem = f"{row['configuration'][0]}_s{row['seed']}"
        e0 = load(batch / "runs" / f"{stem}_e0.json.gz")
        e1 = load(batch / "runs" / f"{stem}_e1.json.gz")
        written.extend(render_ecc_pair(e0, e1, destination, stem))
    hashes = {
        path.relative_to(batch).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in written
    }
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(written)} figures into {destination}")


if __name__ == "__main__":
    main()
