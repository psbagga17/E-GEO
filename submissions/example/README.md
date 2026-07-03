# Example submission

This is a **template** showing the layout of an E-GEO leaderboard submission. Replace it with your own results before opening a PR — see [`../../submission.md`](../../submission.md) for the full workflow.

## Files

- **`metadata.json`** — your submission's metadata. Produced automatically by `src/submission.py` (do not hand-edit): `name`, `type`, `mode` (which of A/B/C ran — this example is Mode A), `judges` (the models scored against — the 5 leaderboard judges by default), `description`, `cost_per_rewrite_usd` (`null` here, since Mode A never runs a rewriter; estimated automatically in modes B/C), `query_blind` (always `true` — every submission attests to the query-blind rule), `contact`, optional `code_url`/`paper_url`, `run_config` (the rewriter model + prompt-optimization config — `null` in Mode A), and `is_paper_baseline` (`false` for community submissions).
- **`results.json`** — the scores the leaderboard reads, written by `submission.py` (don't hand-edit): `per_ranker` `mean`/`se` for all five judges plus `total_queries_scored` and total token/cost figures. **All five rankers are required** — partial submissions are rejected.
- **`rewrites.jsonl`** — the rewrites your scores were computed from: one row per test query, using the canonical keys `query_id`, `rand_idx`, `initial_product`, `optimized_product`, plus a `judges` object with each judge's per-query `improvement`. Shipping this keeps your numbers reproducible — anyone can re-run `submission.py --rewrites rewrites.jsonl` and reproduce the scores. **Truncated here to 2 rows; a real submission has all 2,000 test queries.**

## How it was produced

```bash
uv run python src/submission.py \
    --rewrites rewrites.jsonl \
    --name "Example Submission (GPT-4.1 + competitive)" \
    --contact you@example.com
```

The numbers in `results.json` are illustrative placeholders, not real results (and the `results.json` totals describe a full 2,000-query run, while the shipped `rewrites.jsonl` is truncated to 2 rows for brevity).
