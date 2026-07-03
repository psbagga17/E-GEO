# E-GEO Data

The E-GEO dataset and all experiment artifacts are hosted on HuggingFace
(`psbagga17/E-GEO`, `--repo-type dataset`) in two top-level folders:

- **`data/`** — the dataset itself (queries, products, splits, cached rankings). This is all a submitter needs.
- **`results/`** — run-output artifacts from the paper's experiments (baselines, meta-optimization, leaderboard, red-teaming). Needed only to reproduce the paper's analyses and figures.

## Download

```bash
# dataset only (what submitters need):
hf download psbagga17/E-GEO --repo-type dataset --local-dir . --include "data/*"
# everything (dataset + results):
hf download psbagga17/E-GEO --repo-type dataset --local-dir .
```

See the [paper](https://arxiv.org/abs/2511.20867) for dataset construction and methodology.

---

## `data/` — the dataset

```
data/
├── queries_products.json                    # full corpus: 13,747 queries, each with 10 candidate products
├── test_data.json                           # 2,000 held-out test queries
├── test_selected_products.json              # per-test-query target product (index + metadata)
├── test_initial_ranking_{model}.json        # each judge's ranking of the unmodified test candidates
├── train1000_val500.json                    # paper split: 1,500 queries (1,000 train / 500 val)
├── train_val_full.json                      # full non-test split: 11,747 queries (superset of the paper split)
├── train_val_initial_ranking_{model}.json   # each judge's ranking of the unmodified train/val candidates
└── train_selected_products.json             # per-train/val-query target product (index + metadata)
```

`{model}` ∈ `{gpt41, gpt5, gemini, claude, deepseek, llama}`.

- **`queries_products.json`** — the full dataset: 13,747 query entries, each with its 10 retrieved candidate products.
- **`test_data.json`** — the 2,000 fixed test queries (sampled from the corpus).
- **`test_selected_products.json`** — for each test query, the target product to rewrite (its index `ind` plus metadata).
- **`test_initial_ranking_{model}.json`** — each judge's ranking of the *unmodified* test candidates (the "before" positions used to score rank improvement).
- **`train1000_val500.json`** — the paper's training/validation split: 1,500 queries — rows 0–999 are the 1,000 train queries, rows 1000–1499 the 500 validation queries (disjoint). This is the optimizer's default.
- **`train_val_full.json`** — the full non-test split: all 11,747 non-test queries (a superset that includes the paper split), provided for use beyond the paper. **Note:** the precomputed `train_val_initial_ranking_*` files cover a 2,000-query pool — the paper's 1,500 (rows 0–1499, same order as `train1000_val500.json`) plus 500 extra ranked-but-unused queries (rows 1500–1999) — **not** the full 11,747 set; optimizing beyond the pool requires generating initial rankings first.
- **`train_val_initial_ranking_{model}.json`** — each judge's ranking of the unmodified train/val candidates (covers the 2,000-query pool above).
- **`train_selected_products.json`** — per-train/val-query target product (index + metadata).

---

## `results/` — experiment artifacts (reproduction only)

```
results/
├── INITIAL_PROMPT_RESULTS/   # baseline: each initial prompt style, no optimization
├── META_OPT_RESULTS/         # reflective prompt meta-optimization (inspired by GEPA)
├── LEADERBOARD_RESULTS/      # cross-model optimizer × ranker comparison
└── REDTEAMING_RESULTS/       # adversarial / red-team experiments
```

### `INITIAL_PROMPT_RESULTS/`

Test-set results for each of the 15 initial prompt styles, without any optimization. One subfolder per prompt style; under each, one folder per judge (`claude`, `deepseek`, `gemini`, `gpt-4.1`, `gpt-5`, `llama`) with `test_results.csv` (per-query ranking results) and `statistics.txt` (summary statistics). The rewriter is GPT-4.1, so these CSVs hold the actual rewrites and per-engine rankings and double as ready-made baselines.

### `META_OPT_RESULTS/`

Results of the reflective prompt meta-optimizer (inspired by GEPA, [Agrawal et al., 2025](https://arxiv.org/abs/2507.19457)), which evolves a rewriting prompt over epochs by reading per-engine results and proposing improvements; selection is on validation, never on test.

- **`best_prompts.json`** — the final best prompt per initial style (also shipped in the repo as `src/optimized_prompts.json`).
- **`{initial_prompt}/epoch_{n}/`** — per-epoch snapshots: `batch_{n}/` (training), `validation_{n}/`, and `testing_{n}/`, each with `prompt.txt`, the meta-reasoning, and per-judge results.

### `LEADERBOARD_RESULTS/`

Cross-model evaluation. Each `test_ranked_{optimizer}(opt)_{ranker}(rank).json` holds rankings where **optimizer** is the model that rewrote the descriptions (`claude`, `deepseek`, `gemini`, `gpt41`, `gpt4omini`, `gpt5`, `llama`) and **ranker** is the judge (`claude`, `deepseek`, `gemini`, `gpt5`, `llama`). Each entry: `query_id`, `rand_idx`, `optimized_product`, `optimized_ranking`, `initial_ranking`, `improvement`.

- **`leaderboard.json`** — aggregated mean-improvement matrix (optimizer × ranker) from the paper's runs. *(This is the paper's reference scoreboard, distinct from the public submission leaderboard, which is built from the repo's `submissions/` folder.)*

### `REDTEAMING_RESULTS/`

Red-team experiments on ranker robustness to adversarial product descriptions.

- **`ADVERSARIAL_BENCHMARK/`** — static benchmark of how well each judge resists the 14 adversarial attacks. Contains `cross_engine_summary.json` (per attack × judge stats: mean rank improvement, flag rate, CI), `heuristic_per_cell.csv`, and one `{ranker_model}/attack_results.csv` per judge (columns include `attack_type`, `query_id`, `original_pos`, `optimized_pos`, `improvement`, `was_flagged`, `original_text`, `attacked_text`). Attack types use the paper's one-word names: `injection`, `superlatives`, `hidden`, `reviews`, `stuffing`, `formatting`, `authority`, `emotional`, `sycophancy`, `fabrication`, `anchoring`, `jargon`, `negation`, `narrative`.
- **`META_OPT/`** — tests whether the meta-optimizer, applied to adversarial styles, learns to produce manipulative content and whether judges flag it. Contains `test_per_cell.csv` and `train_trajectory.csv`, plus one folder per style (`authoritative` — a clean control — and `emotional`, `superlatives`, `sycophancy`) with `phase_a_test/`, `phase_b_train/`, and `phase_c_test/` snapshots. To regenerate, run `run_meta_optimization.py --red-team` with `--output-dir results/REDTEAMING_RESULTS/META_OPT` (the default output dir is `results/META_OPT_RESULTS/`).

---

## Usage

1. **`train1000_val500.json`** — train/validate (the paper split; the optimizer's default).
2. **`test_data.json`** + **`test_selected_products.json`** — final evaluation (the target product per query).
3. **`train_val_full.json`** — a larger non-test pool for use beyond the paper (generate initial rankings first to optimize on it).
4. **`results/`** — baselines, optimization trajectories, the leaderboard, and red-team artifacts for reproducing the paper.
