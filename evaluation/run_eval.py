"""정량 평가 스크립트.

    python -m evaluation.run_eval                          # 기본: dev셋, 현재 설정(.env)
    python -m evaluation.run_eval --set holdout --name offline-hybrid-holdout
    LLM_BASE_URL=http://localhost:11434/v1 python -m evaluation.run_eval --name llm-qwen

지표
- 검색   : Hit@k, Recall@k(문서 단위), MRR
- 답변   : Keyword coverage(기대 핵심어 포함률), Faithfulness(proxy), Citation precision
- 도구   : Tool selection accuracy, Tool result accuracy
- 거절   : 범위 밖 질문 거절률(Abstain accuracy)
- 운영   : Latency p50/p95, 토큰 수, 비용(USD)

Faithfulness(proxy): 답변 문장마다 근거 조각의 '문장'들과 최대 임베딩 유사도를 구해
임계값(0.90) 이상이면 '근거 있음'으로 본다. 임계값은 음성 대조군(다른 질문의 근거와
짝지은 답변)으로 보정했다: 0.90에서 양성 98.9% / 음성 1.1% 통과.
단, 한국어로 바꿔 쓴 문장은 부정문('평문 저장해도 된다')도 0.86~0.88이 나와
임베딩만으로는 사실 여부를 가르지 못한다 → LLM 모드는 --judge 로 LLM 판정을 함께 쓴다.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time

import numpy as np

from agent.agent import Agent
from agent.config import ROOT, get_settings
from agent.retriever import VectorIndex

EVAL = ROOT / "evaluation"
SETS = {"dev": EVAL / "questions.jsonl", "holdout": EVAL / "holdout.jsonl"}
FAITH_THRESHOLD = 0.90
# 거절 판정: 거절 표현이 있고 **인용이 하나도 없을 때만** 거절로 본다.
# (v1은 표현만 봐서, 인용을 단 정상 답변 속 "…는 확인되지 않습니다" 한 문장도 거절로 셌고,
#  "답변을 제공할 수 없습니다" 같은 표현은 놓쳤다 → evaluation/error_analysis.md 6절)
ABSTAIN_RE = re.compile(
    r"확인되지 않|찾지 못|제공할 수 없|답변(을|할) 수 없|정보(는|가) 없|관련(된)? (내용|정보)(이|가) 없|not found|no relevant", re.I)


def is_abstain(answer: str, citations: list[str]) -> bool:
    return not citations and (not answer.strip() or bool(ABSTAIN_RE.search(answer)))


def doc_of(chunk_id: str) -> str:
    return chunk_id.split("#")[0]


def retrieval_metrics(retrieved: list[str], expected: list[str], k: int) -> dict:
    docs: list[str] = []
    for cid in retrieved[:k]:
        docs.append(doc_of(cid))
    hit = any(d in expected for d in docs)
    recall = len({d for d in docs if d in expected}) / len(expected) if expected else 0.0
    rr = 0.0
    for i, d in enumerate(docs, 1):
        if d in expected:
            rr = 1 / i
            break
    return {"hit": float(hit), "recall": recall, "rr": rr}


def keyword_coverage(answer: str, groups: list[list[str]]) -> float:
    if not groups:
        return 1.0
    a = answer.lower()
    return sum(any(k.lower() in a for k in g) for g in groups) / len(groups)


def answer_sentences(answer: str) -> list[str]:
    out = []
    for s in re.split(r"(?<=[.!?。])\s+|\n+", answer):
        s = re.sub(r"\[\d+\]", "", s).strip(" -*•")
        if len(s) >= 15 and not s.endswith(":"):
            out.append(s)
    return out


def context_sentences(contexts: list[str]) -> list[str]:
    out = []
    for t in contexts:
        t = re.sub(r"\n(?![\n\-*|#]|\d+\.)", " ", t)  # 에이전트 발췌기와 같은 문장 분리 규칙
        for s in re.split(r"(?<=[.!?])\s+|\n+", t):
            s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
            s = re.sub(r"[`*_]", "", re.sub(r"\s+", " ", s)).strip(" -#|")
            if len(s) >= 20:
                out.append(s)
    return out


JUDGE_PROMPT = """다음 '근거'만 보고 '답변'의 각 문장이 근거로 뒷받침되는지 판정하라.
도구 계산 결과(CVSS 점수 등)나 '문서에서 확인되지 않습니다' 같은 문장은 제외한다.
JSON 한 줄로만 답하라: {{"total": 판정한 문장 수, "supported": 뒷받침되는 문장 수}}

[근거]
{context}

[답변]
{answer}"""


def llm_judge(client, model: str, answer: str, contexts: list[str]) -> float | None:
    if not contexts or not answer.strip():
        return None
    resp = client.chat.completions.create(model=model, temperature=0, messages=[
        {"role": "user", "content": JUDGE_PROMPT.format(context="\n---\n".join(contexts)[:12000], answer=answer)}])
    text = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S)
    # 설명 문장이 섞여도 마지막 {"total":…, "supported":…} 객체만 읽는다
    found = re.findall(r'\{[^{}]*"total"[^{}]*\}', text)
    if not found:
        return None
    try:
        d = json.loads(found[-1])
        total, sup = int(d["total"]), int(d["supported"])
        return min(sup, total) / total if total else None
    except (ValueError, KeyError, TypeError):
        return None


def faithfulness(answer: str, contexts: list[str], embedder) -> float | None:
    sents = answer_sentences(answer)
    contexts = context_sentences(contexts)
    if not sents or not contexts:
        return None
    cv = embedder.embed_passages(contexts)
    sv = embedder.embed_passages(sents)
    best = (sv @ cv.T).max(axis=1)
    return float((best >= FAITH_THRESHOLD).mean())


def tool_check(q: dict, res) -> tuple[float, float]:
    names = [t.name for t in res.tool_calls]
    sel = float(q["expected_tool"] in names)
    out = next((t.output for t in res.tool_calls if t.name == q["expected_tool"]), {})
    exp = q["expected"]
    if q["expected_tool"] == "cvss_calculator":
        ok = out.get("base_score") == exp["base_score"] and out.get("severity") == exp["severity"]
    elif q["expected_tool"] == "cwe_lookup":
        ok = str(out.get("top10", "")).startswith(exp["top10_code"])
    else:
        ok = out.get("passes") == exp["passes"]
    return sel, float(bool(ok))


def pct(xs: list[float], p: float) -> float:
    return float(np.percentile(xs, p)) if xs else 0.0


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 4) if xs else None


def aggregate(rows: list[dict], name: str, set_name: str, config: dict, k: int = 4) -> dict:
    rag = [r for r in rows if r["type"] == "rag"]
    tool = [r for r in rows if r["type"] == "tool"]
    oos = [r for r in rows if r["type"] == "out_of_scope"]
    lat = [r["latency_ms"] for r in rows]
    return {
        "run": name,
        "set": set_name,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "config": config,
        "n_questions": len(rows),
        "retrieval": {f"hit@{k}": mean([r["hit"] for r in rag]), f"recall@{k}": mean([r["recall"] for r in rag]),
                      "mrr": mean([r["rr"] for r in rag]), "n": len(rag)},
        "answer": {"keyword_coverage": mean([r["keyword"] for r in rag]),
                   "faithfulness_proxy": mean([r["faithfulness"] for r in rag]),
                   "faithfulness_llm_judge": mean([r.get("faithfulness_llm") for r in rag]),
                   "citation_precision": mean([r["citation_precision"] for r in rag]),
                   "false_abstain_rate": mean([float(r["abstained"]) for r in rag]),
                   "empty_answer_rate": mean([float(not r["answer"].strip()) for r in rows])},
        "tools": {"selection_accuracy": mean([r["tool_selected"] for r in tool]),
                  "result_accuracy": mean([r["tool_correct"] for r in tool]), "n": len(tool)},
        "out_of_scope": {"abstain_accuracy": mean([float(r["abstained"]) for r in oos]), "n": len(oos)},
        "latency_ms": {"p50": round(pct(lat, 50), 1), "p95": round(pct(lat, 95), 1), "mean": round(statistics.mean(lat), 1)},
        "tokens": {"prompt_total": sum(r["prompt_tokens"] for r in rows),
                   "completion_total": sum(r["completion_tokens"] for r in rows)},
        "cost_usd_total": round(sum(r["cost_usd"] for r in rows), 6),
    }


def run(set_name: str, name: str, k: int, judge: bool = False, budget_s: float | None = None) -> dict | None:
    """budget_s가 주어지면 그 시간 안에서만 문항을 처리하고 partial.jsonl에 이어 쓴다(재개 가능).
    모든 문항이 끝났을 때만 metrics.json을 만든다."""
    t_start = time.perf_counter()
    s = get_settings()
    index = VectorIndex.load(s.index_dir, s.e5_model, s.retrieval_mode, s.hybrid_alpha)
    agent = Agent(index, s)
    questions = [json.loads(line) for line in open(SETS[set_name], encoding="utf-8")]
    out_dir = EVAL / "results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = out_dir / "partial.jsonl"
    rows = [json.loads(line) for line in open(partial, encoding="utf-8")] if partial.exists() else []
    done = {r["id"] for r in rows}
    if not rows:
        agent.ask("warm-up: SQL injection")  # 모델 로딩 시간 제외

    for q in questions:
        if q["id"] in done:
            continue
        if budget_s is not None and time.perf_counter() - t_start > budget_s:
            print(f"PARTIAL {len(rows)}/{len(questions)}")
            return None
        res = agent.ask(q["question"])
        row = {"id": q["id"], "type": q["type"], "question": q["question"], "answer": res.answer,
               "tools": [t.name for t in res.tool_calls], "citations": [c.chunk_id for c in res.citations],
               "retrieved": res.retrieved_chunk_ids[:k], "latency_ms": res.latency_ms,
               "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
               "cost_usd": res.cost_usd}
        if q["type"] == "rag":
            row.update(retrieval_metrics(res.retrieved_chunk_ids, q["expected_docs"], k))
            row["keyword"] = keyword_coverage(res.answer, q.get("keywords", []))
            row["faithfulness"] = faithfulness(res.answer, res.contexts, index.embedder)
            if judge and agent.client is not None:
                row["faithfulness_llm"] = llm_judge(agent.client, s.llm_model, res.answer, res.contexts)
            cited_docs = [doc_of(c) for c in row["citations"]]
            row["citation_precision"] = (sum(d in q["expected_docs"] for d in cited_docs) / len(cited_docs)
                                         if cited_docs else 0.0)
            row["abstained"] = is_abstain(res.answer, row["citations"])
        elif q["type"] == "tool":
            row["tool_selected"], row["tool_correct"] = tool_check(q, res)
        else:
            row["abstained"] = is_abstain(res.answer, row["citations"])
        rows.append(row)
        with open(partial, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    order = {q["id"]: i for i, q in enumerate(questions)}
    rows.sort(key=lambda r: order[r["id"]])

    config = {"mode": "llm:" + s.llm_model if s.use_llm else "offline", "embedder": s.embedder,
              "e5_model": s.e5_model, "retrieval": s.retrieval_mode, "hybrid_alpha": s.hybrid_alpha,
              "top_k": k, "abstain_threshold": s.abstain_threshold, "faith_threshold": FAITH_THRESHOLD,
              "judge": ("self:" + s.llm_model) if (judge and s.use_llm) else None}
    metrics = aggregate(rows, name, set_name, config, k)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(out_dir / "per_question.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    partial.unlink(missing_ok=True)
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="dev", choices=list(SETS))
    ap.add_argument("--name", default=None)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--judge", action="store_true", help="LLM 모드에서 LLM 판정 faithfulness 추가")
    ap.add_argument("--budget", type=float, default=None, help="이번 실행에 쓸 최대 초(초과 시 중단, 다음 실행에서 이어서)")
    a = ap.parse_args()
    s = get_settings()
    name = a.name or f"{'llm' if s.use_llm else 'offline'}-{s.retrieval_mode}-{a.set}"
    m = run(a.set, name, a.k, a.judge, a.budget)
    if m is not None:
        print(json.dumps(m, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
