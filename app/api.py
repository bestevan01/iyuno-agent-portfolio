"""FastAPI 서버.

    uvicorn app.api:app --reload
    curl -s localhost:8000/ask -H 'content-type: application/json' -d '{"question":"SSRF 예방법은?"}'
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import load_agent
from agent.feedback import log_run, record_feedback, stats

app = FastAPI(title="agentic-knowledge-triage", version="1.0.0",
              description="OWASP 문서 기반 RAG + tool calling 보안 Q&A 에이전트")


class AskIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)


class FeedbackIn(BaseModel):
    question: str
    answer: str
    rating: int = Field(..., description="1 = 좋음, -1 = 나쁨")
    correction: str = ""
    citations: list[str] = []


@app.get("/health")
def health() -> dict:
    agent = load_agent()
    return {"status": "ok", "chunks": len(agent.index.chunks), "mode": "llm" if agent.client else "offline"}


@app.post("/ask")
def ask(body: AskIn) -> dict:
    agent = load_agent()
    res = agent.ask(body.question)
    log_run(res, agent.s.db_file)
    return res.to_dict()


@app.get("/stats")
def get_stats() -> dict:
    """운영 지표: 요청 수, 지연시간 p50/p95, 누적 토큰·비용, 피드백 분포."""
    return stats(load_agent().s.db_file)


@app.post("/feedback")
def feedback(body: FeedbackIn) -> dict:
    try:
        saved = record_feedback(body.question, body.answer, body.rating, body.correction, body.citations,
                                load_agent().s.db_file)
        return {"saved": saved}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
