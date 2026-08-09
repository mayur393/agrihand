"""Hard gate: fail if main.py/config.py depend on an unresolved mechanic in docs/findings.md.

TICKET-10. Invoked from eval/smoke.py (both --fast and --full) before any episodes run.

Mechanic registry: mechanic ID -> (keywords that signal reliance, open question).
A row is "resolved" when its Answer column in findings.md is no longer a placeholder.
The keyword map is manually kept in sync with the findings.md §4 table and is a
heuristic (false positives/negatives possible) — a pass is not a safety proof,
it only means no known-unresolved dependency was found.

Usage:
    python eval/check_findings.py [--main main.py] [--config config.py]
Exit code 0 = gate passes (or findings.md missing), 1 = unresolved dependency found.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "docs" / "findings.md"

# mechanic ID -> (keywords whose presence signals reliance, open question)
# Keep in sync with the findings.md §4 table. Keywords are matched as whole
# word-boundary tokens (case-sensitive) so e.g. "HARVEST" doesn't hit "harvested".
MECHANICS: dict[str, tuple[tuple[str, ...], str]] = {
    "M1": (("FEED",), "Does FEED consume from shed or carried inventory?"),
    "M2": (("HARVEST", "DROP", "SELL"), "Harvest->inventory->DROP->SELL flow (SELL reads shed)?"),
    "M3": (("BUY_ANIMAL",), "Does BUY_ANIMAL land the animal in the shed?"),
    "M4": (("PLANT",), "Is PLANT seed consumption all-or-nothing across simultaneous planters?"),
    "M5": (("consecutive_unwatered",), "Exact turn a plant becomes a WEED (seed day counts as first)?"),
    "M6": (("inventories",), "End-of-day auto-drop to shed; overflow discarded?"),
    "M7": (("PICKUP",), "Mid-day carried-inventory cap on farmer/hands (before end-of-day auto-drop)?"),
    "M8": (("HIRE",), "First hired hand spawns at (5,4) on the locked NE quadrant?"),
    "M9a": (("prices",), "Below-target price function reproduces P(I0-T) for all resources?"),
    "M9b": (("prices",), "Above-target price function reproduces P(I0+T)/P(I0+2T) for all resources?"),
    "M10": (("SELL",), "At the $1 floor, is a sold unit still purchased but not added to inventory?"),
}

_UNRESOLVED_RE = re.compile(r"\|\s*M9[ab]?\s*\|[^|]*\|[^|]*\|[^|]*\|\s*`___`", re.IGNORECASE)
# Matches the Answer cell in the table row: after the third pipe, an answer of `___`


def _row_is_resolved(mechanic: str, text: str) -> bool:
    """A row is resolved when its Answer column is no longer a `___` placeholder."""
    lines = text.splitlines()
    for line in lines:
        cells = [c.strip() for c in line.split("|")[1:-1]]  # drop leading/trailing empties
        if len(cells) < 6:
            continue
        # cells: #, Mechanic, Question, Keywords, Answer, Test
        if cells[0].lower() == mechanic.lower():
            return "___" not in cells[4]
    return True  # row absent -> nothing to gate on


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--main", type=Path, default=ROOT / "main.py")
    ap.add_argument("--config", type=Path, default=ROOT / "config.py")
    ap.add_argument("--findings", type=Path, default=FINDINGS)
    args = ap.parse_args()

    findings_text = args.findings.read_text() if args.findings.exists() else ""
    if not findings_text:
        print("[check_findings] docs/findings.md not found — gate skipped (no mechanics tracked).")
        return 0

    targets = [p for p in (args.main, args.config) if p and p.exists()]
    if not targets:
        print("[check_findings] main.py/config.py not found — nothing to scan, gate passes.")
        return 0
    joined = "\n".join(p.read_text(errors="ignore") for p in targets)

    failures: list[str] = []
    for mech, (keywords, question) in MECHANICS.items():
        if _row_is_resolved(mech, findings_text):
            continue  # mechanic verified — no gate
        hits = [kw for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", joined)]
        if hits:
            failures.append(
                f"  {mech}: main.py/config.py references {', '.join(hits)} "
                f"but findings.md row is unresolved. Question: {question}"
            )

    if failures:
        print("[check_findings] FAIL — unresolved mechanic(s) the policy appears to depend on:")
        print("\n".join(failures))
        print("  Resolve the row in docs/findings.md §4 (read the env source, add a micro-test),")
        print("  or remove the dependency from main.py/config.py.")
        return 1

    print("[check_findings] OK — no dependencies on unresolved mechanics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
