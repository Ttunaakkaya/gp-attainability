"""Verify M3 package sources and preserved historical exact-GP science."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def key(row):
    return tuple(row[name] for name in ("robots", "scenario", "seed", "duration_s", "method"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    old_rows = {key(row): row for row in read(args.old)["records"]}
    cache = {}
    counts = {"runs": 0, "motion_rows": 0, "samples": 0, "frames": 0, "plans": 0}
    for row in read(args.new)["records"]:
        if row["gp_backend"] != "exact":
            continue
        old = old_rows[key(row)]
        runs = []
        for record in (old, row):
            path = record["path"]
            if path not in cache:
                cache[path] = read(Path(path) / "comparison.json")
            runs.append(next(r for r in cache[path]["runs"] if r["method"] == row["method"]))
        before, after = runs
        for name in ("motion", "samples"):
            assert len(before[name]) == len(after[name])
            for original, current in zip(before[name], after[name], strict=True):
                assert all(current[field] == value for field, value in original.items())
        assert len(before["frames"]) == len(after["frames"])
        for original, current in zip(before["frames"], after["frames"], strict=True):
            assert all(current[field] == value for field, value in original.items())
        assert len(before["plans"]) == len(after["plans"])
        for original, current in zip(before["plans"], after["plans"], strict=True):
            for field in (
                "plan_id",
                "forecast",
                "sample_times_s",
                "targets_by_epoch",
                "selected_candidate_id",
                "received_sample_keys",
            ):
                assert original[field] == current[field]
        counts["runs"] += 1
        counts["motion_rows"] += len(before["motion"])
        for name in ("samples", "frames", "plans"):
            counts[name] += len(before[name])
    assert counts["runs"] > 0
    package_files = []
    with zipfile.ZipFile(args.wheel) as archive:
        for name in archive.namelist():
            if name.startswith("attain_sampling/") and not name.endswith("/"):
                assert archive.read(name) == (root / "src" / name).read_bytes(), name
                package_files.append(name)
    assert "attain_sampling/gp/sogp.py" in package_files
    source_files = [
        p
        for p in (root / "src/attain_sampling").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    assert set(package_files) == {p.relative_to(root / "src").as_posix() for p in source_files}
    docs = [
        "README.md",
        "REPRODUCIBILITY.md",
        "AKTIF_ONCELIK_PROJE.md",
        "GP_Attainability_Masterplan_TR.md",
        "docs/CONTINUE_HERE.md",
        "docs/DEMO.md",
        "docs/M3_SOGP.md",
        "reports/m3_results_2026-09-15.md",
    ]
    links_checked = 0
    for name in docs:
        path = root / name
        for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            link = match.group(1).split("#", 1)[0].strip("<>")
            if not link or re.match(r"[a-zA-Z]+://", link):
                continue
            assert (path.parent / link).exists(), (name, link)
            links_checked += 1
    result = {
        "exact_preservation": counts,
        "package_files_byte_equal": len(package_files),
        "local_links_checked": links_checked,
        "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
        "old_index_sha256": hashlib.sha256(args.old.read_bytes()).hexdigest(),
        "new_index_sha256": hashlib.sha256(args.new.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
