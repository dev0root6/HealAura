"""Compute metrics and figures from run_llm_eval.py and run_baselines.py outputs.

Writes metrics.json and ../figures/fig6_confusion.png, ../figures/fig7_macro_f1.png.
Usage: python analyze.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"
LABELS = ["positive", "negative", "mixed", "neutral"]
rng = np.random.default_rng(42)
plt.rcParams.update({"font.family": "serif", "font.size": 9})


def load_llm(condition):
    best = {}
    for line in (HERE / f"results_{condition}.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["idx"] not in best or best[r["idx"]]["error"] is not None:
            best[r["idx"]] = r
    return best


def scores(gold, pred):
    p, r, f, s = precision_recall_fscore_support(gold, pred, labels=LABELS, zero_division=0)
    return {
        "n": len(gold),
        "accuracy": accuracy_score(gold, pred),
        "macro_f1": f1_score(gold, pred, labels=LABELS, average="macro", zero_division=0),
        "weighted_f1": f1_score(gold, pred, labels=LABELS, average="weighted", zero_division=0),
        "per_class": {l: {"precision": p[i], "recall": r[i], "f1": f[i], "support": int(s[i])} for i, l in enumerate(LABELS)},
    }


def bootstrap_ci(gold, pred, B=2000):
    gold, pred = np.array(gold), np.array(pred)
    vals = []
    for _ in range(B):
        i = rng.integers(0, len(gold), len(gold))
        vals.append(f1_score(gold[i], pred[i], labels=LABELS, average="macro", zero_division=0))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def main():
    sample_ids = json.loads((HERE / "sample_ids.json").read_text())
    base = json.loads((HERE / "baseline_preds.json").read_text())
    pos = {idx: k for k, idx in enumerate(base["test_idx"])}
    metrics = {"sample_size": len(sample_ids), "models": {}}
    preds_subset = {}

    for cond, name in [("fewshot", "HealAura (Sarvam-105B, few-shot)"), ("zeroshot", "Sarvam-105B zero-shot")]:
        res = load_llm(cond)
        rows = [res[i] for i in sample_ids if i in res]
        ok = [r for r in rows if r["error"] is None]
        gold = [r["gold"] for r in ok]
        pred = [r["pred"] for r in ok]
        lat = np.array([r["latency_s"] for r in ok])
        nseg = np.array([r["n_segments"] for r in ok])
        types = {}
        for r in ok:
            for s in r["segments"]:
                types[s["type"]] = types.get(s["type"], 0) + 1
        m = scores(gold, pred)
        m.update({
            "macro_f1_ci95": bootstrap_ci(gold, pred),
            "api_errors_after_retries": len(rows) - len(ok),
            "fallback_rate": float(np.mean([r["fallback"] for r in ok])),
            "latency_s": {"median": float(np.median(lat)), "p95": float(np.percentile(lat, 95)), "mean": float(lat.mean())},
            "segments_per_comment": {"mean": float(nseg.mean()), "multi_segment_share": float(np.mean(nseg > 1))},
            "segment_types": types,
        })
        metrics["models"][name] = m
        preds_subset[name] = (gold, pred)

    for key, name in [("tfidf_lr", "TF-IDF + LR"), ("mbert", "mBERT fine-tuned")]:
        if key not in base["models"]:
            continue
        predall = base["models"][key]["pred"]
        full = scores(base["gold"], predall)
        gold = [base["gold"][pos[i]] for i in sample_ids]
        pred = [predall[pos[i]] for i in sample_ids]
        sub = scores(gold, pred)
        sub["macro_f1_ci95"] = bootstrap_ci(gold, pred)
        metrics["models"][name] = {**sub, "full_test": full, "meta": base["models"][key]["meta"]}
        preds_subset[name] = (gold, pred)

    # majority-class reference
    gold = preds_subset[next(iter(preds_subset))][0]
    maj = scores(gold, ["positive"] * len(gold))
    metrics["models"]["Majority class (positive)"] = maj
    metrics["gold_distribution"] = {l: gold.count(l) for l in LABELS}
    # Paired bootstrap: macro-F1(other) - macro-F1(HealAura) on the same items.
    ref = "HealAura (Sarvam-105B, few-shot)"
    g_ref, p_ref = map(np.array, preds_subset[ref])
    metrics["paired_diff_vs_healaura"] = {}
    for n, (g, p) in preds_subset.items():
        if n == ref:
            continue
        g, p = np.array(g), np.array(p)
        diffs = []
        for _ in range(2000):
            i = rng.integers(0, len(g), len(g))
            diffs.append(f1_score(g[i], p[i], labels=LABELS, average="macro", zero_division=0)
                         - f1_score(g_ref[i], p_ref[i], labels=LABELS, average="macro", zero_division=0))
        metrics["paired_diff_vs_healaura"][n] = {
            "mean": float(np.mean(diffs)),
            "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "p_le_0": float(np.mean(np.array(diffs) <= 0)),
        }
    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics["paired_diff_vs_healaura"], indent=1))

    # Fig. 6 — confusion matrices
    show = [n for n in ["HealAura (Sarvam-105B, few-shot)", "mBERT fine-tuned", "TF-IDF + LR"] if n in preds_subset]
    fig, axes = plt.subplots(1, len(show), figsize=(2.6 * len(show), 2.6))
    for ax, n in zip(np.atleast_1d(axes), show):
        g, p = preds_subset[n]
        cm = confusion_matrix(g, p, labels=LABELS)
        cmn = cm / cm.sum(axis=1, keepdims=True)
        ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
        for i in range(4):
            for j in range(4):
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8,
                        color="white" if cmn[i, j] > 0.55 else "black")
        ax.set_xticks(range(4), [l[:3] for l in LABELS]); ax.set_yticks(range(4), [l[:3] for l in LABELS])
        ax.set_xlabel("predicted"); ax.set_title(n.replace(" (Sarvam-105B, few-shot)", "\n(few-shot LLM)"), fontsize=8)
    np.atleast_1d(axes)[0].set_ylabel("gold")
    fig.tight_layout()
    fig.savefig(FIG / "fig6_confusion.png", dpi=220, facecolor="white")
    plt.close(fig)

    # Fig. 7 — macro-F1 with bootstrap CI
    order = [n for n in ["Majority class (positive)", "TF-IDF + LR", "mBERT fine-tuned",
                         "Sarvam-105B zero-shot", "HealAura (Sarvam-105B, few-shot)"] if n in metrics["models"]]
    vals = [metrics["models"][n]["macro_f1"] for n in order]
    ci = [metrics["models"][n].get("macro_f1_ci95", [v, v]) for n, v in zip(order, vals)]
    err = np.array([[v - c[0] for v, c in zip(vals, ci)], [c[1] - v for v, c in zip(vals, ci)]])
    fig, ax = plt.subplots(figsize=(6.2, 2.4))
    palette = {"Majority class (positive)": "#bbbbbb", "TF-IDF + LR": "#9db7d5", "mBERT fine-tuned": "#5b8cc0",
               "Sarvam-105B zero-shot": "#f0b27a", "HealAura (Sarvam-105B, few-shot)": "#d9772b"}
    colors = [palette[n] for n in order]
    ax.barh(range(len(order)), vals, xerr=err, color=colors, capsize=3, height=0.6)
    for i, v in enumerate(vals):
        ax.text(v + 0.01, i + 0.25, f"{v:.3f}", fontsize=8)
    ax.set_yticks(range(len(order)), order); ax.set_xlabel("macro-F1 (4-class), 95% bootstrap CI")
    ax.set_xlim(0, 1); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "fig7_macro_f1.png", dpi=220, facecolor="white")
    plt.close(fig)

    for n in order:
        m = metrics["models"][n]
        print(f"{n:40s} n={m['n']} acc={m['accuracy']:.3f} macroF1={m['macro_f1']:.3f} "
              f"wF1={m['weighted_f1']:.3f} " + " ".join(f"{l[:3]}={m['per_class'][l]['f1']:.2f}" for l in LABELS))


if __name__ == "__main__":
    main()
