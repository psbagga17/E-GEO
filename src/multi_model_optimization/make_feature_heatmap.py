"""make_feature_heatmap.py

Generate side-by-side feature-presence heatmaps comparing the 15 initial
heuristic prompts (`src/all_init_prompts.py`) to the 15
best-on-validation optimized prompts (`results/META_OPT_RESULTS/best_prompts.json`,
each equal to the contents of `<method>/epoch_1/testing_1/prompt.txt`,
selected in `src/multi_model_optimization/run_meta_optimization.py` by maximum mean validation
score averaged across LLMs).

Two visualizations are produced:

* binary  (default): each cell is 0 (feature absent) or 1 (feature
  present), drawn as red / green respectively.
* graded            : 0 = absent, 0.5 = weakly / implicitly present,
  1 = explicitly present, drawn with a red-yellow-green colormap.

Both versions are written as PDF (vector, for the paper) and PNG
(quick preview) into the same directory as this script.

Usage
-----
    python make_feature_heatmap.py            # writes both
    python make_feature_heatmap.py --mode binary
    python make_feature_heatmap.py --mode graded
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, ListedColormap


# ---------------------------------------------------------------------------
# Row order: 15 prompt methods, alphabetical (case-insensitive).
# ---------------------------------------------------------------------------
PROMPTS = [
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


def _display(name: str) -> str:
    return name if name == "FAQ" else name.capitalize()


# ---------------------------------------------------------------------------
# Column order: ranking goal -> content (intent, keywords, summary) ->
# layout (sections, bullets) -> content depth (use cases, FAQ-style) ->
# quality controls (no stuffing, factuality).
# ---------------------------------------------------------------------------
FEATURES = [
    "Search-Engine Goal",
    "User Intent",
    "Keywords & Synonyms",
    "Opening Summary",
    "Section Headings",
    "Scannable Bullets",
    "Use Cases",
    "User Questions (FAQ)",
    "No Keyword Stuffing",
    "Maintains Factuality",
]


# ---------------------------------------------------------------------------
# Graded scores: 0 (absent), 0.5 (implicit / weak), 1 (explicit).
# Binary scores are derived as (graded > 0.5).
#
# Justifications (initial prompts):
#   * advertisement: only partial factuality ("maintain core information"
#     while allowing urgency / exclusivity claims).
#   * authoritative: mentions "increase the ranking" but never names a
#     search/recommendation engine -> implicit on TSE.
#   * FAQ: explicit user-question section; partial factuality ("keep as
#     much of the original ... as you decide is necessary"); FAQ sections
#     count as implicit structuring.
#   * format: only initial prompt that explicitly mandates headings + lists;
#     mentions "Answer engines favor ..." as supporting evidence (implicit
#     on TSE); accuracy mentioned but not original-fact preservation
#     (implicit on MF).
#   * language: preserves original meaning explicitly but adds non-original
#     foreign vocabulary -> still scored 1 on MF (meaning preserved).
#   * storytelling: explicitly forbids product details / facts (MF = 0).
#   * trick: explicit ranking-engine goal; mentions LLM-favored "keywords"
#     (implicit on KW).
# ---------------------------------------------------------------------------
INITIAL_GRADED: dict[str, list[float]] = {
    #                 TSE   UI   KW   OS   SS   BP   UC   UQ   NS   MF
    "advertisement": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5],
    "authoritative": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "clickable": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "competitive": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "diverse": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "FAQ": [0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 1.0, 0.0, 0.5],
    "fluent": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "format": [0.5, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.5],
    "language": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "minimalist": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "quality": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "storytelling": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "technical": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "trick": [1.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
    "unique": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
}


# ---------------------------------------------------------------------------
# Justifications (optimized prompts):
#   * Almost every optimized prompt explicitly states a ranking goal across
#     "search / recommendation engines", integrates keywords + synonyms,
#     anticipates user queries, opens with a summary, organises labeled
#     sections with bullets, references use cases, addresses common
#     buyer questions, warns against keyword stuffing, and demands
#     factual accuracy.
#   * Borderline cases (scored 0.5 -> binary 0):
#       - advertisement: "short, clear paragraphs and/or bullet points" but
#         no labeled sections; mentions user concerns, not explicit use
#         cases.
#       - competitive: clear sections + use cases + FAQ but no explicit
#         opening summary.
#       - fluent: flexible structure, no required labeled sections; only
#         implicitly addresses user questions ("user needs/problems").
#       - language: implicit on user questions.
#       - minimalist: by design forbids sections / bullets / FAQs (2-4
#         sentences) -> 0 on those columns.
#       - storytelling: features + FAQ but no explicit use cases section.
#       - trick: keeps the original "tricky" tone -> sections/bullets only
#         "where supported", FAQ + opening summary + use cases all implicit.
# ---------------------------------------------------------------------------
OPTIMIZED_GRADED: dict[str, list[float]] = {
    #                 TSE   UI   KW   OS   SS   BP   UC   UQ   NS   MF
    "advertisement": [1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 0.5, 1.0, 1.0, 1.0],
    "authoritative": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "clickable": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "competitive": [1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "diverse": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "FAQ": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "fluent": [1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 0.5, 1.0, 1.0],
    "format": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "language": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 1.0],
    "minimalist": [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0],
    "quality": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "storytelling": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0],
    "technical": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "trick": [1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0],
    "unique": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
}


# ---------------------------------------------------------------------------
# Plotting helpers.
# ---------------------------------------------------------------------------
RED = "#d97a7a"
YELLOW = "#f0d878"
GREEN = "#7ec88c"


def _matrix(score_dict: dict[str, list[float]]) -> np.ndarray:
    return np.array([score_dict[p] for p in PROMPTS], dtype=float)


def _binarize(mat: np.ndarray) -> np.ndarray:
    return (mat > 0.5).astype(float)


EDGE_COLOR = "#3a3a3a"
EDGE_WIDTH = 0.6


def _draw_panel(
    ax: plt.Axes,
    mat: np.ndarray,
    cmap,
    vmin: float,
    vmax: float,
    show_ylabels: bool,
) -> None:
    n_rows, n_cols = mat.shape
    # pcolormesh draws each cell as an explicit polygon with `edgecolors`
    # painted exactly along its outline, eliminating the antialiased
    # colour bleed across cell boundaries that imshow can produce.
    x_edges = np.arange(n_cols + 1) - 0.5
    y_edges = np.arange(n_rows + 1) - 0.5
    ax.pcolormesh(
        x_edges,
        y_edges,
        mat,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        edgecolors=EDGE_COLOR,
        linewidth=EDGE_WIDTH,
        antialiased=False,
    )
    # pcolormesh places row 0 at the bottom; flip so row 0 sits at the top
    # (matching imshow's default origin="upper").
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.set_xlim(-0.5, n_cols - 0.5)

    # Anchor each rotated single-line column label slightly left of the
    # centre of its column's top edge so the visible start of each label
    # sits over the column it describes.
    ax.set_xticks(np.arange(n_cols) - 0.1)
    ax.set_yticks(np.arange(n_rows))
    ax.set_xticklabels(FEATURES, rotation=45, ha="left", fontsize=8)
    if show_ylabels:
        ax.set_yticklabels([_display(p) for p in PROMPTS], fontsize=9)
    else:
        ax.set_yticklabels([])

    ax.tick_params(
        axis="x",
        which="major",
        top=True,
        labeltop=True,
        bottom=False,
        labelbottom=False,
        length=0,
    )
    ax.tick_params(axis="y", which="major", length=0)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor(EDGE_COLOR)
        spine.set_linewidth(EDGE_WIDTH)


# Layout constants (figure-coordinate fractions). Cell height in figure
# coords is (TOP - BOTTOM) / n_rows; we use it to position the colorbar.
LEFT, RIGHT = 0.10, 0.99
TOP, BOTTOM = 0.83, 0.30
WSPACE = 0.06
N_ROWS = len(PROMPTS)
CBAR_HEIGHT = 0.025

# Vertical positions of the artefacts that live below the heatmap panels:
# panel captions sit just under the heatmap, the colorbar sits below them.
# Each gap (panel <-> caption, caption <-> colorbar) was halved relative to
# the previous version on the user's request.
PANEL_CAPTION_Y = 0.265
CBAR_Y = 0.215


def make_figure(mode: str, out_dir: Path) -> list[Path]:
    init_mat = _matrix(INITIAL_GRADED)
    opt_mat = _matrix(OPTIMIZED_GRADED)

    if mode == "binary":
        init_mat = _binarize(init_mat)
        opt_mat = _binarize(opt_mat)
        cmap = ListedColormap([RED, GREEN])
        vmin, vmax = 0.0, 1.0
    elif mode == "graded":
        cmap = LinearSegmentedColormap.from_list(
            "RYG_soft",
            [(0.0, RED), (0.5, YELLOW), (1.0, GREEN)],
        )
        vmin, vmax = 0.0, 1.0
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    # Wide single-column figure (point 2): cells stay wider than tall but
    # less elongated than the original v2 placeholder.
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 7.0))
    _draw_panel(axes[0], init_mat, cmap, vmin, vmax, show_ylabels=True)
    _draw_panel(axes[1], opt_mat, cmap, vmin, vmax, show_ylabels=False)

    fig.subplots_adjust(left=LEFT, right=RIGHT, top=TOP, bottom=BOTTOM, wspace=WSPACE)

    # Geometry of the heatmap panels in figure-coordinate fractions.
    # subplots_adjust treats wspace as a fraction of the average axes width,
    # so total horizontal extent = (2 + wspace) * panel_width.
    panel_width = (RIGHT - LEFT) / (2.0 + WSPACE)
    panel_a_center = LEFT + 0.5 * panel_width
    panel_b_center = RIGHT - 0.5 * panel_width

    # Panel captions just below each heatmap panel (point 3).
    fig.text(
        panel_a_center,
        PANEL_CAPTION_Y,
        "Initial prompts",
        ha="center",
        va="center",
        fontsize=12,
    )
    fig.text(
        panel_b_center,
        PANEL_CAPTION_Y,
        "Optimized prompts",
        ha="center",
        va="center",
        fontsize=12,
    )

    # Colorbar width = half of total panel width (point 4); centred on the
    # figure's horizontal mid-line.
    total_panel_width = 2.0 * panel_width
    cbar_width = 0.5 * total_panel_width
    cbar_left = 0.5 * (LEFT + RIGHT) - 0.5 * cbar_width

    if mode == "binary":
        absent = mpatches.Patch(facecolor=RED, edgecolor="white", label="Absent")
        present = mpatches.Patch(facecolor=GREEN, edgecolor="white", label="Present")
        fig.legend(
            handles=[absent, present],
            loc="lower center",
            ncol=2,
            frameon=False,
            fontsize=11,
            bbox_to_anchor=(0.5, CBAR_Y - 0.01),
        )
    else:
        cbar_ax = fig.add_axes([cbar_left, CBAR_Y, cbar_width, CBAR_HEIGHT])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0.0, vmax=1.0))
        sm.set_array([])
        cbar = fig.colorbar(
            sm, cax=cbar_ax, orientation="horizontal", ticks=[0.0, 0.5, 1.0]
        )
        cbar.ax.set_xticklabels(["Absent", "Implicit", "Explicit"])
        cbar.outline.set_visible(False)
        cbar.ax.tick_params(length=0)

    pdf_path = out_dir / f"feature_heatmap_v3_{mode}.pdf"
    png_path = out_dir / f"feature_heatmap_v3_{mode}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=200)
    plt.close(fig)
    return [pdf_path, png_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["binary", "graded", "both"],
        default="graded",
        help="Which heatmap variant(s) to generate (default: graded).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: directory of this script).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = ["binary", "graded"] if args.mode == "both" else [args.mode]
    for m in modes:
        for path in make_figure(m, out_dir):
            print(f"[{m}] wrote {path}")


if __name__ == "__main__":
    main()
