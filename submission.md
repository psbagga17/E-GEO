# Submitting to the E-GEO leaderboard

`src/submission.py` is the single command you run to score a submission against the five benchmark judges — **GPT-5, Claude Sonnet 4.5, Gemini 3 Flash Preview, DeepSeek V3.2, and Llama 4 Maverick**. It validates your input, picks one of three modes, estimates cost, and writes the files you submit. It's the only command you need — you never touch the rest of the code.

Evaluation runs **on your machine, on your own API keys**. You get on the public leaderboard by **opening a pull request** that adds your results — there is no upload form and no login. **The PR *is* the submission — once the maintainers verify and merge, your results appear on the [leaderboard](https://github.com/psbagga17/E-GEO).**

> **Keys:** submitting needs only `OPENROUTER_API_KEY`

---

## Setup

```bash
git clone https://github.com/psbagga17/E-GEO.git
cd E-GEO
uv sync        # install dependencies (commands use `uv run`)
# fetch the dataset from HuggingFace (submitters need only data/):
uv run hf download psbagga17/E-GEO --repo-type dataset --local-dir . --include "data/*"
echo "OPENROUTER_API_KEY=sk-or-..." > .env
```

---

## Two scoring rules

1. **Query-blind.** The rewriter may see *only* the original product description — never the search query. (The deployed seller doesn't know what the shopper will type.)
2. **One rewrite per test query.** Each test query names a single target product to rewrite — the one at `rand_idx` in `data/test_selected_products.json`. Rewrite *that* product only (not the other candidates in the query), submit one rewritten version of it, and include **every** test query exactly once — don't drop, duplicate, or add queries.

---

## Three ways to submit (pick one)

| Mode | You provide | What runs |
|------|-------------|-----------|
| **A** | `--mode score --rewrites rewrites.json` | Score your already-produced rewrites. We only evaluate. |
| **B** | `--mode rewrite --prompt final.txt` | We rewrite the test products with your prompt, then score. |
| **C** | `--mode optimize --prompt authoritative` | We prompt-optimize your starting prompt (selecting on validation, never on test), then rewrite + score. |

### Mode A — quickstart

**1. Produce `rewrites.json`.** For every `query_id` in `data/test_data.json`, look up its target product index `rand_idx` (the `ind` field in `data/test_selected_products.json`), rewrite that product's description with any method (prompt, fine-tune, agent), and emit:

```json
[
  {"query_id": "10006", "rand_idx": 9, "initial_product": "<the original description>", "optimized_product": "<your rewritten description>"},
  ...
]
```

Use exactly these field names — `query_id`, `rand_idx`, `initial_product` (the original description, for reproducibility), `optimized_product`. Every `query_id` must be present, every `rand_idx` must match `test_selected_products.json`, and both `initial_product` and `optimized_product` must be non-empty. (A JSON array or JSONL are both accepted.)

**2. Score against all five judges:**

```bash
uv run python src/submission.py \
    --mode score --rewrites rewrites.json --name "My Team" --contact you@example.com
```

In Mode A nothing is re-rewritten, so `cost_per_rewrite_usd` is left blank (`null`)

### Mode B — quickstart

You bring a **finalized rewriting prompt** and we rewrite the test products with it, then score against the models. Use this when you have a prompt you would like to benchmark and don't want any optimization. Requires an `OPENROUTER_API_KEY`.

**1. Write your prompt.** It must contain the `{description}` placeholder — we fill it with each product's original description (and *only* that; the rewriter never sees the query). Pass a built-in method key (e.g. `authoritative` — these already include the placeholder), a `.txt` path, or literal text. A `.txt` file is easiest: it keeps multi-line formatting intact, which a long prompt typed on the command line would lose. Example `final.txt`:

```
Rewrite the following product description to rank higher while keeping every fact accurate.
Do not invent specs, claims, or reviews.

{description}
```

**2. Rewrite with your prompt, then score:**

```bash
uv run python src/submission.py \
    --mode rewrite --prompt final.txt --name "My Team" \
    --rewriter-model openai/gpt-4.1 --contact you@example.com
```

We rewrite all test products with `--rewriter-model` (any OpenRouter model; default `openai/gpt-4.1`) as-is, then score across the five judges. `cost_per_rewrite_usd` is estimated from the rewriter's token usage × its price.

To benchmark one of the paper's optimized prompts instead, skip the file and pass `--prompt optimized:<style>` — e.g. `--mode rewrite --prompt optimized:competitive` runs the strong optimized `competitive` prompt straight from a clone. The 15 styles ship in `src/optimized_prompts.json`.

### Mode C — quickstart

You bring a **starting prompt** and we **prompt-optimize** it (selecting on the validation split, **never** on test) before rewriting + scoring the test set exactly as in Mode B. Use this when you would like to improve upon a prompt via prompt optimization. Requires an `OPENROUTER_API_KEY`.

**1. Pick a starting prompt** — a built-in method key (e.g. `authoritative`), a `.txt` path to a prompt, or literal text containing `{description}`.

**2. Optimize, then rewrite + score** — the **default quickstart** (every prompt-optimization knob uses its default; this is all you need):

```bash
uv run python src/submission.py \
    --mode optimize --prompt authoritative --name "My Team" --contact you@example.com
```

`--mode optimize` runs prompt optimization over `--num-epochs` (default 2), scoring candidate prompts with `--rerank-model` and driving the improvement loop with `--meta-model` (both default `openai/gpt-4.1`); selection happens on validation and **never touches test**. The winning prompt then rewrites + scores the test set as in Mode B. Cap `--max-train-queries` / `--max-val-queries` for cheaper optimization runs. Every prompt-optimization knob — and a worked low-cost example — is in [prompt-optimization parameters](#prompt-optimization-parameters-mode-c) below.

---

## Output (written to `submissions/<team-name>_<timestamp>/`)

- **`metadata.json`** — your submission's metadata: `name`, `type`, `mode` (which of A/B/C ran), `judges` (the models you were scored against — the 5 leaderboard judges by default, plus any extras you added via `--judges`), `description`, `cost_per_rewrite_usd` (in modes B/C **estimated automatically** from the rewriter's token usage × model pricing; in Mode A it's `null`, `query_blind` (usually set to `true` — every submission must agree to the query-blind rule), `contact`, optional `code_url`/`paper_url`, and `run_config` — the rewriter model plus, for **Mode C**, the full prompt-optimization configuration (meta-model, rerank model(s), epochs, batch size, split caps) so the run is reproducible.
- **`results.json`** — the scores the leaderboard reads: `per_ranker` `mean`/`se` for all five judges, plus `total_queries_scored` and total token/cost figures. Written by `submission.py`.
- **`rewrites.jsonl`** — one row per query, using the **same keys as the input** (`query_id`, `rand_idx`, `initial_product`, `optimized_product`) plus a `judges` object with each judge's per-query improvement.
- **`run_summary.json`** — the prompt/config, per-judge token counts, and total eval spend.

`metadata.json` schema (a **Mode C** run shown — see `mode`/`run_config`):

```json
{
  "name": "My Team",
  "type": "model+prompt",
  "mode": "C: optimize prompt, then rewrite",
  "judges": [
    "openai/gpt-5",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2",
    "meta-llama/llama-4-maverick"
  ],
  "description": "GPT-4.1 with our competitive prompt.",
  "cost_per_rewrite_usd": 0.0042,
  "query_blind": true,
  "contact": "you@example.com",
  "code_url": null,
  "paper_url": null,
  "run_config": {
    "rewriter_model": "openai/gpt-4.1",
    "optimized": true,
    "optimization": {
      "meta_model": "openai/gpt-4.1",
      "rerank_models": ["openai/gpt-4.1"],
      "num_epochs": 2,
      "batch_size": 100,
      "max_train_queries": null,
      "max_val_queries": null
    }
  },
  "is_paper_baseline": false
}
```

In **Mode A** `cost_per_rewrite_usd` and `run_config` are both `null`; in **Mode B** `run_config` has `"optimized": false` and `"optimization": null`.

`results.json` example schema:

```json
{
  "per_ranker": {
    "gpt_5":                  {"mean": 0.17, "se": 0.02},
    "claude_sonnet_4_5":      {"mean": 0.16, "se": 0.02},
    "gemini_3_flash_preview": {"mean": 0.16, "se": 0.02},
    "deepseek_v3_2":          {"mean": 0.17, "se": 0.02},
    "llama_4_maverick":       {"mean": 0.15, "se": 0.02}
  },
  "total_queries_scored": 2000,
  "total_input_tokens": 123456,
  "total_output_tokens": 12345,
  "estimated_usd_cost": 1.23
}
```

**All five rankers are required.** Submissions missing any of the five judges are rejected.

---

## Submit via pull request

Evaluation runs **on your machine** — `submission.py` already wrote your results to `submissions/<team-name>_<timestamp>/`. To get on the public leaderboard, **open a pull request to this repository**:

1. In the folder `submission.py` created, keep **`metadata.json`, `results.json`, and `rewrites.jsonl`** — these three are the submission. (The per-judge CSV subfolders, `optimization/`, and `run_summary.json` are local extras) Rename the folder to `submissions/<team-name>/` if you like.
2. Open a pull request against this repo with that folder.
3. A maintainer reviews and merges it. **On merge, your results appear on the leaderboard.**

---

## Cost & time

A full run over the 2,000-query test set across all five judges is **≈\$230 and roughly 1–3 hours** (Claude and GPT-5 are ≈90% of the cost; the other three total under \$25). Use `--max-test-queries N` for test runs but all submissions must score all queries on all five judges.

Every mode validates your input first and exits with a clear error before spending anything, so there is no separate validate step. To pre-flight before committing to a full run — free, no key, no API calls — add `--validate-only` to any submission command; it checks the input and exits before any model is called.

---

## Key flags (`submission.py`)

| Flag | Meaning |
|------|---------|
| `--rewrites PATH` | **Mode A**: score these rewrites (mutually exclusive with `--prompt`). |
| `--prompt KEY/PATH/TEXT` | **Mode B/C**: a method key, `optimized:<style>` (one of the 15 optimized prompts in `src/optimized_prompts.json`), a `.txt` path, or literal text containing `{description}` (mutually exclusive with `--rewrites`). |
| `--name` | **Required.** Leaderboard row label (the unique key). |
| `--type` | `model+prompt-name` (default), `fine-tuned`, or `agent`. |
| `--description` | One-line description recorded in `metadata.json`. |
| `--contact` | Contact (e.g. email) recorded in `metadata.json` |
| `--code-url` / `--paper-url` | Optional links recorded in `metadata.json`. |
| `--rewriter-model` | Modes B/C only: the model that rewrites the products and prices the estimated `cost_per_rewrite_usd` (default `openai/gpt-4.1`). Any OpenRouter model ID — the rewriter is always routed via OpenRouter; unconfigured models get a default output cap and report `n/a` cost if unpriced. (Mode A ignores it — cost is left `null`.) |
| `--judges` | Comma-separated models to score against (default: the 5 leaderboard judges). You may add extras for your own benchmarking — **the 5 leaderboard judges are always required**. Whatever you run is recorded in `metadata.json`'s `judges` and `results.json`'s `per_ranker`. |
| `--mode {score,rewrite,optimize}` | Which mode to run: **score** (A — score a `--rewrites` file), **rewrite** (B — rewrite with `--prompt`, no optimization), **optimize** (C — prompt-optimize `--prompt`, then rewrite). Inferred when omitted: `score` with `--rewrites`, `optimize` with `--prompt`. |
| `--rerank-model` | **Mode C** only: comma-separated model(s) the prompt-optimization loop reranks with to score candidate prompts (default `openai/gpt-4.1`). |
| `--meta-model` | **Mode C** only: the model that drives the prompt-improvement loop (default `openai/gpt-4.1`). |
| `--num-epochs` | **Mode C** only: number of prompt-optimization epochs (default 2). |
| `--batch-size` | Queries per batch for rewriting/scoring (default 100). |
| `--max-train-queries` / `--max-val-queries` | **Mode C** only: cap the train/val splits for cheaper optimization (default: full split). |
| `--max-test-queries N` | Cap test queries for a cheap smoke test (a real submission scores all). |
| `--output-dir` | Where to write the submission bundle (default `submissions/<team-name>_<timestamp>/`). |
| `--seed` | RNG seed (default 42). |
| `--validate-only` | Pre-flight the input and exit without any API call (free, no key). |
| `--openrouter-key` | OpenRouter key (else `OPENROUTER_API_KEY` from env/`.env`). |

---

## Prompt-optimization parameters (Mode C)

Mode C runs prompt optimization on your starting prompt. Prompt optimization evolves it over several epochs: the **meta-model** reads how the current prompt performed per judge, proposes an improved prompt, and each candidate is scored by the **rerank model(s)** on the **validation** split. The best-on-validation prompt is kept — **the test set is never touched during optimization** — and that winning prompt then rewrites + scores the test set exactly as Mode B does. You never call the optimization loop yourself: **every knob below is a `submission.py` flag.**

| Flag | Default | What it controls |
|------|---------|------------------|
| `--prompt KEY/PATH/TEXT` | — (required) | The **starting** prompt the optimizer evolves: a method key (e.g. `authoritative`), a `.txt` path, or literal text containing `{description}`. |
| `--meta-model` | `openai/gpt-4.1` | The model that reads each round's results and proposes the next prompt (drives the improvement loop). |
| `--rerank-model` | `openai/gpt-4.1` | Comma-separated model(s) used to **score candidate prompts** on validation. Fewer/cheaper rerankers here make optimization cheaper; final scoring still uses all five judges. |
| `--rewriter-model` | `openai/gpt-4.1` | The model that rewrites products with the winning prompt (any OpenRouter model ID). |
| `--num-epochs` | `2` | Number of optimization epochs (more epochs = more prompt-improvement rounds = higher cost). |
| `--batch-size` | `100` | Queries per batch during optimization and scoring. |
| `--max-train-queries` | full split | Cap the **training** queries optimization runs on (lower = cheaper, noisier). |
| `--max-val-queries` | full split | Cap the **validation** queries used to select the best prompt. |
| `--seed` | `42` | RNG seed for reproducible splits/sampling. |

> Selection is **always** on validation; capping `--max-test-queries` only affects the final score, never the prompt that's chosen. A real submission must leave the test set uncapped.

Nothing above is required — the [default quickstart](#mode-c--quickstart) above runs prompt optimization with every knob at its default. A typical **low-cost** Mode C run caps the splits:

```bash
uv run python src/submission.py \
    --mode optimize --prompt authoritative --name "My Team" --contact you@example.com \
    --meta-model openai/gpt-4.1 --rerank-model openai/gpt-4.1 \
    --num-epochs 2 --batch-size 100 \
    --max-train-queries 200 --max-val-queries 100
```
