import os
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from all_init_prompts import INITIAL_PROMPTS
from config import BATCH_SIZE, DATA_DIR, MODEL_NAMES, MODEL_PROVIDERS, RESULTS_DIR
from llm_helpers import optimize_products_parallel
from utils import load_data

INITIAL_PROMPT_RESULTS_DIR = os.path.join(RESULTS_DIR, "INITIAL_PROMPT_RESULTS")

REWRITER_MODEL = "openai/gpt-4.1"


def run_testing(prompt_names: list[str], prompt_dir: dict, output_dir: str):
    test_data = load_data(os.path.join(DATA_DIR, "test_data.json"))
    test_query_ids = list(test_data.keys())
    num_batches = (len(test_query_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    provider = MODEL_PROVIDERS[REWRITER_MODEL]
    print(f"Test queries: {len(test_query_ids)} | Batches: {num_batches}")
    print(f"Rewriter: {MODEL_NAMES[REWRITER_MODEL]}")

    for prompt_name in prompt_names:
        print(f"\n{'='*60}\nInitial prompt: {prompt_name}\n{'='*60}")

        prompt_template = prompt_dir[prompt_name]
        prompt_dir = os.path.join(output_dir, MODEL_NAMES[REWRITER_MODEL], prompt_name)
        os.makedirs(prompt_dir, exist_ok=True)

        optimized_results = []
        for batch in range(num_batches):
            batch_ids = test_query_ids[batch * BATCH_SIZE : (batch + 1) * BATCH_SIZE]
            batch_data = {k: test_data[k] for k in batch_ids}
            optimized_results += optimize_products_parallel(
                batch_data, REWRITER_MODEL, prompt_template, provider, isTest=True
            )

        df = pd.DataFrame(optimized_results)[
            ["query_id", "rand_idx", "optimized_product"]
        ]
        csv_path = os.path.join(prompt_dir, "test_results.csv")
        df.to_csv(csv_path, index=False)
        print(f"  Saved {len(df)} results → {csv_path}")


if __name__ == "__main__":
    load_dotenv()
    np.random.seed(42)

    # CHANGE THIS WHEN TESTING DIFFERENT INITIAL PROMPTS - currently set to test all
    prompt_names = list(INITIAL_PROMPTS.keys())
    prompt_dir = INITIAL_PROMPTS
    print(f"Found {len(prompt_names)} initial prompts: {prompt_names}")

    os.makedirs(INITIAL_PROMPT_RESULTS_DIR, exist_ok=True)
    run_testing(p_name, p_dir, "../../tmp/")
