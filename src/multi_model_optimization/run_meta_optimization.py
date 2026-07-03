import argparse
import copy
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from config import DATA_DIR, MODEL_ANON, RESULTS_DIR, SYSTEM_PROMPTS
from cross_engine_optimization import meta_optimize_cross_engine
from dotenv import load_dotenv
from llm_helpers import (
    combine_with_initial_rankings,
    optimize_products_parallel,
    rerank_products_parallel,
)

from all_init_prompts import INITIAL_PROMPTS
from analysis import analyze_results
from utils import extract_statistics, load_data

MODEL_REGISTRY = list(MODEL_ANON.keys())


def _load_from_checkpoint(output_dir, num_batches, start_epoch, start_batch):
    if start_batch != 0:
        batch_dir = os.path.join(
            output_dir, f"epoch_{start_epoch}/batch_{start_batch - 1}/"
        )
    else:
        batch_dir = os.path.join(
            output_dir, f"epoch_{start_epoch - 1}/batch_{num_batches - 1}"
        )

    with open(os.path.join(batch_dir, "prompt.txt"), "r") as f:
        current_prompt = f.read()

    model_names = list(MODEL_ANON.values())
    validation_history = []
    epoch_history = []

    for epoch in range(start_epoch + 1):
        for batch in range(num_batches):
            if epoch == start_epoch and batch == start_batch:
                break

            if batch % 2 != 0:
                val_dir = os.path.join(output_dir, f"epoch_{epoch}/validation_{batch}")
                prompt_file = os.path.join(val_dir, "prompt.txt")
                with open(prompt_file, "r") as f:
                    prompt = f.read()
                for model_name in model_names:
                    stat_file = os.path.join(val_dir, model_name, "statistics.txt")
                    if not os.path.exists(stat_file):
                        continue
                    with open(stat_file, "r") as f:
                        stat = f.read()
                    cur = extract_statistics(
                        stat, epoch, batch, prompt, tp="validation"
                    )
                    cur["model"] = model_name
                    validation_history.append(cur)

            if epoch == start_epoch:
                batch_dir = os.path.join(output_dir, f"epoch_{epoch}/batch_{batch}")
                with open(os.path.join(batch_dir, "prompt.txt"), "r") as f:
                    prompt = f.read()
                for model_name in model_names:
                    stat_file = os.path.join(batch_dir, model_name, "statistics.txt")
                    if not os.path.exists(stat_file):
                        continue
                    with open(stat_file, "r") as f:
                        stat = f.read()
                    cur = extract_statistics(stat, epoch, batch, prompt, tp="train")
                    cur["model"] = model_name
                    epoch_history.append(cur)

        if epoch != start_epoch:
            last_batch_dir = os.path.join(
                output_dir, f"epoch_{epoch}/batch_{num_batches - 1}"
            )
            with open(os.path.join(last_batch_dir, "prompt.txt"), "r") as f:
                prompt = f.read()
            for model_name in model_names:
                stat_file = os.path.join(last_batch_dir, model_name, "statistics.txt")
                if not os.path.exists(stat_file):
                    continue
                with open(stat_file, "r") as f:
                    stat = f.read()
                cur = extract_statistics(
                    stat, epoch, num_batches - 1, prompt, tp="train"
                )
                cur["model"] = model_name
                epoch_history.append(cur)

    return current_prompt, validation_history, epoch_history


def run_multi_llm(
    data_path,
    output_dir,
    batch_size=100,
    num_epochs=2,
    start_epoch=0,
    start_batch=0,
    rewriter_model="openai/gpt-4.1",
    method="authoritative",
    max_train_queries=None,
    max_val_queries=None,
    max_test_queries=None,
    red_team=False,
):
    experiment_dir = os.path.join(output_dir, method)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(experiment_dir, exist_ok=True)

    train_val_data = load_data(os.path.join(data_path, "train1000_val500.json"))
    test_data = load_data(os.path.join(data_path, "test_data.json"))

    train_query_ids = list(train_val_data.keys())
    val_query_ids = list(train_val_data.keys())
    test_query_ids = list(test_data.keys())

    if max_train_queries is not None:
        train_query_ids = train_query_ids[:max_train_queries]
    if max_val_queries is not None:
        val_query_ids = val_query_ids[-max_val_queries:]
    if max_test_queries is not None:
        test_query_ids = test_query_ids[:max_test_queries]

    train_data = {k: train_val_data[k] for k in train_query_ids}
    val_data = {k: train_val_data[k] for k in val_query_ids}

    num_batches_train = (len(train_query_ids) + batch_size - 1) // batch_size
    num_batches_val = (len(val_query_ids) + batch_size - 1) // batch_size
    num_batches_test = (len(test_query_ids) + batch_size - 1) // batch_size

    print(
        f"Train: {len(train_query_ids)} | Val: {len(val_query_ids)} | Test: {len(test_query_ids)}"
    )
    print(
        f"\n{'='*70}\nMethod: {method} | Rewriter: {rewriter_model}\nOutput: {experiment_dir}\n{'='*70}"
    )

    rewriter_provider = (
        "openai" if rewriter_model.startswith("openai/") else "openrouter"
    )

    if start_epoch == 0 and start_batch == 0:
        current_prompt = INITIAL_PROMPTS[method]
        validation_history = []
        epoch_history = []
    else:
        current_prompt, validation_history, epoch_history = _load_from_checkpoint(
            experiment_dir, num_batches_train, start_epoch, start_batch
        )

    for epoch in range(start_epoch, num_epochs):
        print(f"\n{'='*70}\nEPOCH {epoch}\n{'='*70}")
        epoch_dir = os.path.join(experiment_dir, f"epoch_{epoch}")
        os.makedirs(epoch_dir, exist_ok=True)

        train_history = copy.deepcopy(epoch_history)
        if epoch != start_epoch:
            start_batch = 0

        ########################
        #       TRAINING       #
        ########################

        for batch in range(start_batch, num_batches_train):
            print(f"\n--- Batch {batch+1}/{num_batches_train} ---")

            batch_dir = os.path.join(epoch_dir, f"batch_{batch}")
            os.makedirs(batch_dir, exist_ok=True)

            batch_ids = train_query_ids[batch * batch_size : (batch + 1) * batch_size]
            batch_data = {k: train_data[k] for k in batch_ids}

            optimized_results = optimize_products_parallel(
                batch_data, rewriter_model, current_prompt, rewriter_provider
            )
            cur_scores = {}

            for model in MODEL_REGISTRY:
                model_dir = os.path.join(batch_dir, MODEL_ANON[model])
                os.makedirs(model_dir, exist_ok=True)

                provider = "openai" if model.startswith("openai/") else "openrouter"
                reranked, _, _ = rerank_products_parallel(
                    optimized_results,
                    batch_data,
                    model,
                    SYSTEM_PROMPTS[model],
                    provider,
                )
                combined = combine_with_initial_rankings(model, reranked, split="train")

                csv_path = os.path.join(model_dir, f"train_results_{batch}.csv")
                pd.DataFrame(combined).to_csv(csv_path, index=False)

                perf = analyze_results(csv_path)
                cur_scores[MODEL_ANON[model]] = perf
                train_history.append(
                    {
                        "epoch": epoch,
                        "batch": batch,
                        "prompt": current_prompt,
                        "type": "train",
                        "model": MODEL_ANON[model],
                        **{k: v for k, v in perf.items() if k != "improvements"},
                    }
                )
                print(
                    f"  TRAIN {MODEL_ANON[model]}: mean={perf['mean']:.3f}, success={perf['improvement_rate']:.1f}%"
                )

            ########################
            #   META-OPTIMIZATION  #
            ########################

            new_prompt, reasoning = meta_optimize_cross_engine(
                current_prompt, cur_scores, train_history, batch_size, red_team=red_team
            )

            with open(os.path.join(batch_dir, "meta_analysis.txt"), "w") as f:
                f.write(
                    f"REASONING:\n{reasoning}\n\n{'='*70}\nNEW PROMPT:\n{'='*70}\n\n{new_prompt}"
                )

            current_prompt = new_prompt
            with open(os.path.join(batch_dir, "prompt.txt"), "w") as f:
                f.write(current_prompt)

            # if batch % 2 == 0:
            #     continue

            #########################
            #      VALIDATION       #
            #########################

            validation_dir = os.path.join(epoch_dir, f"validation_{batch}")
            os.makedirs(validation_dir, exist_ok=True)

            optimized_val = []
            for vbatch in range(num_batches_val):
                vbatch_ids = val_query_ids[
                    vbatch * batch_size : (vbatch + 1) * batch_size
                ]
                vbatch_data = {k: val_data[k] for k in vbatch_ids}
                optimized_val.append(
                    optimize_products_parallel(
                        vbatch_data, rewriter_model, current_prompt, rewriter_provider
                    )
                )

            for model in MODEL_REGISTRY:
                combined = []
                for vbatch in range(num_batches_val):
                    vbatch_ids = val_query_ids[
                        vbatch * batch_size : (vbatch + 1) * batch_size
                    ]
                    vbatch_data = {k: val_data[k] for k in vbatch_ids}
                    provider = "openai" if model.startswith("openai/") else "openrouter"
                    reranked, _, _ = rerank_products_parallel(
                        optimized_val[vbatch],
                        vbatch_data,
                        model,
                        SYSTEM_PROMPTS[model],
                        provider,
                    )
                    combined += combine_with_initial_rankings(
                        model, reranked, split="validation"
                    )

                model_dir = os.path.join(validation_dir, MODEL_ANON[model])
                os.makedirs(model_dir, exist_ok=True)
                csv_path = os.path.join(model_dir, "validation_results.csv")
                pd.DataFrame(combined).to_csv(csv_path, index=False)

                perf = analyze_results(csv_path)
                validation_history.append(
                    {
                        "epoch": epoch,
                        "batch": batch,
                        "prompt": current_prompt,
                        "type": "validation",
                        "model": MODEL_ANON[model],
                        **{k: v for k, v in perf.items() if k != "improvements"},
                    }
                )

            with open(os.path.join(validation_dir, "prompt.txt"), "w") as f:
                f.write(current_prompt)

        #####################
        #      TESTING      #
        #####################
        # CAN COMMENT THIS IF TESTING IS DONE PER EPOCH INSTEAD OF JUST AT THE END
        if epoch != num_epochs - 1:
            continue

        prompt_scores = defaultdict(list)
        for entry in validation_history:
            prompt_scores[entry["prompt"]].append(entry["mean"])
        best_prompt = max(
            prompt_scores, key=lambda p: sum(prompt_scores[p]) / len(prompt_scores[p])
        )

        test_dir = os.path.join(epoch_dir, f"testing_{epoch}")
        os.makedirs(test_dir, exist_ok=True)

        optimized_test = []
        for tbatch in range(num_batches_test):
            tbatch_ids = test_query_ids[tbatch * batch_size : (tbatch + 1) * batch_size]
            tbatch_data = {k: test_data[k] for k in tbatch_ids}
            optimized_test.append(
                optimize_products_parallel(
                    tbatch_data,
                    rewriter_model,
                    best_prompt,
                    rewriter_provider,
                    isTest=True,
                )
            )

        test_perf = {}
        for model in MODEL_REGISTRY:
            combined = []
            for tbatch in range(num_batches_test):
                tbatch_ids = test_query_ids[
                    tbatch * batch_size : (tbatch + 1) * batch_size
                ]
                tbatch_data = {k: test_data[k] for k in tbatch_ids}
                provider = "openai" if model.startswith("openai/") else "openrouter"
                reranked, _, _ = rerank_products_parallel(
                    optimized_test[tbatch],
                    tbatch_data,
                    model,
                    SYSTEM_PROMPTS[model],
                    provider,
                )
                combined += combine_with_initial_rankings(model, reranked, split="test")

            model_dir = os.path.join(test_dir, MODEL_ANON[model])
            os.makedirs(model_dir, exist_ok=True)
            csv_path = os.path.join(model_dir, "test_results.csv")
            pd.DataFrame(combined).to_csv(csv_path, index=False)

            perf = analyze_results(csv_path)
            test_perf[MODEL_ANON[model]] = perf
            print(
                f"  TEST {MODEL_ANON[model]}: mean={perf['mean']:.3f}, success={perf['improvement_rate']:.1f}%"
            )

        with open(os.path.join(test_dir, "test_performance.txt"), "w") as f:
            f.write(str(test_perf))

        train_history[-1]["meta-reasoning"] = reasoning
        epoch_history.extend(train_history[-len(MODEL_REGISTRY) :])

        with open(os.path.join(test_dir, "prompt.txt"), "w") as f:
            f.write(best_prompt)


if __name__ == "__main__":
    load_dotenv()
    np.random.seed(42)

    parser = argparse.ArgumentParser(
        description="Multi-LLM reflective prompt meta-optimization (inspired by GEPA, Agrawal et al. 2025)"
    )
    parser.add_argument("--data-path", type=str, default=DATA_DIR)
    parser.add_argument(
        "--output-dir", type=str, default=os.path.join(RESULTS_DIR, "META_OPT_RESULTS")
    )
    parser.add_argument("--method", type=str, default="authoritative")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--num-epochs", type=int, default=2)
    parser.add_argument("--start-epoch", type=int, default=0)
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--rewriter-model", type=str, default="openai/gpt-4.1")
    parser.add_argument("--max-train-queries", type=int, default=None)
    parser.add_argument("--max-val-queries", type=int, default=None)
    parser.add_argument("--max-test-queries", type=int, default=None)
    parser.add_argument(
        "--red-team",
        action="store_true",
        help="Use red-team meta-optimizer prompts (Pareto-optimize rank gain + low flag rate).",
    )

    args = parser.parse_args()

    start_time = datetime.now()
    print(f"Started at {start_time.isoformat()}")

    run_multi_llm(
        data_path=args.data_path,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        num_epochs=args.num_epochs,
        start_epoch=args.start_epoch,
        start_batch=args.start_batch,
        rewriter_model=args.rewriter_model,
        method=args.method,
        max_train_queries=args.max_train_queries,
        max_val_queries=args.max_val_queries,
        max_test_queries=args.max_test_queries,
        red_team=args.red_team,
    )

    elapsed = datetime.now() - start_time
    h, rem = divmod(int(elapsed.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    print(f"Elapsed: {h:02d}:{m:02d}:{s:02d}")
