"""Agent / Router.

두 가지 실행 모드를 같은 인터페이스(Agent.ask)로 제공한다.

1) LLM 모드 (LLM_BASE_URL 설정 시)
   OpenAI 호환 Chat Completions + tool calling 루프.
   모델이 search_docs / cvss_calculator / cwe_lookup / password_policy_check 중
   필요한 도구를 스스로 골라 호출하고, 검색 결과의 [n] 번호로 인용한 답변을 만든다.

2) 오프라인 모드 (LLM 없음)
   규칙 기반 라우터가 도구를 고르고, 검색 결과에서 질문과 가장 가까운 문장을
   발췌해 인용과 함께 돌려준다. CI·평가 재현용이며 LLM 모드의 하한선(baseline) 역할.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .config import Settings, get_settings
from .retriever import VectorIndex
from .tools import TOOL_SCHEMAS, VECTOR_RE, build_registry, mask_args

SYSTEM_PROMPT = """너는 OWASP 공개 문서를 근거로 답하는 애플리케이션 보안 도우미다.
규칙:
1. 보안 개념·대응 방법·권고 사항 질문은 반드시 search_docs 로 근거를 찾은 뒤 답한다.
2. CVSS 벡터 점수는 cvss_calculator, CWE 번호는 cwe_lookup, 비밀번호 강도 검사는 password_policy_check 를 호출한다. 직접 계산하거나 추측하지 않는다.
3. 답변의 각 주장 뒤에 근거 번호를 [1], [2] 형식으로 붙인다. 번호는 search_docs 결과에 표시된 ref 값만 사용한다.
4. 근거 문서에 없는 내용은 "제공된 문서에서 확인되지 않습니다"라고 말한다.
5. 한국어로 간결하게(5문장 이내) 답한다. 비밀번호 원문은 답변에 다시 쓰지 않는다."""


@dataclass
class Citation:
    ref: int
    chunk_id: str
    title: str
    section: str
    url: str


@dataclass
class ToolCall:
    name: str
    arguments: dict
    latency_ms: float
    ok: bool
    output: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    question: str
    answer: str
    mode: str
    citations: list[Citation] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    fallback: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class _RefBook:
    """검색 결과 조각에 대화 전체에서 고유한 인용 번호를 매긴다."""

    def __init__(self):
        self.by_chunk: dict[str, int] = {}
        self.items: list[dict] = []

    def add(self, r: dict) -> int:
        if r["chunk_id"] not in self.by_chunk:
            self.by_chunk[r["chunk_id"]] = len(self.items) + 1
            self.items.append(r)
        return self.by_chunk[r["chunk_id"]]

    def citation(self, ref: int) -> Citation:
        r = self.items[ref - 1]
        return Citation(ref, r["chunk_id"], r["title"], r["section"], r["url"])


class Agent:
    def __init__(self, index: VectorIndex, settings: Settings | None = None, client: Any = None):
        self.s = settings or get_settings()
        self.index = index
        self.tools = build_registry(index, self.s)
        self.client = client
        if self.client is None and self.s.use_llm:
            from openai import OpenAI

            self.client = OpenAI(base_url=self.s.llm_base_url, api_key=self.s.llm_api_key, timeout=120)

    # ------------------------------------------------------------ public
    def ask(self, question: str) -> AgentResult:
        t0 = time.perf_counter()
        res = self._ask_llm(question) if self.client is not None else self._ask_offline(question)
        res.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        res.cost_usd = round(
            res.prompt_tokens / 1e6 * self.s.price_in_per_m + res.completion_tokens / 1e6 * self.s.price_out_per_m, 6
        )
        return res

    # ------------------------------------------------------------ tool exec
    def _run_tool(self, name: str, args: dict, book: _RefBook, res: AgentResult) -> dict:
        t0 = time.perf_counter()
        ok = True
        try:
            out = self.tools[name](**args)
        except Exception as e:  # 도구 오류는 모델에게 그대로 알려 재시도하게 한다
            out, ok = {"error": f"{type(e).__name__}: {e}"}, False
        if name == "search_docs" and "results" in out:
            out["low_confidence"] = bool(not out["results"] or out["results"][0]["score"] < self.s.abstain_threshold)
            for r in out["results"]:
                r["ref"] = book.add(r)
                if r["chunk_id"] not in res.retrieved_chunk_ids:
                    res.retrieved_chunk_ids.append(r["chunk_id"])
                    res.contexts.append(r["text"])
        summary = out if name != "search_docs" else {
            "low_confidence": out.get("low_confidence"),
            "hits": [(r["chunk_id"], r["score"]) for r in out.get("results", [])],
        }
        res.tool_calls.append(ToolCall(name, mask_args(name, args), round((time.perf_counter() - t0) * 1000, 1), ok, summary))
        return out

    # ------------------------------------------------------------ LLM mode
    def _ask_llm(self, question: str) -> AgentResult:
        res = AgentResult(question, "", mode=f"llm:{self.s.llm_model}")
        book = _RefBook()
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
        answer = ""
        for step in range(self.s.max_steps + 1):
            kwargs = dict(model=self.s.llm_model, messages=messages, temperature=0.2)
            if step < self.s.max_steps:
                kwargs["tools"] = TOOL_SCHEMAS
            else:  # 도구 호출 한도 도달 → 지금까지의 근거로 답하라고 명시
                messages.append({"role": "user", "content": "도구 호출 한도에 도달했습니다. 지금까지 받은 결과만으로 [n] 인용을 붙여 최종 답변을 작성하세요."})
            resp = self.client.chat.completions.create(**kwargs)
            if getattr(resp, "usage", None):
                res.prompt_tokens += resp.usage.prompt_tokens or 0
                res.completion_tokens += resp.usage.completion_tokens or 0
            msg = resp.choices[0].message
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                answer = msg.content or ""
                break
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls],
            })
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if c.function.name not in self.tools:
                    out = {"error": f"unknown tool {c.function.name}"}
                else:
                    out = self._run_tool(c.function.name, args, book, res)
                messages.append({"role": "tool", "tool_call_id": c.id, "content": self._tool_payload(c.function.name, out)})
        res.answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
        if not res.answer:
            # 모델이 도구는 불렀지만 빈 답을 낸 경우(qwen t07, gpt-oss q12에서 관찰)
            # → 같은 질문을 규칙 기반 경로로 다시 풀어 답을 채운다(도구 결과·인용 포함).
            off = self._ask_offline(question)
            res.fallback = True
            res.answer = "(모델이 최종 답변을 만들지 못해 규칙 기반 답변으로 대체합니다)\n" + off.answer
            res.citations = off.citations
            res.tool_calls += off.tool_calls
            for cid, ctx in zip(off.retrieved_chunk_ids, off.contexts, strict=True):
                if cid not in res.retrieved_chunk_ids:
                    res.retrieved_chunk_ids.append(cid)
                    res.contexts.append(ctx)
            return res
        self._attach_citations(res, book)
        return res

    @staticmethod
    def _tool_payload(name: str, out: dict) -> str:
        if name == "search_docs" and "results" in out:
            warn = ("[주의] 검색 점수가 낮습니다. 문서에 답이 없을 가능성이 큽니다. "
                    "근거가 없으면 '제공된 문서에서 확인되지 않습니다'라고 답하세요.\n\n") if out.get("low_confidence") else ""
            return warn + "\n\n".join(
                f"[ref {r['ref']}] {r['title']} — {r['section']}\n{r['text']}" for r in out["results"]
            )
        return json.dumps(out, ensure_ascii=False)

    @staticmethod
    def _attach_citations(res: AgentResult, book: _RefBook) -> None:
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", res.answer) if 0 < int(n) <= len(book.items)})
        res.citations = [book.citation(n) for n in cited]

    # ------------------------------------------------------------ offline mode
    PW_RE = re.compile(r"(?:비밀번호|패스워드|password)\s*[\"'“‘`]([^\"'”’`]+)[\"'”’`]", re.I)
    CWE_RE = re.compile(r"CWE[-\s]?(\d+)", re.I)

    def route(self, question: str) -> list[tuple[str, dict]]:
        """규칙 기반 라우터: (도구 이름, 인자) 목록을 반환."""
        plan: list[tuple[str, dict]] = []
        if m := VECTOR_RE.search(question):
            plan.append(("cvss_calculator", {"vector": m.group(0)}))
        for m in self.CWE_RE.finditer(question):
            plan.append(("cwe_lookup", {"cwe_id": f"CWE-{m.group(1)}"}))
        if m := self.PW_RE.search(question):
            mfa = bool(re.search(r"MFA|2단계|다중\s*인증|OTP", question, re.I)) and not re.search(
                r"(MFA|2단계|다중\s*인증|OTP)[^.?!,]{0,8}(없|미사용|안\s*(써|씀|함|해)|off|no)", question, re.I)
            plan.append(("password_policy_check", {"password": m.group(1), "mfa_enabled": mfa}))
        needs_docs = not plan or re.search(r"왜|어떻게|방법|대응|예방|권장|설명|무엇|뭐|how|why|what|prevent", question, re.I)
        if needs_docs:
            query = question
            if m := self.PW_RE.search(query):  # 비밀번호 원문은 검색어에서 제거
                query = query.replace(m.group(1), "")
            plan.append(("search_docs", {"query": query, "k": self.s.top_k}))
        return plan

    def _ask_offline(self, question: str) -> AgentResult:
        res = AgentResult(question, "", mode="offline")
        book = _RefBook()
        parts: list[str] = []
        for name, args in self.route(question):
            out = self._run_tool(name, args, book, res)
            if name == "cvss_calculator":
                parts.append(f"CVSS v3.1 Base Score는 **{out['base_score']} ({out['severity']})** 입니다."
                             if "error" not in out else out["error"])
            elif name == "cwe_lookup":
                if out.get("found"):
                    parts.append(f"{out['id']}({out['name']})는 OWASP Top 10 2021의 **{out['top10']}** 에 매핑됩니다.")
                    # 해당 카테고리 문서를 근거로 추가 인용
                    extra = self._run_tool("search_docs", {"query": out["top10"] + " overview", "k": 1}, book, res)
                    if extra.get("results"):
                        parts[-1] += f" [{extra['results'][0]['ref']}]"
                else:
                    parts.append(out.get("message") or out.get("error", ""))
            elif name == "password_policy_check":
                verdict = "기준을 만족합니다" if out["passes"] else "기준을 만족하지 않습니다: " + "; ".join(out["issues"])
                ev = self._run_tool("search_docs", {"query": "password minimum length MFA weak blocklist", "k": 1}, book, res)
                ref = f" [{ev['results'][0]['ref']}]" if ev.get("results") else ""
                parts.append(f"입력한 비밀번호({out['length']}자)는 OWASP 비밀번호 강도 {verdict}.{ref}")
            elif name == "search_docs":
                if out.get("low_confidence"):
                    parts.append("제공된 문서(OWASP Top 10 2021·Cheat Sheet)에서 확인되지 않습니다. "
                                 "이 에이전트는 애플리케이션 보안 질문에만 답합니다.")
                else:
                    parts.append(self._extractive(question, out.get("results", [])))
        res.answer = "\n\n".join(p for p in parts if p)
        self._attach_citations(res, book)
        return res

    def _extractive(self, question: str, results: list[dict], n_sent: int = 3) -> str:
        """상위 문서 조각에서 질문과 가장 가까운 문장 n개를 발췌."""
        cands: list[tuple[str, int]] = []
        for r in results[:3]:
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", r["text"])      # 링크 → 텍스트
            text = re.sub(r"\n(?![\n\-*|#]|\d+\.)", " ", text)               # 줄바꿈으로 끊긴 문장 잇기
            for s in re.split(r"(?<=[.!?])\s+|\n+", text):
                s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # 마크다운 링크 → 텍스트
                s = re.sub(r"[`*_]", "", re.sub(r"\s+", " ", s)).strip(" -#|")
                if (50 <= len(s) <= 400 and not s.startswith(("|", "CWE-")) and not s.endswith((":", "following"))
                        and not re.match(r"^(See|Articles|OWASP Testing Guide)", s)):
                    cands.append((s, r["ref"]))
        if not cands:
            return "제공된 문서에서 관련 근거를 찾지 못했습니다."
        emb = self.index.embedder
        q = emb.embed_query(question)
        vecs = emb.embed_passages([c[0] for c in cands])
        order = np.argsort(-(vecs @ q))[:n_sent]
        lines = [f"- {cands[i][0]} [{cands[i][1]}]" for i in sorted(order)]
        return "문서 근거 발췌(오프라인 모드):\n" + "\n".join(lines)
