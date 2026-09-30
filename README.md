# Agrihand — Kaggriculture Competition Agent

🤖 **Vibe coded:** built with AI coding assistants.

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
scripts/build_submission.sh     # precheck + submission.tar.gz (main.py + config.py at root)
kaggle competitions submit kaggriculture -f submission.tar.gz -m "agrihand v2"
```

## Repo layout

See `PLAN.md` §2. Short version: `main.py` + `config.py` ship in the submission bundle; `agents/` archives frozen candidates; `eval/` has the gates; `scripts/` has setup/submit; `reports/` + `docs/` hold outputs and rationale.

## Archived candidates

| Version | Files | sha256 (main) | Changelog |
|---|---|---|---|
| agrihand_v2 | `agents/agrihand_v2.{py,cfg}` | `b4829109…e4ae` | 2026-09-30: v1 + top-bot research: sell-first market ordering and return-per-dollar animal funding. Beats v1 55/25 (80 games); 20/0 vs RM-050, starter and two mid-strength public bots; loses to public V21 by ~$20k. Other researched techniques are implemented as config knobs, off (measured worse). See docs/plan.md. |
| agrihand_v1 (v4 value-based) | `agents/agrihand_v1.{py,cfg}` | `11b57623…67ef` | 2026-09-30 rebuild: every decision priced in projected dollars (market model, crop/animal/land/crew planning, demand-matched selling, value-per-turn routing). 12/0 vs RM-050 live bot, starter and two mid-strength public bots; 0/20 vs public V21 (gap −$20.7k). See docs/plan.md 2026-09-30. |
| rm050_rework_batch_pickup | `agents/rm050_rework_batch_pickup.{py,cfg}` | — | RM-050 live bot (submission 55715426), superseded by v4. |
| v3_combo_ladder_v1 | `agents/v3_combo_ladder_v1.{py,cfg}` | `900adb48…4511` | RM-039 live-rated ladder entry. Full progression: v1 wheat/carrot → animals promoted (RM-021) → MELON/STRAWBERRY/WHEAT + early hire + crop spread combo promoted (RM-036) → robustness confirmed 124/0, Wilson CI [0.970, 1.000] (RM-038). |
| v3_animals_on_baseline | `agents/v3_animals_on_baseline.py` | `48c70330…255c` | Superseded animals-ON baseline (wheat/carrot, no hands), archived at RM-036. Current committed main.py = this + RM-036 combo promoted: MELON/STRAWBERRY/WHEAT mix + early hire + crop spread. Self-play 80/0 vs this baseline, CI [0.954, 1.000], zero escapes. |
| v2_animals_off_baseline | `agents/v2_animals_off_baseline.py` | `63e8b0aa…adac` | Superseded crop-only baseline, archived at RM-021 Part A. Current committed main.py = this + animals promoted (ANIMALS_ENABLED=True): RM-020 A/B 80/0 vs this baseline, CI [0.954, 1.000], zero escapes on the 50-episode --animals gate. |
| v1_wheat_loop | `agents/v1_wheat_loop.{py,cfg}` | `6f66a1b2…3887` | RM-012 promoted vs starter: 160/0, CI [0.977, 1.000]. NW-field wheat/carrot loop, shed-room-aware harvest (M7), floor-aware selling, no land buying. |
