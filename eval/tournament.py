#!/usr/bin/env python3
"""eval/tournament.py — paired, seeded, slot-swapped tournament runner (RM-006).

Promotion decision (TICKET-01): sequential Wilson-score rule. Promote only when
the lower bound of the 95% Wilson CI on win rate clears 0.50; reject early
(futility) when the upper bound is below 0.50. Margin is diagnostic only.

Pairing: for each seed, the candidate plays player 0 once and player 1 once
against the same opponent, so board-position asymmetry cancels. The engine
seed is passed via configuration["seed"] and resolved by
resolve_episode_seed() into env.info["seed"], which seeds the demand RNG
(line 858 of the env source: random.Random((seed*1_000_003) ^ day)) — engine
state is reproducible per seed. Caveat (verified 2026-08-12): the built-in
`random` opponent uses an unseeded random.Random() per step, so `random` adds
its own entropy; `pass` and `starter` are deterministic. Candidate/opponent
may be a builtin name or a path to a Python file exposing agent(obs).

Usage:
    python eval/tournament.py --candidate main.py --opponent starter \
        --games 40 --seed 1
    python eval/tournament.py --candidate main.py --opponent agents/v1.py \
        --games 100 --seed 42 --episode-steps 720
Exit code: 0 = promotable (CI lower bound > 0.50), 2 = rejected
(CI upper bound < 0.50), 1 = inconclusive (ambiguous).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from kaggle_environments import make  # dev-only dep, not shipped

ROOT = Path(__file__).resolve().parent.parent
BUILTINS = ("pass", "random", "starter")


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval (lower, upper) on win rate."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def promotion_decision(wins: int, n: int) -> tuple[str, float, float]:
    """TICKET-01: promote when CI LB > 0.50; reject when CI UB < 0.50; else inconclusive."""
    lb, ub = wilson_ci(wins, n)
    if lb > 0.50:
        verdict = "PROMOTE"
    elif ub < 0.50:
        verdict = "REJECT"
    else:
        verdict = "INCONCLUSIVE"
    return verdict, lb, ub


def resolve_agent(name: str, cwd: Path):
    """Return a callable agent from a builtin name or a path to a module with agent(obs)."""
    if name in BUILTINS:
        return name  # kaggle_environments resolves builtins by string
    path = Path(name)
    if not path.is_absolute():
        path = cwd / path
    if not path.exists():
        raise SystemExit(f"agent not found: {name} (tried {path})")
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "agent"):
        raise SystemExit(f"{path}: no agent(obs) function found")
    return mod.agent


def run_paired(
    candidate,
    opponent,
    games: int,
    seed: int,
    episode_steps: int,
    cwd: Path,
) -> tuple[int, int, int]:
    """Play `games` paired episodes (candidate in both seats), return (wins, losses, ties)."""
    wins = losses = ties = 0
    for g in range(games):
        ep_seed = seed + g  # one seed per paired episode; both seats share it
        for seat in (0, 1):
            agents = [candidate, opponent] if seat == 0 else [opponent, candidate]
            env = make(
                "kaggriculture",
                configuration={"episodeSteps": episode_steps, "seed": ep_seed},
                debug=True,
            )
            env.run(agents)
            final = env.steps[-1]
            # compare candidate's seat (0 in seat 0, 1 in seat 1) vs the other
            cand_idx = 0 if seat == 0 else 1
            opp_idx = 1 - cand_idx
            c_money = final[cand_idx].observation["farms"][cand_idx]["money"]
            o_money = final[opp_idx].observation["farms"][opp_idx]["money"]
            if c_money > o_money:
                wins += 1
            elif c_money < o_money:
                losses += 1
            else:
                ties += 1
    return wins, losses, ties


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=720)
    args = ap.parse_args()

    cwd = ROOT
    candidate = resolve_agent(args.candidate, cwd)
    opponent = resolve_agent(args.opponent, cwd)

    wins, losses, ties = run_paired(
        candidate, opponent, args.games, args.seed, args.episode_steps, cwd
    )
    n = wins + losses + ties
    win_rate = wins / n if n else 0.0
    lb, ub = wilson_ci(wins, n)
    verdict, vlb, vub = promotion_decision(wins, n)

    print(f"candidate: {args.candidate}")
    print(f"opponent:  {args.opponent}")
    print(f"games:     {args.games} paired (candidate both seats) | seed: {args.seed} | steps: {args.episode_steps}")
    print(f"W/L/T:     {wins}/{losses}/{ties}")
    print(f"win rate:  {win_rate:.3f}")
    print(f"Wilson 95% CI: [{lb:.3f}, {ub:.3f}]")
    print(f"decision:  {verdict} (promote iff LB > 0.50; reject iff UB < 0.50)")
    print(f"mean margin diagnostic: {abs(wins - losses) / n:.2f} wins-vs-losses share")

    return 0 if verdict == "PROMOTE" else (2 if verdict == "REJECT" else 1)


if __name__ == "__main__":
    sys.exit(main())
