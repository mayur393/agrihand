# Agrihand — Kaggriculture Competition Agent

Autonomous heuristic agent for Kaggle's Kaggriculture simulation competition (two-player farming sim, 720 turns, winner = most banked coins, Elo-style ladder). Solo project: rule-based policy, stdlib-only submission bundle, evaluated locally with a seeded tournament harness before every submission. Strategy lives in `PLAN.md`; the running experiment log is `docs/plan.md`; mechanics and timings are verified in `docs/findings.md`.

**Attribution:** this project *studies* public competition code and documentation but writes its own agent. The public MIT-licensed [Seyamalam/Kaggriculture](https://github.com/Seyamalam/Kaggriculture) repo (docs + harness) is used as a reference for mechanics and as a tournament opponent only — its `main.py` is never copied into our submission. Our own baseline starts from `~/Downloads/main.py` and is ported into `main.py` with all literals extracted to `config.py` (TICKET-06).

## Quickstart

```bash
# Dev-only deps (NOT shipped in the submission bundle)
scripts/setup.sh                # py3.12 venv + kaggle-environments 1.32.x + kaggle CLI
source .venv/bin/activate

# Gates
python eval/smoke.py --fast     # every non-trivial change
python eval/smoke.py --full     # before promotion/submission
python eval/tournament.py       # Wilson-CI promotion decision (TICKET-01)

# Submit
scripts/submit.sh               # archives agents/vN_*, bundles submission.tar.gz, submits
```

## Repo layout

See `PLAN.md` §2. Short version: `main.py` + `config.py` ship in the submission bundle; `agents/` archives frozen candidates; `eval/` has the gates; `scripts/` has setup/submit; `reports/` + `docs/` hold outputs and rationale.

## Archived candidates

| Version | Files | sha256 (main) | Changelog |
|---|---|---|---|
| v1_wheat_loop | `agents/v1_wheat_loop.{py,cfg}` | `6f66a1b2…3887` | RM-012 promoted vs starter: 160/0, CI [0.977, 1.000]. NW-field wheat/carrot loop, shed-room-aware harvest (M7), floor-aware selling, no land buying. |
