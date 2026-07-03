import json
import os
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from all_init_prompts import INITIAL_PROMPTS
from analysis import analyze_results
from config import (
    BATCH_SIZE,
    DATA_DIR,
    RESULTS_DIR,
    MODEL_NAMES,
    MODEL_PROVIDERS,
    SYSTEM_PROMPTS,
    ALL_MODELS,
)
from llm_helpers import combine_with_initial_rankings, rerank_products_parallel
from utils import load_data

INITIAL_PROMPT_RESULTS_DIR = os.path.join(RESULTS_DIR, "INITIAL_PROMPT_RESULTS")


def load_optimized_products(
    prompt_name: str,
    base_dir: str = INITIAL_PROMPT_RESULTS_DIR,
    filename: str = "test_results.csv",
) -> list[dict]:
    # csv_path = os.path.join(base_dir, prompt_name, filename)
    csv_path = os.path.join(base_dir, filename)
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"No optimized products found at {csv_path}")
    df = pd.read_csv(csv_path)
    return df[["query_id", "rand_idx", "optimized_product"]].to_dict(orient="records")


def run_testing(
    prompt_names: list[str],
    output_dir: str,
    input_dir: str = INITIAL_PROMPT_RESULTS_DIR,
):
    test_data = load_data(os.path.join(DATA_DIR, "test_data.json"))
    test_query_ids = list(test_data.keys())
    num_batches = (len(test_query_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Test queries: {len(test_query_ids)} | Batches: {num_batches}")

    all_results = {}

    for prompt_name in prompt_names:
        print(f"\n{'='*60}\nInitial prompt: {prompt_name}\n{'='*60}")

        prompt_dir = os.path.join(output_dir, prompt_name)
        os.makedirs(prompt_dir, exist_ok=True)

        optimized_results = load_optimized_products(prompt_name, base_dir=input_dir)
        print(f"  Loaded {len(optimized_results)} optimized products")

        prompt_perf = {}

        for model in ALL_MODELS:
            print(f"  Reranking with {MODEL_NAMES[model]}...")
            system_prompt = SYSTEM_PROMPTS[model]
            provider = MODEL_PROVIDERS[model]

            combined_results = []
            model_input_tokens = 0
            model_output_tokens = 0

            for batch in range(num_batches):
                batch_ids = set(
                    test_query_ids[batch * BATCH_SIZE : (batch + 1) * BATCH_SIZE]
                )
                batch_optimized = [
                    r for r in optimized_results if str(r["query_id"]) in batch_ids
                ]
                batch_data = {k: test_data[k] for k in batch_ids if k in test_data}

                reranked, in_tok, out_tok = rerank_products_parallel(
                    batch_optimized, batch_data, model, system_prompt, provider
                )
                combined_results += combine_with_initial_rankings(model, reranked)
                model_input_tokens += in_tok
                model_output_tokens += out_tok

            model_dir = os.path.join(prompt_dir, MODEL_NAMES[model])
            os.makedirs(model_dir, exist_ok=True)
            csv_path = os.path.join(model_dir, "test_results.csv")
            pd.DataFrame(combined_results).to_csv(csv_path, index=False)

            perf = analyze_results(csv_path)
            prompt_perf[MODEL_NAMES[model]] = {
                k: (float(v) if hasattr(v, "item") else v)
                for k, v in perf.items()
                if k != "improvements"
            }

            print(
                f"  {MODEL_NAMES[model]}: mean={perf['mean']:.3f}, improvement_rate={perf['improvement_rate']:.1f}%"
                f"  |  tokens: {model_input_tokens:,} in / {model_output_tokens:,} out"
            )

        all_results[prompt_name] = prompt_perf

    out_file = os.path.join(output_dir, "initial_prompt_performance.json")
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to {out_file}")

    return all_results


if __name__ == "__main__":
    load_dotenv()
    np.random.seed(42)

    # CHANGE THIS WHEN TESTING DIFFERENT INITIAL PROMPTS - currently set to test all
    prompt_names = list(INITIAL_PROMPTS.keys())
    print(f"Found {len(prompt_names)} initial prompts: {prompt_names}")

    out_dir = os.path.join(RESULTS_DIR, "INITIAL_PROMPT_RESULTS")
    os.makedirs(out_dir, exist_ok=True)

    # To read from tmp/gpt-4.1/ instead of the default results dir, pass input_dir:
    run_testing(prompt_names, out_dir, input_dir=INITIAL_PROMPT_RESULTS_DIR)
