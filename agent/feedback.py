"""실행 로그 + 피드백 저장소(SQLite).

- runs     : 질문마다 지연시간·토큰·비용·호출한 도구를 기록 → /stats 로 운영 지표 확인
- feedback : 사용자의 👍/👎 와 수정 의견
`python -m agent.feedback export` 는 👎 + 수정 의견이 달린 항목을
평가셋 후보(evaluation/feedback_candidates.jsonl)로 변환한다.
→ 틀린 답변이 다음 평가 라운드의 회귀 테스트가 되는 구조.
"""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

from .config import ROOT, get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    question TEXT NOT NULL,
    mode TEXT,
    tools TEXT,
    n_citations INTEGER,
    latency_ms REAL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cost_usd REAL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    correction TEXT DEFAULT '',
    citations TEXT DEFAULT '[]'
);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or get_settings().db_file
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


PW_IN_QUESTION = re.compile(r"((?:비밀번호|패스워드|password)\s*[\"'“‘`])([^\"'”’`]+)([\"'”’`])", re.I)


def redact(question: str) -> str:
    """질문에 들어 있는 비밀번호 원문을 ***로 가린다(로그 저장용)."""
    return PW_IN_QUESTION.sub(lambda m: m.group(1) + "*" * len(m.group(2)) + m.group(3), question)


def log_run(result, path: Path | None = None) -> None:
    """AgentResult 한 건을 기록. 비밀번호 원문은 가리고, 도구 인자는 저장하지 않는다."""
    with connect(path) as con:
        con.execute(
            "INSERT INTO runs (ts, question, mode, tools, n_citations, latency_ms, prompt_tokens, completion_tokens, cost_usd)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (_now(), redact(result.question), result.mode, json.dumps([t.name for t in result.tool_calls]),
             len(result.citations), result.latency_ms, result.prompt_tokens, result.completion_tokens, result.cost_usd),
        )


def stats(path: Path | None = None) -> dict:
    with connect(path) as con:
        rows = con.execute("SELECT latency_ms, prompt_tokens, completion_tokens, cost_usd FROM runs").fetchall()
        fb = con.execute("SELECT rating, COUNT(*) c FROM feedback GROUP BY rating").fetchall()
    lat = sorted(r["latency_ms"] for r in rows)
    return {
        "runs": len(rows),
        "latency_ms_p50": statistics.median(lat) if lat else None,
        "latency_ms_p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else None,
        "tokens_total": sum(r["prompt_tokens"] + r["completion_tokens"] for r in rows),
        "cost_usd_total": round(sum(r["cost_usd"] for r in rows), 6),
        "feedback": {("positive" if r["rating"] == 1 else "negative"): r["c"] for r in fb},
    }


def record_feedback(question: str, answer: str, rating: int, correction: str = "",
                    citations: list[str] | None = None, path: Path | None = None) -> dict:
    if rating not in (1, -1):
        raise ValueError("rating must be 1 (good) or -1 (bad)")
    row = {"ts": _now(), "question": question, "answer": answer, "rating": rating,
           "correction": correction.strip(), "citations": citations or []}
    with connect(path) as con:
        con.execute("INSERT INTO feedback (ts, question, answer, rating, correction, citations) VALUES (?,?,?,?,?,?)",
                    (row["ts"], question, answer, rating, row["correction"], json.dumps(row["citations"])))
    return row


def export_candidates(src: Path | None = None, dst: Path | None = None) -> int:
    dst = dst or ROOT / "evaluation" / "feedback_candidates.jsonl"
    with connect(src) as con:
        rows = con.execute("SELECT question, correction FROM feedback WHERE rating = -1 AND correction != ''"
                           " ORDER BY id").fetchall()
    with open(dst, "w", encoding="utf-8") as out:
        for i, r in enumerate(rows, 1):
            out.write(json.dumps({
                "id": f"fb-{i:03d}",
                "type": "rag",
                "question": r["question"],
                "reference_answer": r["correction"],
                "expected_docs": [],  # 사람이 검수 후 채움
                "source": "user_feedback",
            }, ensure_ascii=False) + "\n")
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        print(f"exported {export_candidates()} candidates")
    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    else:
        print("usage: python -m agent.feedback [export|stats]")
