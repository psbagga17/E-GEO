# Submissions

Leaderboard submissions live here — **one folder per submission**:

```
submissions/<team-name>/
├── metadata.json    # name, type, mode (A/B/C), cost, query_blind, contact, run_config
├── results.json     # per_ranker mean/se for all five judges + totals
└── rewrites.jsonl   # the rewrites your scores were computed from
```

To submit, open a pull request that adds your `submissions/<team-name>/` folder. On merge, the leaderboard updates. See **[`../submission.md`](../submission.md)** for the full workflow and how to generate these files with `src/submission.py`.

See **[`example/`](./example/)** for a filled-in template.

> Note: `example/` is an illustrative template only — its scores are placeholders, not real results, and it is **not** a leaderboard entry. Leaderboard tooling should skip it.
