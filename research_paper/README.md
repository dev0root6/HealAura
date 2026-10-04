# HealAura — IEEE research paper

- `HealAura_IEEE_Paper.md` — the paper (IEEE section/table/figure/reference style).
- `figures/` — Figs. 1–7. Figs. 1–5 come from `make_figures.py`; Figs. 6–7 come from `eval/analyze.py`.
- `eval/` — every experiment behind Section V, with raw outputs:
  - `run_llm_eval.py` — runs HealAura's production classifier (few-shot) and a zero-shot ablation on 500 Tanglish comments from DravidianCodeMix → `results_*.jsonl`. Needs `SARVAM_API_KEY` in `.env`, and the calls count against your Sarvam usage.
  - `run_baselines.py` — TF-IDF + logistic regression (and an mBERT baseline, which was not completed on CPU) → `baseline_preds.json`.
  - `analyze.py` — metrics, bootstrap CIs, paired tests, Figs. 6–7 → `metrics.json`.
  - `run_agent_checks.py` — runs the real well-being agent against an in-memory database and SMTP stand-in → `agent_checks.json`.

Reproduce (from the repo root, using the project venv):

```bash
.venv/bin/pip install scikit-learn datasets matplotlib
.venv/bin/python research_paper/eval/run_llm_eval.py --n 500 --concurrency 2
.venv/bin/python research_paper/eval/run_baselines.py --skip-mbert
.venv/bin/python research_paper/eval/analyze.py
.venv/bin/python research_paper/eval/run_agent_checks.py
python3 research_paper/make_figures.py
```

To build a PDF, convert with `pandoc HealAura_IEEE_Paper.md -o paper.tex` and move the content into the IEEEtran LaTeX template.
