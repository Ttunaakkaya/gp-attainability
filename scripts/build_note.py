"""Build the M8 technical note: fill its numbers from the held-out analyses, print a PDF.

Every table and every number marked ``$name`` in ``docs/technical_note/note_template.html``
comes from the frozen batches' ``analysis.json`` files (via ``figures_m8.BATCHES``), the
recomputed stranded-robot counts, or the test collection. The prose around them is
written by hand and states no number of its own. The PDF is printed by a local Chrome or
Edge in headless mode; nothing is fetched from the network.

Usage::

    python scripts/figures_m8.py      # first, if the figures are missing
    python scripts/build_note.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figures_m8 import BATCHES, METHODS, PLATFORMS, ROOT, SCENARIOS, VARIANTS  # noqa: E402

NOTE_DIR = ROOT / "docs" / "technical_note"
FIGURES = ROOT / "reports" / "figures" / "m8"
BROWSERS = (
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
)


def _analysis(name: str) -> dict[str, Any]:
    return json.loads((BATCHES[name] / "analysis.json").read_text(encoding="utf-8"))


def _ci(stats: dict[str, Any], digits: int = 4) -> str:
    text = (
        f"{stats['mean']:+.{digits}f} [{stats['ci_low']:+.{digits}f}, "
        f"{stats['ci_high']:+.{digits}f}]"
    ).replace("-", "−")
    return f'<span class="sig">{text}</span>' if _significant(stats) else text


def _significant(stats: dict[str, Any]) -> bool:
    return not stats["ci_low"] <= 0.0 <= stats["ci_high"]


def _count(stats: dict[str, Any]) -> str:
    return f"{stats['negative']} / {stats['positive']}"


def _table(caption: str, head: list[str], rows: list[list[str]]) -> str:
    header = "".join(f"<th>{cell}</th>" for cell in head)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        f"<table><caption>{caption}</caption><thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _of(count: int, total: int) -> str:
    return f"{count} of {total}"


def _test_count() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    if match is None:
        raise SystemExit("could not count the tests:\n" + result.stdout[-2000:])
    return int(match.group(1))


def values(tests: int) -> dict[str, str]:
    data = {name: _analysis(name) for name in BATCHES}
    main = {name: data[name]["analysis"]["main"] for name in BATCHES}
    ablation = {name: data[name]["analysis"]["ablation"] for name in PLATFORMS}
    stranded = json.loads((FIGURES / "stopped_robots.json").read_text(encoding="utf-8"))["counts"]

    primary = [
        [SCENARIOS[s]]
        + [
            cell
            for name in PLATFORMS
            for cell in (_ci(main[name][s]["primary"]), _count(main[name][s]["primary"]))
        ]
        for s in SCENARIOS
    ]
    methods_rows = []
    for name in PLATFORMS:
        for s in SCENARIOS:
            means = {m: main[name][s]["methods"][m]["rmse"]["mean"] for m in METHODS}
            low = min(means.values())
            methods_rows.append(
                [f"{PLATFORMS[name].split(' · ')[1]} · {SCENARIOS[s]}"]
                + [
                    f'<span class="sig">{v:.4f}</span>' if v <= low else f"{v:.4f}"
                    for v in means.values()
                ]
            )
    cost_rows = []
    ratios = []
    for s in SCENARIOS:
        row = [SCENARIOS[s]]
        for name in PLATFORMS:
            b3 = main[name][s]["methods"]["dp"]["planning_s"]["median"]
            p = main[name][s]["methods"]["p"]["planning_s"]["median"]
            ratios.append(p / b3)
            row += [f"{b3:.1f}", f"{p:.1f}", f"{p / b3:.1f}×"]
        cost_rows.append(row)
    ablation_rows = [
        [VARIANTS[v]]
        + [
            _ci(ablation[name][v]["minus_full_p"][metric])
            for name in PLATFORMS
            for metric in ("rmse", "mean_variance")
        ]
        for v in VARIANTS
    ]

    def beats(pair: str, name: str) -> str:
        # B2 significantly better: the difference (method minus B2) is positive.
        wins = sum(main[name][s]["pairs"][pair]["rmse"]["ci_low"] > 0 for s in SCENARIOS)
        return _of(wins, len(SCENARIOS))

    v2 = main["m7v2"]["combined"]
    straight = data["m7v2"]["analysis"]["straight_line"]
    tied = sum(not _significant(main[name][s]["primary"]) for name in PLATFORMS for s in SCENARIOS)
    sogp = data["m6"]["analysis"]["sogp"]["sogp_32"]["minus_exact"]
    mismatch = data["m6"]["analysis"]["mismatch"]["length_scale_16"]
    mismatch_rmse = [mismatch["minus_matched"][m]["rmse"]["mean"] for m in METHODS]
    return {
        "date": date.today().strftime("%d %B %Y").lstrip("0"),
        "fig": Path("../../reports/figures/m8").as_posix(),
        "tasks": str(main["m6"]["nominal"]["methods"]["dp"]["tasks"]),
        "tied_blocks": str(tied),
        "all_blocks": str(len(PLATFORMS) * len(SCENARIOS)),
        "ratio_range": f"{min(ratios):.1f}–{max(ratios):.0f}",
        "prefixes": f"{sum(data[n]['audits']['m4_recomputed_prefixes'] for n in PLATFORMS):,}",
        "primary_table": _table(
            "Table 1. P − B3 field RMSE, mean [95% interval]; bold intervals exclude zero. "
            "Counts are tasks where P / B3 was better.",
            ["Scenario"] + [h for name in PLATFORMS for h in (PLATFORMS[name], "P / B3 better")],
            primary,
        ),
        "methods_table": _table(
            "Table 2. Mean mission-end field RMSE over 40 tasks; the lowest per block in bold.",
            ["Block"] + [spec["label"] for spec in METHODS.values()],
            methods_rows,
        ),
        "cost_table": _table(
            "Table 3. Median planning time per 90 s mission (s) and the P / B3 ratio.",
            ["Scenario"]
            + [
                h
                for name in PLATFORMS
                for h in (f"B3 · {PLATFORMS[name].split(' · ')[1]}", "P", "P / B3")
            ],
            cost_rows,
        ),
        "ablation_table": _table(
            "Table 4. Variant minus full P on loss + drift, mean [95% interval]; bold "
            "intervals exclude zero.",
            ["Variant"]
            + [
                f"{PLATFORMS[name].split(' · ')[1]} · {label}"
                for name in PLATFORMS
                for label in ("RMSE", "variance")
            ],
            ablation_rows,
        ),
        "b2_b3_m6": beats("dp-adaptive", "m6"),
        "b2_b3_m7": beats("dp-adaptive", "m7v2"),
        "b2_p_m6": beats("p-adaptive", "m6"),
        "b2_p_m7": beats("p-adaptive", "m7v2"),
        "rollout_identical_m6": str(ablation["m6"]["p_no_rollout"]["identical_to_full_p"]),
        "rollout_identical_m7": str(ablation["m7v2"]["p_no_rollout"]["identical_to_full_p"]),
        "arrival_ablation": (
            f"{ablation['m7v2']['p_no_rollout']['minus_full_p']['mean_arrival_error_m']['mean']:.1f}"
        ),
        "straight_reached": str(straight["straight"]["methods"]["p"]["target_reached"]),
        "straight_no_rollout_reached": str(
            straight["straight_no_rollout"]["methods"]["p"]["target_reached"]
        ),
        "var_m7_combined": _ci(v2["pairs"]["p-dp"]["mean_variance"], 3),
        "arrival_m7_combined": _ci(v2["pairs"]["p-dp"]["mean_arrival_error_m"], 2),
        "target_p": str(v2["methods"]["p"]["target_reached"]),
        "target_b3": str(v2["methods"]["dp"]["target_reached"]),
        "v1_drift": _ci(main["m7v1"]["drift"]["primary"]),
        "v1_combined": _ci(main["m7v1"]["combined"]["primary"]),
        "stuck_drift": str(stranded["m7v1"]["drift"]["dp"]),
        "stuck_drift_p": str(stranded["m7v1"]["drift"]["p"]),
        "fc_m6_dropout": (
            f"{main['m6']['dropout']['methods']['p']['one_step_forecast_error_mean']['mean']:+.4f}"
        ),
        "fc_m7_combined": (f"{v2['methods']['p']['one_step_forecast_error_mean']['mean']:+.4f}"),
        "sogp_dp": f"{sogp['dp']['rmse']['mean']:+.3f}",
        "sogp_p": f"{sogp['p']['rmse']['mean']:+.3f}",
        "mismatch_range": f"{min(mismatch_rmse):+.3f} to {max(mismatch_rmse):+.3f}",
        "tests": f"{tests:,}",
        "sha_m6": _sha(BATCHES["m6"] / "analysis.json"),
        "sha_m7v1": _sha(BATCHES["m7v1"] / "analysis.json"),
        "sha_m7v2": _sha(BATCHES["m7v2"] / "analysis.json"),
    }


def _sha(path: Path) -> str:
    return f"<code>{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}</code>"


def print_pdf(html: Path, pdf: Path) -> None:
    browser = next((path for path in BROWSERS if path.is_file()), None)
    if browser is None:
        found = shutil.which("chrome") or shutil.which("msedge")
        browser = Path(found) if found else None
    if browser is None:
        raise SystemExit("no Chrome or Edge found; open the HTML and print it to PDF by hand")
    subprocess.run(
        [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf}",
            html.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--tests", type=int, default=None, help="skip counting the tests")
    args = parser.parse_args()
    if not (FIGURES / "stopped_robots.json").is_file():
        raise SystemExit("run scripts/figures_m8.py first")
    template = Template((NOTE_DIR / "note_template.html").read_text(encoding="utf-8"))
    text = template.substitute(values(args.tests or _test_count()))
    html = NOTE_DIR / "technical_note.html"
    html.write_bytes(text.encode("utf-8"))
    print(html.relative_to(ROOT).as_posix())
    if not args.no_pdf:
        pdf = NOTE_DIR / "FIELDWORK_technical_note.pdf"
        print_pdf(html, pdf)
        pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
        print(f"{pdf.relative_to(ROOT).as_posix()} · {pages} pages")


if __name__ == "__main__":
    main()
