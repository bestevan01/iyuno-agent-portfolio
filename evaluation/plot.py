"""평가 결과 그래프 생성 + evaluation/metrics.json(요약본) 작성.

    python -m evaluation.plot
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from agent.config import ROOT  # noqa: E402

EVAL = ROOT / "evaluation"
RES = EVAL / "results"
FIG = EVAL / "figures"

# 범주형 색(고정 순서): blue, orange, aqua — 색각이상 검증된 팔레트의 1~3번 슬롯
C = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _font():
    for name in ["Noto Sans CJK KR", "Noto Sans CJK JP", "NanumGothic", "AppleGothic", "Malgun Gothic"]:
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            return
    plt.rcParams["font.family"] = "DejaVu Sans"


def load(name: str) -> dict | None:
    p = RES / name / "metrics.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _style(ax, title: str):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=13, color=INK, pad=14, fontweight="bold")
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 1.18)


def grouped(ax, groups, series, values, colors):
    n = len(series)
    w = 0.8 / n
    for i, (name, vals, col) in enumerate(zip(series, values, colors, strict=True)):
        xs = [g + (i - (n - 1) / 2) * w for g in range(len(groups))]
        bars = ax.bar(xs, vals, width=w - 0.04, color=col, label=name, edgecolor=SURFACE, linewidth=2)
        for b, v in zip(bars, vals, strict=True):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", va="bottom",
                    fontsize=9, color=INK2)
    ax.set_xticks(range(len(groups)), groups, fontsize=11, color=INK)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 1.02), ncol=n, fontsize=10)


def main() -> None:
    _font()
    FIG.mkdir(parents=True, exist_ok=True)
    runs = {k: load(k) for k in ["offline-tfidf-dev", "offline-dense-dev", "offline-hybrid-dev",
                                 "offline-dense-holdout", "offline-hybrid-holdout"]}

    # 1) 검색 방식 비교 (dev 30문항)
    metrics = ["hit@4", "recall@4", "mrr"]
    labels = ["Hit@4", "Recall@4", "MRR"]
    names = [("offline-tfidf-dev", "TF-IDF (키워드만)"), ("offline-dense-dev", "e5 Dense"),
             ("offline-hybrid-dev", "Hybrid (e5 + 용어사전)")]
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    grouped(ax, labels, [n for _, n in names],
            [[runs[k]["retrieval"][m] for m in metrics] for k, _ in names], C)
    _style(ax, "검색 방식별 성능 — 개발셋 30문항")
    fig.text(0.01, 0.01, "한국어 질문 → 영문 OWASP 문서. 높을수록 좋음.", fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / "retrieval_ablation.png", dpi=160)
    plt.close(fig)

    # 2) 개발셋 vs 홀드아웃 (과적합 확인)
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    groups = ["Hit@4 (dev)", "Hit@4 (holdout)", "Keyword (dev)", "Keyword (holdout)"]
    dense = [runs["offline-dense-dev"]["retrieval"]["hit@4"], runs["offline-dense-holdout"]["retrieval"]["hit@4"],
             runs["offline-dense-dev"]["answer"]["keyword_coverage"], runs["offline-dense-holdout"]["answer"]["keyword_coverage"]]
    hybrid = [runs["offline-hybrid-dev"]["retrieval"]["hit@4"], runs["offline-hybrid-holdout"]["retrieval"]["hit@4"],
              runs["offline-hybrid-dev"]["answer"]["keyword_coverage"], runs["offline-hybrid-holdout"]["answer"]["keyword_coverage"]]
    grouped(ax, groups, ["e5 Dense", "Hybrid"], [dense, hybrid], C[1:3])
    _style(ax, "튜닝 후 새 질문(홀드아웃 12문항)에서도 개선이 유지되는가")
    fig.text(0.01, 0.01, "용어사전은 개발셋 오류 분석 후 추가 → 홀드아웃은 그 뒤에 작성해 한 번만 평가.", fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / "dev_vs_holdout.png", dpi=160)
    plt.close(fig)

    # 요약 metrics.json
    llm = sorted(p.parent.name for p in RES.glob("llm-*/metrics.json"))
    summary = {
        "primary_run": "offline-hybrid-dev",
        "primary": runs["offline-hybrid-dev"],
        "holdout": runs["offline-hybrid-holdout"],
        "ablation": {k: {"retrieval": v["retrieval"], "answer": v["answer"], "latency_ms": v["latency_ms"]}
                     for k, v in runs.items() if v},
        "llm_runs": {k: load(k) for k in llm},
    }
    (EVAL / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("figures ->", FIG, "| summary -> evaluation/metrics.json")


if __name__ == "__main__":
    main()
