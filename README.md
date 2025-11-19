# **E-GEO**

A framework for E-Commerce Generative Engine Optimization.

---

## **Setup**

#### **1. Clone the repository**
```bash
git clone https://github.com/psbagga17/E-GEO.git
cd E-GEO
```

#### **2. Pull the datasets**
```bash
git lfs pull
```

#### **3. Install the dependencies**
```bash
uv sync
source .venv/bin/activate
```

#### **4. Add API keys**
Create a `.env` file in the project root and include your OpenAI or OpenRouter key:
```bash
OPENAI_API_KEY=your_key
# or
OPENROUTER_API_KEY=your_key
```


## **Project Structure**
```bash
E-GEO/
│
├── data/                    # Dataset files, product rankings, experiment inputs
│
└── src/
    ├── all_init_prompts.py      # List of 15 initial prompts used for meta-optimization
    ├── prompts.py               # All system/user prompts used across the project
    ├── prompt_optimization.py   # Main meta-optimization loop (train/validation/test)
    ├── run_experiments.py       # Batch processing, parallel execution, result logging
    ├── analysis.py              # Metrics, histograms, statistical summaries
    ├── utils.py                 # Helper functions
    └── visualiser.py            # Graph plotting utilities
```

## Command-Line Flags

Below are all available flags for `prompt_optimization.py`, with a clear explanation of what each one controls.

`--method`
Selects which initial system prompt style to use for optimization (e.g., authoritative, friendly, concise, etc.).

`--data-path`
Path to the dataset directory containing all product descriptions, rankings, or experiment data.

`--batch-size`
How many data samples to process per batch during each experiment cycle.

`--batch-num`
Total number of batches to run per epoch for training.  
Final number of processed samples = `batch_size * batch_num`.

`--num-epochs` 
How many optimization epochs to run.  
Each epoch evaluates all batches and updates the meta-prompt.

`--meta-model`
Which LLM to use for evaluating and optimizing prompts (e.g., `gpt-4o`, `gpt-4o-mini`, etc.).

`--start-epoch` 
Resume training from a specific epoch.  
Useful if you're restarting a long experiment.

`--start-batch`
Resume training inside the start_epoch at a specific batch number.

---

## Example Usage

```bash
python3 prompt_optimization.py \
    --method authoritative \
    --data-path ../data/ \
    --batch-size 100 \
    --batch-num 10 \
    --num-epochs 5 \
    --meta-model gpt-4o-mini \
    --start-epoch 0 \
    --start-batch 0
```

