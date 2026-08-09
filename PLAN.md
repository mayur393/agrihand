# Agrihand — Kaggriculture Competition Plan

## 1. Goal

Build and submit agents for Kaggle's **Kaggriculture** simulation competition (two-player farming sim, 720 turns, winner = most banked coins; Elo-style ladder, only win/loss/tie affects rating). Solo project, heuristic + rule-based policy, evaluated locally with a seeded tournament harness before every submission.

**Ladder reality that shapes everything:** rating only cares about win/loss/tie, only the latest 2 submissions are active, and 5 submissions/day max. So we need *measurably-better variants* and *safe cadence*, not one perfect bot.

**Win/loss-first principle (TICKET-08):** *Prioritize reliably beating whoever we're matched against over maximizing absolute coin margin — a defensive agent that wins by $1 outranks a volatile one that sometimes wins big and sometimes collapses.* Every tuning decision is checked against this: promotion uses win rate only (margin is diagnostic, never a promotion criterion), and no "maximize coins" framing is used for strategy choices. See `docs/strategy.md` for the cross-check of existing rules against this principle.

**Ground rules (from AGENTS.md):**
- No new dependency unless it earns its place. Agent runs **stdlib-only** (Kaggle sim hosts: 6.5 GB RAM, 1.6 vCPU, 100 MiB limit — no pip installs at runtime).
- Submission is a **tar.gz bundle** (`main.py` + `config.py` at root — the spec explicitly allows multi-file agents; both files stdlib-only).
- Dev-only deps: `kaggle-environments` (1.32.x) and `kaggle` CLI, on **Python 3.12** (host Python 3.14 is ahead of sim deps).
- Every non-trivial change leaves one runnable check: the smoke gate (`eval/smoke.py --fast` or `--full`) must pass before any candidate is promoted.
- Study the public MIT-licensed Seyamalam/Kaggriculture repo (docs + harness) for mechanics; **write our own agent code**. Its `main.py` (V21, ~2053 rating) can be used as a *tournament opponent only* — that is standard practice for public code, and attribution goes in the README.

## 2. Repo layout (`/home/mayur/agrihand`)

```
agrihand/
├── README.md                  # what/why, attribution, quickstart, config.py purpose (TICKET-06)
├── main.py                    # THE submission entry: agent(obs), stdlib-only, imports config.py
├── config.py                  # ALL tunable strategy constants (TICKET-06) — single source of truth, ships in bundle
├── agents/                    # frozen candidates + baselines (each submitted variant archived here)
│   ├── v1_wheat_loop.py       # first working baseline (starts from Downloads/main.py logic)
│   └── ...                    # v2, v3... every submitted/considered variant, immutable once archived
├── eval/
│   ├── smoke.py               # two-tier gate (TICKET-02): --fast on every change, --full before promotion
│   ├── tournament.py          # seeded paired tournament; reports win rate + Wilson 95% CI (TICKET-01)
│   ├── micro_tests.py         # assert-based mechanic verifications (TICKET-03/07 items live here)
│   └── replay_bench.py        # optional: benchmark vs downloaded leaderboard replays (open-loop)
├── scripts/
│   ├── setup.sh               # py3.12 venv + pip install kaggle-environments kaggle
│   └── submit.sh              # archive current main.py+config.py to agents/, tar.gz, kaggle submit, poll status
├── reports/                   # tournament/smoke outputs + benchmark logs (git-committed)
└── docs/
    ├── findings.md            # mechanic verifications, timing benchmarks, timeout research (TICKET-02/03/07)
    ├── strategy.md            # policy decisions + rationale (TICKET-04/05/06/08)
    ├── rules-notes.md         # Rules/Terms capture from the live competition page (disqualification terms, gap #1)
    └── plan.md                # DATED EXPERIMENT LOG: every promotion decision, candidate hash, CI result
```

`PLAN.md` (this file) is the canonical plan. `docs/plan.md` is the running experiment log — every promotion/rejection decision gets a dated row there recording candidate hash, opponent, game count, win rate, and CI (TICKET-01).

## 3. Agent design (heuristic + rule-based)

### 3.1 Observation handling
- Parse `obs`: `farms[player]` (money, tiles, farmer [x,y], hands, unlocked_quadrants, hires_today), `market` (inventory, prices), `town.unlocked_shops`, `private` (shed, seeds, inventories).
- Compute `step = day*turnsPerDay + hour` (spec's `step` key is not in the official obs format — derive it).
- **No bare numeric literals in decision logic** (TICKET-06): all tunable thresholds live in `config.py` (Section 3.6). `main.py` and `eval/tournament.py` import it.

### 3.2 Per-turn decision loop
1. **Market orders** (up to 10/turn, free of the movement action): buy seeds/fertilizer/animals per budget, HIRE hands per plan, BUY_LAND per plan, SELL per sale policy (see 3.4).
2. **Task assignment** for farmer + hired hands: build a priority queue of tile tasks —
   `WATER` (unwatered plants) / `FEED` (unfed animals) > `HARVEST` (ready yield) > `COLLECT_FERTILIZER` > `CARE` > `DIG` (weeds) > `PLANT` (empty tile + seed) > `PLACE` (animal onto structure) > shed logistics (`DROP`/`PICKUP`).
   Each unit picks the nearest task via BFS over the board (LOCKED tiles are passable), moves until adjacent/on target, then acts. Movement no-ops off-board.
3. **Fallback:** if no tasks, `PASS` (or restock seeds near shed).

### 3.3 Strategy phases (day-based, tuned empirically)
- **Days 0–3 — setup:** plant wheat + carrot loop near shed; water/harvest religiously; sell staples in small batches. Rule: never sell below a per-crop floor price you compute from the curve.
- **Days 4–12 — scale:** buy the **NE** quadrant ($1k) then **SW** ($2k) when cash allows with a reserve buffer (`CASH_RESERVE_BUFFER`, default 300) — **land order is pinned NE→SW→SE** (verified from the competition page; Q4 is always SE, see `docs/strategy.md`). Buying NE first also unlocks the first-hired-hand spawn tile (5,4), which sits in NE. Hire 1–2 hands when standing-task count > farmer can service alone. Add tomatoes (no replant labor, ongoing) and time a melon wave to harvest days ~20–24 when town demand has drained melons.
- **Quadrant #4 policy — explicit (TICKET-04):** buy only if `day <= QUADRANT4_LATEST_DAY (16)` AND `money >= QUADRANT4_CASH_THRESHOLD (6000)` AND post-purchase money still `>= QUADRANT4_RESERVE (1000)`. Reasoning: $4k cost vs. remaining season; a melon wave bought by day 16 harvests day ~27–30, but 25 tiles of premium glut will crash the price, and ~25 daily water-actions require 2–3 units of labor — payback only clears under the cash-and-time conditions above. Full ROI write-up in `docs/strategy.md`.
- **Days 8–20 — animals:** geese first (cheap, daily eggs, 1.00 Y/t/d), then cows, then sheep as wheat buffer allows. Hard rule: **keep wheat buffer ≥ (`WHEAT_BUFFER_PER_ANIMAL` (2) × animals) + `WHEAT_BUFFER_BASE` (5)**; if buffer breaks, sell nothing and stop buying. CARE + COLLECT_FERTILIZER daily (fertilizer sells ~100 or boosts crops).
- **Days 21–30 — harvest & liquidate:** harvest everything, convert inventory to cash (unsold inventory counts for nothing). Sell into demand ticks (see 3.4). No new planting after day ~24 except fast wheat if wheat price spikes.

### 3.4 Market / sale policy (the actual differentiator)
- **Premium goods (strawberry, melon, milk, wool) have `above_target > 1` → glut crashes them to the $1 floor.** Never dump in quantity. Sell small batches **the first turn after a town-consumption tick** (town center every 12 turns; shops every 4 turns; demand grows as shops unlock) — that's when inventory is lowest and price highest.
- **Staples (wheat, carrot, egg):** wheat absorbs gluts (`above log 0.2`) but panics on scarcity (`sqrt 0.8`); carrot is the inverse. Sell wheat/carrots steadily; keep a wheat buffer for feeding.
- **BUY_PRODUCT:** only WHEAT (feed) and FERTILIZER (buy when price < ~120 and it's melon/tomato season). Never buy back anything else (net-zero trap).
- **Opponent-aware premium sale timing — STRETCH GOAL (TICKET-05):** track opponent's visible premium-crop counts + `yield_units` and sell our premium stock just before their big harvest lands. **Scoped to Aug 25–Sep 10 only. Behind `OPPONENT_AWARE_SELL_TIMING = False` in config.py, default OFF.** The core loop (first two bullets + task assignment) must pass smoke + tournament gates with the flag off — this feature is a bolt-on, never a dependency of v1/v2 readiness. Noise caveat: visible `yield_units` shows what's harvestable, not when the opponent will actually harvest or sell — documented in `docs/strategy.md` so tuning never over-trusts the signal.

### 3.5 Known simplifications + compute budget (TICKET-03)
- Task assignment is greedy per-turn BFS, not a global schedule — fine up to ~25 units; upgrade path = time-expanded assignment if hands > 12.
- No RL, no lookahead search (1.6 vCPU/turn budget; heuristic ceiling is documented, upgrade path = offline self-play policy trained in dev, never at runtime).
- **Per-turn compute guardrails:** cap BFS search radius (`BFS_MAX_STEPS`, default 16 = half-board), cache the shed path and nearest-target search across turns, and keep worst-case per-turn work < ~100 ms locally. Exact host timeout (if any) is verified during setup (Section 7, TICKET-03) and logged in `docs/findings.md`; if a limit exists and we're close, the fallback is smaller radius + task queue truncation.

### 3.6 config.py — single source of truth for tuning (TICKET-06)
All tunable values as named constants with comments linking to the plan section that justifies them:
`CASH_RESERVE_BUFFER`, `WHEAT_BUFFER_BASE`, `WHEAT_BUFFER_PER_ANIMAL`, `QUADRANT4_LATEST_DAY`, `QUADRANT4_CASH_THRESHOLD`, `QUADRANT4_RESERVE`, **`QUADRANT4_CROP` (`"MELON"` — committed default per TICKET-16)**, `HIRE_THRESHOLD_TASKS`, `SELL_WINDOW_TICKS`, `FERTILIZER_BUY_MAX_PRICE`, `BFS_MAX_STEPS`, `OPPONENT_AWARE_SELL_TIMING`, seed costs, land costs, price-curve constants — plus everything currently hardcoded in `agents/v1_wheat_loop.py` (migrated as part of v1 cleanup).
Both `main.py` and `eval/tournament.py` import it, so parameter sweeps vary one file. Ships in the submission bundle (stdlib-only). Documented in README + `docs/strategy.md`.

## 4. Eval harness (the gate before every submission)

### 4.1 Two-tier gate (TICKET-02)
- **Fast gate** — `eval/smoke.py --fast`: 3 episodes × 3 opponents (`pass`, `random`, `starter`) at `episodeSteps=200`, target < ~30 s. Run on **every non-trivial change** (catches exceptions + gross errors in the first ~8 days: setup, first harvest, shed flow).
- **Full gate** — `eval/smoke.py --full`: 50 episodes × 3 opponents at 720 turns, target < ~10 min. Run **only before promotion/submission**.
- Single-episode wall-clock benchmark logged in `docs/findings.md` during setup (TICKET-02); tier runtimes documented there as the numbers land.

### 4.2 Promotion rule — CI-based, not fixed-count (TICKET-01)
Replace the old "≥55% over 40+ paired games" rule (wide CI at n=40 — a coinflip can clear it, a real marginal edge can fail it) with a sequential Wilson-score rule:
- **Evaluate after every 20 paired games; floor of 30 games before any decision; hard cap 150 games.**
- **Promote** when the **lower bound** of the Wilson 95% CI on win rate **> 0.50**.
- **Reject early (futility stop)** when the Wilson **upper bound < 0.50** (not better than coinflip — stop burning compute).
- At the 150-game cap: promote only if LB > 0.50, else reject.

Worked examples (z=1.96):
- 22/40 (55%) → LB ≈ 0.40 → **not promotable** (old rule would have passed this — that's the bug).
- 30/40 (75%) → LB ≈ 0.60 → promotable.
- 60/100 (60%) → LB ≈ 0.50 → borderline; a genuine 60% edge typically needs ~110–130 games. This is the intended cost of requiring real evidence for a small edge.

`eval/tournament.py` output includes win rate + Wilson CI (+ mean margin as a diagnostic only — never a promotion criterion, per TICKET-08). Paired games are slot-swapped (candidate plays both seats) to cancel seat effects. Every decision gets a dated row in `docs/plan.md` with candidate hash, opponent, games, win rate, CI.

## 5. Submission ops & cadence (solo)

- **Accept the rules + join the competition on Kaggle in week 1** (must be done before Sep 23 — do it immediately, it costs nothing).
- `kaggle competitions download kaggriculture -p data/raw` once, early (replays + starter data).
- Cadence: nothing submitted until the agent is full-gate-clean vs `starter` and beats it in tournament. Then ≤ 1–2 submissions/day, mostly in the final 3 weeks. Reserve the 5/day cap for the last tuning week. Only latest 2 are live — **we pick the 2 best variants deliberately**, not by accident. The leaderboard shows only the best-scoring bot, so after each submission also check the Submissions page for **both** active bots' episodes — a regression on the second active bot is easy to miss otherwise.
- `scripts/submit.sh` archives current `main.py` + `config.py` → `agents/vN_<desc>.{py,cfg}` (with sha256 + changelog in README table), bundles both into `submission.tar.gz` with `main.py` at root (the near-term default per TICKET-13 — always both files, never single-file), submits, then polls status. The leaderboard's "best-scoring bot" maps back to a known archived candidate.
- Post-submit loop: `kaggle competitions submissions kaggriculture` → on errors `kaggle competitions logs <id> 0` → fix, re-gate locally, resubmit.

## 6. Timeline (solo, mapped to competition dates)

| When | Milestone |
|---|---|
| Jul 29 – Aug 10 | Setup: `scripts/setup.sh`, harness, smoke gate, **single-episode benchmark + host timeout research (TICKET-02/03)**. Accept rules + join on Kaggle; **read + store the competition Rules/Terms page (`kaggle.com/competitions/kaggriculture/rules`) → `docs/rules-notes.md`** (disqualification terms, e.g. the no-network/requirements clause). Download competition data. Read installed `kaggriculture` env source + public repo docs → fill `docs/findings.md` (mechanics incl. mid-day inventory cap, TICKET-07; timeout value, TICKET-03). Extract `config.py` (TICKET-06). Ship v1 wheat/carrot loop that beats `starter` locally. |
| Aug 10 – Aug 25 | Scale logic: expansion, hands, crop mix; sale-timing rules; geese. Gate vs `starter`/`random` + self-play via CI rule (TICKET-01). First submission only if full-gate clean and tournament-green. |
| Aug 25 – Sep 10 | Cows/sheep + care/fertilizer. **Stretch window: opponent-aware premium sale timing (TICKET-05), validated independently with its flag ON vs OFF before ever being considered for promotion.** Weekly cadence of 1–2 submitted variants; track leaderboard, download replays of our own episodes for analysis. |
| Sep 10 – Sep 22 | Freeze window: full-gate stress (≥ 200 episodes across seeds), tournament vs full `agents/` pool, pick the **2 live candidates**, final submissions done by **Sep 22** (1-day buffer before entry deadline). |
| Sep 23 | Entry + team-merger deadline (N/A for solo; rules already accepted). No risky changes. |
| Sep 30 | Final submission deadline. Submissions locked; games run through ~Oct 15. |
| Oct 1–15 | Monitor episodes, no changes possible; only verify + log. |

## 7. Risk register

| Risk | Mitigation | Status |
|---|---|---|
| **Mechanic unknowns** (FEED wheat source; HARVEST→inventory→DROP→SELL flow; BUY_ANIMAL→shed; PLANT all-or-nothing simultaneous-seed consumption; decay/weed timing; end-of-day auto-drop overflow; first-hire spawn at (5,4) on locked NE) | Verify each by reading the env source; one assert-based micro-test per item in `eval/micro_tests.py` before the policy relies on it; log in `docs/findings.md` | Pending |
| **Mid-day carried-inventory cap (TICKET-07)** | Spec says "stockpiling on farmer/hand inventories does not bypass the cap" → a cap almost certainly exists. Pin the exact value in the env source + micro-test; log in `docs/findings.md`. If cap < shed capacity, add shed-run (`DROP`) tasks to the task priority so heavy harvesters cycle back mid-day | Pending |
| **Per-turn compute limit on host (TICKET-03)** | Search `kaggle_environments` source + Kaggle docs for the per-step timeout during setup; log exact value (or "no explicit timeout found, verified via X") in `docs/findings.md`. Benchmark worst-case BFS turn locally (max hands, fully unlocked 10×10); keep < ~100 ms. Fallbacks: `BFS_MAX_STEPS` radius cap, path caching, task-queue truncation | Pending |
| **Smoke/tournament gate too slow to use (TICKET-02)** | Two-tier gate (fast on every change, full before promotion); single-episode benchmark logged in `docs/findings.md` | Pending |
| Engine version drift (competition updates `kaggle-environments`) | Pin 1.32.x locally; re-run fast gate after every upgrade | Active |
| Solo bandwidth | Phase gates in Section 6; heuristic scope (no RL) keeps progress steady and attributable | Active |
| Sell/price misexecution (floor trap at $1; net-zero buy-sell trap) | Sale-policy rules in 3.4 + dedicated price-function unit check in `eval/micro_tests.py` | Pending |
| Feature creep from stretch goal (TICKET-05) | Opponent-aware timing behind `OPPONENT_AWARE_SELL_TIMING=False`, default off, date-scoped; core loop never depends on it | Active |

## 8. Verification

1. `eval/smoke.py --fast` → 3 × 3 episodes at 200 steps, zero exceptions (**mandatory on every non-trivial change**).
2. `eval/smoke.py --full` → 50 × 3 episodes at 720 steps, zero exceptions, zero invalid-action episodes (**mandatory before promotion**).
3. `eval/tournament.py --candidate main.py --opponent starter --paired` → Wilson 95% CI on win rate; promote only when LB > 0.50 per Section 4.2.
4. Same vs `agents/` pool + self-play (slot-swapped) before promoting a variant.
5. Local submit dry-run: `python -c "from kaggle_environments import make; env=make('kaggriculture',debug=True); env.run(['main.py','random']); print([(i,s.reward) for i,s in enumerate(env.steps[-1])])"`.
6. Post-submission: `kaggle competitions submissions kaggriculture`, `kaggle competitions episodes <id> -v`, `kaggle competitions logs <id> 0` on errors, `kaggle competitions leaderboard kaggriculture -s` for rating tracking.
7. Final scorecard: leaderboard position after convergence (~Oct 15) vs our logged expectations in `docs/plan.md`.
8. **Pre-submit compliance check (hard gate, from the competition Rules):** `main.py` at the tar.gz root; **zero network calls in the submission** (episodes have no network ingress/egress — a violating submission is void per the Foundational Rules' requirements clause); all imports resolve from stdlib or `/kaggle_simulations/agent/`.

## 9. First implementation steps (when we exit plan mode)

1. `mkdir /home/mayur/agrihand`, write `README.md`, `config.py` (TICKET-06 skeleton with all constants from Sections 3.3/3.4), `scripts/setup.sh` (py3.12 venv, kaggle-environments, kaggle CLI), confirm `kaggle competitions list -s kaggriculture` works.
2. **Benchmark (TICKET-02):** time one full 720-turn episode locally → log in `docs/findings.md`. **Timeout research (TICKET-03):** search `kaggle_environments` source + Kaggle docs for the per-step timeout → log exact value; benchmark worst-case BFS turn.
3. Unzip `~/Downloads/kaggriculture-agent-main.zip` for reference; port the sample loop into `main.py` as v1 (plant/water/harvest/move), moving its literals into `config.py` (TICKET-06).
4. Write `eval/smoke.py` (two tiers), `eval/tournament.py` (Wilson CI output), `eval/micro_tests.py` (mechanic verifications incl. mid-day inventory cap, TICKET-07). Get v1 green on fast gate vs all three built-ins.
5. Read the installed `kaggriculture` env source + public repo `docs/` → fill `docs/findings.md` + `docs/strategy.md`, then iterate strategy per Section 3, gating every change per Section 4.
