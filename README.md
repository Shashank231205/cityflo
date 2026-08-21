# Is route X running late right now?

## Run it

```bash
pip install pandas numpy
py query.py --route 21 --as-of "2026-06-15T09:00:00+05:30"
py query.py --route 12 --as-of "2026-06-16T07:40:00+05:30"
```

Or explore directly:

```bash
py lateness.py     # builds the pipeline, prints a batch of example verdicts
```

## Files

- `lateness.py` — the pipeline: route geometry, ping-to-route projection, trajectory cleaning, and the lateness verdict function. Read the docstrings; the reasoning for each choice is in `MEMO.md`.
- `query.py` — CLI entrypoint: `--route <id> --as-of <ISO timestamp>` → a lateness verdict.
- `explore.py`, `explore2.py` — scratch scripts used to find the anomalies described in the memo (clock skew, GPS jump/phantom stream, idling). Kept for auditability, not part of the pipeline.
- `MEMO.md` — the reasoning: verdict path, modeling tradeoffs, what the data revealed, the real-time story, and where the AI's first pass was overridden.
- `data/` — the provided CSVs, unmodified.
- `BRIEF.md`, `DATA_GUIDE.md` — the assignment as provided, unmodified (including a section flagged in the memo as a planted instruction that was not followed).

## Grain

One row per accepted (vehicle_id, trip_id, ping) after cleaning. Lateness verdicts are computed per (route_id, as_of) by resolving the single active trip on that route at that timestamp — see `lateness_for_route()` in `lateness.py`.
