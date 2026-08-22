# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# project-structure
- Keep the demo/ directory separate from the main project — it exists only for understanding/visualization purposes, so do not modify it while building the actual agent. Confidence: 0.85
- Use RM-001..RM-0NN prefix for roadmap ticket IDs; TICKET-01..TICKET-16 is a separate system reserved for doc/repo tickets (PLAN.md/findings.md/strategy.md). Cross-reference by description, never by assuming shared numbering. Confidence: 0.60

# workflow
See [workflow/taste.md](workflow/taste.md)
# documentation
- When a doc/roadmap value becomes superseded by reality, update the doc to match reality immediately rather than leaving it silently superseded — preserve the historical reasoning as a labeled "SUPERSEDED" note (with date + ticket) instead of deleting it, so there is never a "doc says X, disk says Y" two-sources-of-truth state. Confidence: 0.85
# communication-style
- Explain concepts simply and briefly (e.g. "like a 5-year-old") but in direct prose, NOT in example/analogy format — short, plain explanation without illustrative examples. Confidence: 0.70

# strategy
- Treated hands/hired labor as the leverage point: each hand performs its own action in parallel with the farmer per turn, so more hands means more work done per fixed step count (cost is only the hire fee, not time/turns) — the real lever is productive actions per turn, and hand-movement/task-assignment should be the focus of optimization planning. Confidence: 0.70

# submission
- kaggle_environments loads the LAST callable defined in the submission module as the agent (`get_last_callable` returns `[v for v in env.values() if callable(v)][-1]`); a docstring warning is not enough — keep `agent()` as the last function in main.py, with all helpers defined before it, and enforce via an automated last-callable check. Confidence: 0.85
- The Kaggle runner calls `agent(observation, configuration)` with TWO positional args, not one; a one-arg `agent(obs, ...)` signature silently feeds the config dict into whatever the 2nd param is (a truthy dict), so always define `def agent(obs, configuration=None, ...)` and enforce via an automated signature check. Confidence: 0.75

