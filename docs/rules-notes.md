# Kaggriculture — Competition Rules & Terms Notes

Capture of the live competition rules/terms (competition gap #1). Verified 2026-08-04 from the live Kaggle pages + authenticated API (see the public Seyamalam/Kaggriculture `docs/competition.md` mirror for the source summary). This file exists so disqualification-relevant terms are recorded and never forgotten; it is a working reference, not a second source of truth for strategy (that's PLAN.md + docs/strategy.md).

## Identity & prizes

- Slug: `kaggriculture` · Competition ID: 147734 · Featured simulation competition (points + medals).
- Sponsor: Google LLC; platform: Kaggle. Prize pool **$50,000**, ten equal **$5,000** prizes for places 1–10.
- Objective: autonomous agent finishes a 30-day season with more banked coins than its opponent.

## Timeline (all 23:59 UTC)

| Milestone | Date |
|---|---|
| Start | 2026-07-29 |
| Entry deadline | 2026-09-23 |
| Team merger deadline | 2026-09-23 |
| Final submission deadline | 2026-09-30 |
| Continued games / convergence | ~2026-10-01 → 2026-10-15 |

## Evaluation (how we rank)

- Up to **5 submissions/day**; only the **latest 2** remain active and count for final evaluation.
- A new upload runs a **self-play validation episode** first — runtime failure → `Error` status + downloadable logs.
- Ladder: wins/losses/ties vs similarly-rated opponents; rating change depends on **opponent rating, not coin margin**.
- Leaderboard shows the **best active submission**; the Submissions page tracks both active bots.
- Uploads lock at the final deadline; games continue ~2 weeks to reduce uncertainty.
- Final standings via **Bradley–Terry tournament** over episodes. No private leaderboard.

## Game contract (what the agent faces)

- Two separate farms; opponent's public farm + bank visible, but shed/seeds/inventories hidden.
- 30 days × 24 turns = **720 turns**. Start: $3,000, one farmer, NW 5×5 quadrant, empty shed.
- Additional quadrants in pinned order: **NE $1k → SW $2k → SE $4k**.
- One action per farmer/hand per turn + up to **10 ordered market orders**.
- Products: wheat, carrot, tomato, strawberry, melon, eggs, milk, wool, fertilizer. Crops need watering; animals need wheat feed. Two missed daily refreshes = plant dies / animal lost.
- Shared market: fixed seed/animal costs, supply-sensitive prices; town demand drains supply and can support prices.
- Winner = more banked coins after final turn; **unsold inventory has zero terminal value**.

## Submission contract (compliance-relevant — these void a submission)

- Artifact root must contain `main.py` exposing `agent(obs)`. Single file or `.tar.gz` with `main.py` at root.
- Runtime files at `/kaggle_simulations/agent/` — imports must resolve from there.
- **No network ingress or egress** in episodes — a submission that attempts network access is void (Foundational Rules requirements clause). Our pre-submit checklist (PLAN.md §8 item 8) enforces this.
- Replays and agent actions **may be public** — assume everything we submit is visible.
- Resources at verification: 100 MiB upload, 8 GiB disk, 6.5 GiB RAM, 1.6 vCPU (recheck before relying — the raw CLI page had unresolved template tokens).

## Disqualification-relevant terms (from Foundational Rules / Rules page)

- Submissions are void if they: don't meet the requirements (e.g. missing `main.py`), are altered after the deadline, violate the code-of-conduct, or use disallowed external resources (network access at runtime).
- Solo entry: no team-merger concerns; rules already accepted at join.
- Deadline discipline: final submissions done by **Sep 22** (1-day buffer before the Sep 23 entry deadline), no risky changes after freeze.

## Sources

- Live: `kaggle.com/competitions/kaggriculture/{overview,data,rules,evaluation}`
- Public verified mirror: Seyamalam/Kaggriculture `docs/competition.md` (dated 2026-08-04)
- Final-evaluation announcement: competition discussion #731587
