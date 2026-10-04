"""Supervised baselines on the same Tanglish sentiment task as run_llm_eval.py.

1. TF-IDF (word 1-2 grams + char 2-5 grams) + logistic regression (class-balanced)
2. mBERT (bert-base-multilingual-cased) fine-tuned for 2 epochs on CPU

Both are trained on the train split (not-Tamil removed), with model selection on
validation, and evaluated on (a) the full test split and (b) the same 500-item
sample the LLM saw (sample_ids.json). Predictions are written to
baseline_preds.json for analyze.py.

Usage: python run_baselines.py [--skip-mbert]
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from datasets import load_dataset
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

HERE = Path(__file__).resolve().parent
LABELS = ["positive", "negative", "mixed", "neutral"]  # dataset ids 0..3; 4 (not-Tamil) dropped
SEED = 42


def split(name):
    ds = load_dataset("community-datasets/tamilmixsentiment", split=name)
    rows = [(i, r["text"], r["label"]) for i, r in enumerate(ds) if r["label"] < 4]
    idx, x, y = zip(*rows)
    return list(idx), list(x), np.array(y)


def tfidf_lr(xtr, ytr, xva, yva, xte):
    word = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
    Xtr = hstack([word.fit_transform(xtr), char.fit_transform(xtr)]).tocsr()
    Xva = hstack([word.transform(xva), char.transform(xva)]).tocsr()
    Xte = hstack([word.transform(xte), char.transform(xte)]).tocsr()
    best = None
    for C in (0.5, 1, 2, 4, 8):
        clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=SEED)
        clf.fit(Xtr, ytr)
        f1 = f1_score(yva, clf.predict(Xva), average="macro")
        print(f"  TF-IDF LR C={C}: val macro-F1={f1:.4f}")
        if best is None or f1 > best[0]:
            best = (f1, C, clf)
    print(f"  selected C={best[1]}")
    return best[2].predict(Xte), {"C": best[1], "val_macro_f1": best[0]}


def mbert(xtr, ytr, xva, yva, xte, epochs=2, max_len=64, bs=32, lr=3e-5):
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    torch.manual_seed(SEED)
    torch.set_num_threads(8)
    name = "bert-base-multilingual-cased"
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name, num_labels=4)

    def enc(x, y=None):
        e = tok(x, truncation=True, max_length=max_len, padding="max_length", return_tensors="pt")
        t = [e["input_ids"], e["attention_mask"]]
        if y is not None:
            t.append(torch.tensor(y))
        return TensorDataset(*t)

    tr = DataLoader(enc(xtr, ytr), batch_size=bs, shuffle=True)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * len(tr)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    def predict(x):
        model.eval()
        out = []
        with torch.no_grad():
            for ids, mask in DataLoader(enc(x), batch_size=128):
                out.append(model(input_ids=ids, attention_mask=mask).logits.argmax(-1).numpy())
        return np.concatenate(out)

    best_f1, best_state, log = -1, None, []
    for ep in range(epochs):
        model.train()
        t0 = time.time()
        for step, (ids, mask, y) in enumerate(tr):
            loss = model(input_ids=ids, attention_mask=mask, labels=y).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            if step % 50 == 0:
                print(f"  mBERT ep{ep} step {step}/{len(tr)} loss={loss.item():.3f} ({time.time()-t0:.0f}s)", flush=True)
        f1 = f1_score(yva, predict(xva), average="macro")
        log.append({"epoch": ep + 1, "val_macro_f1": f1, "epoch_time_s": time.time() - t0})
        print(f"  mBERT epoch {ep+1}: val macro-F1={f1:.4f}", flush=True)
        if f1 > best_f1:
            best_f1 = f1
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return predict(xte), {"epochs": log, "max_len": max_len, "batch_size": bs, "lr": lr}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-mbert", action="store_true")
    args = ap.parse_args()
    _, xtr, ytr = split("train")
    _, xva, yva = split("validation")
    ite, xte, yte = split("test")
    print(f"train={len(xtr)} val={len(xva)} test={len(xte)}")

    out = {"test_idx": ite, "gold": [LABELS[i] for i in yte], "models": {}}
    pth = HERE / "baseline_preds.json"
    if pth.exists():
        out["models"] = json.loads(pth.read_text()).get("models", {})

    print("TF-IDF + LR")
    p, meta = tfidf_lr(xtr, ytr, xva, yva, xte)
    out["models"]["tfidf_lr"] = {"pred": [LABELS[i] for i in p], "meta": meta}
    pth.write_text(json.dumps(out))

    if not args.skip_mbert:
        print("mBERT")
        p, meta = mbert(xtr, ytr, xva, yva, xte)
        out["models"]["mbert"] = {"pred": [LABELS[i] for i in p], "meta": meta}
        pth.write_text(json.dumps(out))
    print("wrote", pth)


if __name__ == "__main__":
    main()
