from prompts import (
    get_claude_prompt,
    get_deepseek_prompt,
    get_gemini_prompt,
    get_gpt41_prompt,
    get_gpt5_prompt,
    get_llama_prompt,
)

DATA_DIR = "../../data"
RESULTS_DIR = "../../results"
BATCH_SIZE = 100

ALL_MODELS = [
    "openai/gpt-4.1",
    "openai/gpt-5",
    "google/gemini-3-flash-preview",
    "anthropic/claude-sonnet-4.5",
    "deepseek/deepseek-v3.2",
    "meta-llama/llama-4-maverick",
]

SYSTEM_PROMPTS = {
    "openai/gpt-4.1": get_gpt41_prompt(),
    "openai/gpt-5": get_gpt5_prompt(),
    "google/gemini-3-flash-preview": get_gemini_prompt(),
    "anthropic/claude-sonnet-4.5": get_claude_prompt(),
    "deepseek/deepseek-v3.2": get_deepseek_prompt(),
    "meta-llama/llama-4-maverick": get_llama_prompt(),
}

# Keyed by model → split ("train" / "validation" / "test")
INITIAL_RANKINGS = {
    "openai/gpt-4.1": {
        "train": "initial_ranking/train_val_initial_ranking_gpt41.json",
        "validation": "initial_ranking/train_val_initial_ranking_gpt41.json",
        "test": "initial_ranking/test_initial_ranking_gpt41.json",
    },
    "openai/gpt-5": {
        "train": "initial_ranking/train_val_initial_ranking_gpt5.json",
        "validation": "initial_ranking/train_val_initial_ranking_gpt5.json",
        "test": "initial_ranking/test_initial_ranking_gpt5.json",
    },
    "google/gemini-3-flash-preview": {
        "train": "initial_ranking/train_val_initial_ranking_gemini.json",
        "validation": "initial_ranking/train_val_initial_ranking_gemini.json",
        "test": "initial_ranking/test_initial_ranking_gemini.json",
    },
    "anthropic/claude-sonnet-4.5": {
        "train": "initial_ranking/train_val_initial_ranking_claude.json",
        "validation": "initial_ranking/train_val_initial_ranking_claude.json",
        "test": "initial_ranking/test_initial_ranking_claude.json",
    },
    "deepseek/deepseek-v3.2": {
        "train": "initial_ranking/train_val_initial_ranking_deepseek.json",
        "validation": "initial_ranking/train_val_initial_ranking_deepseek.json",
        "test": "initial_ranking/test_initial_ranking_deepseek.json",
    },
    "meta-llama/llama-4-maverick": {
        "train": "initial_ranking/train_val_initial_ranking_llama.json",
        "validation": "initial_ranking/train_val_initial_ranking_llama.json",
        "test": "initial_ranking/test_initial_ranking_llama.json",
    },
}

MODEL_NAMES = {
    "openai/gpt-4.1": "GPT-4.1",
    "openai/gpt-5": "GPT-5",
    "google/gemini-3-flash-preview": "Gemini",
    "anthropic/claude-sonnet-4.5": "Claude",
    "deepseek/deepseek-v3.2": "DeepSeek",
    "meta-llama/llama-4-maverick": "LLaMA 4 Maverick",
}

MODEL_ANON = {
    "openai/gpt-4.1": "Model A",
    "google/gemini-3-flash-preview": "Model B",
    "deepseek/deepseek-v3.2": "Model C",
    "meta-llama/llama-4-maverick": "Model D",
    "anthropic/claude-sonnet-4.5": "Model E",
    "openai/gpt-5": "Model F",
}

MODEL_PROVIDERS = {
    "openai/gpt-4.1": "openai",
    "openai/gpt-5": "openai",
    "google/gemini-3-flash-preview": "openrouter",
    "anthropic/claude-sonnet-4.5": "openrouter",
    "deepseek/deepseek-v3.2": "openrouter",
    "meta-llama/llama-4-maverick": "openrouter",
}

NO_TEMPERATURE_MODELS = {
    "openai/gpt-5",
}

MAX_COMPLETION_TOKENS_OPTIMIZATION = {
    "openai/gpt-4.1": 500,
    "openai/gpt-5": 500,
    "google/gemini-3-flash-preview": 500,
    "anthropic/claude-sonnet-4.5": 500,
    "deepseek/deepseek-v3.2": 500,
    "meta-llama/llama-4-maverick": 500,
}

MAX_COMPLETION_TOKENS_RANKING = {
    "openai/gpt-4.1": 500,
    "openai/gpt-5": 5000,
    "google/gemini-3-flash-preview": 100,
    "anthropic/claude-sonnet-4.5": 100,
    "deepseek/deepseek-v3.2": 100,
    "meta-llama/llama-4-maverick": 900,
}

# $ per million tokens: (input, output)
PRICING = {
    "openai/gpt-4.1": (2.00, 8.00),
    "google/gemini-3-flash-preview": (1.50, 6.00),
    "deepseek/deepseek-v3.2": (0.50, 2.00),
    "meta-llama/llama-4-maverick": (0.20, 1.00),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "openai/gpt-5": (1.25, 10.00),
}
