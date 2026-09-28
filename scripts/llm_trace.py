"""LLM 모드 실행 기록(trace)을 마크다운으로 남긴다 — 모델이 실제로 어떤 도구를 어떤 인자로 불렀는지의 증거.

    LLM_BASE_URL=http://<ollama>:11434/v1 LLM_MODEL=qwen3.5:9b python scripts/llm_trace.py
    → docs/llm_trace_<모델명>.md
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import load_agent  # noqa: E402
from agent.config import ROOT  # noqa: E402

QUESTIONS = [
    "SSRF를 막으려면 어떻게 해야 하나요?",
    "반사형 XSS 취약점의 CVSS 벡터가 AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N 인데 몇 점이고 심각도는?",
    "CWE-352가 뭔지, OWASP Top 10 몇 번에 해당하는지 알려줘",
    '비밀번호 "qwerty123" 써도 되나요? MFA는 안 써요.',
    "김치찌개를 맛있게 끓이는 방법을 알려줘",
]


def main() -> None:
    agent = load_agent()
    if agent.client is None:
        sys.exit("LLM_BASE_URL을 설정해야 합니다.")
    model = agent.s.llm_model
    agent.ask("warm-up")
    lines = [f"# LLM 모드 실행 기록 — `{model}`", "",
             f"- 생성: {time.strftime('%Y-%m-%d %H:%M')} · 엔드포인트: Ollama(OpenAI 호환) · 검색: {agent.index.mode}",
             "- 스크립트: `scripts/llm_trace.py` · 비밀번호 인자는 기록 단계에서 `*`로 가려집니다.", ""]
    for i, q in enumerate(QUESTIONS, 1):
        r = agent.ask(q)
        lines += [f"## {i}. {q}", "",
                  f"`{r.latency_ms / 1000:.1f}초 · 토큰 {r.prompt_tokens:,}+{r.completion_tokens:,} · 대체 경로 {'예' if r.fallback else '아니오'}`", "",
                  "**모델이 호출한 도구**", ""]
        if r.tool_calls:
            for t in r.tool_calls:
                lines.append(f"- `{t.name}({json.dumps(t.arguments, ensure_ascii=False)})` — {t.latency_ms:.0f} ms")
        else:
            lines.append("- (도구 호출 없음)")
        lines += ["", "**답변**", "", *[f"> {line}" if line else ">" for line in r.answer.splitlines()], ""]
        if r.citations:
            lines += ["**출처**", ""] + [f"- [{c.ref}] [{c.title} — {c.section}]({c.url})" for c in r.citations] + [""]
    out = ROOT / "docs" / f"llm_trace_{model.replace(':', '-').replace('.', '-')}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
