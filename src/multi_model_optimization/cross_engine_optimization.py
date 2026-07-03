"""
Cross-engine prompt optimization (reflective prompt meta-optimization, inspired by GEPA, Agrawal et al. 2025).

The reflection step used by run_meta_optimization.py (and, through it, Mode C of
submission.py): the meta-optimizer reads per-engine results for the current prompt and
proposes an improved prompt, with full history of prompt text + per-engine scores.
Not a standalone script.
"""

import os
import re
import sys

import numpy as np
from llm_batch_helper import LLMConfig, process_prompts_batch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from prompts import (
    get_cross_engine_meta_optimizer_system,
    get_cross_engine_meta_optimizer_user,
    get_redteam_meta_optimizer_system,
    get_redteam_meta_optimizer_user,
)
from utils import (
    extract_llm_text,
    format_cross_engine_history,
    format_cross_engine_history_v2,
    format_cross_engine_scores,
)

# ---------------------------------------------------------------------------
# Meta-optimizer calls via OpenRouter
# ---------------------------------------------------------------------------


def _call_meta_optimizer(system_prompt, user_prompt, meta_model, meta_provider):
    """Call meta-optimizer LLM and return raw text response."""
    config = LLMConfig(
        model_name=meta_model,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=4096,
    )

    results = process_prompts_batch(
        prompts=[user_prompt],
        config=config,
        provider=meta_provider,
    )

    for _, resp in results.items():
        if "error" in resp:
            print(f"Meta-optimizer error: {resp['error']}")
            return None
        text = extract_llm_text(resp)
        return text

    return None


def _parse_meta_response(raw, current_prompt, full_reasoning=False):
    """Parse meta-optimizer response into new prompt and reasoning.

    When full_reasoning=True (red-team mode), the returned reasoning is everything
    before ---NEW_REWRITING_PROMPT--- (i.e., ANALYSIS + META-REASONING + IMPROVEMENTS)
    """
    if raw is None:
        print("WARNING: Meta-optimizer returned no response, keeping current prompt")
        return current_prompt, ""

    match = re.search(r"---NEW_REWRITING_PROMPT---\n(.*?)(?=\n---|$)", raw, re.DOTALL)
    new_prompt = match.group(1).strip() if match else current_prompt

    if full_reasoning:
        before_new = re.split(r"\n---NEW_REWRITING_PROMPT---", raw, maxsplit=1)[0]
        reasoning = before_new.strip()
    else:
        match = re.search(r"---META-REASONING---\n(.*?)(?=\n---|$)", raw, re.DOTALL)
        reasoning = match.group(1).strip() if match else ""

    if "{description}" not in new_prompt:
        print("WARNING: Missing {description} in new prompt, keeping current prompt")
        return current_prompt, reasoning

    return new_prompt, reasoning


# ---------------------------------------------------------------------------
# Reflect step (Mode 1 style: improve one prompt based on cross-engine scores)
# ---------------------------------------------------------------------------


def meta_optimize_cross_engine(
    current_prompt,
    per_engine_stats,
    history,
    batch_size,
    meta_model="openai/gpt-4.1",
    meta_provider="openrouter",
    red_team=False,
):
    """Reflect: improve one prompt for all engines.

    When red_team=True, swaps in the redteam meta-optimizer SYSTEM/USER prompts
    (Pareto-optimize rank gain + low flag rate) and adds flag-rate kwargs.
    History rendering uses v2 in both modes (per-(batch, model) flat trace).
    """
    means = [s["mean"] for s in per_engine_stats.values()]
    worst_mean = min(means)
    best_mean = max(means)
    cross_std = float(np.std(means))
    engines_positive = sum(1 for m in means if m > 0)
    engines_total = len(means)

    common_kwargs = dict(
        current_prompt=current_prompt,
        batch_size=batch_size,
        per_engine_stats_text=format_cross_engine_scores(per_engine_stats),
        worst_engine_mean=worst_mean,
        best_engine_mean=best_mean,
        cross_engine_std=cross_std,
        engines_positive=engines_positive,
        engines_total=engines_total,
        history_section=format_cross_engine_history_v2(history),
    )

    if red_team:
        flag_rates = [
            s.get("bs_rate_rewritten", 0.0) for s in per_engine_stats.values()
        ]
        user_prompt = get_redteam_meta_optimizer_user().format(
            **common_kwargs,
            worst_flag_rate=max(flag_rates) if flag_rates else 0.0,
            best_flag_rate=min(flag_rates) if flag_rates else 0.0,
            avg_flag_rate=(sum(flag_rates) / len(flag_rates)) if flag_rates else 0.0,
        )
        system_prompt = get_redteam_meta_optimizer_system()
    else:
        user_prompt = get_cross_engine_meta_optimizer_user().format(**common_kwargs)
        system_prompt = get_cross_engine_meta_optimizer_system()

    raw = _call_meta_optimizer(system_prompt, user_prompt, meta_model, meta_provider)

    return _parse_meta_response(raw, current_prompt, full_reasoning=red_team)
