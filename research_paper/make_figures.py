"""Generate the figures used in HealAura_IEEE_Paper.md (run: python make_figures.py)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.size": 9})

C_UI, C_API, C_AI, C_DB, C_EXT = "#dbe9f6", "#e3f1df", "#fde9d4", "#ece3f4", "#f6dede"


def box(ax, x, y, w, h, text, color, fs=8.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=color, ec="#333", lw=0.9))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            weight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, label="", style="-|>", ls="-", fs=7.5, off=(0, 0.12)):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, lw=0.9, color="#333", linestyle=ls))
    if label:
        ax.text((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1], label, ha="center",
                fontsize=fs, style="italic", color="#222")


def canvas(w, h, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, xlim); ax.set_ylim(0, ylim); ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# Fig. 1 — System architecture
fig, ax = canvas(7.2, 4.4, 12, 7.3)
box(ax, 0.2, 5.6, 11.6, 1.4, "", C_UI)
ax.text(0.4, 6.75, "Client — React 19 + TypeScript (Vite)", fontsize=8.5, weight="bold", va="center")
for i, t in enumerate(["Talk with AI\n(text / voice journal)", "Community\n(anonymous)",
                       "Counsellors\n(directory)", "Close friends", "Admin"]):
    box(ax, 0.45 + i * 2.28, 5.75, 2.05, 0.8, t, "white", fs=7.5)
box(ax, 0.2, 2.5, 7.4, 2.6, "", C_API)
ax.text(0.4, 4.85, "Backend — FastAPI / Uvicorn (async)", fontsize=8.5, weight="bold", va="center")
box(ax, 0.4, 3.55, 1.6, 0.95, "Auth\n(bearer token)", "white", fs=7.5)
box(ax, 2.15, 3.55, 1.7, 0.95, "Segmenter &\nclassifier", C_AI, fs=7.5)
box(ax, 4.0, 3.55, 1.7, 0.95, "Back-channel\nlistener", C_AI, fs=7.5)
box(ax, 5.85, 3.55, 1.55, 0.95, "Well-being\nagent", C_AI, fs=7.5)
box(ax, 0.4, 2.65, 3.45, 0.7, "Speech I/O (STT / TTS)", "white", fs=7.5)
box(ax, 4.0, 2.65, 3.4, 0.7, "Reminder scheduler", "white", fs=7.5)
box(ax, 8.2, 2.5, 3.6, 2.6, "", C_EXT)
ax.text(10.0, 4.8, "Sarvam AI (external)", fontsize=8.5, weight="bold", ha="center", va="center")
box(ax, 8.4, 3.75, 3.2, 0.7, "Sarvam-105B (LLM)", "white", fs=7.5)
box(ax, 8.4, 2.65, 1.5, 0.85, "Saaras v3\nSTT", "white", fs=7)
box(ax, 10.05, 2.65, 1.55, 0.85, "Bulbul v3\nTTS", "white", fs=7)
box(ax, 0.2, 0.3, 7.4, 1.5, "", C_DB)
ax.text(3.9, 1.5, "PostgreSQL (Neon) via asyncpg", fontsize=8.5, weight="bold", ha="center", va="center")
ax.text(3.9, 0.8, "users · sessions · entries (segments, sentiment,\ncorrected_*) · messages · friends · community",
        fontsize=7.5, ha="center", va="center")
box(ax, 8.2, 0.3, 3.6, 1.5, "SMTP (Gmail)\ncheck-in e-mail to\nopted-in close friends", C_EXT, fs=7.5)
arrow(ax, 3.9, 5.6, 3.9, 5.1, "REST / JSON  (Vite proxy)", style="<|-|>", off=(1.6, -0.05))
arrow(ax, 7.6, 4.1, 8.2, 4.1, style="<|-|>")
arrow(ax, 7.6, 3.0, 8.2, 3.0, style="<|-|>")
arrow(ax, 3.9, 2.5, 3.9, 1.8, style="<|-|>")
arrow(ax, 6.6, 3.55, 9.2, 1.8)
ax.text(6.9, 1.95, "only on sustained distress", fontsize=7, style="italic", ha="center")
save(fig, "fig1_architecture.png")

# Fig. 2 — Entry processing pipeline
fig, ax = canvas(8.4, 3.0, 14.2, 5.4)
box(ax, 0.1, 2.3, 1.6, 1.0, "Voice\nentry", C_UI)
box(ax, 0.1, 0.5, 1.6, 1.0, "Text\nentry", C_UI)
box(ax, 2.3, 2.3, 1.9, 1.0, "Saaras v3\nSTT", C_EXT, fs=8)
box(ax, 4.8, 1.3, 1.8, 1.2, "Raw entry\n+ language", "white", fs=8)
box(ax, 7.3, 3.2, 2.5, 1.2, "Segment + classify\n(type, sentiment,\ndate, time, person)", C_AI, fs=7.5)
box(ax, 7.3, 0.3, 2.5, 1.2, "Back-channel reply\n(≤ 6 words)\n+ needs_support", C_AI, fs=7.5)
box(ax, 10.5, 3.2, 1.6, 1.2, "Validate\n& store", C_DB, fs=8)
box(ax, 10.5, 0.3, 1.6, 1.2, "Reply\n(text / TTS)", C_UI, fs=8)
box(ax, 12.5, 1.75, 1.6, 1.3, "Well-being\nagent", C_AI, fs=8)
arrow(ax, 1.7, 2.8, 2.3, 2.8)
arrow(ax, 4.2, 2.8, 4.8, 2.1)
arrow(ax, 1.7, 1.0, 4.8, 1.6)
arrow(ax, 6.6, 2.1, 7.3, 3.8)
arrow(ax, 6.6, 1.7, 7.3, 0.9)
arrow(ax, 9.8, 3.8, 10.5, 3.8)
arrow(ax, 9.8, 0.9, 10.5, 0.9)
arrow(ax, 12.1, 3.8, 12.8, 3.05)
arrow(ax, 9.8, 1.2, 12.5, 2.2, "flag", off=(0.9, 0.05))
ax.text(7.3, 5.05, "retry ×3 → fallback: single memory / neutral segment", fontsize=7, style="italic")
save(fig, "fig2_pipeline.png")

# Fig. 4 — Well-being agent gating (horizontal arrows = "yes")
fig, ax = canvas(9.0, 2.4, 16.6, 4.4)
steps = [("Entry\nprocessed", C_UI),
         ("G1: LLM\nneeds_support?", C_AI),
         ("G2: ≥ 3 negative\nsegments in 24 h?", C_AI),
         ("G3: no alert in\nlast 12 h?", C_AI),
         ("G4: ≥ 1 close\nfriend listed?", C_AI),
         ("E-mail check-in\n(no content shared)", C_EXT)]
for i, (t, c) in enumerate(steps):
    box(ax, 0.1 + i * 2.75, 2.2, 2.35, 1.3, t, c, fs=7.5)
    if i:
        arrow(ax, 0.1 + i * 2.75 - 0.4, 2.85, 0.1 + i * 2.75, 2.85)
    if 1 <= i <= 4:
        arrow(ax, 1.27 + i * 2.75, 2.2, 1.27 + i * 2.75, 1.0, "no", off=(0.25, 0))
box(ax, 2.8, 0.2, 11.2, 0.8, "Stop silently — journaling flow is never blocked (errors swallowed and logged)", "#f2f2f2", fs=8)
save(fig, "fig4_agent.png")

# Fig. 3 — Human-in-the-loop label loop, vs. base-paper active learning
fig, ax = canvas(8.2, 3.1, 16.4, 6)
ax.text(3.8, 5.6, "(a) Adaptive active learning [7]", ha="center", weight="bold")
ax.text(12.3, 5.6, "(b) HealAura correction loop", ha="center", weight="bold")
for (cx, items) in [(3.8, ["Labelled pool", "Train classifier", "Score unlabelled pool\n(uncertainty)", "Query oracle\n(expert label)"]),
                    (12.3, ["LLM segment labels\n(type, sentiment)", "Show to user", "User edits one field\n(PATCH /entries)", "corrected_* overrides\nmodel label"])]:
    pts = [(cx - 1.3, 4.1), (cx + 1.0, 2.5), (cx - 1.3, 0.3), (cx - 3.4, 2.5)]
    for (x, y), t in zip(pts, items):
        box(ax, x, y, 2.9, 1.05, t, C_AI if "classif" in t or "LLM" in t else "white", fs=7.5)
    arrow(ax, cx + 1.3, 4.6, cx + 2.2, 3.55)
    arrow(ax, cx + 2.2, 2.5, cx + 1.3, 1.1)
    arrow(ax, cx - 1.3, 0.8, cx - 2.1, 2.5)
    arrow(ax, cx - 2.1, 3.55, cx - 1.3, 4.6)
save(fig, "fig3_hitl_loop.png")

# Fig. 5 — Illustration of the sustained-distress rule on a synthetic timeline
hours = [h / 4 for h in range(0, 48 * 4 + 1)]
neg_events = [2, 5, 9, 14, 15, 16, 21, 31, 40, 41, 42]  # synthetic, for illustration only
need = {15, 21, 41}
roll = [sum(1 for e in neg_events if h - 24 < e <= h) for h in hours]
fig, ax = plt.subplots(figsize=(7.0, 2.4))
ax.step(hours, roll, where="post", color="#3b6ea5", lw=1.4, label="negative segments in trailing 24 h")
ax.axhline(3, color="#b04040", ls="--", lw=1, label="threshold (3)")
for e in neg_events:
    ax.plot(e, 0.15, "|", color="#555", ms=8)
alerts, last = [], -99
for e in sorted(need):
    if sum(1 for n in neg_events if e - 24 < n <= e) >= 3 and e - last >= 12:
        alerts.append(e); last = e
    ax.plot(e, 0.15, "v", color="#d08020", ms=6)
for a in alerts:
    ax.axvspan(a, a + 12, color="#f0c0c0", alpha=0.35)
    ax.annotate("alert", (a, 3.2), xytext=(a + 1.0, 7.6), fontsize=7.5, arrowprops=dict(arrowstyle="->", lw=0.7))
ax.set_xlabel("time (h)"); ax.set_ylabel("count"); ax.set_ylim(0, 8.5)
ax.plot([], [], "v", color="#d08020", label="needs_support flag")
ax.fill_between([], [], color="#f0c0c0", label="12 h cooldown")
ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=4, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
save(fig, "fig5_distress_rule.png")
print("figures written to", OUT)
