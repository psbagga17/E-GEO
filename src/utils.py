import json
import os
from typing import Dict, List


def extract_llm_text(resp):
    """
    Extract assistant text from any LLM provider response format.
    Handles ChatCompletion, Completion, vendor-specific keys,
    Markdown fences, nested envelopes, and fallback structures.
    """
    if resp is None:
        return None

    if not isinstance(resp, dict):
        try:
            print("Warning: response not a dict, attempting to stringify.")
            return str(resp)
        except Exception:
            print("Failed to stringify response.")
            return None

    # Standard OpenAI ChatCompletion
    try:
        choices = resp.get("choices")
        if isinstance(choices, list) and len(choices) > 0:
            choice = choices[0]

            msg = choice.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if content:
                    print("Extracted content from chat message.")
                    return content

            if "text" in choice and choice["text"]:
                return choice["text"]
    except Exception:
        print("Failed to extract from OpenAI format.")

    for key in [
        "response_text",
        "output_text",
        "generated_text",
        "response",
        "text",
        "result",
        "content",
    ]:
        try:
            if key in resp and resp[key]:
                return resp[key]
        except Exception:
            print("Failed to extract from response using standard keys.")

    # Fallback: flatten any nested dict/JSON into a string
    try:
        return json.dumps(resp, ensure_ascii=False)
    except Exception:
        print("Failed to stringify response last resort", str(resp))
        return None


def extract_statistics(stat, epoch, batch, prompt, tp="train"):
    """
    transforms the statistics text into a dictionary
    """
    cur = {}
    for line in stat.splitlines():
        if ":" in line:
            metrics = line.split(":")
            key = metrics[0].strip()
            try:
                value = float(metrics[-1].strip())
            except ValueError:
                continue
            cur[key] = value
    cur["epoch"] = epoch
    cur["batch"] = batch
    cur["type"] = tp
    cur["prompt"] = prompt

    return cur


def format_history_section(history: List[Dict]) -> str:
    """Format previous epochs for context."""
    if not history:
        return ""

    section = "\nPREVIOUS ATTEMPTS:\n"

    for h in history[:]:
        section += f"\nEpoch {h['epoch']}:\n"
        section += f"  Mean: {h['mean']:.3f}, Success: {h['improvement_rate']:.1f}%\n"
        if "meta_reasoning" in h:
            reasoning = (
                h["meta_reasoning"][:200] + "..."
                if len(h.get("meta_reasoning", "")) > 200
                else h.get("meta_reasoning", "")
            )
            section += f"  Strategy: {reasoning}\n"
        if "prompt" in h:
            prompt_preview = (
                h["prompt"][:150] + "..."
                if len(h.get("prompt", "")) > 150
                else h.get("prompt", "")
            )
            section += f"  Prompt: {prompt_preview}\n"

    return section


def format_histogram_text(improvements: List[float]) -> str:
    """Format improvement histogram as text for meta-optimizer."""
    import numpy as np

    if not improvements:
        return "No data available"

    try:
        min_val = int(min(improvements))
        max_val = int(max(improvements))
        hist, edges = np.histogram(improvements, bins=range(min_val, max_val + 2))

        text = ""
        for edge, count in zip(edges[:-1], hist):
            if count > 0:
                bar = "█" * min(int(count), 50)
                text += f"  {edge:+3d}: {count:3d} {bar}\n"

        return text if text else "No histogram data"
    except Exception as e:
        return f"Error: {e}"


def format_product(product: Dict) -> str:
    import ast

    title = product.get("title", "")

    features_raw = product.get("features", "")
    if isinstance(features_raw, str) and features_raw:
        try:
            features_list = ast.literal_eval(features_raw)
            features = (
                " ".join(features_list)
                if isinstance(features_list, list)
                else str(features_raw)
            )
        except (ValueError, SyntaxError):
            features = str(features_raw)
    else:
        features = ""

    description_raw = product.get("description", "")
    if isinstance(description_raw, str) and description_raw:
        try:
            description_list = ast.literal_eval(description_raw)
            description = (
                " ".join(description_list)
                if isinstance(description_list, list)
                else str(description_raw)
            )
        except (ValueError, SyntaxError):
            description = str(description_raw)
    else:
        description = ""

    combined = f"{title}\n{features}\n{description}".strip()
    return combined


def format_products(products: List[Dict], optimized=None, ind=-1) -> str:
    """
    Format products as a numbered list for the LLM.

    Args:
        products: List of product dictionaries

    Returns:
        Formatted string with numbered products
    """
    formatted = ""

    if ind == -1:
        for i, product in enumerate(products, 1):
            product_text = format_product(product)
            formatted += f"[{i}] {product_text}\n\n"
    else:
        formatted_product_texts = [format_product(p) for p in products]
        formatted_product_texts[ind] = optimized

        for i, text in enumerate(formatted_product_texts, 1):
            formatted += f"[{i}] {text}\n\n"

    return formatted


def load_data(data_path: str) -> Dict:
    """Load queries and products from JSON file."""

    if data_path.endswith(".jsonl"):
        data = {}
        with open(data_path, "r") as f:
            for line in f:
                item = json.loads(line.strip())
                data[item["id"]] = item["data"]
        return data
    else:
        with open(data_path, "r") as f:
            data = json.load(f)
        return data


def extract_json_object(text):
    """
    Extracts the first complete JSON object from a string,
    handling markdown code blocks like ```json ... ```.
    """
    if not isinstance(text, str):
        return None

    # Check for markdown code block
    markdown_start = text.find("```json")
    if markdown_start != -1:
        # Find the closing ```
        markdown_end = text.find("```", markdown_start + 7)
        if markdown_end != -1:
            # Extract content between ```json and ```
            json_content = text[markdown_start + 7 : markdown_end].strip()
            try:
                return json.loads(json_content)
            except json.JSONDecodeError:
                pass

    # Fallback to original logic for plain JSON objects
    start = text.find("{")
    if start == -1:
        return None

    brace_count = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                json_str = text[start : i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return None
    return None


def parse_json_string(value):
    if not isinstance(value, str):
        return value
    # Clean markdown and fix quotes
    cleaned = value
    cleaned = cleaned.strip().replace("```json", "").replace("```", "").strip()
    cleaned = cleaned.replace('""', '"')
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: try to extract first JSON object from the string
    # (handles cases where LLM adds reasoning text around the JSON)
    import re

    match = re.search(r'\{[^{}]*"ranking"\s*:\s*\[.*?\].*?\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    print("Failed to parse JSON string inside parse_json_string:", len(cleaned[:200]))
    new_cleaned = extract_json_object(value)
    if new_cleaned != None:
        print("BUT MANAGED TO DO IT SECOND TIME")
        return new_cleaned
    return value  # fallback — return original if parsing fails


def format_cross_engine_scores(per_engine_stats: Dict) -> str:
    """Format per-engine stats block for the cross-engine meta-optimizer."""
    lines = []
    for engine_label, stats in per_engine_stats.items():
        mean = stats["mean"]
        std = stats["std"]
        rate = stats["improvement_rate"]
        bs = stats.get("bs_rate_rewritten", 0.0)
        lines.append(
            f"  {engine_label}: Mean {mean:+.3f}, Std {std:.3f}, "
            f"Success {rate:.1f}%, BS rate {bs:.1f}%"
        )
    return "\n".join(lines)


def format_prompt_engine_matrix(matrix: Dict, prompts: Dict) -> str:
    """Format the full (prompt x engine) matrix for Mode 2 meta-optimizer.

    Args:
        matrix: {prompt_name: {engine_label: stats_dict}}
        prompts: {prompt_name: prompt_text}
    """
    import numpy as np

    prompt_names = list(matrix.keys())
    engine_labels = list(next(iter(matrix.values())).keys())

    # Header
    header = f"{'':>20s}"
    for eng in engine_labels:
        header += f"  {eng:>12s}"
    lines = [header]

    # Rows
    for pname in prompt_names:
        row = f"{pname:>20s}"
        for eng in engine_labels:
            mean = matrix[pname][eng]["mean"]
            row += f"  {mean:>+12.3f}"
        lines.append(row)

    # Aggregate row
    lines.append("")
    agg = f"{'BEST per engine':>20s}"
    for eng in engine_labels:
        best = max(matrix[pname][eng]["mean"] for pname in prompt_names)
        agg += f"  {best:>+12.3f}"
    lines.append(agg)

    return "\n".join(lines)


def load_baseline_rankings(data_dir, engine_name):
    """
    Load per-engine baseline rankings from Tamar's JSON files.

    Args:
        data_dir: Path to final_data/ directory
        engine_name: One of 'gpt4omini', 'claude', 'gemini', 'gpt5'
                     OR engine label like 'Engine A'

    Returns:
        dict: {query_id_str: {"ranking": [...], "questionable_products": [...]}}
    """
    label_to_name = {
        "Engine A": "gpt4omini",
        "Engine B": "claude",
        "Engine C": "gemini",
        "Engine D": "gpt5",
    }

    if engine_name in label_to_name:
        engine_name = label_to_name[engine_name]

    for prefix in ["test_ranked_results", "train_val_ranked_results"]:
        fpath = os.path.join(data_dir, f"{prefix}_{engine_name}.json")
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                raw = json.load(f)

            parsed = {}
            for qid, entry in raw.items():
                results_str = entry.get("results", "")
                results_parsed = parse_json_string(results_str)
                if isinstance(results_parsed, dict):
                    parsed[qid] = results_parsed
                else:
                    print(
                        f"WARNING: Could not parse results for query {qid} in {fpath}"
                    )

            print(f"Loaded {len(parsed)} baseline rankings from {fpath}")
            return parsed

    raise FileNotFoundError(
        f"No baseline rankings file found for engine '{engine_name}' in {data_dir}"
    )


def format_cross_engine_history_v2(history: List[Dict]) -> str:
    """Format history with full prompt text and per-engine breakdown.

    Each history entry has:
      - epoch (int)
      - batch (int)
      - prompt (str, full text)
      - type (str, "train" or "validation")
      - model (str, engine label)
      - stats (dict: {mean, std, improvement_rate, bs_rate_rewritten})
    """
    if not history:
        return ""

    section = "\nPREVIOUS ITERATIONS:\n"

    for h in history:
        epoch = h.get("epoch", "?")
        batch = h.get("batch", "?")
        section += f"\nEpoch {epoch}, Batch {batch}:\n"

        # Full prompt text
        prompt = h.get("prompt", "")
        prompt_preview = prompt[:300] + "..." if len(prompt) > 300 else prompt
        section += f"  Prompt: {prompt_preview}\n"

        model = h.get("model", "")
        mean = h.get("mean", 0)
        rate = h.get("improvement_rate", 0)
        bs = h.get("bs_rate_rewritten", 0.0)
        section += (
            f"  {model}: Mean {mean:+.3f}, Success {rate:.1f}%, BS rate {bs:.1f}%\n"
        )

        # Reasoning
        reasoning = h.get("meta_reasoning", "")
        if reasoning:
            reasoning_preview = (
                reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            )
            section += f"  Reasoning: {reasoning_preview}\n"

    print("Formatted cross-engine history section:\n", section)
    return section


def format_cross_engine_history(history: List[Dict]) -> str:
    """Format history with full prompt text and per-engine breakdown.

    Each history entry has:
      - iteration (int)
      - prompt (str, full text)
      - per_engine_stats (dict: {engine_label: stats_dict})
      - meta_reasoning (str, optional)
    """
    if not history:
        return ""

    section = "\nPREVIOUS ITERATIONS:\n"

    for h in history:
        iteration = h.get("iteration", "?")
        section += f"\nIteration {iteration}:\n"

        # Full prompt text
        prompt = h.get("prompt", "")
        prompt_preview = prompt[:300] + "..." if len(prompt) > 300 else prompt
        section += f"  Prompt: {prompt_preview}\n"

        # Per-engine scores
        per_engine = h.get("per_engine_stats", {})
        for eng, stats in per_engine.items():
            mean = stats["mean"]
            rate = stats["improvement_rate"]
            bs = stats.get("bs_rate_rewritten", 0.0)
            section += (
                f"  {eng}: Mean {mean:+.3f}, Success {rate:.1f}%, BS rate {bs:.1f}%\n"
            )

        # Reasoning
        reasoning = h.get("meta_reasoning", "")
        if reasoning:
            reasoning_preview = (
                reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            )
            section += f"  Reasoning: {reasoning_preview}\n"

    return section
