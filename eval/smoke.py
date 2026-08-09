"""Two-tier smoke gate for agrihand (TICKET-02, TICKET-10).

Usage:
    python eval/smoke.py --fast    # 3 episodes x 3 opponents @ 200 steps — on every non-trivial change
    python eval/smoke.py --full    # 50 episodes x 3 opponents @ 720 steps — before promotion/submission

Both tiers run the findings hard-gate (eval/check_findings.py) FIRST — the gate
fails if main.py/config.py depend on a mechanic whose findings.md row is unresolved.

Episode timing budget (TICKET-02): log the real single-episode number in
docs/findings.md §2 during setup; the fast tier targets <~30 s, full <~10 min.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import kaggle_environments  # dev-only dep, not shipped in the submission bundle

ROOT = Path(__file__).resolve().parent.parent
OPPONENTS = ("pass", "random", "starter")
TIERS = {
    "fast": {"episode_steps": 200, "episodes_per_opponent": 3},
    "full": {"episode_steps": 720, "episodes_per_opponent": 50},
}


def _run_findings_gate() -> None:
    """TICKET-10: both tiers must run the hard gate before any episodes."""
    res = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "check_findings.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(res.stdout, end="")
    if res.returncode != 0:
        raise SystemExit("smoke gate aborted: findings hard-gate failed (see above).")


def _run_tier(tier: str) -> int:
    cfg = TIERS[tier]
    failures = 0
    total_episodes = 0
    for opp in OPPONENTS:
        for ep in range(cfg["episodes_per_opponent"]):
            total_episodes += 1
            env = kaggle_environments.make(
                "kaggriculture",
                configuration={"episodeSteps": cfg["episode_steps"]},
                debug=True,
            )
            env.run(["main.py", opp])  # resolve main.py in ROOT; cwd below
            final = env.steps[-1]
            for i, s in enumerate(final):
                if s.status not in ("DONE", "INVALID"):  # INVALID is checked separately below
                    failures += 1
                    print(f"[{tier}] ep {total_episodes} vs {opp}: player {i} status={s.status}")
            # invalid actions / exceptions surface via debug mode logs; count any non-DONE
            if any(s.status != "DONE" for s in final):
                failures += 1
                print(f"[{tier}] ep {total_episodes} vs {opp}: episode not clean DONE")
    print(f"[smoke {tier}] {total_episodes} episodes, {failures} failures.")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="fast tier (every change)")
    ap.add_argument("--full", action="store_true", help="full tier (before promotion)")
    args = ap.parse_args()
    if not (args.fast or args.full):
        ap.error("pass --fast or --full")

    _run_findings_gate()
    tier = "fast" if args.fast else "full"
    return _run_tier(tier)


if __name__ == "__main__":
    sys.exit(main())
