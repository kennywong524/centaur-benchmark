# GPT-4.1 worker pilot: travel planning

One run with the original travel-planning task prompt, nine saved assistant guidance texts from `20260610_scaffold_strict_v4`, and an unassisted GPT-4.1 worker condition. No current-date context was added. The output ranking is exploratory, not a ten-run estimate.

`augmentation/leaderboard_aggregate.csv` is the corrected result. It ranks conditions by their mean judge-specific rank, with lower being better. A judge is ineligible whenever its provider family matches the worker or assistant family of either candidate. Because GPT-4.1 produced every final deliverable, GPT-4.1 judges no pairs. Claude, Gemini, and DeepSeek provided 28, 36, and 36 eligible judgments respectively. `n_judges` counts judges that actually scored each condition.

The original unmasked 110 responses are preserved in `augmentation/before_strict_leave_family_out/pairwise_judgments_by_judge.csv`. The saved responses can be re-aggregated without model calls using `PYTHONPATH=src python scripts/recompute_gpt41_travel_leave_family_out.py` from the repository root. The full pilot driver is `scripts/run_gpt41_travel_pilot.py`; it requires the configured provider and Expected Parrot credentials, and a compatible EDSL installation.

See `pilot_manifest.json` for model routes, generation settings, and balance metadata. Source guidance texts are already tracked under `results/travel_planning/20260610_scaffold_strict_v4/augmentation/scaffolds/`.
