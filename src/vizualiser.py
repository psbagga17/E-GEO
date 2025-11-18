import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

all_methods = [
    "advertisement",
    "authoritative",
    "clickable",
    "competitive",
    "diverse",
    "FAQ",
    "fluent",
    "format",
    "language",
    "minimalist",
    "quality",
    "storytelling",
    "technical",
    "trick",
    "unique",
]


def plot_all_methods(epoch_num, batch_num, folder):
    all_means = []
    all_batches = []
    all_ci_lowers = []
    all_ci_uppers = []

    for method in all_methods:
        cur_mean = []
        cur_ci_lower = []
        cur_ci_upper = []
        cur_batches = []

        for batch in range(batch_num):
            file_path = os.path.join(
                folder,
                f"epoch_{epoch_num}/validation_{batch}",
                f"statistics_{method}.txt",
            )
            if not os.path.isfile(file_path):
                print(f"Warning: missing file {file_path}, skipping epoch {batch}")
                continue

            with open(file_path, "r") as file:
                text = file.read()
            try:
                mean_line = [line for line in text.splitlines() if "mean" in line][0]
                mean_value = float(mean_line.split(":")[-1].strip())

                ci_lower_line = [
                    line for line in text.splitlines() if "ci_lower" in line
                ][0]
                ci_lower_value = float(ci_lower_line.split(":")[-1].strip())

                ci_upper_line = [
                    line for line in text.splitlines() if "ci_upper" in line
                ][0]
                ci_upper_value = float(ci_upper_line.split(":")[-1].strip())
            except (IndexError, ValueError) as e:
                print(f"Warning: could not parse mean from {file_path}: {e}")
                continue
            cur_batches.append(batch)
            cur_mean.append(mean_value)
            cur_ci_lower.append(ci_lower_value)
            cur_ci_upper.append(ci_upper_value)

        all_means.append(cur_mean)
        all_batches.append(cur_batches)
        all_ci_lowers.append(cur_ci_lower)
        all_ci_uppers.append(cur_ci_upper)

    for means, method in zip(all_means, all_methods):
        print(method, "\n")
        print(means, "\n")

    # Pretty plot: one bar per method (mean of validation means) with asymmetric CI errorbars.
    n_methods = len(all_methods)
    x = np.arange(n_methods)

    # Plot per-method lines over batches with CI as filled bands (so you can compare convergence)
    if "seaborn-whitegrid" in plt.style.available:
        plt.style.use("seaborn-whitegrid")
    else:
        plt.style.use("default")

    fig, ax = plt.subplots(figsize=(14, 7))
    cmap = plt.get_cmap("tab20")
    n_methods = len(all_methods)
    colors = cmap(np.linspace(0, 1, n_methods))

    any_data = False
    y_min, y_max = float("inf"), float("-inf")

    for i, (method_name, cur_batches, cur_mean, cur_ci_l, cur_ci_u) in enumerate(
        zip(all_methods, all_batches, all_means, all_ci_lowers, all_ci_uppers)
    ):
        if not cur_batches:
            # mark missing data in legend
            ax.plot([], [], color=colors[i], label=f"{method_name} (no data)")
            continue

        any_data = True
        # ensure arrays sorted by batch index
        idx = np.argsort(cur_batches)
        x = np.array(cur_batches)[idx]
        y = np.array(cur_mean, dtype=float)[idx]
        cl = np.array(cur_ci_l, dtype=float)[idx]
        cu = np.array(cur_ci_u, dtype=float)[idx]

        # update global y limits
        y_min = min(y_min, np.nanmin(cl))
        y_max = max(y_max, np.nanmax(cu))

        color = colors[i]
        # CI band
        ax.fill_between(x, cl, cu, color=color, alpha=0.12, linewidth=0, zorder=1)
        # mean line
        ax.plot(
            x,
            y,
            label=method_name,
            color=color,
            marker="o",
            linewidth=2.0,
            markersize=6,
            zorder=3,
        )
        # per-batch points
        ax.scatter(x, y, color=color, edgecolors="k", s=36, zorder=4)
        # annotate last point with final mean
        ax.text(
            x[-1],
            y[-1],
            f" {y[-1]:.2f}",
            fontsize=8,
            va="center",
            ha="left",
            color=color,
        )

    if not any_data:
        print("No batch data found for any method; nothing to plot.")
    else:
        ax.set_xlabel("batch")
        ax.set_ylabel("Validation Mean Score")
        ax.set_title("Per-method mean over batches with 95% CI — compare convergence")
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0))
        ax.grid(True, linestyle="--", alpha=0.35)

        # nice y-limits with margin
        if y_min < y_max:
            yrange = y_max - y_min
            ax.set_ylim(y_min - 0.06 * yrange, y_max + 0.06 * yrange)

        plt.tight_layout(rect=(0, 0, 0.85, 1.0))  # leave room for legend on the right

        save_dir = "./results/plots"
        os.makedirs(save_dir, exist_ok=True)
        save_path_pdf = os.path.join(save_dir, "validation_all_methods.pdf")
        # also keep PNG if you want both formats
        save_path_png = os.path.join(save_dir, "validation_all_methods.png")
        plt.savefig(save_path_pdf, dpi=180, bbox_inches="tight")
        plt.savefig(save_path_png, dpi=180, bbox_inches="tight")
        plt.close()
        print(f"Saved summary plots to {save_path_pdf} and {save_path_png}")


def plot_across_epochs(start_epoch, end_epoch, folder):
    all_batches = []
    train_means = []
    validation_means = []
    train_ci_lowers = []
    train_ci_uppers = []
    validation_ci_lowers = []
    validation_ci_uppers = []
    train_stds = []
    validation_stds = []

    for i in range(int(start_epoch), int(end_epoch)):
        for batch in range(10):
            file_path = os.path.join(
                folder, f"epoch_{i}/batch_{batch}", f"statistics_{method}.txt"
            )
            if not os.path.isfile(file_path):
                print(f"Warning: missing file {file_path}, skipping epoch {batch}")
                continue

            with open(file_path, "r") as file:
                text = file.read()

            try:
                mean_line = [line for line in text.splitlines() if "mean" in line][0]
                mean_value = float(mean_line.split(":")[-1].strip())

                std_line = [line for line in text.splitlines() if "std" in line][0]
                std_value = float(std_line.split(":")[-1].strip())

                ci_lower_line = [
                    line for line in text.splitlines() if "ci_lower" in line
                ][0]
                ci_lower_value = float(ci_lower_line.split(":")[-1].strip())

                ci_upper_line = [
                    line for line in text.splitlines() if "ci_upper" in line
                ][0]
                ci_upper_value = float(ci_upper_line.split(":")[-1].strip())
            except (IndexError, ValueError) as e:
                print(f"Warning: could not parse mean from {file_path}: {e}")
                continue

            all_batches.append((i - int(start_epoch)) * 10 + batch)
            train_means.append(mean_value)
            train_stds.append(std_value)
            train_ci_lowers.append(ci_lower_value)
            train_ci_uppers.append(ci_upper_value)

            file_path = os.path.join(
                folder, f"epoch_{i}/validation_{batch}", f"statistics_{method}.txt"
            )
            if not os.path.isfile(file_path):
                print(f"Warning: missing file {file_path}, skipping epoch {batch}")
                continue

            with open(file_path, "r") as file:
                text = file.read()

            try:
                mean_line = [line for line in text.splitlines() if "mean" in line][0]
                mean_value = float(mean_line.split(":")[-1].strip())

                std_line = [line for line in text.splitlines() if "std" in line][0]
                std_value = float(std_line.split(":")[-1].strip())

                ci_lower_line = [
                    line for line in text.splitlines() if "ci_lower" in line
                ][0]
                ci_lower_value = float(ci_lower_line.split(":")[-1].strip())

                ci_upper_line = [
                    line for line in text.splitlines() if "ci_upper" in line
                ][0]
                ci_upper_value = float(ci_upper_line.split(":")[-1].strip())
            except (IndexError, ValueError) as e:
                print(f"Warning: could not parse mean from {file_path}: {e}")
                continue
            validation_means.append(mean_value)
            validation_stds.append(std_value)
            validation_ci_lowers.append(ci_lower_value)
            validation_ci_uppers.append(ci_upper_value)

    train_x = all_batches
    train_y = train_means
    val_x = all_batches
    val_y = validation_means

    # sanity checks
    if len(train_y) != len(train_stds):
        print(
            f"Warning: train means ({len(train_y)}) and stds ({len(train_stds)}) length mismatch."
        )
    if len(val_y) != len(validation_stds):
        print(
            f"Warning: validation means ({len(val_y)}) and stds ({len(validation_stds)}) length mismatch."
        )

    if not train_x and not val_x:
        print("No data to plot.")
    else:
        plt.figure(figsize=(9, 5))

        if train_x:
            plt.plot(
                train_x,
                train_y,
                label="train (batches)",
                color="tab:blue",
                marker="o",
                linewidth=2,
                markersize=6,
            )
            for i, (x, y) in enumerate(zip(train_x, train_y)):
                s = train_stds[i] if i < len(train_stds) else 0.0
                plt.scatter(
                    [x], [y], s=60, facecolors="none", edgecolors="tab:blue", zorder=3
                )
                y_offset = 0.01 * (
                    max(train_y) - min(train_y) if len(train_y) > 1 else 1
                )
                plt.text(
                    x,
                    y + y_offset,
                    f"{y:.2f} (±{s:.2f})",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="tab:blue",
                )

        if val_x:
            plt.plot(
                val_x,
                val_y,
                label="validation (batches)",
                color="tab:red",
                marker="s",
                linewidth=2,
                markersize=6,
            )
            for i, (x, y) in enumerate(zip(val_x, val_y)):
                s = validation_stds[i] if i < len(validation_stds) else 0.0
                plt.scatter(
                    [x], [y], s=80, facecolors="none", edgecolors="tab:red", zorder=4
                )
                y_offset = 0.01 * (max(val_y) - min(val_y) if len(val_y) > 1 else 1)
                plt.text(
                    x,
                    y + y_offset,
                    f"{y:.2f} (±{s:.2f})",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="tab:red",
                )

        plt.grid(True, linestyle="--", alpha=0.4)
        plt.xlabel("batch")
        plt.ylabel("Mean Score")
        plt.title("Train vs Validation Mean Scores per Batch")
        plt.legend()
        # set x ticks to union of train and validation batch numbers (sorted)
        xticks = sorted(set(train_x) | set(val_x))
        if xticks:
            plt.xticks(xticks)
        plt.tight_layout()

        save_path = os.path.join(
            os.path.dirname(folder), f"mean_scores_train_vs_validation_{method}_V2.png"
        )
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"Saved plot to {save_path}")

    train_x = all_batches
    train_y = train_means
    val_x = all_batches
    val_y = validation_means
    ci_x_lower = train_ci_lowers
    ci_x_upper = train_ci_uppers
    ci_y_lower = validation_ci_lowers
    ci_y_upper = validation_ci_uppers

    print(ci_y_lower, ci_y_upper)

    # sanity checks
    if len(train_y) != len(train_stds):
        print(
            f"Warning: train means ({len(train_y)}) and stds ({len(train_stds)}) length mismatch."
        )
    if len(val_y) != len(validation_stds):
        print(
            f"Warning: validation means ({len(val_y)}) and stds ({len(validation_stds)}) length mismatch."
        )

    if not train_x and not val_x:
        print("No data to plot.")
    else:
        # Use seaborn-whitegrid if available, otherwise fall back to default style
        if "seaborn-whitegrid" in plt.style.available:
            plt.style.use("seaborn-whitegrid")
        else:
            plt.style.use("default")
        plt.figure(figsize=(10, 5))

        # Colors
        train_color = "#4C72B0"  # pleasant blue
        val_color = "#FF7F0E"  # warm orange (brighter for better visibility)

        # Convert to numpy arrays for positioning
        tx = np.array(train_x) if train_x else np.array([])
        vx = np.array(val_x) if val_x else np.array([])

        # Plot CI as bars behind the lines
        bar_width = 0.6
        # Train CI bars
        if len(tx) and len(ci_x_lower) == len(ci_x_upper) == len(tx):
            t_ci_lower = np.array(ci_x_lower)
            t_ci_upper = np.array(ci_x_upper)
            t_heights = t_ci_upper - t_ci_lower
            plt.bar(
                tx,
                t_heights,
                bottom=t_ci_lower,
                width=bar_width,
                color=train_color,
                alpha=0.18,
                zorder=1,
                edgecolor="none",
            )
        # Validation CI bars (slightly narrower and offset)
        if len(vx) and len(ci_y_lower) == len(ci_y_upper) == len(vx):
            v_ci_lower = np.array(ci_y_lower)
            v_ci_upper = np.array(ci_y_upper)
            v_heights = v_ci_upper - v_ci_lower
            offset = bar_width * 0.18
            plt.bar(
                vx + offset,
                v_heights,
                bottom=v_ci_lower,
                width=bar_width * 0.78,
                color=val_color,
                alpha=0.18,
                zorder=1,
                edgecolor="none",
            )

        # Plot lines and markers on top
        if train_x:
            plt.plot(
                tx,
                train_y,
                label="train (batches)",
                color=train_color,
                marker="o",
                linewidth=2.2,
                markersize=7,
                zorder=4,
            )
            # markers with white edge to pop on bars
            plt.scatter(
                tx,
                train_y,
                s=90,
                facecolors=train_color,
                edgecolors="w",
                linewidths=0.9,
                zorder=5,
            )
            for i, (x, y) in enumerate(zip(tx, train_y)):
                y_offset = 0.01 * (
                    max(train_y) - min(train_y) if len(train_y) > 1 else 1
                )
                plt.text(
                    x,
                    y + y_offset,
                    f"{y:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=train_color,
                    zorder=6,
                )

        if val_x:
            plt.plot(
                vx,
                val_y,
                label="validation (batches)",
                color=val_color,
                marker="s",
                linewidth=2.2,
                markersize=7,
                zorder=4,
            )
            plt.scatter(
                vx,
                val_y,
                s=110,
                facecolors=val_color,
                edgecolors="w",
                linewidths=0.9,
                zorder=5,
            )
            for i, (x, y) in enumerate(zip(vx, val_y)):
                y_offset = 0.01 * (max(val_y) - min(val_y) if len(val_y) > 1 else 1)
                plt.text(
                    x,
                    y + y_offset,
                    f"{y:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=val_color,
                    zorder=6,
                )

        # Styling
        plt.grid(True, linestyle="--", alpha=0.35)
        plt.xlabel("batch")
        plt.ylabel("Mean Score")
        plt.title("Train vs Validation Mean Scores per Batch (with 95% CI)")
        # legend including CI patches
        handles = [
            Patch(facecolor=train_color, alpha=0.18, label="train CI"),
            Patch(facecolor=val_color, alpha=0.18, label="validation CI"),
        ]
        plt.legend(
            handles=handles + plt.gca().get_legend_handles_labels()[0], loc="best"
        )

        # set x ticks to union of train and validation batch numbers (sorted)
        xticks = sorted(set(train_x) | set(val_x))
        if xticks:
            plt.xticks(xticks)
        plt.tight_layout()

        save_path = os.path.join(
            os.path.dirname(folder),
            f"epoch_{start_epoch}/t_vs_v_{method}_{start_epoch}.png",
        )
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"Saved plot to {save_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot train/validation mean scores")
    parser.add_argument("--method", "-m", type=str, default="authoritative")
    parser.add_argument("--start", "-s", type=str, default="0")
    parser.add_argument("--end", "-e", type=str, default="0")
    parser.add_argument(
        "--folder", "-f", type=str, default="./results/prompt_opt_authoritative/"
    )

    # parse and set variables for the rest of the script
    args = parser.parse_args()
    method = args.method
    start_epoch = args.start
    end_epoch = args.end
