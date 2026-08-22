# AGENTS.md — Project Rules for Agrihand

Working rules for AI agents (and humans) on this repo. `PLAN.md` is the canonical plan; this file is the *how-to-work-here* contract. Read `PLAN.md`, `docs/findings.md`, and `docs/strategy.md` before changing strategy logic.

## The goal

Autonomous heuristic agent for Kaggle's **Kaggriculture** simulation competition: two-player farming sim, 720 turns (30 days × 24 hours), winner = more banked coins, Elo-style ladder (only win/loss/tie affects rating). Solo project; rule-based policy evaluated locally with a seeded tournament harness before every submission.

## Ground rules (non-negotiable)

1. **Stdlib-only in the submission.** `main.py` + `config.py` ship in a `submission.tar.gz` with `main.py` at root. No pip installs at runtime (host: 6.5 GB RAM, 1.6 vCPU, 100 MiB limit, **no network ingress/egress**). Every import must resolve from stdlib or `/kaggle_simulations/agent/`.
2. **No new dependency unless it earns its place.** Dev-only deps are `kaggle-environments` (pin 1.32.x) and `kaggle` CLI, on **Python 3.12** (`python3.12 -m venv .venv`). Host Python 3.14 is ahead of sim deps — never use system python for the harness.
3. **Win/loss-first (TICKET-08).** Promote on win rate only (Wilson 95% CI lower bound > 0.50, TICKET-01). Margin is diagnostic, never a promotion criterion. A defensive agent that wins by $1 outranks a volatile one.
4. **Every non-trivial change leaves one runnable check.** `eval/smoke.py --fast` on every change; `--full` before promotion/submission. `eval/check_findings.py` runs first in both tiers (TICKET-10).
5. **No bare numeric literals in decision logic.** All tunable thresholds live in `config.py` (TICKET-06), each with a comment linking to its PLAN.md section. `main.py` and `eval/tournament.py` import it.
6. **Study, don't copy.** The public MIT-licensed Seyamalam/Kaggriculture repo is a reference + tournament opponent only. Write our own agent. Attribution in README.
7. **`docs/findings.md` is ground truth — no guesses.** Mechanics must be verified against the installed engine source (`kaggle_environments/envs/kaggriculture/kaggriculture.py`) with an assert-based micro-test before any policy relies on it. A row whose Answer is still `___` must not be depended on (enforced by `eval/check_findings.py`).
8. **Engine is authoritative over the rules doc (TICKET-14).** When live engine behavior contradicts the public rules doc, the engine wins — log the discrepancy on the findings row, never silently.
9. **Pre-submit compliance (hard gate).** `main.py` at tar.gz root; zero network calls in the submission; imports resolve from stdlib or `/kaggle_simulations/agent/`; size < 100 MiB.
10. **Track both active bots.** Only the latest 2 submissions are live; the leaderboard shows only the best-scoring one. After each submission, check the Submissions page for **both** active bots' episodes.

## Repo layout (see PLAN.md §2 for full map)

- `main.py` — submission entry `agent(obs)`, stdlib-only, imports `config.py`
- `config.py` — ALL tunable constants, single source of truth, ships in bundle
- `agents/` — frozen candidates + baselines, immutable once archived
- `demo/` — visualizer/discuss-mode tooling (serve_demo.py, annotate_replay.py, demo_hustler.py); NOT part of the submission, not gated by eval/
- `eval/` — `smoke.py` (two-tier gate), `check_findings.py` (hard gate), `micro_tests.py` (M1–M10 mechanics), `tournament.py` (Wilson CI, TICKET-01)
- `scripts/` — `setup.sh` (venv + deps), `submit.sh` (archive + tar.gz + submit)
- `reports/` — tournament/smoke outputs + benchmarks (git-committed)
- `docs/` — `findings.md` (mechanics), `strategy.md` (policy rationale), `plan.md` (dated experiment log), `rules-notes.md` (competition rules capture)

## Engine gotchas (learned the hard way — read before touching strategy)

- **Plant tiles do NOT carry `first_yield_day`/`max_yield_day` in obs.** Look them up by `crop` name from the CROPS table. Harvest before `first_yield_day` is silently rejected by the engine — the agent must never offer HARVEST to an immature plant or it will sit there spamming a no-op forever.
- **PLANT requires an empty tile (`tile is None`) and consumes seed directly from `private["seeds"]`** — no PICKUP needed. Seeds never pass through farmer inventory.
- **HARVEST goes to the unit's inventory**, then must be DROPPED at the shed before it reaches the shed; SELL reads the shed. Ongoing crops (tomato/strawberry) yield repeatedly after `first_yield_day`; non-ongoing (wheat/carrot/melon) have a single yield window.
- **HIRE cost is fibonacci**: 1st hand $1, 2nd $1, 3rd $2, 4th $3… (`cost = fib(hires_today)` before the hire; obs `hires_today` is post-hire).
- **Land order is pinned NE → SW → SE** at $1k/$2k/$4k. The first hired hand spawns at (5,4), which sits in the NE quadrant — buying NE early means the spawn lands on owned land.
- **30s-class truncation analog (audio project, not here):** N/A — but for the sim, note the 720-turn cap and that unsold inventory has zero terminal value.
- **The market has a shared inventory** — your glut depresses the price of what *you* sell too. Premium goods crash to the $1 floor on oversupply; wheat absorbs gluts.

## Demo/visualizer (discuss mode) — lives in `demo/`, isolated from the competition pipeline

`demo/serve_demo.py` serves a full 720-turn match with subtitle captions. It is **not** part of the submission, is not gated by `eval/smoke.py`, and does not touch `main.py`/`config.py`:
- The bundled visualizer **does not self-play standalone** — the overlay acts as the playback controller: a self-rescheduling `setTimeout` posts `{step:N}` to the board, with play/pause, a speed selector (0.25×–4×), and a scrub slider. Captions render from the same `step` in lockstep.
- `demo/annotate_replay.py` converts each step's actions into plain-language captions (all ops + entities, phrased per engine rules). Captions are built from actual actions, never invented.
- `demo/demo_hustler.py` is the demo player agent (hires hands, buys animals, etc.) — NOT a candidate, never archived in `agents/`.
- The server runs as a child of the shell — it stops when the session ends. Restart with `.venv/bin/python demo/serve_demo.py --steps 720 --port 8000`.

## Experiment log

Every promotion/rejection decision gets a dated row in `docs/plan.md`: candidate hash, opponent, game count, win rate, Wilson CI, decision. `docs/plan.md` is the running record — append, never rewrite.
