import json

import pytest
from fastapi.testclient import TestClient

import app.api as api
from agent.feedback import export_candidates, record_feedback, redact


@pytest.fixture()
def client(agent, monkeypatch):
    monkeypatch.setattr(api, "load_agent", lambda: agent)
    return TestClient(api.app)


def test_health(client):
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["chunks"] > 100 and r["mode"] == "offline"


def test_ask_endpoint(client):
    r = client.post("/ask", json={"question": "CWE-352 top 10 category"})
    assert r.status_code == 200
    body = r.json()
    assert "A01" in body["answer"]
    assert body["tool_calls"][0]["name"] == "cwe_lookup"


def test_ask_validation(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_stats_after_requests(client):
    client.post("/ask", json={"question": "CWE-89"})
    client.post("/feedback", json={"question": "q", "answer": "a", "rating": -1, "correction": "fix"})
    st = client.get("/stats").json()
    assert st["runs"] >= 1 and st["latency_ms_p50"] is not None
    assert st["feedback"]["negative"] >= 1


def test_feedback_roundtrip(tmp_path):
    fb = tmp_path / "fb.db"
    record_feedback("q1", "a1", 1, path=fb)
    record_feedback("q2", "a2", -1, "정답은 Argon2id", path=fb)
    record_feedback("q3", "a3", -1, "", path=fb)  # 수정 의견 없음 → 후보 제외
    out = tmp_path / "cand.jsonl"
    assert export_candidates(fb, out) == 1  # SQLite → 평가셋 후보 JSONL
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["question"] == "q2" and row["reference_answer"] == "정답은 Argon2id"


def test_feedback_rejects_bad_rating(tmp_path):
    with pytest.raises(ValueError):
        record_feedback("q", "a", 5, path=tmp_path / "x.db")


def test_redact_password_in_question():
    assert redact('비밀번호 "hunter22" 괜찮나요?') == '비밀번호 "********" 괜찮나요?'
    assert redact("SSRF 예방법") == "SSRF 예방법"
