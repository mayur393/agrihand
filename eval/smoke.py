"""Two-tier smoke gate for agrihand (TICKET-02, TICKET-10).

Usage:
    python eval/smoke.py --fast      # 3 episodes x 3 opponents @ 200 steps — on every non-trivial change
    python eval/smoke.py --full      # 50 episodes x 3 opponents @ 720 steps — before promotion/submission
    python eval/smoke.py --animals   # RM-020 gate: 50 animal-enabled episodes, zero escapes

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
ANIMALS_EPISODES = 50


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


def _escape_events(steps) -> list[tuple[int, int, str]]:
    """Detect animal escapes across an episode's recorded steps.

    An escape is a tile that held an animal in step N but no longer holds one in
    step N+1, with the same (x, y) now holding the structure only. The engine
    does exactly this on the second consecutive unfed daily refresh.
    """
    events: list[tuple[int, int, str]] = []
    prev: dict[tuple[int, int], str] = {}
    for st in steps:
        farm = st[0].observation["farms"][0]
        cur: dict[tuple[int, int], str] = {}
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                if isinstance(t, dict) and "animal" in t:
                    cur[(x, y)] = t["animal"]
        for pos, animal in prev.items():
            if pos not in cur:
                events.append((pos[0], pos[1], animal))
        prev = cur
    return events


def _run_animals_gate() -> int:
    """RM-020 hard gate: zero animal escapes across 50 animal-enabled episodes.

    Runs main.py's agent (called with the engine's own (obs, configuration)
    arguments) vs `pass` and fails loudly on any escape or non-clean episode.
    An earlier version wrapped the agent in a lambda whose 2nd parameter caught
    the configuration, so the agent crashed on turn 1 of every episode and the
    gate reported "0 escapes" without ever running an animal.
    """
    import importlib.util

    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("main", ROOT / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    escapes = 0
    failures = 0
    for ep in range(ANIMALS_EPISODES):
        env = kaggle_environments.make(
            "kaggriculture",
            configuration={"episodeSteps": 720, "seed": ep + 1},
            debug=False,
        )
        env.run([mod.agent, "pass"])  # engine passes (obs, configuration)
        events = _escape_events(env.steps)
        if events:
            escapes += 1
            for x, y, animal in events:
                print(f"[animals] ep {ep + 1}: ESCAPE {animal} at ({x},{y})")
        if any(s.status != "DONE" for s in env.steps[-1]):
            failures += 1
            print(f"[animals] ep {ep + 1}: episode not clean DONE")
    print(f"[smoke animals] {ANIMALS_EPISODES} episodes, {escapes} escapes, {failures} failures.")
    return 1 if (escapes or failures) else 0


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
    ap.add_argument("--animals", action="store_true", help="RM-020 animal-escape gate (50 episodes)")
    args = ap.parse_args()
    if not (args.fast or args.full or args.animals):
        ap.error("pass --fast, --full, or --animals")

    _run_findings_gate()
    if args.animals:
        return _run_animals_gate()
    tier = "fast" if args.fast else "full"
    return _run_tier(tier)


if __name__ == "__main__":
    sys.exit(main())
