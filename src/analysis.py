import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats


def load_results_from_csv(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def calculate_statistics(data: pd.DataFrame) -> dict:
    """
    Calculate statistics on ranking improvements.

    Args:
        data: DataFrame with 'improvement' column

    Returns:
        Dictionary with statistics
    """
    improvements = data["improvement"].dropna().values

    mean = np.mean(improvements)
    median = np.median(improvements)
    std = np.std(improvements)

    # Calculate 95% confidence interval
    sem = stats.sem(improvements)
    ci = stats.t.interval(0.95, len(improvements) - 1, loc=mean, scale=sem)

    # Count improvements vs degradations
    positive = np.sum(improvements > 0)
    negative = np.sum(improvements < 0)
    neutral = np.sum(improvements == 0)

    return {
        "mean": mean,
        "median": median,
        "std": std,
        "ci_lower": float(ci[0]),
        "ci_upper": float(ci[1]),
        "total": len(improvements),
        "improved": positive,
        "degraded": negative,
        "neutral": neutral,
        "improvement_rate": float(positive / len(improvements) * 100),
        "improvements": improvements.tolist(),
    }


def generate_histogram(
    data: pd.DataFrame, output_path: str, optimization_method: str = None
):
    """
    Generate histogram of ranking improvements.

    Args:
        data: DataFrame with 'improvement' column
        output_path: Path to save the histogram image
        optimization_method: Name of optimization method for title
    """
    improvements = data["improvement"].dropna()

    if len(improvements) == 0:
        print("No improvement data to plot!")
        return

    plt.figure(figsize=(10, 6))

    bins = range(int(improvements.min()), int(improvements.max()) + 2)
    plt.hist(improvements, bins=bins, edgecolor="black", alpha=0.7, color="steelblue")

    title = f"Histogram of Ranking Improvements{f' ({optimization_method.capitalize()})' if optimization_method else ''}"

    plt.title(title, fontsize=14, fontweight="bold")
    plt.xlabel("Improvement (positions)", fontsize=12)
    plt.ylabel("Frequency", fontsize=12)
    plt.grid(axis="y", linestyle="--", alpha=0.6)

    plt.axvline(
        x=0, color="red", linestyle="--", linewidth=1.5, alpha=0.7, label="No change"
    )

    mean_improvement = improvements.mean()
    plt.axvline(
        x=mean_improvement,
        color="green",
        linestyle="--",
        linewidth=1.5,
        alpha=0.7,
        label=f"Mean: {mean_improvement:.2f}",
    )

    plt.legend()

    # save figure to output path
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Histogram saved to: {output_path}")


def print_summary(stats: dict, optimization_method: str = None):
    """
    Print a summary of the results.

    Args:
        stats: Dictionary with statistics
        optimization_method: Name of optimization method for title
    """
    print("\n" + "=" * 60)
    title = (
        f"RESULTS SUMMARY - {optimization_method.upper()}"
        if optimization_method
        else "RESULTS SUMMARY"
    )
    print(title)
    print("=" * 60)

    print(f"\nTotal experiments: {stats['total']}")
    print(f"Improved rankings: {stats['improved']} ({stats['improvement_rate']:.1f}%)")
    print(
        f"Degraded rankings: {stats['degraded']} ({stats['degraded']/stats['total']*100:.1f}%)"
    )
    print(f"No change: {stats['neutral']} ({stats['neutral']/stats['total']*100:.1f}%)")

    print(f"\nRanking Improvement Statistics:")
    print(f"  Mean: {stats['mean']:.3f} positions")
    print(f"  Median: {stats['median']:.3f} positions")
    print(f"  Std Dev: {stats['std']:.3f}")
    print(f"  95% CI: [{stats['ci_lower']:.3f}, {stats['ci_upper']:.3f}]")

    print("\n" + "=" * 60 + "\n")


def analyze_results(csv_path: str, output_dir: str = None):
    """
    Main analysis function.

    Args:
        csv_path: path to results CSV file
        output_dir: directory to save outputs (default: same as csv_path)
    """
    print(f"Loading results from: {csv_path}")
    data = load_results_from_csv(csv_path)

    # Determine output directory
    output_dir = output_dir or os.path.dirname(csv_path)
    os.makedirs(output_dir, exist_ok=True)

    # Determine optimization method
    optimization_method = None
    if "optimization_method" in data.columns and len(data) > 0:
        optimization_method = data["optimization_method"].iloc[0]
    else:
        basename = os.path.basename(csv_path)
        if "rankings_" in basename:
            optimization_method = basename.replace("rankings_", "").replace(".csv", "")

    stats_dict = calculate_statistics(data)
    print_summary(stats_dict, optimization_method)

    histogram_filename = (
        f"histogram_{optimization_method}.png"
        if optimization_method
        else "histogram.png"
    )
    histogram_path = os.path.join(output_dir, histogram_filename)
    generate_histogram(data, histogram_path, optimization_method)

    # Print histogram data
    improvements = data["improvement"].dropna()
    if len(improvements) > 0:
        hist = np.histogram(
            improvements,
            bins=range(int(improvements.min()), int(improvements.max()) + 2),
        )
        print("\nHistogram bins (improvement: count):")
        for edge, count in zip(hist[1], hist[0]):
            if count > 0:
                print(f"  {edge:3d}: {count:3d} {'#' * int(count)}")

    # Save statistics to file
    stats_filename = (
        f"statistics_{optimization_method}.txt"
        if optimization_method
        else "statistics.txt"
    )
    stats_path = os.path.join(output_dir, stats_filename)

    with open(stats_path, "w") as f:
        f.write(f"Analysis Results for {optimization_method}\n")
        f.write("=" * 60 + "\n\n")
        for key, value in stats_dict.items():
            if isinstance(value, float):
                f.write(f"{key}: {value:.4f}\n")
            else:
                f.write(f"{key}: {value}\n")

    print(f"\nStatistics saved to: {stats_path}")

    return stats_dict
