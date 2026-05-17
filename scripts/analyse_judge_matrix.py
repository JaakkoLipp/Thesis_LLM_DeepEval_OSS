"""Analyse judge-matrix data against single-rater reference labels.

This is the replication entry point for the agreement analysis reported in
Chapter 6.3 of the thesis. It computes:

  - Reliability: proportion of judge invocations producing a parseable verdict
  - Self-consistency: proportion of (fixture, metric) cells where all runs
    agreed on pass/fail (multi-run only)
  - Cohen's kappa vs the single-rater reference labels, overall and broken
    down by metric and by difficulty tier
  - Score-level instability across runs (multi-run only)
  - Pairwise judge-vs-judge kappa (when the input is a full matrix)
  - A one-row-per-judge summary table
  - Optional reproduction of Figures 6.1 and 6.2 (requires matplotlib)

Input layout is auto-detected. Three shapes are supported:

  Single run, single judge (flat directory of events, used for informal probes):
    <input>/evt_*.json

  Multi-run, single judge:
    <input>/run1/<judge>/evt_*.json
    <input>/run2/<judge>/evt_*.json
    <input>/run3/<judge>/evt_*.json

  Multi-run, multiple judges (the canonical scored matrix):
    <input>/run1/<judge_a>/evt_*.json
    <input>/run1/<judge_b>/evt_*.json
    <input>/run2/<judge_a>/evt_*.json
    ...

Each evt_*.json must follow the deepeval_mvp event schema, with either
status == "done" and an "evaluation.metrics" array, or status == "error" with
an "error.type" and "error.message" field.

Reference labels are expected as an xlsx with columns:
  fixture, metric, difficulty, user_input, model_output, label

where label is "pass" or "fail" (case-insensitive). Fixtures are joined to
events on (user_input, model_output) because user_input alone is not unique
(e.g. valid_sample and not_valid_sample share an input).

Usage:
  # Single judge (informal probe):
  python analyse_judge_matrix.py \\
      --input  output/judge-matrix/gemini-3-1-pro-preview \\
      --labels tests/reference_labels_COMPLETED.xlsx \\
      --out    output/analysis/gemini-pro-preview

  # Full scored matrix (reproduces the Chapter 6.3 tables and figures):
  python analyse_judge_matrix.py \\
      --input  output/judge-matrix/judge_matrix_20260515_084658 \\
      --labels tests/reference_labels_COMPLETED.xlsx \\
      --out    output/analysis/scored_matrix \\
      --figures
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.metrics import cohen_kappa_score

METRICS = [
    "Faithfulness",
    "AnswerRelevancy",
    "ContextualRelevancy",
    "Completeness",
    "Informativeness",
]

# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _key(user_input: Optional[str], model_output: Optional[str]) -> str:
    return (user_input or "") + "||" + (model_output or "")


def _run_sort_key(p: Path) -> int:
    m = re.search(r"\d+$", p.name)
    return int(m.group()) if m else 0


def load_labels(path: Path) -> tuple[pd.DataFrame, dict]:
    labels = pd.read_excel(path)
    required = {"fixture", "metric", "user_input", "model_output", "label"}
    missing = required - set(labels.columns)
    if missing:
        raise ValueError(f"Reference labels missing columns: {missing}")
    labels["human_pass"] = (labels["label"].astype(str).str.lower() == "pass").astype(int)
    labels["_key"] = [
        _key(u, m) for u, m in zip(labels["user_input"].fillna(""), labels["model_output"].fillna(""))
    ]
    key_to_fixture = dict(zip(labels["_key"], labels["fixture"]))
    return labels, key_to_fixture


def detect_layout(input_dir: Path) -> tuple[str, dict[str, list[tuple[str, Path]]]]:
    """Auto-detect the input layout.

    Returns:
      ("single_flat",  {judge_name: [("run1", input_dir)]})
      ("single_judge", {judge_name: [(run_id, run_dir), ...]})
      ("matrix",       {judge_a: [...], judge_b: [...], ...})
    """
    run_dirs = sorted(
        (d for d in input_dir.iterdir() if d.is_dir() and d.name.startswith("run")),
        key=_run_sort_key,
    )
    if not run_dirs:
        if any(input_dir.glob("evt_*.json")):
            return "single_flat", {input_dir.name: [("run1", input_dir)]}
        raise ValueError(f"No evt_*.json files found under {input_dir} (flat or nested)")

    judges: dict[str, list[tuple[str, Path]]] = {}
    for rd in run_dirs:
        for sub in sorted(d for d in rd.iterdir() if d.is_dir()):
            judges.setdefault(sub.name, []).append((rd.name, sub))

    if not judges:
        raise ValueError(f"No judge sub-folders found under {input_dir}/run*")

    layout = "matrix" if len(judges) > 1 else "single_judge"
    return layout, judges


def load_events(judge_runs: list[tuple[str, Path]], key_to_fixture: dict,
                judge_name: str) -> pd.DataFrame:
    rows = []
    unmatched = 0
    for run_id, run_path in judge_runs:
        for evt_path in sorted(run_path.glob("evt_*.json")):
            evt = json.loads(evt_path.read_text(encoding="utf-8"))
            payload = evt.get("payload", {}) or {}
            key = _key(payload.get("user_input"), payload.get("output"))
            fixture = key_to_fixture.get(key)
            if fixture is None:
                unmatched += 1
                continue
            if evt.get("status") == "error":
                err = evt.get("error", {}) or {}
                msg = f"{err.get('type', 'Error')}: {(err.get('message') or '')[:160]}"
                for metric in METRICS:
                    rows.append({"judge": judge_name, "run": run_id, "fixture": fixture,
                                 "metric": metric, "judge_pass": None, "score": None,
                                 "error": True, "err_msg": msg})
                continue
            for m in evt.get("evaluation", {}).get("metrics", []):
                rows.append({"judge": judge_name, "run": run_id, "fixture": fixture,
                             "metric": m["name"],
                             "judge_pass": int(m["success"]) if m.get("success") is not None else None,
                             "score": m.get("score"),
                             "error": m.get("error") is not None,
                             "err_msg": m.get("error")})
    if unmatched:
        print(f"  WARNING [{judge_name}]: {unmatched} events did not match any fixture key")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _kappa_or_nan(a: pd.Series, b: pd.Series) -> float:
    if a.nunique() < 2 or b.nunique() < 2:
        return float("nan")
    return float(cohen_kappa_score(a, b))


def reliability(df: pd.DataFrame) -> pd.DataFrame:
    rel = (df.groupby("metric")
             .agg(n_attempts=("error", "size"), n_errors=("error", "sum"))
             .reset_index())
    rel["reliability"] = (rel["n_attempts"] - rel["n_errors"]) / rel["n_attempts"]
    overall = pd.DataFrame([{
        "metric": "(overall)",
        "n_attempts": len(df),
        "n_errors": int(df["error"].sum()),
        "reliability": 1 - df["error"].sum() / max(len(df), 1),
    }])
    return pd.concat([rel, overall], ignore_index=True)


def self_consistency(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    if df["run"].nunique() < 2:
        return pd.DataFrame(), pd.DataFrame(), float("nan")

    verdicts = df.pivot_table(index=["fixture", "metric"], columns="run",
                              values="judge_pass", aggfunc="first")
    errs = df.pivot_table(index=["fixture", "metric"], columns="run",
                          values="error", aggfunc="first")
    mask = (~errs.any(axis=1)) & verdicts.notna().all(axis=1)
    eligible = verdicts[mask]
    consistent = eligible.apply(lambda r: len(set(r)) == 1, axis=1)
    overall = float(consistent.mean()) if len(consistent) else float("nan")

    per_metric = (consistent.reset_index().rename(columns={0: "consistent"})
                  .groupby("metric")["consistent"]
                  .agg(["sum", "count"]).reset_index())
    per_metric["self_consistency"] = per_metric["sum"] / per_metric["count"]

    scores = df.pivot_table(index=["fixture", "metric"], columns="run",
                            values="score", aggfunc="first")
    scores["range"] = scores.max(axis=1) - scores.min(axis=1)
    big_swings = (scores[scores["range"] >= 0.5]
                  .sort_values("range", ascending=False)
                  .reset_index())
    return per_metric, big_swings, overall


def majority_verdicts(df: pd.DataFrame) -> pd.DataFrame:
    if df["run"].nunique() < 2:
        ok = df[df["error"] == False].copy()
        return (
            ok[["fixture", "metric", "judge_pass"]]
            .drop_duplicates(subset=["fixture", "metric"])
            .rename(columns={"judge_pass": "majority"})
        )
    verdicts = df.pivot_table(index=["fixture", "metric"], columns="run",
                              values="judge_pass", aggfunc="first")
    errs = df.pivot_table(index=["fixture", "metric"], columns="run",
                          values="error", aggfunc="first")
    mask = (~errs.any(axis=1)) & verdicts.notna().all(axis=1)
    majority = verdicts[mask].apply(lambda r: int(sum(r) > len(r) / 2), axis=1)
    return majority.reset_index().rename(columns={0: "majority"})


def kappa_vs_reference(df: pd.DataFrame, labels: pd.DataFrame) -> dict:
    majority = majority_verdicts(df)
    joined = labels.merge(majority, on=["fixture", "metric"], how="left").dropna(subset=["majority"])
    joined["majority"] = joined["majority"].astype(int)

    out = {
        "pooled_kappa": _kappa_or_nan(joined["human_pass"], joined["majority"]),
        "pooled_pct_agree": float((joined["human_pass"] == joined["majority"]).mean()) if len(joined) else float("nan"),
        "pooled_n": int(len(joined)),
    }

    out["per_metric"] = pd.DataFrame([{
        "metric": m,
        "kappa": _kappa_or_nan(joined[joined["metric"] == m]["human_pass"],
                               joined[joined["metric"] == m]["majority"]),
        "pct_agree": float((joined[joined["metric"] == m]["human_pass"]
                            == joined[joined["metric"] == m]["majority"]).mean())
                     if (joined["metric"] == m).any() else float("nan"),
        "n": int((joined["metric"] == m).sum()),
    } for m in METRICS])

    out["per_tier"] = pd.DataFrame([{
        "difficulty": tier,
        "kappa": _kappa_or_nan(s["human_pass"], s["majority"]),
        "pct_agree": float((s["human_pass"] == s["majority"]).mean()) if len(s) else float("nan"),
        "n": int(len(s)),
    } for tier, s in joined.groupby("difficulty")])

    out["joined"] = joined
    out["majority"] = majority
    return out


def pairwise_judge_kappa(judge_majorities: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    names = sorted(judge_majorities.keys())
    for a, b in combinations(names, 2):
        ma = judge_majorities[a].rename(columns={"majority": "v_a"})
        mb = judge_majorities[b].rename(columns={"majority": "v_b"})
        m = ma.merge(mb, on=["fixture", "metric"], how="inner")
        if not len(m):
            rows.append({"judge_a": a, "judge_b": b, "kappa": float("nan"),
                         "pct_agree": float("nan"), "n": 0})
            continue
        rows.append({
            "judge_a": a, "judge_b": b,
            "kappa": _kappa_or_nan(m["v_a"].astype(int), m["v_b"].astype(int)),
            "pct_agree": float((m["v_a"] == m["v_b"]).mean()),
            "n": int(len(m)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Per-judge driver
# ---------------------------------------------------------------------------

def analyse_one_judge(judge: str, runs: list[tuple[str, Path]],
                      labels: pd.DataFrame, key_to_fixture: dict,
                      out_dir: Path) -> dict:
    print(f"\n--- Judge: {judge}  ({len(runs)} run(s)) ---")
    df = load_events(runs, key_to_fixture, judge)
    print(f"  Loaded {len(df)} records, {df['fixture'].nunique()} fixtures")

    rel = reliability(df)
    rel.to_csv(out_dir / f"{judge}_reliability.csv", index=False)

    sc_per_metric, big_swings, sc_overall = self_consistency(df)
    if len(sc_per_metric):
        sc_per_metric.to_csv(out_dir / f"{judge}_self_consistency.csv", index=False)
        big_swings.to_csv(out_dir / f"{judge}_score_swings.csv", index=False)

    k = kappa_vs_reference(df, labels)
    k["per_metric"].to_csv(out_dir / f"{judge}_kappa_per_metric.csv", index=False)
    k["per_tier"].to_csv(out_dir / f"{judge}_kappa_per_tier.csv", index=False)
    k["joined"].to_csv(out_dir / f"{judge}_joined.csv", index=False)
    df.to_csv(out_dir / f"{judge}_long.csv", index=False)

    print(f"  Reliability: {rel.iloc[-1]['reliability']:.3f}   "
          f"Self-consistency: {sc_overall:.3f}   "
          f"Kappa: {k['pooled_kappa']:.3f}   N: {k['pooled_n']}")

    return {
        "judge": judge,
        "n_runs": len(runs),
        "reliability": float(rel.iloc[-1]["reliability"]),
        "n_attempts": int(rel.iloc[-1]["n_attempts"]),
        "n_errors": int(rel.iloc[-1]["n_errors"]),
        "self_consistency": sc_overall,
        "pooled_kappa": k["pooled_kappa"],
        "pooled_pct_agree": k["pooled_pct_agree"],
        "pooled_n": k["pooled_n"],
        "_per_tier": k["per_tier"],
        "_majority": k["majority"],
    }


# ---------------------------------------------------------------------------
# Optional figures
# ---------------------------------------------------------------------------

def emit_figures(summary: pd.DataFrame, per_tier: dict[str, pd.DataFrame],
                 out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\n  matplotlib not installed; skipping figure generation. "
              "Install it with: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    for _, r in summary.iterrows():
        ax.scatter(r["reliability"], r["pooled_kappa"], s=80, alpha=0.85)
        ax.annotate(r["judge"], (r["reliability"], r["pooled_kappa"]),
                    xytext=(6, 4), textcoords="offset points", fontsize=9)
    ax.set_xlabel("Reliability (proportion of attempts producing a verdict)")
    ax.set_ylabel("Cohen's $\\kappa$ vs single-rater reference")
    ax.set_xlim(0, 1.02)
    ax.axhline(0.0, color="grey", linewidth=0.5)
    ax.axhline(0.4, color="grey", linewidth=0.4, linestyle="--", alpha=0.5)
    ax.set_title("Figure 6.1. Reliability versus agreement, per judge")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "figure_6_1_reliability_vs_agreement.png", dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    judges = list(summary["judge"])
    tiers = ["1-easy", "2-medium", "3-hard", "4-stress"]
    x = np.arange(len(tiers))
    width = 0.8 / max(len(judges), 1)
    for i, j in enumerate(judges):
        pt = per_tier[j].set_index("difficulty")
        vals = [float(pt.loc[t, "pct_agree"]) if t in pt.index else float("nan") for t in tiers]
        ax.bar(x + (i - (len(judges) - 1) / 2) * width, vals, width=width, label=j)
    ax.set_xticks(x)
    ax.set_xticklabels(tiers)
    ax.set_ylabel("Percentage agreement with single-rater reference")
    ax.set_ylim(0, 1.05)
    ax.set_title("Figure 6.2. Percentage agreement by difficulty tier, per judge")
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "figure_6_2_agreement_by_tier.png", dpi=300)
    plt.close(fig)

    print(f"  Figures: {out_dir}/figure_6_1_*.png and figure_6_2_*.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", required=True, type=Path,
                   help="Judge data directory. Layout auto-detected: flat (single run), "
                        "nested run1/run2/run3 (single or multi-judge).")
    p.add_argument("--labels", required=True, type=Path,
                   help="Reference labels xlsx (with columns fixture, metric, "
                        "difficulty, user_input, model_output, label).")
    p.add_argument("--out", default=Path("./analysis_output"), type=Path,
                   help="Output directory for CSVs and figures (default: ./analysis_output).")
    p.add_argument("--figures", action="store_true",
                   help="Emit Figures 6.1 and 6.2 PNGs (matrix mode only; requires matplotlib).")
    args = p.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print(f"Input:  {args.input}")
    print(f"Labels: {args.labels}")
    print(f"Output: {args.out}")
    print("=" * 72)

    labels, key_to_fixture = load_labels(args.labels)
    layout, judges = detect_layout(args.input)
    print(f"Detected layout: {layout}  ({len(judges)} judge(s))")

    summary_rows = []
    per_tier_collected = {}
    judge_majorities = {}
    for judge, runs in judges.items():
        result = analyse_one_judge(judge, runs, labels, key_to_fixture, args.out)
        summary_rows.append({k: v for k, v in result.items() if not k.startswith("_")})
        per_tier_collected[judge] = result["_per_tier"]
        judge_majorities[judge] = result["_majority"]

    summary = pd.DataFrame(summary_rows).sort_values("pooled_kappa",
                                                     ascending=False, na_position="last")
    summary.to_csv(args.out / "summary.csv", index=False)
    print("\n=== Summary (one row per judge) ===")
    print(summary.to_string(index=False))

    if layout == "matrix":
        pw = pairwise_judge_kappa(judge_majorities)
        pw.to_csv(args.out / "pairwise_kappa.csv", index=False)
        print("\n=== Pairwise judge-vs-judge kappa ===")
        print(pw.to_string(index=False))

        if args.figures:
            emit_figures(summary, per_tier_collected, args.out)

    print(f"\nOutputs written to: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())