import copy
import json
import os
import re
import sys
from datetime import datetime

import openai
from dotenv import load_dotenv

from all_init_prompts import INITIAL_PROMPTS

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from analysis import analyze_results
from prompts import get_meta_optimizer_system, get_meta_optimizer_user
from run_experiments import run_all_experiments
from utils import extract_statistics, format_histogram_text, format_history_section


def eval_prompt(
    prompt_template,
    data_path,
    batch_size,
    output_dir,
    method,
    batch_num,
    run_type="train",
):
    """Evaluate a prompt: run experiments and get performance metrics."""

    # Run experiments
    csv_path, _ = run_all_experiments(
        data_path=data_path,
        output_dir=output_dir,
        batch_size=batch_size,
        batch_num=batch_num,
        prompt_template=prompt_template,
        prompt_type=method,
        run_type=run_type,
    )

    # Run analysis (saves histogram)
    stats_dict = analyze_results(csv_path, output_dir)
    return stats_dict


def meta_optimize(
    current_prompt, performance, history, batch_size, meta_model="gpt-4o"
):
    """Call meta-optimizer to get improved prompt."""
    load_dotenv(override=True)
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Format request
    user_message = get_meta_optimizer_user().format(
        current_prompt=current_prompt,
        batch_size=batch_size,
        mean=performance["mean"],
        std=performance["std"],
        improvement_rate=performance["improvement_rate"],
        median=performance["median"],
        total=performance["total"],
        improved=performance["improved"],
        degraded=performance["degraded"],
        neutral=performance["neutral"],
        histogram_text=format_histogram_text(performance["improvements"]),
        history_section=format_history_section(history),
    )

    # Call meta-optimizer
    response = client.chat.completions.create(
        model=meta_model,
        messages=[
            {"role": "system", "content": get_meta_optimizer_system()},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
    )

    raw = response.choices[0].message.content

    # Extract new prompt
    match = re.search(r"---NEW_REWRITING_PROMPT---\n(.*?)(?=\n---|$)", raw, re.DOTALL)
    new_prompt = match.group(1).strip() if match else current_prompt

    # Extract reasoning
    match = re.search(r"---META-REASONING---\n(.*?)(?=\n---|$)", raw, re.DOTALL)
    reasoning = match.group(1).strip() if match else ""

    # Validate
    if "{description}" not in new_prompt:
        print("WARNING: Missing {description}, keeping current prompt")
        return current_prompt, reasoning

    return new_prompt, reasoning


def _load_from_checkpoint(experiment_dir, batch_num, method, start_epoch, start_batch):
    if start_batch != 0:
        # Open file with start_epoch start_batch-1 prompt.txt
        batch_dir = os.path.join(
            experiment_dir, f"epoch_{start_epoch}/batch_{start_batch - 1}/"
        )
        with open(os.path.join(batch_dir, "prompt.txt"), "r") as file:
            current_prompt = file.read()
    else:
        batch_dir = os.path.join(
            experiment_dir, f"epoch_{start_epoch - 1}/batch_{batch_num - 1}"
        )
        with open(os.path.join(batch_dir, "prompt.txt"), "r") as file:
            current_prompt = file.read()

    # reload validation_history
    validation_history = []
    epoch_history = []

    for epoch in range(start_epoch + 1):
        for batch in range(batch_num):
            if epoch == start_epoch and batch == start_batch:
                break

            # load validation statistics from each batch
            val_dir = os.path.join(experiment_dir, f"epoch_{epoch}/validation_{batch}")
            stat_file = os.path.join(val_dir, f"statistics_{method}.txt")
            prompt_file = os.path.join(val_dir, "prompt.txt")

            with open(stat_file, "r") as file:
                stat = file.read()

            with open(prompt_file, "r") as file:
                prompt = file.read()

            # extract statistics
            cur = extract_statistics(stat, epoch, batch, prompt, tp="validation")
            validation_history.append(cur)

            # Load every batch for start_epoch history into
            if epoch == start_epoch:
                # extract statistics from validation_{batch}
                # load validation statistics
                batch_dir = os.path.join(experiment_dir, f"epoch_{epoch}/batch_{batch}")
                stat_file = os.path.join(batch_dir, f"statistics_{method}.txt")
                prompt_file = os.path.join(batch_dir, "prompt.txt")

                with open(stat_file, "r") as file:
                    stat = file.read()

                with open(prompt_file, "r") as file:
                    prompt = file.read()

                # extract the statistics
                cur = extract_statistics(stat, epoch, batch, prompt, tp="train")
                epoch_history.append(cur)

        # Load only last batch from previous epochs
        if epoch != start_epoch:
            # load validation statistics
            val_dir = os.path.join(
                experiment_dir, f"epoch_{epoch}/batch_{batch_num - 1}"
            )
            stat_file = os.path.join(val_dir, f"statistics_{method}.txt")
            prompt_file = os.path.join(val_dir, "prompt.txt")

            with open(stat_file, "r") as file:
                stat = file.read()

            with open(prompt_file, "r") as file:
                prompt = file.read()

            cur = extract_statistics(stat, epoch, batch, prompt, tp="train")
            epoch_history.append(cur)

    return current_prompt, validation_history, epoch_history


def optimize_prompt(
    data_path,
    batch_size=100,
    batch_num=10,
    num_epochs=5,
    meta_model="gpt-4o",
    method="authoritative",
    start_epoch=0,
    start_batch=0,
):
    """Simple for loop: eval → meta-optimize → eval → meta-optimize"""

    experiment_dir = os.path.join("./results", f"prompt_opt_{method}")
    os.makedirs(experiment_dir, exist_ok=True)

    print(f"\n{'='*70}\nPROMPT OPTIMIZATION\n{'='*70}")
    print(
        f"Dir: {experiment_dir} | Batch Size: {batch_size} | Batch Num: {batch_num} | Epoch Num: {num_epochs}\n{'='*70}"
    )

    # Depending where we start load the appropriate prompt
    current_prompt = ""
    validation_history = []
    epoch_history = []
    if start_epoch == 0 and start_batch == 0:
        current_prompt = INITIAL_PROMPTS[method]
    else:
        current_prompt, validation_history, epoch_history = _load_from_checkpoint(
            experiment_dir, batch_num, method, start_epoch, start_batch
        )

    # MAIN OPTIMIZATION LOOP
    for epoch in range(start_epoch, num_epochs):
        print(f"\n{'='*70}\nEPOCH {epoch}\n{'='*70}")
        epoch_dir = os.path.join(experiment_dir, f"epoch_{epoch}")
        os.makedirs(epoch_dir, exist_ok=True)

        # Start with last prompts from previous epochs
        train_history = copy.deepcopy(epoch_history)

        for batch in range(start_batch, batch_num):
            print(f"\n--- Batch {batch+1}/{batch_num} ---")

            batch_dir = os.path.join(epoch_dir, f"batch_{batch}")
            os.makedirs(batch_dir, exist_ok=True)

            # Save current prompt
            with open(os.path.join(batch_dir, "prompt.txt"), "w") as f:
                f.write(current_prompt)

            ########################
            #       TRAINING
            ########################

            perf = eval_prompt(
                current_prompt,
                data_path,
                batch_size,
                batch_dir,
                method,
                batch,
                run_type="train",
            )

            train_history.append(
                {
                    "epoch": epoch,
                    "batch": batch,
                    "prompt": current_prompt,
                    "type": "train",
                    **{k: v for k, v in perf.items() if k != "improvements"},
                }
            )

            print(
                f"Results: Mean={perf['mean']:.3f}, Std={perf['std']:.3f}, Success={perf['improvement_rate']:.1f}%"
            )

            ########################
            #       VALIDATION
            ########################

            validation_dir = os.path.join(epoch_dir, f"validation_{batch}")
            os.makedirs(validation_dir, exist_ok=True)

            # Save current prompt
            with open(os.path.join(validation_dir, "prompt.txt"), "w") as f:
                f.write(current_prompt)

            val_perf = eval_prompt(
                current_prompt,
                data_path,
                batch_size,
                validation_dir,
                method,
                batch,
                run_type="validation",
            )

            validation_history.append(
                {
                    "epoch": epoch,
                    "batch": batch,
                    "prompt": current_prompt,
                    "type": "validation",
                    **{k: v for k, v in val_perf.items() if k != "improvements"},
                }
            )

            ########################
            #     META-OPTIMIZE
            ########################
            new_prompt, reasoning = meta_optimize(
                current_prompt, perf, train_history, batch_size, meta_model
            )

            # Save meta-optimizer output
            with open(os.path.join(batch_dir, "meta_analysis.txt"), "w") as f:
                f.write(
                    f"REASONING:\n{reasoning}\n\n{'='*70}\nNEW PROMPT:\n{'='*70}\n\n{new_prompt}"
                )

            train_history[-1]["meta_reasoning"] = reasoning
            current_prompt = new_prompt
            print(f"Meta-optimized: {reasoning[:100]}...")

        # Update the epoch history with the last new prompt
        epoch_history.append(train_history[-1])
        start_batch = 0
        print("EPOCH HISTORY")
        print(epoch_history)
        print("-" * 60)

    # Last Validation
    validation_dir = os.path.join(epoch_dir, f"validation_{batch_num}")
    os.makedirs(validation_dir, exist_ok=True)

    # Save last optimized prompt
    with open(os.path.join(validation_dir, "prompt.txt"), "w") as f:
        f.write(new_prompt)

    val_perf = eval_prompt(
        current_prompt,
        data_path,
        batch_size,
        validation_dir,
        method,
        batch,
        run_type="validation",
    )

    validation_history.append(
        {
            "epoch": epoch,
            "batch": batch_num,
            "prompt": current_prompt,
            "type": "validation",
            **{k: v for k, v in val_perf.items() if k != "improvements"},
        }
    )
    # Save results
    best = max(validation_history, key=lambda x: x["mean"])

    with open(os.path.join(experiment_dir, "summary.txt"), "w") as f:
        f.write(
            f"BEST: batch {best['batch']} | Mean={best['mean']:.3f} | Success={best['improvement_rate']:.1f}%\n\n{'='*70}\nBEST PROMPT:\n{'='*70}\n\n{best['prompt']}"
        )

    with open(os.path.join(experiment_dir, "history.json"), "w") as f:
        json.dump(validation_history, f, indent=2)

    print(
        f"\n{'='*70}\n✓ DONE! Best: batch {best['batch']} (Mean={best['mean']:.3f})\nResults: {experiment_dir}\n{'='*70}"
    )

    ######################
    #    Testing
    ######################

    # Choose best validation prompt
    history_path = os.path.join(experiment_dir, f"history.json")

    with open(history_path, "r") as file:
        history = file.read()
    history = json.loads(history)
    best = max(history, key=lambda x: x["mean"])
    best_prompt = best["prompt"]
    test_dir = os.path.join(experiment_dir, f"test_{method}")
    print(best_prompt)

    test_perf = eval_prompt(
        best_prompt, data_path, 50, test_dir, method, 0, run_type="test"
    )

    print("TESTING PERFORMANCE", test_perf["mean"])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--method",
        type=str,
        default="authoritative",
        choices=list(INITIAL_PROMPTS.keys()),
    )

    parser.add_argument("--data-path", type=str, default="../data/")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--batch-num", type=int, default=10)
    parser.add_argument("--num-epochs", type=int, default=5)
    parser.add_argument("--meta-model", type=str, default="gpt-4o")
    parser.add_argument("--start-epoch", type=int, default=0)
    parser.add_argument("--start-batch", type=int, default=0)

    args = parser.parse_args()

    start_time = datetime.now()
    print(f"Timer started at {start_time.isoformat()}")

    optimize_prompt(
        data_path=args.data_path,
        batch_size=args.batch_size,
        batch_num=args.batch_num,
        num_epochs=args.num_epochs,
        meta_model=args.meta_model,
        method=args.method,
        start_batch=args.start_batch,
        start_epoch=args.start_epoch,
    )
    end_time = datetime.now()
    elapsed = end_time - start_time
    elapsed_seconds = elapsed.total_seconds()
    hours, remainder = divmod(int(elapsed_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)

    print(f"Timer ended at {end_time.isoformat()}")
    print(
        f"Elapsed time: {elapsed} (hh:mm:ss -> {hours:02d}:{minutes:02d}:{seconds:02d}, seconds -> {elapsed_seconds:.2f}s)"
    )
