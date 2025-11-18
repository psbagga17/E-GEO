"""
Run experiments for Method A: Direct LLM Ranking
Runs multiple experiments with different optimization functions.
"""

import csv
import os
import random
import sys

import pandas as pd
from llm_batch_helper import LLMConfig, process_prompts_batch

from all_init_prompts import INITIAL_PROMPTS
from utils import (
    extract_llm_text,
    format_product,
    format_products,
    load_data,
    parse_json_string,
)

# Add parent directory to path to import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prompts import (
    get_chatgpt_prompt,
    get_optimizing_prompt,
    get_ranking_user_prompt,
)


def optimize_products_parallel(query_ids, data, prompt_template):
    """
    Optimizes random product descriptions in parallel
    """

    system_prompt = get_optimizing_prompt()
    config = LLMConfig(
        model_name="gpt-4o-mini",
        temperature=0.5,
        max_concurrent_requests=100,
        system_instruction=system_prompt,
        max_retries=5,
    )

    prompts = []
    final_results = []

    for query_id in query_ids:
        query_data = data[query_id]
        products = query_data["products"]

        random_idx = random.randint(0, len(products) - 1)
        product = products[random_idx]
        formatted_product = format_product(product)

        final_results.append(
            {
                "query_id": query_id,
                "rand_idx": random_idx,
                "initial_product": formatted_product,
            }
        )
        final_prompt = prompt_template.format(description=formatted_product)
        prompts.append(final_prompt)

    results = process_prompts_batch(
        prompts=prompts,
        config=config,
        provider="openai",
    )

    for initial, response in zip(final_results, results.items()):
        _, resp = response

        text = extract_llm_text(resp)
        if text is None:
            initial["error"] = "Failed to extract optimized product description."
        initial["optimized_product"] = text

    return final_results


def rank_products_parallel(initial_results, data):
    """
    Reranks products in parallel after optimization
    """

    prompts = []

    for init in initial_results:
        if init.get("optimized_product", None) == None:
            print(
                "Skipping ranking due to optimization error for query id:",
                init["query_id"],
                init,
            )
            continue

        query_id = init["query_id"]
        rand_idx = init["rand_idx"]
        initial_product = init["initial_product"]
        optimized_product = init["optimized_product"]
        query = data[query_id]["query"]
        products = data[query_id]["products"]

        formatted = format_products(products, optimized_product, rand_idx)

        user_prompt = get_ranking_user_prompt().format(
            query=query,
            formatted_products=formatted,
        )

        prompts.append(user_prompt)

    system_prompt = get_chatgpt_prompt()

    config = LLMConfig(
        model_name="gpt-4o-mini",
        temperature=0.3,
        max_completion_tokens=5000,
        max_concurrent_requests=100,
        system_instruction=system_prompt,
        max_retries=5,
    )

    results = process_prompts_batch(
        prompts=prompts,
        config=config,
        provider="openai",
    )

    for initial, response in zip(initial_results, results.items()):
        _, resp = response
        # error handling
        if "error" in resp:
            initial["optimized_ranking"] = None
            initial["error"] = resp["error"]
            print(
                "Error occured in optimizing product description for query id:",
                initial["query_id"],
            )
            print(resp["error"])
        else:
            initial["optimized_ranking"] = parse_json_string(
                resp.get("response_text", None)
            )

    return initial_results


def process_queries_parallel(query_ids, data, prompt_template):
    """Process queries in parallel using LLMConfig and LLM batch helper."""

    initial = optimize_products_parallel(
        query_ids,
        data,
        prompt_template,
    )

    final = rank_products_parallel(
        initial_results=initial,
        data=data,
    )

    return final


def extract_original_ranking(df, query_id: int):
    """
    Extracts original ranking from initial results dataframe
    """
    row = df[df["query_id"] == int(query_id)]
    original_ranking = parse_json_string(row.iloc[0]["ranking"])["ranking"]
    return original_ranking


def save_query_ids(query_ids, experiment_dir, prompt_type, prompt_template, batch_num):
    """
    Save query IDs to a text file
    """
    query_ids_file = os.path.join(experiment_dir, "query_ids.txt")
    with open(query_ids_file, "w") as f:
        f.write(f"Experiment: {prompt_type}\n")
        f.write(f"Prompt Template: {prompt_template}\n")
        f.write(f"Number of queries: {batch_num}\n")
        f.write(f"\nQuery IDs:\n")
        for batch in query_ids:
            for qid in batch:
                f.write(f"{qid}\n")
    print(f"Query IDs saved to: {query_ids_file}")


def process_datum(result, data, df, prompt_type):
    if result.get("optimized_ranking", None) is None:
        print(
            "Skipping saving due to ranking error for query id:",
            result["query_id"],
            result.get("error", ""),
        )
        return None

    query_id = result["query_id"]
    rand_idx = result["rand_idx"]
    product_num = rand_idx + 1
    initial_product = result["initial_product"]
    optimized_product = result["optimized_product"]
    optimized_ranking = result["optimized_ranking"]

    # query_id, rand_idx, initial_product, optimized_product, optimized_ranking = i
    query_data = data[query_id]
    query = query_data["query"]

    original_ranking = extract_original_ranking(df, query_id)
    optimized_ranking = dict(optimized_ranking).get("ranking", [])

    # Safely attempt to find the positions; if not found or invalid types, skip this result
    try:
        original_pos = original_ranking.index(product_num)
        optimized_pos = optimized_ranking.index(product_num)
    except (ValueError, KeyError, TypeError) as e:
        print(
            f"""Index not found or invalid ranking for query {query_id}, product num {product_num}
            {original_ranking} and {optimized_ranking}: {e}"""
        )
        # skip this entry and continue processing the next one
        return None

    improvement = (
        original_pos - optimized_pos
        if (original_pos >= 0 and optimized_pos >= 0)
        else 0
    )

    cur = {
        "query_id": query_id,
        "query": query,
        "optimization_method": prompt_type,
        "product_id": None,
        "optimized_product_idx": rand_idx,
        "optimized_product_num": rand_idx + 1,
        "original_pos": original_pos,
        "optimized_pos": optimized_pos,
        "improvement": improvement,
        "original_ranking": original_ranking,
        "optimized_ranking": optimized_ranking,
        "original_text": initial_product,
        "optimized_text": optimized_product,
    }

    return cur


def run_all_experiments(
    data_path: str,
    output_dir: str = "./results",
    batch_size: int = 100,
    batch_num: int = 1,
    prompt_template: str = INITIAL_PROMPTS["authoritative"],
    prompt_type: str = "authoritative",
    run_type: ["train", "validation", "test"] = "train",
) -> tuple[str, str]:
    """
    Run experiments on multiple queries.

    Args:
        data_path: Path to queries_products JSON file
        optimization_fn_name: Name of optimization function ('fluent', 'technical', etc.)
        custom_optimization_fn: Optional custom optimization function (overrides optimization_fn_name)
        num_queries: Number of queries to test
        output_dir: Directory to save results
        num_products_per_query: How many products to use per query
        shuffle_queries: Whether to shuffle queries before selecting

    Returns:
        Tuple of (path to output CSV file, path to experiment directory)
    """
    # Determine method name for file naming

    print(f"\n{'='*60}")
    print(
        f"Running batch num {batch_num} with size {batch_size} experiments with optimization: {prompt_type}"
    )
    print(f"{'='*60}")

    experiment_dir = os.path.join(
        output_dir, f"{prompt_type}_{batch_num}_batch_queries"
    )
    os.makedirs(experiment_dir, exist_ok=True)

    print(f"Experiment directory: {experiment_dir}")

    output_file = os.path.join(experiment_dir, f"rankings_{batch_num}.csv")

    if run_type == "test":
        data_path = os.path.join(data_path, "test.jsonl")
        data = load_data(data_path)
        query_ids = list(data.keys())
    else:
        data_path = os.path.join(data_path, "train_val.jsonl")
        data = load_data(data_path)

        if run_type == "train":
            query_ids = list(data.keys())[:1000]
        else:
            query_ids = list(data.keys())[1000:]

    batched_query_ids = [
        query_ids[i : i + batch_size] for i in range(0, len(query_ids), batch_size)
    ]

    save_query_ids(
        batched_query_ids, experiment_dir, prompt_type, prompt_template, batch_num
    )

    initial_results_df = pd.read_csv("../data/full_dataset_rankings_v3.csv")

    csv_results = []
    for batch in batched_query_ids:
        all_results = process_queries_parallel(batch, data, prompt_template)
        for result in all_results:
            processed_datum = process_datum(
                result,
                data,
                initial_results_df,
                prompt_type,
            )
            if processed_datum is not None:
                csv_results.append(processed_datum)

    if csv_results:
        fieldnames = [
            "query_id",
            "query",
            "optimization_method",
            "product_id",
            "optimized_product_idx",
            "optimized_product_num",
            "original_pos",
            "optimized_pos",
            "improvement",
            "original_ranking",
            "optimized_ranking",
            "original_text",
            "optimized_text",
        ]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_results)

        print(f"\n{'='*60}")
        print(f"Results saved to: {output_file}")
        print(f"Total experiments: {len(csv_results)}")
        print(f"{'='*60}\n")

    return output_file, experiment_dir
