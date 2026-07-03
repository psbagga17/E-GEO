"""
Heuristic adversarial-attack benchmark (paper Section 6.1 / Figure 5).

For each of the 14 one-word adversarial attacks x 5 judge re-rankers, over the first
`--batch-size` test queries (200 in the paper):
  1. Rewrite the canonical target product ONCE with GPT-4.1 under the attack prompt
     (the target index is the published one in test_selected_products.json).
  2. Each judge ranks the rewritten listing among its 10 candidates with its native
     system prompt, and reports its questionable_products flag.
  3. Score rank improvement (initial position - rewritten position) and the flag.

Reproduces the released layout under results/REDTEAMING_RESULTS/ADVERSARIAL_BENCHMARK/:
  <judge>/attack_results.csv    # per (attack, query) rows
  heuristic_per_cell.csv        # per (attack, judge) aggregate
  cross_engine_summary.json     # {attack: {judge: stats}}

Run (makes API calls; needs OPENAI_API_KEY + OPENROUTER_API_KEY):
    uv run python src/multi_model_optimization/adversarial_benchmark.py
"""

import argparse
import csv
import json
import math
import os
import sys

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from all_init_prompts import INITIAL_PROMPTS
from config import DATA_DIR, MODEL_PROVIDERS, RESULTS_DIR, SYSTEM_PROMPTS
from llm_helpers import (
    combine_with_initial_rankings,
    optimize_products_parallel,
    rerank_products_parallel,
)
from utils import load_data

# The 14 adversarial attacks, by the paper's one-word names (a subset of INITIAL_PROMPTS).
ATTACKS = [
    "injection", "superlatives", "hidden", "reviews", "stuffing", "formatting",
    "authority", "emotional", "sycophancy", "fabrication", "anchoring", "jargon",
    "negation", "narrative",
]

# The rewriter is fixed to GPT-4.1; the 5 judges are the leaderboard re-rankers.
REWRITER_MODEL = "openai/gpt-4.1"
JUDGE_MODELS = [
    "openai/gpt-5",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2",
    "meta-llama/llama-4-maverick",
]

CSV_FIELDS = [
    "attack_type", "query_id", "target_product_num", "original_pos", "optimized_pos",
    "improvement", "was_flagged", "original_text", "attacked_text", "ranking",
    "questionable_products",
]

OUTPUT_DIR = os.path.join(RESULTS_DIR, "REDTEAMING_RESULTS", "ADVERSARIAL_BENCHMARK")


def _judge_dirname(model: str) -> str:
    """results/.../ADVERSARIAL_BENCHMARK/<judge> dir name (model id's last segment)."""
    return model.split("/")[-1]


def _per_cell_stats(rows: list[dict]) -> dict:
    """Aggregate a list of scored rows (improvement + was_flagged) into cell stats."""
    scored = [r for r in rows if r.get("improvement") is not None]
    n = len(scored)
    if n == 0:
        return {
            "n_queries": 0, "mean_rank_improvement": float("nan"),
            "se_rank_improvement": float("nan"), "median_rank_improvement": float("nan"),
            "std_rank_improvement": float("nan"), "ci_lower": float("nan"),
            "ci_upper": float("nan"), "flag_count": 0, "flag_rate": float("nan"),
            "se_flag_rate": float("nan"),
        }
    imps = [int(r["improvement"]) for r in scored]
    mean = float(np.mean(imps))
    std = float(np.std(imps, ddof=1)) if n > 1 else 0.0
    se = std / math.sqrt(n)
    flag_count = int(sum(1 for r in scored if r["was_flagged"]))
    flag_rate = flag_count / n
    se_flag = math.sqrt(flag_rate * (1 - flag_rate) / n)
    return {
        "n_queries": n,
        "mean_rank_improvement": mean,
        "se_rank_improvement": se,
        "median_rank_improvement": float(np.median(imps)),
        "std_rank_improvement": std,
        "ci_lower": mean - 1.96 * se,
        "ci_upper": mean + 1.96 * se,
        "flag_count": flag_count,
        "flag_rate": flag_rate,
        "se_flag_rate": se_flag,
    }


def _score_rows(attack: str, combined: list[dict]) -> list[dict]:
    """Turn combine_with_initial_rankings output into CSV rows for one (attack, judge)."""
    rows = []
    for r in combined:
        opt = r.get("optimized_ranking")
        init = r.get("initial_ranking")
        if not isinstance(opt, dict) or not isinstance(init, dict):
            continue
        target_num = int(r["rand_idx"]) + 1
        try:
            original_pos = init["ranking"].index(target_num)
            optimized_pos = opt["ranking"].index(target_num)
        except (ValueError, KeyError):
            continue
        was_flagged = str(r.get("optimized_product_is_questionable")) == "True"
        rows.append({
            "attack_type": attack,
            "query_id": r["query_id"],
            "target_product_num": target_num,
            "original_pos": original_pos,
            "optimized_pos": optimized_pos,
            "improvement": r.get("improvement"),
            "was_flagged": was_flagged,
            "original_text": r.get("initial_product", ""),
            "attacked_text": r.get("optimized_product", ""),
            "ranking": opt.get("ranking", []),
            "questionable_products": opt.get("questionable_products", []),
        })
    return rows


def _write_csv(path: str, rows: list[dict]):
    write_header = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            w.writeheader()
        for r in rows:
            out = dict(r)
            out["ranking"] = json.dumps(out["ranking"])
            out["questionable_products"] = json.dumps(out["questionable_products"])
            w.writerow(out)


def run_benchmark(attacks: list[str], judges: list[str], batch_size: int):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    test_data = load_data(os.path.join(DATA_DIR, "test_data.json"))
    query_ids = list(test_data.keys())[:batch_size]
    batch = {qid: test_data[qid] for qid in query_ids}
    print(f"[adv] {len(attacks)} attacks x {len(judges)} judges x {len(query_ids)} queries")

    # Reset per-judge CSVs so a fresh run doesn't accumulate stale rows.
    for model in judges:
        jdir = os.path.join(OUTPUT_DIR, _judge_dirname(model))
        os.makedirs(jdir, exist_ok=True)
        csv_path = os.path.join(jdir, "attack_results.csv")
        if os.path.exists(csv_path):
            os.remove(csv_path)

    cross_engine: dict[str, dict[str, dict]] = {}
    per_cell_rows = []

    for attack in attacks:
        print(f"\n[adv] === attack: {attack} ===")
        template = INITIAL_PROMPTS[attack]
        # Rewrite the canonical target once (isTest=True reads test_selected_products.json).
        optimized = optimize_products_parallel(
            batch, REWRITER_MODEL, template, MODEL_PROVIDERS[REWRITER_MODEL], isTest=True
        )
        cross_engine[attack] = {}
        for model in judges:
            reranked, _, _ = rerank_products_parallel(
                [dict(o) for o in optimized], test_data, model, SYSTEM_PROMPTS[model],
                MODEL_PROVIDERS[model],
            )
            combined = combine_with_initial_rankings(model, reranked, split="test")
            rows = _score_rows(attack, combined)
            stats = _per_cell_stats(rows)
            cross_engine[attack][_judge_dirname(model)] = stats
            per_cell_rows.append({"attack_name": attack, "engine": _judge_dirname(model),
                                  **{k: stats[k] for k in (
                                      "n_queries", "mean_rank_improvement",
                                      "se_rank_improvement", "flag_rate", "se_flag_rate")},
                                  "n_flagged": stats["flag_count"],
                                  "n_evaluated": stats["n_queries"]})
            _write_csv(os.path.join(OUTPUT_DIR, _judge_dirname(model), "attack_results.csv"), rows)
            print(f"[adv]   {_judge_dirname(model):<24} n={stats['n_queries']} "
                  f"mean_imp={stats['mean_rank_improvement']:+.3f} "
                  f"flag_rate={stats['flag_rate']:.3f}")

    with open(os.path.join(OUTPUT_DIR, "cross_engine_summary.json"), "w") as f:
        json.dump(cross_engine, f, indent=2)

    per_cell_cols = ["attack_name", "engine", "n_queries", "mean_rank_improvement",
                     "se_rank_improvement", "flag_rate", "se_flag_rate", "n_flagged",
                     "n_evaluated"]
    with open(os.path.join(OUTPUT_DIR, "heuristic_per_cell.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=per_cell_cols)
        w.writeheader()
        w.writerows(per_cell_rows)

    print(f"\n[adv] done. results in {OUTPUT_DIR}/")


def main():
    parser = argparse.ArgumentParser(description="Heuristic 14-attack adversarial benchmark.")
    parser.add_argument("--attacks", nargs="+", default=["all"],
                        help=f"attack names (default: all). choices: {ATTACKS}")
    parser.add_argument("--judges", nargs="+", default=["all"],
                        help=f"judge model ids (default: all). choices: {JUDGE_MODELS}")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    attacks = ATTACKS if args.attacks == ["all"] else args.attacks
    unknown = [a for a in attacks if a not in INITIAL_PROMPTS]
    if unknown:
        parser.error(f"unknown attacks: {unknown}")
    judges = JUDGE_MODELS if args.judges == ["all"] else args.judges
    unknown = [j for j in judges if j not in SYSTEM_PROMPTS]
    if unknown:
        parser.error(f"unknown judges: {unknown}")

    load_dotenv()
    np.random.seed(42)
    config.DATA_DIR = DATA_DIR
    run_benchmark(attacks, judges, args.batch_size)


if __name__ == "__main__":
    main()
