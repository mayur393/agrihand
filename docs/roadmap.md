# Agrihand Project Roadmap (v2 — corrected)

Kaggriculture Competition — Professional Engineering Ticket Breakdown

NOTE ON TICKET IDs: This roadmap uses RM-001..RM-034 (Roadmap) to avoid
colliding with TICKET-01..TICKET-16, which already have real history in
PLAN.md / findings.md / strategy.md. Roadmap tickets and doc tickets are
two separate reference systems — cross-reference by description, not by
assuming shared numbering.

## EPIC 0 — FOUNDATION

### RM-001 — Initialize Repo Skeleton
- Create agrihand/ folder structure (agents/, eval/, scripts/, reports/, docs/)
- git init + initial commit
- README with attribution note (public repos studied, not copied)
- Stop Point: Structure Review
- STATUS: DONE

### RM-002 — Configure Development Environment
- Python 3.12 venv, pip install kaggle-environments + kaggle CLI
- Verify: kaggle competitions list -s kaggriculture
- STATUS: DONE — Python 3.12.13, kaggle-environments 1.32.6, CLI works,
  findings.md §1 filled in.
- REMAINING: version pin isn't reproducible yet — add
  `pip freeze > scripts/requirements-dev.txt` (or a pinned
  requirements-dev.txt) so the environment can be rebuilt exactly.

### RM-003 — Join Competition & Capture Rules
- Accept rules on Kaggle website (before Sep 23 deadline)
- Complete identity verification (required to submit)
- Capture Rules/Terms page → docs/rules-notes.md
- Confirm --group entered via CLI
- STATUS: DONE — docs/rules-notes.md written and thorough (timeline,
  $50k prize, 5/day submission cap, network-compliance void clause,
  all dates captured).

## EPIC 1 — EVAL HARNESS (build the gate infrastructure first)

### RM-004 — Smoke Gate (Fast + Full Tiers)
- eval/smoke.py --fast (short episodes, run every change)
- eval/smoke.py --full (50 episodes × 3 built-ins @ 720 turns, pre-submit only)
- Zero exceptions, zero invalid-action episodes required
- STATUS: DONE — both tiers verified clean vs PASS placeholder
  (2026-08-12: --fast 9 ep/0 fail ~9 s; --full 150 ep/0 fail ~5 min).
  Findings gate (RM-005) passes; placeholder main.py trimmed so its
  docstring doesn't trip unresolved-mechanic keywords before RM-012.

### RM-005 — Findings Enforcement Gate
- eval/check_findings.py greps main.py/config.py for mechanic keywords
- Fails smoke if a referenced mechanic's findings.md row is unresolved
- STATUS: DONE — non-vacuously enforced 2026-08-12: the placeholder
  main.py's docstring (op vocabulary in prose) tripped M1/M2/M3/M4/M7/
  M8/M10. Docstring trimmed to scaffold-only prose; gate kept strict.
  Proof it catches even incidental references, not just logic.

### RM-006 — Tournament Runner + Promotion Rule
- eval/tournament.py: paired, seeded, slot-swapped, --seed pinned so
  CI numbers are reproducible run-to-run (explicit requirement, not
  just an intent — reruns of the same candidate/opponent pair must
  produce comparable results)
- Win-rate + 95% CI output (not fixed game count alone)
- Promotion rule: only when CI lower bound clears 50%
- Worked example logged in findings.md §5
- STATUS: DONE — built and verified 2026-08-12 vs PASS placeholder:
  vs `starter` REJECT (0/80, CI [0.000, 0.046]), vs `random` PROMOTE
  (80/0, CI [0.954, 1.000]); same-seed rerun reproduces W/L/T exactly.
  Rule discriminates correctly. Caveats logged in findings.md §5:
  `random` is unseeded internally (smoke-only baseline) — `starter` is
  the real v1 gate.

## EPIC 2 — GROUND TRUTH & MECHANICS VERIFICATION (fills in using Epic 1's harness)

### RM-007 — Engine Source Audit
- Locate installed kaggriculture env source
- Confirm engine version + Python version in findings.md §1
- STATUS: DONE — source at .venv/lib/python3.12/site-packages/
  kaggle_environments/envs/kaggriculture/kaggriculture.py (1073 lines);
  engine 1.32.6, Python 3.12.13 logged in findings §1.

### RM-008 — Timing & Compute Benchmarks
- Fast-gate vs full-gate smoke tier budgets
- Per-turn/action timeout search on host docs
- Worst-case BFS turn benchmark (target < ~100ms)
- STATUS: DONE — single-episode wall-clock 1.9 s vs starter logged
  in findings.md §2 (2026-08-12); fast gate ~9 s / 9 ep, full gate
  ~5 min / 150 ep observed. Tier budgets now grounded in real runs.
  Remaining: worst-case BFS turn benchmark (needs v1 task logic) and
  host timeout search (needs submission infra) — deferred, not blocking.

### RM-009 — Mechanic Micro-Tests (M1–M10)
- Assert-based tests in eval/micro_tests.py (runs inside RM-004's harness)
- FEED source, HARVEST→SELL flow, BUY_ANIMAL, PLANT consumption,
  weed timing, end-of-day drop, mid-day inventory cap (M7 — see RM-013
  acceptance criteria), hire spawn, price function (M9a/M9b split,
  per-resource), price floor behavior
- Policy must not rely on a mechanic whose row is still blank
- STATUS: DONE — all M1–M10 rows answered from engine source and
  asserted in eval/micro_tests.py (2026-08-12, ALL PASS). Three
  findings with strategy impact: M1 (FEED uses carried inventory,
  not shed), M7 (NO mid-day carried cap — rules-doc assumption
  overturned, TICKET-07), M8 (spawn is first-free NWSE tile, not
  always (5,4)). Logged in findings §4/§6 + docs/plan.md. Price
  table (M9a/M9b) fully verified ✅.

### RM-010 — Discrepancy Policy
- Engine behavior authoritative over rules-doc text when they conflict
- Log discrepancies per-row in findings.md, not silently
- STATUS: DONE — applied live at RM-009: M1 (FEED source), M7 (no
  mid-day cap), M8 (spawn precision) logged on findings §4 rows +
  §6 retroactive note + docs/plan.md entry. Procedure exercised, not
  just stated.

## EPIC 3 — V1 CORE AGENT

### RM-011 — config.py Scaffold
- Single source of truth for tunable thresholds
- Imported by main.py and eval/tournament.py
- Comments link each constant back to its PLAN.md justification
- STATUS: DONE — verification pass 2026-08-12. All tunables referenced
  in strategy.md/PLAN.md have matching commented constants. Added
  missing single-source entries: `MARKET_PARAMS` (full price table),
  `PRICE_FLOOR`, `SHED_CAPACITY` (M7 mirror + no-midday-cap doc note).
  micro_tests.py now imports MARKET_PARAMS/PRICE_FLOOR from config
  (duplicate killed). main.py imports config at RM-012; tournament.py
  has no tunable dependence today (pure CLI runner — no dead import).

### RM-012 — Wheat/Carrot Loop (main.py v1)
- Port plant→water→harvest→sell loop
- Never sell below per-crop floor price
- ACCEPTANCE CRITERIA:
  - Gate: smoke --full clean vs pass/random/starter
  - Gate: tournament (seeded, slot-swapped, per RM-006) CI lower
    bound > 0.50 vs starter
  - Gate: farmer/hand carried inventory never silently overfills
    before end-of-day auto-drop — verify against M7's confirmed cap
    (findings.md: "stockpiling on farmer/hand inventories does not
    bypass the cap"), not just shed capacity
- STATUS: DONE — v1 loop in main.py (small NW field near shed,
  deterministic scan order, shed-room-aware harvest per M7, no land
  buying until RM-015, floor-aware selling). Gates: smoke --full
  150 ep / 0 fail; tournament vs starter 160/0, CI [0.977, 1.000]
  PROMOTE (verified across seeds 1,2,3,5,7,11 — all WINS by ~$800);
  micro_tests incl. new RM-012 M7 shed-room assertion ALL PASS.
  Notable port fix: kaggle_environments loads the LAST callable as
  agent — helpers must precede `agent` (engine contract documented
  in main.py docstring).

### RM-013 — First Submission
- Bundle main.py + config.py as submission.tar.gz (confirmed multi-file default)
- THIS IS THE FIRST REAL ENFORCEMENT POINT for two things that were
  previously only designed, not tested against a real submission:
  (a) the no-network + root-import hard compliance gate (RM-003's
      rules-notes.md constraint), and
  (b) RM-005's findings-enforcement gate, which stops passing
      vacuously the moment main.py/config.py exist
- Submit, monitor via kaggle competitions submissions
- Archive to agents/v1_wheat_loop.py with sha256 + changelog
- Stop Point: v1 Live on Ladder

## EPIC 4 — SCALE LOGIC

### RM-014 — Task Assignment (BFS Priority Queue)
- Priority: WATER/FEED > HARVEST > COLLECT_FERTILIZER > CARE > DIG > PLANT > PLACE
- Nearest-task-first per unit, LOCKED tiles passable not actionable

### RM-015 — Land Expansion Logic
- Pinned order NE→SW→SE ($1k/$2k/$4k)
- NE-first unlocks the (5,4) first-hire spawn tile
- Cash reserve buffer before any purchase

### RM-016 — Farm Hand Hiring
- Trigger once task backlog exceeds farmer capacity
- Fibonacci daily cost awareness (1,1,2,3,5,8… resets daily)

### RM-017 — Crop Diversification (Tomato, Melon)
- Ongoing vs one-time yield handling
- Melon wave timed to town-demand troughs

### RM-018 — Sale/Market Timing Policy
- Premium goods (strawberry/melon/milk/wool): small batches, post-demand-tick
- Staples: steady sell, maintain wheat feed buffer
- BUY_PRODUCT restricted to WHEAT/FERTILIZER only
- Gate + archive each promoted variant, ≤1–2 submissions/day cadence

## EPIC 5 — ANIMALS

### RM-019 — Coop/Pasture + Placement
- BUILD_COOP / BUILD_PASTURE + PLACE logic

### RM-020 — Feeding & Care Discipline
- Wheat buffer ≥ animals×2+5 (hard rule, never break for a sale)
- Daily FEED + CARE + COLLECT_FERTILIZER in task queue
- ACCEPTANCE CRITERIA: zero animal escapes across 50+ smoke episodes
  (explicit gate, not just a design intent — an escape is a
  catastrophic loss and must fail the smoke gate, not just get noted)

### RM-021 — Quadrant 4 Decision
- Buy only if day ≤16 AND money ≥6000 AND reserve ≥1000
- Default crop: MELON (explicit, not left ambiguous)
- Caution driven by price-crash + labor risk, not a revenue shortfall

## EPIC 6 — STRETCH: OPPONENT-AWARE STRATEGY

### RM-022 — Opponent Tile Tracking
- Behind config flag OPPONENT_AWARE_SELL_TIMING, default False
- Scoped strictly to Aug 25–Sep 10 phase window

### RM-023 — Flagged A/B Validation
- Tournament (seeded, per RM-006): flag ON vs OFF vs identical opponents
- Promote only if ON's CI lower bound clears OFF's win rate
- Noise caveat: visible yield_units ≠ opponent's actual sell timing

## EPIC 7 — TEAM ALIGNMENT & VISUALIZATION

### RM-024 — Static Design Mockup
- 2D grid HUD, tile inspector, market/town panels, scoreboard
- Scoreboard emphasizes rating/W-L-T over raw coins (matches scoring)
- STATUS: DONE

### RM-025 — Running Strategy Simulator
- Simplified turn-by-turn sim, selectable strategies side by side
- Used to discuss algorithm tradeoffs with team before engine build-out
- Explicitly caveated as approximate, not a source of truth for tuning
- STATUS: DONE

### RM-026 — Replay Viewer (optional, real data)
- Load actual kaggle competitions replay <EPISODE_ID> JSON
- Animate real episodes for post-submission analysis

## EPIC 8 — SUBMISSION OPS & COMPLIANCE

### RM-027 — scripts/submit.sh
- Archives current main.py+config.py before each submit
- kaggle competitions submit + status polling

### RM-028 — Post-Submit Monitoring
- Check both active bots' episodes, not just best-shown
- Download logs on Error status, fix, re-gate, resubmit

### RM-029 — Foundational Rules Compliance Check
- Private/public code sharing (§6a/§6b) reviewed against repo workflow
- Original-work warranty (§14a) — study, don't copy, confirmed
- STATUS: DONE — no violations found, 4 gaps folded into docs

## EPIC 9 — TUNING & FREEZE WINDOW

### RM-030 — Stress Test Suite
- ≥200 episodes across varied seeds
- Full agents/ pool + self-play, slot-swapped

### RM-031 — Final Candidate Selection
- Head-to-head comparison of top variants
- Deliberately pick the 2 live submissions (not "whatever's newest")
- Stop Point: Freeze Review

### RM-032 — Final Submissions
- Completed by Sep 22 (1-day buffer before Sep 23 entry deadline)
- No risky changes after Sep 23

## EPIC 10 — MONITORING & CLOSEOUT

### RM-033 — Post-Lock Monitoring
- No code changes possible after Sep 30
- Track leaderboard through ~Oct 15 convergence

### RM-034 — Final Scorecard
- Log final leaderboard position vs. logged expectations
- Retrospective: which strategy decisions held up, which didn't

## TOTAL
11 Epics · 34 Tickets (RM-001..RM-034)

## Project Flow

Foundation → Eval Harness (build the gate infrastructure) → Ground Truth &
Mechanics (fill it in using that infrastructure) → V1 Core Agent → Scale Logic
→ Animals → Stretch: Opponent-Aware Strategy → Team Alignment & Visualization
(parallel — can run alongside any stage) → Submission Ops & Compliance →
Tuning & Freeze Window → Monitoring & Closeout

## Changelog vs. v1 of this roadmap

- Renumbered TICKET-001..034 → RM-001..034 to eliminate collision with
  TICKET-01..16 already in use across PLAN.md/findings.md/strategy.md.
- Swapped epic order: Eval Harness now precedes Ground Truth & Mechanics
  Verification — the harness (smoke.py, check_findings.py, tournament.py)
  is infrastructure that mechanic-verification tests run inside, so it
  needs to exist first. Matches PLAN.md's own §4-before-§5 sequencing.
- Corrected RM-002 (env config) and RM-003 (rules capture) from
  incorrectly-stated "not yet done" to DONE, matching verified disk state.
- Added explicit remaining task to RM-002: pin the environment
  reproducibly (requirements-dev.txt), since the version pin itself
  wasn't captured anywhere despite being logged in findings.md.
- Added M7 (mid-day inventory cap) as an explicit RM-012 acceptance
  criterion, not just a findings.md row.
- Flagged RM-013 as the first real enforcement point for both the
  no-network/root-import gate and RM-005's findings-enforcement gate.
- Added the specific unfilled benchmark (single-episode wall-clock) to
  RM-008 instead of a generic "pending" status.
- Added explicit "zero animal escapes across 50+ episodes" gate to RM-020.
- Made seeded/slot-swapped tournament runs an explicit requirement in
  RM-006, referenced from RM-012 and RM-023.

## Notes on scope vs. the YieldIQ format this mirrors

- No Navigation/Auth/Backend/Database/Maps/Voice/Admin epics — Agrihand
  ships as a single main.py + config.py, not an app with users or a UI.
- "Team Alignment & Visualization" (Epic 7) is the Agrihand equivalent of
  YieldIQ's Shared UI epic — but it exists to help reason about algorithms
  in a meeting, not as a shipped product surface.
- Stop Points are kept at the same high-leverage moments YieldIQ uses:
  after foundational structure, after v1 goes live, before the freeze
  window locks in final candidates.
