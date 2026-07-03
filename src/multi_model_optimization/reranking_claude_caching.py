import asyncio
import json
import os
from typing import Optional

import anthropic
import numpy as np
import pandas as pd
from dotenv import load_dotenv

from all_init_prompts import INITIAL_PROMPTS
from analysis import analyze_results
from config import BATCH_SIZE, DATA_DIR, MODEL_NAMES, RESULTS_DIR, SYSTEM_PROMPTS
from llm_helpers import combine_with_initial_rankings
from prompts import get_ranking_user_prompt
from utils import format_products, load_data, parse_json_string

INITIAL_PROMPT_RESULTS_DIR = os.path.join(RESULTS_DIR, "INITIAL_PROMPT_RESULTS")

TEST_MODEL = "anthropic/claude-sonnet-4.5"

_ANTHROPIC_MODEL_MAP = {
    "anthropic/claude-sonnet-4.5": "claude-sonnet-4-5",
}


def load_optimized_products(
    prompt_name: str,
    base_dir: str = INITIAL_PROMPT_RESULTS_DIR,
    filename: str = "test_results.csv",
) -> list[dict]:
    csv_path = os.path.join(base_dir, prompt_name, filename)
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"No optimized products found at {csv_path}")
    df = pd.read_csv(csv_path)
    return df[["query_id", "rand_idx", "optimized_product"]].to_dict(orient="records")


async def _call_claude_cached_async(
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
    system_blocks: list,
    user_prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
    max_retries: int = 5,
) -> tuple[Optional[str], int, int, int, int]:
    async with semaphore:
        for attempt in range(max_retries):
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                usage = response.usage
                return (
                    response.content[0].text,
                    usage.input_tokens,
                    usage.output_tokens,
                    getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    getattr(usage, "cache_read_input_tokens", 0) or 0,
                )
            except anthropic.RateLimitError:
                await asyncio.sleep(2**attempt)
            except Exception as e:
                print(f"API ERROR: {e}")
                return None, 0, 0, 0, 0
    return None, 0, 0, 0, 0


def _rerank_claude_with_caching(
    prompts: list[str],
    system_prompt: str,
    max_tokens: int = 100,
    temperature: float = 0.3,
    max_concurrent: int = 100,
) -> tuple[list[Optional[str]], int, int]:
    anthropic_model = _ANTHROPIC_MODEL_MAP.get(
        TEST_MODEL, TEST_MODEL.removeprefix("anthropic/").replace(".", "-")
    )
    system_blocks = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    async def _run_all():
        async with anthropic.AsyncAnthropic() as aclient:
            semaphore = asyncio.Semaphore(max_concurrent)
            warmup = await _call_claude_cached_async(
                aclient,
                semaphore,
                system_blocks,
                prompts[0],
                anthropic_model,
                max_tokens,
                temperature,
            )
            tasks = [
                _call_claude_cached_async(
                    aclient,
                    semaphore,
                    system_blocks,
                    p,
                    anthropic_model,
                    max_tokens,
                    temperature,
                )
                for p in prompts[1:]
            ]
            return [warmup] + list(await asyncio.gather(*tasks))

    raw = asyncio.run(_run_all())
    texts = [r[0] for r in raw]
    total_in = sum(r[1] for r in raw)
    total_out = sum(r[2] for r in raw)
    total_cache_create = sum(r[3] for r in raw)
    total_cache_read = sum(r[4] for r in raw)
    print(
        f"    cache_creation={total_cache_create:,} | cache_read={total_cache_read:,} | uncached_in={total_in:,}"
    )
    return texts, total_in, total_out


def rerank_products_parallel(
    optimized_results: list[dict], test_data: dict
) -> tuple[list[dict], int, int]:
    system_prompt = SYSTEM_PROMPTS[TEST_MODEL]
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

    texts, total_input_tokens, total_output_tokens = _rerank_claude_with_caching(
        prompts, system_prompt, max_tokens=100, temperature=0.3, max_concurrent=100
    )

    for item, text in zip(valid_results, texts):
        if text is None:
            item["optimized_ranking"] = None
        else:
            try:
                item["optimized_ranking"] = parse_json_string(text)
            except Exception:
                print(f"FAILED PARSING: {text!r}")
                item["optimized_ranking"] = None

    return valid_results, total_input_tokens, total_output_tokens


def run_testing(prompt_names: list[str], output_dir: str):
    model_name = MODEL_NAMES[TEST_MODEL]
    test_data = load_data(os.path.join(DATA_DIR, "test_data.json"))
    test_query_ids = list(test_data.keys())
    num_batches = (len(test_query_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Test queries: {len(test_query_ids)} | Batches: {num_batches}")

    all_results = {}

    for prompt_name in prompt_names:
        print(f"\n{'='*60}\nInitial prompt: {prompt_name}\n{'='*60}")

        prompt_dir = os.path.join(output_dir, prompt_name)
        os.makedirs(prompt_dir, exist_ok=True)

        optimized_results = load_optimized_products(prompt_name)
        print(f"  Loaded {len(optimized_results)} optimized products")

        print(f"  Reranking with {model_name}...")
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

            print(
                f"  Batch {batch + 1}/{num_batches} | {len(batch_optimized)} products..."
            )
            reranked, in_tok, out_tok = rerank_products_parallel(
                batch_optimized, batch_data
            )
            combined_results += combine_with_initial_rankings(TEST_MODEL, reranked)
            model_input_tokens += in_tok
            model_output_tokens += out_tok
            print(
                f"  Batch {batch + 1}/{num_batches} done | tokens so far: {model_input_tokens:,} in / {model_output_tokens:,} out"
            )

        model_dir = os.path.join(prompt_dir, model_name)
        os.makedirs(model_dir, exist_ok=True)
        csv_path = os.path.join(model_dir, "test_results.csv")
        pd.DataFrame(combined_results).to_csv(csv_path, index=False)

        perf = analyze_results(csv_path)
        all_results[prompt_name] = {
            model_name: {
                k: (float(v) if hasattr(v, "item") else v)
                for k, v in perf.items()
                if k != "improvements"
            }
        }

        print(
            f"  {model_name}: mean={perf['mean']:.3f}, improvement_rate={perf['improvement_rate']:.1f}%"
            f"  |  tokens: {model_input_tokens:,} in / {model_output_tokens:,} out"
        )

    out_file = os.path.join(output_dir, "initial_prompt_performance_claude.json")
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to {out_file}")

    return all_results


if __name__ == "__main__":
    load_dotenv()
    np.random.seed(42)

    prompt_names = list(INITIAL_PROMPTS.keys())
    print(f"Found {len(prompt_names)} initial prompts: {prompt_names}")

    out_dir = INITIAL_PROMPT_RESULTS_DIR
    os.makedirs(out_dir, exist_ok=True)

    run_testing(prompt_names, out_dir)
