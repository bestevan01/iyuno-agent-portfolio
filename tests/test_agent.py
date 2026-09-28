import json
from types import SimpleNamespace as NS

from agent.agent import Agent


def test_router_picks_tools(agent):
    plan = [n for n, _ in agent.route("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H 점수?")]
    assert plan == ["cvss_calculator"]
    assert [n for n, _ in agent.route("CWE-79 는 어디?")] == ["cwe_lookup"]
    assert "password_policy_check" in [n for n, _ in agent.route('비밀번호 "abc" 검사')]
    assert [n for n, _ in agent.route("SQL injection prevention")] == ["search_docs"]


def test_router_mfa_negation(agent):
    args = dict(agent.route('비밀번호 "qwerty123" 괜찮나요? MFA는 없어요')[0:1])["password_policy_check"]
    assert args["mfa_enabled"] is False
    args = dict(agent.route('MFA 켜둔 계정 비밀번호 "abc"')[0:1])["password_policy_check"]
    assert args["mfa_enabled"] is True


def test_offline_answer_has_citations(agent):
    res = agent.ask("How to prevent SQL injection with prepared statements?")
    assert res.citations, res.answer
    assert all(f"[{c.ref}]" in res.answer for c in res.citations)
    assert res.mode == "offline"


def test_offline_cvss_answer(agent):
    res = agent.ask("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
    assert "9.8" in res.answer


def test_password_never_in_trace(agent):
    res = agent.ask('비밀번호 "qwerty123" 괜찮나요? MFA는 없어요')
    assert "qwerty123" not in json.dumps(res.to_dict()["tool_calls"], ensure_ascii=False)
    assert "qwerty123" not in res.answer


def test_abstain_when_nothing_relevant(index, settings):
    settings_hi = type(settings)(**{**settings.__dict__, "abstain_threshold": 0.99})
    res = Agent(index, settings_hi).ask("zzzz qqqq")
    assert "확인되지 않" in res.answer
    assert res.citations == []


# ---------------- LLM 모드: 가짜 OpenAI 클라이언트로 tool calling 루프 검증 ----------------
class FakeClient:
    """1차 응답: search_docs 호출 → 2차 응답: [1] 인용한 최종 답변."""

    def __init__(self):
        self.calls = 0
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.calls += 1
        usage = NS(prompt_tokens=100, completion_tokens=20)
        if self.calls == 1:
            assert kw["tools"], "첫 호출에는 도구 스키마가 전달돼야 한다"
            tc = NS(id="c1", function=NS(name="search_docs", arguments=json.dumps({"query": "SSRF allowlist"})))
            return NS(choices=[NS(message=NS(content="", tool_calls=[tc]))], usage=usage)
        tool_msg = kw["messages"][-1]
        assert tool_msg["role"] == "tool" and "[ref 1]" in tool_msg["content"]
        return NS(choices=[NS(message=NS(content="<think>x</think>허용 목록을 사용하세요 [1].", tool_calls=None))],
                  usage=usage)


def test_llm_tool_calling_loop(index, settings):
    s = type(settings)(**{**settings.__dict__, "price_in_per_m": 1.0, "price_out_per_m": 2.0})
    res = Agent(index, s, client=FakeClient()).ask("SSRF 예방법은?")
    assert res.answer == "허용 목록을 사용하세요 [1]."
    assert [t.name for t in res.tool_calls] == ["search_docs"]
    assert len(res.citations) == 1 and res.citations[0].ref == 1
    assert res.prompt_tokens == 200 and res.completion_tokens == 40
    assert abs(res.cost_usd - (200 / 1e6 * 1 + 40 / 1e6 * 2)) < 1e-9


class EmptyAnswerClient(FakeClient):
    """검색은 하지만 최종 답변을 비워 보내는 모델(gpt-oss에서 실제로 관찰됨)."""

    def create(self, **kw):
        self.calls += 1
        usage = NS(prompt_tokens=10, completion_tokens=0)
        if self.calls == 1:
            tc = NS(id="c1", function=NS(name="search_docs", arguments=json.dumps({"query": "SQL injection prepared statements"})))
            return NS(choices=[NS(message=NS(content="", tool_calls=[tc]))], usage=usage)
        return NS(choices=[NS(message=NS(content="", tool_calls=None))], usage=usage)


def test_llm_empty_answer_falls_back_to_extractive(index, settings):
    res = Agent(index, settings, client=EmptyAnswerClient()).ask("SQL 인젝션 방어법")
    assert res.fallback is True
    assert res.answer.startswith("(모델이 최종 답변을 만들지 못해")
    assert res.citations, "대체 답변에도 인용이 붙어야 한다"


class EmptyAfterToolClient(FakeClient):
    """비밀번호 도구를 부른 뒤 빈 답을 내는 모델(qwen t07에서 관찰)."""

    def create(self, **kw):
        self.calls += 1
        usage = NS(prompt_tokens=10, completion_tokens=0)
        if self.calls == 1:
            args = json.dumps({"password": "qwerty123", "mfa_enabled": False})
            tc = NS(id="c1", function=NS(name="password_policy_check", arguments=args))
            return NS(choices=[NS(message=NS(content="", tool_calls=[tc]))], usage=usage)
        return NS(choices=[NS(message=NS(content="", tool_calls=None))], usage=usage)


def test_llm_empty_after_tool_still_reports_tool_result(index, settings):
    res = Agent(index, settings, client=EmptyAfterToolClient()).ask('비밀번호 "qwerty123" 괜찮나요? MFA는 안 써요')
    assert res.fallback is True
    assert "만족하지 않습니다" in res.answer
    assert "qwerty123" not in res.answer
