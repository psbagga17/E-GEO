import os

import numpy as np
from llm_batch_helper import LLMConfig, process_prompts_batch

from config import (
    DATA_DIR,
    INITIAL_RANKINGS,
    MAX_COMPLETION_TOKENS_OPTIMIZATION,
    MAX_COMPLETION_TOKENS_RANKING,
    NO_TEMPERATURE_MODELS,
)
from prompts import get_optimizing_prompt, get_ranking_user_prompt
from utils import (
    extract_llm_text,
    format_product,
    format_products,
    load_data,
    parse_json_string,
)


def optimize_products_parallel(
    data: dict, model: str, prompt_template: str, provider: str, isTest: bool = False
) -> list[dict]:
    system_prompt = get_optimizing_prompt()
    api_model = model.split("/", 1)[-1] if provider == "openai" else model

    config = LLMConfig(
        model_name=api_model,
        **({} if model in NO_TEMPERATURE_MODELS else {"temperature": 0.5}),
        max_completion_tokens=MAX_COMPLETION_TOKENS_OPTIMIZATION[model],
        max_concurrent_requests=100,
        system_instruction=system_prompt,
        max_retries=5,
    )

    if isTest:
        rand_idx_data = load_data(f"{DATA_DIR}/test_selected_products.json")
    else:
        rand_idx_data = {}
        for query_id, query_data in data.items():
            products = query_data["products"]
            rand_idx = np.random.randint(0, len(products) - 1)
            rand_idx_data[query_id] = {"ind": rand_idx, "product": products[rand_idx]}

    prompts = []
    final_results = []

    for query_id, query_data in data.items():
        rand_idx = rand_idx_data[query_id]["ind"]
        product = rand_idx_data[query_id]["product"]
        formatted_product = format_product(product)

        final_results.append(
            {
                "query_id": query_id,
                "rand_idx": rand_idx,
                "initial_product": formatted_product,
            }
        )
        prompts.append(prompt_template.format(description=formatted_product))

    results = process_prompts_batch(prompts=prompts, config=config, provider=provider)

    for item, (_, resp) in zip(final_results, results.items()):
        text = extract_llm_text(resp)
        if text is None:
            item["error"] = "Failed to extract optimized product description."
        item["optimized_product"] = text

    return final_results


def rerank_products_parallel(
    optimized_results: list[dict],
    test_data: dict,
    model: str,
    system_prompt: str,
    provider: str,
) -> tuple[list[dict], int, int]:
    prompts = []
    valid_results = []

    for item in optimized_results:
        if not item.get("optimized_product"):
            continue
        query_id = str(item["query_id"])
        if query_id not in test_data:
            continue

        rand_idx = item["rand_idx"]
        products = test_data[query_id]["products"]
        query = test_data[query_id]["query"]

        formatted = format_products(products, item["optimized_product"], rand_idx)
        user_prompt = get_ranking_user_prompt().format(
            query=query, formatted_products=formatted
        )
        prompts.append(user_prompt)
        valid_results.append(dict(item))

    api_model = model.split("/", 1)[-1] if provider == "openai" else model

    config = LLMConfig(
        model_name=api_model,
        **({} if model in NO_TEMPERATURE_MODELS else {"temperature": 0.3}),
        max_completion_tokens=MAX_COMPLETION_TOKENS_RANKING[model],
        max_concurrent_requests=100,
        system_instruction=system_prompt,
        max_retries=5,
    )

    batch_results = process_prompts_batch(
        prompts=prompts, config=config, provider=provider
    )

    total_input_tokens = 0
    total_output_tokens = 0

    for item, (_, resp) in zip(valid_results, batch_results.items()):
        if "error" in resp:
            item["optimized_ranking"] = None
            item["error"] = resp["error"]
        else:
            usage = resp.get("usage_details") or {}
            total_input_tokens += usage.get("prompt_token_count", 0)
            total_output_tokens += usage.get("completion_token_count", 0)
            response_text = resp.get("response_text")
            try:
                item["optimized_ranking"] = parse_json_string(response_text)
            except Exception:
                print(f"FAILED PARSING: {response_text!r}")
                item["optimized_ranking"] = None

    return valid_results, total_input_tokens, total_output_tokens


def combine_with_initial_rankings(
    model: str, optimized_results: list[dict], split: str = "test"
) -> list[dict]:
    file_path = os.path.join(DATA_DIR, INITIAL_RANKINGS[model][split])
    initial_data = load_data(file_path)

    combined = []
    for result in optimized_results:
        query_id = str(result["query_id"])
        product_idx = result["rand_idx"]
        if query_id not in initial_data:
            continue

        initial_ranking = initial_data[query_id]["results"]
        result["initial_ranking"] = initial_ranking

        optimized_ranking = result.get("optimized_ranking")
        if optimized_ranking is not None and initial_ranking is not None:
            try:
                initial_pos = initial_ranking["ranking"].index(product_idx + 1)
                optimized_pos = optimized_ranking["ranking"].index(product_idx + 1)
                result["improvement"] = initial_pos - optimized_pos
            except Exception:
                result["improvement"] = None
        else:
            result["improvement"] = None

        if isinstance(optimized_ranking, dict):
            questionable = optimized_ranking.get("questionable_products") or []
            if not isinstance(questionable, list):
                questionable = []
            target_num = product_idx + 1
            result["optimized_product_is_questionable"] = str(
                target_num in questionable
            )
            result["num_questionable"] = len(questionable)
        else:
            result["optimized_product_is_questionable"] = None
            result["num_questionable"] = None

        combined.append(result)
    return combined
