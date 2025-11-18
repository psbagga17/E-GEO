import json
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
            key = metrics[0]
            value = float(metrics[-1].strip())
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


def parse_json_string(value):
    if not isinstance(value, str):
        return value
    # Clean markdown and fix quotes
    cleaned = value.strip().replace("```json", "").replace("```", "").strip()
    cleaned = cleaned.replace('""', '"')
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print("Failed to parse JSON string:", cleaned)
        return value  # fallback — return original if parsing fails
