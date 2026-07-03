"""
Length/structure robustness check for E-GEO.

Tests whether GEO rank gains are explained by rewrites simply being LONGER or more
STRUCTURED (bulleted / headed) rather than better. This backs the robustness
paragraph in the simple-prompt section of the paper.

We assemble per-pair records (one row per query x rewriter x re-ranker) from the
released results, compute text features of each rewrite relative to the original
listing, and (i) report the Spearman rank correlation between per-pair rank
improvement and the change in description length, and (ii) regress rank improvement
on the length change and a bulleted-list indicator, with rewriter and re-ranker fixed
effects and standard errors clustered by query.

Two datasets are analyzed:
    (A) Simple-prompt leaderboard  (7 rewriters x 5 evaluation re-rankers): every
        rewriter gets the same one-line prompt, so only the rewrite text varies.
        This is the comparison reported in the paper.
    (B) Heuristic prompts          (15 prompts x re-rankers, rewriter = GPT-4.1):
        fixes the rewriter and varies the prompt; the `format` heuristic explicitly
        asks for structure, the most likely place a confound would show up. This
        backs the footnote replication.

Run:
    uv run python src/length_structure_analysis.py

Output: a printed console summary (correlations, regression coefficients, the
R^2 variance decomposition, and per-rewriter means).
"""
import os, re, ast, glob, csv, json, sys
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

# Run-output artifacts live in the top-level `results/` folder (one level up from src/);
# this script reads the released leaderboard and heuristic-prompt results from there.
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

# The five evaluation re-rankers reported in the paper's leaderboard table.
EVAL_RERANKERS = ["gpt5", "claude", "gemini", "deepseek", "llama"]

WORD_RE = re.compile(r"\w+")
BULLET_RE = re.compile(r"(?m)^\s*([-*\u2022\u2023\u25E6\u2043\u2219]|\d+[.)])\s+")
HEADER_RE = re.compile(r"(?m)^\s*#{1,6}\s+")
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")


def n_words(t):
    return len(WORD_RE.findall(t or ""))


def n_bullets(t):
    return len(BULLET_RE.findall(t or ""))


def n_structure(t):
    """Any list/heading/bold markers -> a count of structural cues."""
    return n_bullets(t) + len(HEADER_RE.findall(t or "")) + len(BOLD_RE.findall(t or ""))


def feats(orig, opt):
    ow, pw = n_words(orig), n_words(opt)
    ob, pb = n_bullets(orig), n_bullets(opt)
    os_, ps_ = n_structure(orig), n_structure(opt)
    return dict(
        orig_words=ow, opt_words=pw,
        delta_words=pw - ow,
        log_ratio_words=np.log((pw + 1) / (ow + 1)),
        opt_bullets=pb, delta_bullets=pb - ob,
        opt_struct=ps_, delta_struct=ps_ - os_,
        has_bullets=int(pb >= 2),          # rewrite uses a bulleted list
        has_structure=int(ps_ >= 2),       # any list/header/bold structure
    )


# ----------------------------------------------------------------------------
# Load simple-prompt leaderboard (has both initial_product and optimized_product)
# ----------------------------------------------------------------------------
def load_leaderboard():
    rows = []
    orig_map = {}
    files = sorted(glob.glob(os.path.join(RESULTS, "LEADERBOARD_RESULTS",
                                          "*(opt)_*(rank).json")))
    for f in files:
        base = os.path.basename(f)
        m = re.match(r"(?:test_ranked_)?(.+)\(opt\)_(.+)\(rank\)\.json", base)
        rewriter, reranker = m.group(1), m.group(2)
        recs = json.load(open(f))
        for r in recs:
            qid = str(r["query_id"])
            orig = r.get("initial_product", "")
            opt = r.get("optimized_product", "")
            if orig:
                orig_map[qid] = orig
            imp = r.get("improvement")
            if imp is None or not opt:
                continue
            row = dict(query_id=qid, rewriter=rewriter, reranker=reranker,
                       improvement=float(imp))
            row.update(feats(orig, opt))
            rows.append(row)
    return pd.DataFrame(rows), orig_map


# ----------------------------------------------------------------------------
# Load heuristic-prompt results (CSV; optimized_product only -> use orig_map)
# ----------------------------------------------------------------------------
def load_heuristics(orig_map):
    rows = []
    root = os.path.join(RESULTS, "INITIAL_PROMPT_RESULTS")
    if not os.path.isdir(root):
        return pd.DataFrame(rows)
    for prompt in sorted(os.listdir(root)):
        pdir = os.path.join(root, prompt)
        if not os.path.isdir(pdir):
            continue
        for reranker in sorted(os.listdir(pdir)):
            csvf = os.path.join(pdir, reranker, "test_results.csv")
            if not os.path.isfile(csvf):
                continue
            with open(csvf, newline="") as fh:
                for r in csv.DictReader(fh):
                    qid = str(r["query_id"])
                    orig = orig_map.get(qid)
                    opt = r.get("optimized_product", "")
                    if orig is None or not opt or r.get("improvement") in (None, ""):
                        continue
                    try:
                        imp = float(r["improvement"])
                    except ValueError:
                        continue
                    row = dict(query_id=qid, prompt=prompt, reranker=reranker,
                               improvement=imp)
                    row.update(feats(orig, opt))
                    rows.append(row)
    return pd.DataFrame(rows)


def summarize(df, label, group_col, lines):
    lines.append(f"\n{'='*78}\n{label}\n{'='*78}")
    lines.append(f"n pairs = {len(df):,} | unique queries = {df.query_id.nunique():,}")
    lines.append(f"mean rank improvement = {df.improvement.mean():+.3f} "
                 f"(sd {df.improvement.std():.3f})")
    lines.append(f"mean delta_words = {df.delta_words.mean():+.1f} | "
                 f"share rewrites w/ bullets = {df.has_bullets.mean():.1%} | "
                 f"share w/ any structure = {df.has_structure.mean():.1%}")

    # Spearman rank correlations with rank improvement (rho)
    lines.append("\n-- Spearman correlations (rho) with rank improvement --")
    for v in ["delta_words", "log_ratio_words", "opt_words",
              "opt_bullets", "opt_struct", "has_bullets", "has_structure"]:
        rho, p = stats.spearmanr(df[v], df.improvement)
        lines.append(f"   rho(improvement, {v:<16}) = {rho:+.3f}  (p={p:.1e})")

    # OLS with query-clustered SE
    cl = {"groups": df["query_id"]}
    specs = [
        ("M1  length only",            "improvement ~ delta_words"),
        ("M2  + bullets",              "improvement ~ delta_words + has_bullets"),
        ("M3  + full structure",       "improvement ~ delta_words + has_bullets + delta_struct"),
        (f"M4  + {group_col} & reranker FE",
         f"improvement ~ delta_words + has_bullets + C({group_col}) + C(reranker)"),
    ]
    fits = {}
    lines.append("\n-- OLS (query-clustered SE); coefficients on length/structure --")
    for name, formula in specs:
        fit = smf.ols(formula, data=df).fit(cov_type="cluster", cov_kwds=cl)
        fits[name] = fit
        b_dw = fit.params.get("delta_words", np.nan)
        se_dw = fit.bse.get("delta_words", np.nan)
        p_dw = fit.pvalues.get("delta_words", np.nan)
        b_hb = fit.params.get("has_bullets", np.nan)
        se_hb = fit.bse.get("has_bullets", np.nan)
        p_hb = fit.pvalues.get("has_bullets", np.nan)
        lines.append(f"   [{name}]  R2={fit.rsquared:.4f} | "
                     f"delta_words={b_dw:+.5f} (se {se_dw:.5f}, p={p_dw:.2f}) | "
                     f"has_bullets={b_hb:+.4f} (se {se_hb:.4f}, p={p_hb:.1e})")

    # how much variance length/structure explain vs. rewriter/prompt identity
    r2_ls = fits["M2  + bullets"].rsquared
    r2_id = smf.ols(f"improvement ~ C({group_col}) + C(reranker)",
                    data=df).fit().rsquared
    r2_full = fits[f"M4  + {group_col} & reranker FE"].rsquared
    lines.append("\n-- Variance decomposition (R^2) --")
    lines.append(f"   length+bullets only         : {r2_ls:.4f}")
    lines.append(f"   {group_col}+reranker identity only : {r2_id:.4f}")
    lines.append(f"   all together                : {r2_full:.4f}")

    # per-group means: does the 'best' group simply write longest / most bullets?
    g = (df.groupby(group_col)
           .agg(mean_improvement=("improvement", "mean"),
                mean_delta_words=("delta_words", "mean"),
                share_bullets=("has_bullets", "mean"))
           .sort_values("mean_improvement", ascending=False))
    lines.append(f"\n-- Per-{group_col} means (sorted by rank improvement) --")
    lines.append(g.to_string(float_format=lambda v: f"{v:+.3f}"))

    # within-group Spearman correlation of delta_words with improvement (de-confounded)
    within = []
    for key, sub in df.groupby(group_col):
        if len(sub) > 10:
            rho = stats.spearmanr(sub.delta_words, sub.improvement).correlation
            within.append(rho)
    lines.append(f"\n-- Within-{group_col} rho(improvement, delta_words): "
                 f"mean {np.mean(within):+.3f}, range [{min(within):+.3f}, {max(within):+.3f}]")
    return g


def main():
    lines = []
    print("Loading leaderboard ...", file=sys.stderr)
    lb, orig_map = load_leaderboard()
    # Restrict to the five evaluation re-rankers reported in the paper.
    lb = lb[lb.reranker.isin(EVAL_RERANKERS)].copy()
    print(f"  {len(lb):,} leaderboard pairs", file=sys.stderr)
    print("Loading heuristic prompts ...", file=sys.stderr)
    he = load_heuristics(orig_map)
    print(f"  {len(he):,} heuristic pairs", file=sys.stderr)

    summarize(lb, "DATASET A -- Simple-prompt leaderboard (7 rewriters x 5 re-rankers)",
              "rewriter", lines)
    if len(he):
        summarize(he, "DATASET B -- Heuristic prompts (15 prompts, rewriter = GPT-4.1)",
                  "prompt", lines)

    print("\n".join(lines))


if __name__ == "__main__":
    main()
