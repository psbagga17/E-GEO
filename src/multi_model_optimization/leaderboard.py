import json
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from all_init_prompts import INITIAL_PROMPTS
from analysis import analyze_results
from config import (
    ALL_MODELS,
    BATCH_SIZE,
    DATA_DIR,
    MODEL_NAMES,
    MODEL_PROVIDERS,
    RESULTS_DIR,
    SYSTEM_PROMPTS,
)
from llm_helpers import combine_with_initial_rankings, rerank_products_parallel
from utils import load_data

OPTIMIZER_RESULTS_DIR = os.path.join(RESULTS_DIR, "INITIAL_PROMPT_RESULTS")
LEADERBOARD_DIR = os.path.join(RESULTS_DIR, "LEADERBOARD_RESULTS")

OPTIMIZER_MODELS = ALL_MODELS
RERANKER_MODELS = ALL_MODELS
PROMPT_NAMES = [INITIAL_PROMPTS["simple"]]


def load_optimized_products(
    optimizer_name: str,
    prompt_name: str,
    base_dir: str = OPTIMIZER_RESULTS_DIR,
    filename: str = "test_results.csv",
) -> list[dict]:
    csv_path = os.path.join(base_dir, optimizer_name, prompt_name, filename)
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(
            f"No optimized results at {csv_path} — run optimizing_initial_prompts.py first"
        )
    df = pd.read_csv(csv_path)
    return df[["query_id", "rand_idx", "optimized_product"]].to_dict(orient="records")


def run_leaderboard(
    optimizer_models: list[str],
    reranker_models: list[str],
    prompt_names: list[str],
    output_dir: str,
):
    test_data = load_data(os.path.join(DATA_DIR, "test_data.json"))
    test_query_ids = list(test_data.keys())
    num_batches = (len(test_query_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Test queries: {len(test_query_ids)} | Batches: {num_batches}")

    # leaderboard[row_label][reranker_name] = {"mean": ..., "sem": ...}
    leaderboard: dict[str, dict[str, dict]] = {}

    for optimizer_model in optimizer_models:
        optimizer_name = MODEL_NAMES[optimizer_model]

        for prompt_name in prompt_names:
            row_label = f"{optimizer_name}+{prompt_name}"
            print(f"\n{'='*60}\n{row_label}\n{'='*60}")

            try:
                optimized_results = load_optimized_products(optimizer_name, prompt_name)
            except FileNotFoundError as e:
                print(f"  Skipping: {e}")
                continue
            print(f"  Loaded {len(optimized_results)} optimized products")

            leaderboard[row_label] = {}

            for reranker_model in reranker_models:
                reranker_name = MODEL_NAMES[reranker_model]
                reranker_provider = MODEL_PROVIDERS[reranker_model]
                print(f"  Reranking with {reranker_name}...")

                combined_results = []
                for batch in range(num_batches):
                    batch_ids = set(
                        test_query_ids[batch * BATCH_SIZE : (batch + 1) * BATCH_SIZE]
                    )
                    batch_optimized = [
                        r for r in optimized_results if str(r["query_id"]) in batch_ids
                    ]
                    batch_data = {k: test_data[k] for k in batch_ids if k in test_data}

                    reranked, _, _ = rerank_products_parallel(
                        batch_optimized,
                        batch_data,
                        reranker_model,
                        SYSTEM_PROMPTS[reranker_model],
                        reranker_provider,
                    )
                    combined_results += combine_with_initial_rankings(
                        reranker_model, reranked
                    )

                reranker_dir = os.path.join(
                    output_dir, optimizer_name, prompt_name, reranker_name
                )
                os.makedirs(reranker_dir, exist_ok=True)
                csv_path = os.path.join(reranker_dir, "test_results.csv")
                pd.DataFrame(combined_results).to_csv(csv_path, index=False)

                perf = analyze_results(csv_path)
                sem = perf["std"] / np.sqrt(perf["total"]) if perf["total"] > 0 else 0.0
                leaderboard[row_label][reranker_name] = {
                    "mean": float(perf["mean"]),
                    "sem": float(sem),
                }
                print(f"    {reranker_name}: {perf['mean']:.4f} (±{sem:.4f})")

        _save_leaderboard(leaderboard, reranker_models, output_dir)

    return leaderboard


def _save_leaderboard(leaderboard: dict, reranker_models: list[str], output_dir: str):
    reranker_names = [MODEL_NAMES[m] for m in reranker_models]

    mean_rows, sem_rows, combined_rows = [], [], []
    for row_label, reranker_results in leaderboard.items():
        mean_row = {"Rewriter (Model+Prompt)": row_label}
        sem_row = {"Rewriter (Model+Prompt)": row_label}
        combined_row = {"Rewriter (Model+Prompt)": row_label}
        for name in reranker_names:
            entry = reranker_results.get(name, {})
            m, se = entry.get("mean"), entry.get("sem")
            mean_row[name] = round(m, 4) if m is not None else None
            sem_row[name] = round(se, 4) if se is not None else None
            combined_row[name] = (
                f"{m:.4f} ({se:.4f})" if m is not None and se is not None else None
            )
        mean_rows.append(mean_row)
        sem_rows.append(sem_row)
        combined_rows.append(combined_row)

    pd.DataFrame(mean_rows).to_csv(
        os.path.join(output_dir, "leaderboard_mean.csv"), index=False
    )
    pd.DataFrame(sem_rows).to_csv(
        os.path.join(output_dir, "leaderboard_sem.csv"), index=False
    )
    pd.DataFrame(combined_rows).to_csv(
        os.path.join(output_dir, "leaderboard.csv"), index=False
    )

    with open(os.path.join(output_dir, "leaderboard.json"), "w") as f:
        json.dump(leaderboard, f, indent=2)

    print(f"\nLeaderboard saved to {output_dir}")
    print(pd.DataFrame(mean_rows).to_string(index=False))


if __name__ == "__main__":
    load_dotenv()
    np.random.seed(42)

    os.makedirs(LEADERBOARD_DIR, exist_ok=True)
    run_leaderboard(
        optimizer_models=OPTIMIZER_MODELS,
        reranker_models=RERANKER_MODELS,
        prompt_names=PROMPT_NAMES,
        output_dir=LEADERBOARD_DIR,
    )
