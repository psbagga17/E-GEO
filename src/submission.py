import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

_SRC = os.path.dirname(os.path.abspath(__file__))
for _p in (_SRC, os.path.join(_SRC, "multi_model_optimization")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config
import llm_helpers
import run_meta_optimization as mopt
from all_init_prompts import INITIAL_PROMPTS
from analysis import analyze_results
from config import MODEL_NAMES, SYSTEM_PROMPTS
from llm_helpers import (
    combine_with_initial_rankings,
    optimize_products_parallel,
    rerank_products_parallel,
)
from prompts import get_optimizing_prompt
from run_meta_optimization import run_multi_llm
from utils import load_data

JUDGE_PREFIX = {
    "openai/gpt-5": "gpt_5",
    "anthropic/claude-sonnet-4.5": "claude_sonnet_4_5",
    "google/gemini-3-flash-preview": "gemini_3_flash_preview",
    "deepseek/deepseek-v3.2": "deepseek_v3_2",
    "meta-llama/llama-4-maverick": "llama_4_maverick",
}

REPO_ROOT = Path(__file__).resolve().parents[1]


def _chunks(ids, size):
    for i in range(0, len(ids), size):
        yield ids[i : i + size]


def _parse_models(spec: str) -> list[str]:
    """Comma-separated model ids -> list (whitespace tolerated)."""
    return [m.strip() for m in spec.split(",") if m.strip()]


_OPTIMIZED_PROMPTS_PATH = Path(__file__).resolve().parent / "optimized_prompts.json"
OPTIMIZED_PROMPTS = (
    json.loads(_OPTIMIZED_PROMPTS_PATH.read_text())
    if _OPTIMIZED_PROMPTS_PATH.is_file()
    else {}
)


def _resolve_prompt(prompt_arg: str) -> str:
    """A method key (e.g. 'authoritative'), 'optimized:<style>' (an entry of
    src/optimized_prompts.json), a path to a .txt file, or literal prompt text."""
    if prompt_arg.startswith("optimized:"):
        key = prompt_arg.split(":", 1)[1]
        if key in OPTIMIZED_PROMPTS:
            return OPTIMIZED_PROMPTS[key]
        sys.exit(
            f"ERROR: unknown optimized prompt '{key}'. "
            f"Available: {', '.join(sorted(OPTIMIZED_PROMPTS))}"
        )
    if prompt_arg in INITIAL_PROMPTS:
        return INITIAL_PROMPTS[prompt_arg]
    if os.path.isfile(prompt_arg):
        with open(prompt_arg) as f:
            return f.read()
    return prompt_arg


def _load_rewrites(path: str) -> list[dict]:
    """Load a submitter's rewrites file (a JSON array or JSONL) into rows.

    Rows use the canonical submission keys {query_id, rand_idx, optimized_product, initial_product}
    """
    text = Path(path).read_text().strip()
    if not text:
        sys.exit(f"ERROR: {path} is empty.")
    try:
        rows = json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("rewrites", [])
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(rows, list):
        sys.exit(f"ERROR: {path} must be a JSON array or JSONL of rewrite objects.")
    return rows


def _validate_rewrites(
    optimized: list[dict], test_data: dict, data_dir: str
) -> list[str]:
    """
    Verifies each row is well-formed (carries the baseline initial_product and a non-empty rewrite), that the rewritten product index matches the fixed published target for that query, and that every (capped) test query has exactly one rewrite.
    """
    selected = load_data(os.path.join(data_dir, "test_selected_products.json"))
    errors = []
    counts = {}
    for i, row in enumerate(optimized):
        qid = str(row.get("query_id")) if row.get("query_id") is not None else ""
        if not qid:
            errors.append(f"row {i}: missing query_id")
            continue
        counts[qid] = counts.get(qid, 0) + 1
        if not row.get("optimized_product"):
            errors.append(f"query {qid}: empty rewritten description")
        if not row.get("initial_product"):
            errors.append(f"query {qid}: missing initial_product")
        if row.get("rand_idx") is None:
            errors.append(f"query {qid}: missing rand_idx")
        elif qid in selected and int(row["rand_idx"]) != int(selected[qid]["ind"]):
            errors.append(
                f"query {qid}: rand_idx {row['rand_idx']} != fixed test product index {selected[qid]['ind']}"
            )

    missing = set(test_data.keys()) - set(counts)
    if missing:
        errors.append(
            f"{len(missing)} test queries have no rewrite (e.g. {sorted(missing)[:5]})"
        )
    dupes = [q for q, c in counts.items() if c > 1]
    if dupes:
        errors.append(f"duplicate rewrites for {len(dupes)} queries (e.g. {dupes[:5]})")
    return errors


def evaluate_prompt(
    prompt_text: str,
    test_data: dict,
    judges: list[str],
    rewriter_model: str,
    out_dir: Path,
    batch_size: int,
):
    """Rewrite the fixed test products with `prompt_text`, then score them (modes B/C)."""
    test_ids = list(test_data.keys())
    optimized = []
    for batch in _chunks(test_ids, batch_size):
        batch_data = {k: test_data[k] for k in batch}
        optimized += optimize_products_parallel(
            batch_data, rewriter_model, prompt_text, "openrouter", isTest=True
        )
    return score_rewrites(optimized, test_data, judges, out_dir, batch_size)


def score_rewrites(
    optimized: list[dict],
    test_data: dict,
    judges: list[str],
    out_dir: Path,
    batch_size: int,
):
    """Rerank already-rewritten products across `judges`, returning (per_judge_metrics, rewrites).Each item has the pipeline shape {query_id, rand_idx, optimized_product, initial_product}. Routes via OpenRouter."""
    test_ids = list(test_data.keys())
    print(
        f"\n{'#'*70}\n# EVAL — {len(test_ids)} queries across {len(judges)} judges\n{'#'*70}"
    )

    per_judge = {}
    per_query_judges = {}
    for model in judges:
        judge_name = MODEL_NAMES.get(model, model)
        judge_key = JUDGE_PREFIX.get(model, model)
        print(f"\n--- reranking with {judge_name} ---")
        combined = []
        judge_in = judge_out = 0
        for batch in _chunks(test_ids, batch_size):
            batch_ids = set(batch)
            batch_optimized = [r for r in optimized if str(r["query_id"]) in batch_ids]
            batch_data = {k: test_data[k] for k in batch if k in test_data}
            reranked, in_tok, out_tok = rerank_products_parallel(
                batch_optimized, batch_data, model, SYSTEM_PROMPTS[model], "openrouter"
            )
            judge_in += in_tok
            judge_out += out_tok
            combined += combine_with_initial_rankings(model, reranked, split="test")

        judge_dir = out_dir / judge_name
        judge_dir.mkdir(parents=True, exist_ok=True)
        csv_path = judge_dir / "results.csv"
        pd.DataFrame(combined).to_csv(csv_path, index=False)

        price_in, price_out = config.PRICING.get(model, (0.0, 0.0))
        judge_usd = judge_in / 1e6 * price_in + judge_out / 1e6 * price_out
        try:
            stats = analyze_results(str(csv_path), str(judge_dir))
            per_judge[model] = {
                "mean": float(stats["mean"]),
                "se": float(stats["standard_error"]),
                "n": int(stats["total"]),
                "improvement_rate": float(stats["improvement_rate"]),
                "input_tokens": int(judge_in),
                "output_tokens": int(judge_out),
                "usd": round(judge_usd, 4),
            }
            print(
                f"  {judge_name}: mean={stats['mean']:+.4f} (se={stats['standard_error']:.4f}, n={stats['total']})"
            )
        except Exception as e:
            per_judge[model] = None
            print(
                f"  WARNING: {judge_name} produced no usable score "
                f"({type(e).__name__}: {e}); marking it incomplete."
            )
        for row in combined:
            qid = str(row["query_id"])
            per_query_judges.setdefault(qid, {})[judge_key] = {
                "improvement": row.get("improvement"),
                "questionable": row.get("optimized_product_is_questionable"),
            }

    rewrites = [
        {
            "query_id": item["query_id"],
            "rand_idx": item["rand_idx"],
            "initial_product": item.get("initial_product"),
            "optimized_product": item.get("optimized_product"),
            "judges": per_query_judges.get(str(item["query_id"]), {}),
        }
        for item in optimized
    ]
    return per_judge, rewrites


def _configure_meta_opt(rerank_models, meta_model):
    orig_opt = mopt.optimize_products_parallel
    orig_rerank = mopt.rerank_products_parallel
    orig_meta = mopt.meta_optimize_cross_engine

    def opt(data, model, prompt_template, provider, isTest=False):
        return orig_opt(data, model, prompt_template, "openrouter", isTest=isTest)

    def rerank(optimized_results, test_data, model, system_prompt, provider):
        return orig_rerank(
            optimized_results, test_data, model, system_prompt, "openrouter"
        )

    def meta(*args, **kwargs):
        kwargs.setdefault("meta_model", meta_model)
        kwargs["meta_provider"] = "openrouter"
        return orig_meta(*args, **kwargs)

    mopt.optimize_products_parallel = opt
    mopt.rerank_products_parallel = rerank
    mopt.meta_optimize_cross_engine = meta
    mopt.MODEL_REGISTRY = list(rerank_models)


def _read_best_prompt(
    mopt_out: Path, method_key: str, num_epochs: int, fallback: str
) -> str:
    """The prompt-optimization loop writes the best (validation-selected) prompt to the last epoch's testing dir."""
    last = num_epochs - 1
    candidate = (
        mopt_out / method_key / f"epoch_{last}" / f"testing_{last}" / "prompt.txt"
    )
    if candidate.is_file():
        return candidate.read_text()
    prompts = sorted(
        (mopt_out / method_key).rglob("prompt.txt"), key=lambda p: p.stat().st_mtime
    )
    if prompts:
        return prompts[-1].read_text()
    print("WARNING: no optimized prompt found, falling back to the initial prompt.")
    return fallback


def _describe_run(args, rerank_models):
    """Return (mode, run_config) for metadata.json."""
    if args.rewrites:
        return "A: score provided rewrites", None
    if not args.optimize:
        return "B: rewrite with provided prompt (no optimization)", {
            "rewriter_model": args.rewriter_model,
            "optimized": False,
            "optimization": None,
        }
    return "C: optimize prompt, then rewrite", {
        "rewriter_model": args.rewriter_model,
        "optimized": True,
        "optimization": {
            "meta_model": args.meta_model,
            "rerank_models": rerank_models,
            "num_epochs": args.num_epochs,
            "batch_size": args.batch_size,
            "max_train_queries": args.max_train_queries,
            "max_val_queries": args.max_val_queries,
        },
    }


def build_metadata(
    name,
    rewriter_type,
    mode,
    judges,
    description,
    cost_per_rewrite_usd,
    contact,
    code_url,
    paper_url,
    run_config,
):
    """The submission's metadata.json"""
    return {
        "name": name,
        "type": rewriter_type,
        "mode": mode,
        "judges": list(judges),
        "description": description,
        "cost_per_rewrite_usd": cost_per_rewrite_usd,
        "query_blind": True,
        "contact": contact,
        "code_url": code_url,
        "paper_url": paper_url,
        "run_config": run_config,
        "is_paper_baseline": False,
    }


def build_results(
    metrics,
    total_queries_scored,
    total_input_tokens,
    total_output_tokens,
    estimated_usd_cost,
):
    """The submission's results.json — per_ranker mean/se for all five judges + totals."""
    per_ranker = {}
    for model, prefix in JUDGE_PREFIX.items():
        m = metrics.get(model)
        per_ranker[prefix] = {
            "mean": round(m["mean"], 4) if m else None,
            "se": round(m["se"], 4) if m else None,
        }
    # Include any extra judges beyond the 5 leaderboard models (keyed by a sanitized model id).
    for model, m in metrics.items():
        if model in JUDGE_PREFIX or not m:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
        per_ranker[key] = {"mean": round(m["mean"], 4), "se": round(m["se"], 4)}
    return {
        "per_ranker": per_ranker,
        "total_queries_scored": total_queries_scored,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_usd_cost": estimated_usd_cost,
    }


def _estimate_cost_per_rewrite(rewrites, prompt_text, rewriter_model):
    """Estimate the average USD to produce one rewrite (modes B/C only).

    The rewriter call doesn't hand back billed token counts, so we estimate  using a ~4-chars/token heuristic and config.PRICING for the rewriter:
        input  = the optimizing system prompt + the rewrite prompt + the original product
        output = the rewrite itself
    Output is capped at ~500 tokens by MAX_COMPLETION_TOKENS_OPTIMIZATION
    """
    pricing = config.PRICING.get(rewriter_model)
    if not rewrites or pricing is None:
        return None
    price_in, price_out = pricing
    fixed_input_chars = len(get_optimizing_prompt()) + len(prompt_text)
    costs = []
    for r in rewrites:
        in_tok = (fixed_input_chars + len(r.get("initial_product") or "")) / 4
        out_tok = len(r.get("optimized_product") or "") / 4
        costs.append((in_tok * price_in + out_tok * price_out) / 1e6)
    return round(sum(costs) / len(costs), 6)


def main():
    parser = argparse.ArgumentParser(
        description="Score an E-GEO submission and write its leaderboard bundle."
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Initial prompt: a method key, a .txt path, or literal text containing {description}. Mutually exclusive with --rewrites.",
    )
    parser.add_argument(
        "--rewrites",
        default=None,
        help="Path to a JSON/JSONL of already-rewritten products to score (mode A). Mutually exclusive with --prompt.",
    )
    parser.add_argument(
        "--name", required=True, help="Rewriter name for the leaderboard card"
    )
    parser.add_argument(
        "--type",
        default="model+prompt",
        choices=["model+prompt", "fine-tuned", "agent"],
    )
    parser.add_argument("--description", default="", help="Optional card description")
    parser.add_argument(
        "--contact",
        default="",
        help="Contact (e.g. email) recorded in metadata.json so we can reach you",
    )
    parser.add_argument(
        "--code-url",
        default=None,
        help="Optional link to the code that produced the rewrites",
    )
    parser.add_argument(
        "--paper-url", default=None, help="Optional link to the associated paper"
    )
    parser.add_argument(
        "--rewriter-model",
        default="openai/gpt-4.1",
        help="Model that rewrites the product descriptions",
    )
    parser.add_argument(
        "--judges",
        default=",".join(JUDGE_PREFIX.keys()),
        help="Comma-separated models to score against (default: the 5 leaderboard judges). You may "
        "add extra models; the 5 leaderboard judges are always required. "
        "Your run is recorded in metadata.json's `judges` and results.json's `per_ranker`.",
    )
    parser.add_argument(
        "--rerank-model",
        default="openai/gpt-4.1",
        help="Comma-separated model(s) the prompt-optimization loop reranks with to score candidate prompts (default: gpt-4.1)",
    )
    parser.add_argument(
        "--meta-model",
        default="openai/gpt-4.1",
        help="Model that drives the prompt-improvement loop (default: gpt-4.1)",
    )
    parser.add_argument(
        "--openrouter-key",
        default=None,
        help="OpenRouter key (else uses $OPENROUTER_API_KEY / .env)",
    )
    parser.add_argument(
        "--mode",
        choices=["score", "rewrite", "optimize"],
        default=None,
        help="Submission mode: 'score' (Mode A — score a --rewrites file), 'rewrite' (Mode B — "
        "rewrite the test products with your --prompt, no optimization), or 'optimize' (Mode C — "
        "prompt-optimize your --prompt, then rewrite). Inferred when omitted: 'score' with --rewrites, "
        "'optimize' with --prompt.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Pre-flight only: validate the rewrites (mode A) or prompt (mode B/C) and exit "
        "without calling any model. Free; needs no API key.",
    )
    parser.add_argument(
        "--num-epochs",
        type=int,
        default=2,
        help="Mode C: number of prompt-optimization epochs (default 2; more = more prompt-improvement rounds and higher cost).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Queries per batch for optimization/rewriting/scoring (default 100).",
    )
    parser.add_argument(
        "--max-train-queries",
        type=int,
        default=None,
        help="Mode C: cap the training queries (default: full train split).",
    )
    parser.add_argument(
        "--max-val-queries",
        type=int,
        default=None,
        help="Mode C: cap the validation queries used to pick the best prompt (default: full val split).",
    )
    parser.add_argument(
        "--max-test-queries",
        type=int,
        default=None,
        help="Cap test queries scored at the end (use a small value for smoke tests; a real submission scores all).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Where to write the submission bundle (default: submissions/<team-name>_<timestamp>/).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducible splits/sampling (default 42).",
    )
    args = parser.parse_args()

    if bool(args.rewrites) == bool(args.prompt):
        sys.exit(
            "ERROR: provide exactly one of --rewrites (score given rewrites) or --prompt (rewrite/optimize)."
        )

    if args.mode is None:
        args.mode = "score" if args.rewrites else "optimize"
    if args.mode == "score" and not args.rewrites:
        sys.exit(
            "ERROR: --mode score scores a --rewrites file; pass --rewrites (not --prompt)."
        )
    if args.mode in ("rewrite", "optimize") and not args.prompt:
        sys.exit(f"ERROR: --mode {args.mode} needs a --prompt (not --rewrites).")
    args.optimize = args.mode == "optimize"

    if args.openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = args.openrouter_key
    load_dotenv()
    if not args.validate_only and not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit(
            "ERROR: no OpenRouter key. Pass --openrouter-key or set OPENROUTER_API_KEY in .env"
        )

    np.random.seed(args.seed)

    data_dir = str(REPO_ROOT / "data")
    config.DATA_DIR = data_dir
    llm_helpers.DATA_DIR = data_dir
    if not os.path.isfile(os.path.join(data_dir, "test_data.json")):
        sys.exit(f"ERROR: dataset not found in {data_dir} — run `git lfs pull` first.")

    judges = _parse_models(args.judges)
    rerank_models = _parse_models(args.rerank_model)
    known = set(config.SYSTEM_PROMPTS) & set(config.INITIAL_RANKINGS)
    bad = [m for m in judges + rerank_models if m not in known]
    if bad:
        sys.exit(f"ERROR: unknown model(s): {bad}. Known: {sorted(known)}")

    missing_judges = set(JUDGE_PREFIX) - set(judges)
    if missing_judges:
        sys.exit(
            "ERROR: all five leaderboard rankers are required; partial submissions are not "
            f"accepted in v1. Missing: {sorted(MODEL_NAMES.get(m, m) for m in missing_judges)}"
        )

    if (
        args.prompt
        and args.rewriter_model not in config.MAX_COMPLETION_TOKENS_OPTIMIZATION
    ):
        config.MAX_COMPLETION_TOKENS_OPTIMIZATION[args.rewriter_model] = 500
        print(
            f"Note: '{args.rewriter_model}' isn't a preconfigured model; rewriting via "
            "OpenRouter with a default 500-token output cap. If it rejects a temperature "
            "param, add it to config.NO_TEMPERATURE_MODELS; cost shows n/a unless priced."
        )

    test_data = load_data(os.path.join(data_dir, "test_data.json"))
    if args.max_test_queries is not None:
        test_data = {
            k: test_data[k] for k in list(test_data.keys())[: args.max_test_queries]
        }

    optimized = None
    prompt = None
    if args.rewrites:
        optimized = _load_rewrites(args.rewrites)
        optimized = [r for r in optimized if str(r.get("query_id")) in test_data]
        errors = _validate_rewrites(optimized, test_data, data_dir)
        if errors:
            print("Rewrites failed validation:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print(
            f"Validation passed: {len(optimized)} rewrites cover {len(test_data)} test queries."
        )
    else:
        prompt = _resolve_prompt(args.prompt)
        if "{description}" not in prompt:
            sys.exit("ERROR: the prompt must contain the '{description}' placeholder.")
        print("Validation passed: prompt resolves and contains '{description}'.")

    if args.validate_only:
        print("Validate-only: no API calls made. Exiting.")
        sys.exit(0)

    team_name = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    out_dir = (
        Path(args.output_dir)
        if args.output_dir
        else REPO_ROOT / "submissions" / f"{team_name}_{int(time.time())}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {out_dir}")

    if args.rewrites:
        print(f"Scoring rewrites from {args.rewrites} | Judges: {len(judges)}")
        did_optimize = False
        metrics, rewrites = score_rewrites(
            optimized, test_data, judges, out_dir, args.batch_size
        )
        cost_per_rewrite = None
    else:
        did_optimize = args.optimize

        print(
            f"Rewriter: {args.rewriter_model} | Judges: {len(judges)} | Optimize: {args.optimize}"
        )
        if args.optimize:
            print(f"Reranker(s): {rerank_models} | meta-model: {args.meta_model}")
            method_key = f"submission_{team_name}"
            INITIAL_PROMPTS[method_key] = prompt
            _configure_meta_opt(rerank_models, args.meta_model)
            mopt_out = out_dir / "optimization"
            run_multi_llm(
                data_path=data_dir,
                output_dir=str(mopt_out),
                batch_size=args.batch_size,
                num_epochs=args.num_epochs,
                rewriter_model=args.rewriter_model,
                method=method_key,
                max_train_queries=args.max_train_queries,
                max_val_queries=args.max_val_queries,
                max_test_queries=1,
            )
            prompt = _read_best_prompt(mopt_out, method_key, args.num_epochs, prompt)

        metrics, rewrites = evaluate_prompt(
            prompt, test_data, judges, args.rewriter_model, out_dir, args.batch_size
        )
        cost_per_rewrite = _estimate_cost_per_rewrite(
            rewrites, prompt, args.rewriter_model
        )

    rewrites_path = out_dir / "rewrites.jsonl"
    with open(rewrites_path, "w") as f:
        for row in rewrites:
            f.write(json.dumps(row) + "\n")

    incomplete = [
        MODEL_NAMES.get(model, model)
        for model in JUDGE_PREFIX
        if metrics.get(model) is None
        or metrics[model].get("mean") is None
        or not np.isfinite(metrics[model]["mean"])
    ]
    if incomplete:
        sys.exit(
            "ERROR: partial submission — these rankers produced no score: "
            f"{sorted(incomplete)}. All five are required; not writing results."
        )

    total_in = sum(int(m.get("input_tokens", 0)) for m in metrics.values() if m)
    total_out = sum(int(m.get("output_tokens", 0)) for m in metrics.values() if m)
    total_usd = round(sum(float(m.get("usd", 0.0)) for m in metrics.values() if m), 4)

    mode, run_config = _describe_run(args, rerank_models)
    metadata = build_metadata(
        args.name,
        args.type,
        mode,
        judges,
        args.description,
        cost_per_rewrite,
        args.contact,
        args.code_url,
        args.paper_url,
        run_config,
    )
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    results = build_results(metrics, len(test_data), total_in, total_out, total_usd)
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    summary = {
        "name": args.name,
        "rewriter_model": None if args.rewrites else args.rewriter_model,
        "optimized": did_optimize,
        "num_test_queries": len(test_data),
        "prompt": prompt,
        "cost_per_rewrite_usd": cost_per_rewrite,
        "metrics": metrics,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "estimated_usd_cost": total_usd,
    }
    with open(out_dir / "run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*70}\nDONE\n{'='*70}")
    print(f"{'Judge':<22}{'mean':>12}{'se':>12}")
    for model in judges:
        name = MODEL_NAMES.get(model, model)
        m = metrics.get(model) or {}
        print(
            f"{name:<22}{m.get('mean', float('nan')):>12.4f}{m.get('se', float('nan')):>12.4f}"
        )
    cost_str = (
        f"${cost_per_rewrite:.6f}"
        if cost_per_rewrite is not None
        else "n/a (unpriced model)"
    )
    print(f"\nCost per rewrite: {cost_str}  (priced as {args.rewriter_model})")
    print(
        f"Actual eval spend: ${total_usd:,.2f}  (in {total_in:,} tok, out {total_out:,} tok)"
    )
    print(f"\nMetadata: {out_dir / 'metadata.json'}")
    print(f"Results:  {out_dir / 'results.json'}")
    print(f"Rewrites: {rewrites_path}  ({len(rewrites)} rows)")
    print(f"Summary:  {out_dir / 'run_summary.json'}")
    print(
        f"\nTo submit: open a PR to the public E-GEO repo "
        f"(https://github.com/psbagga17/E-GEO) committing the three files above from\n  {out_dir}\n"
        "(metadata.json + results.json + rewrites.jsonl — the per-judge CSV folders, optimization/, and "
        "run_summary.json are local extras). On merge, the leaderboard updates."
    )


if __name__ == "__main__":
    main()
