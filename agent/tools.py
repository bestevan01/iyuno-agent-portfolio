"""에이전트가 호출하는 도구들과 OpenAI 호환 tool 스키마.

- search_docs            : RAG 검색 (근거 문서 조각 + 인용 번호 반환)
- cvss_calculator        : CVSS v3.1 Base Score 계산기 (FIRST 공식 수식 구현)
- cwe_lookup             : CWE ID → 이름 / 매핑된 OWASP Top 10 2021 카테고리 조회
- password_policy_check  : OWASP Authentication Cheat Sheet 기준 비밀번호 정책 검사
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable

# ------------------------------------------------------------------ CVSS v3.1
_W = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "CIA": {"H": 0.56, "L": 0.22, "N": 0.0},
}
_PR = {"U": {"N": 0.85, "L": 0.62, "H": 0.27}, "C": {"N": 0.85, "L": 0.68, "H": 0.5}}
_REQUIRED = ["AV", "AC", "PR", "UI", "S", "C", "I", "A"]
VECTOR_RE = re.compile(r"(CVSS:3\.[01]/)?AV:[NALP]/AC:[LH]/PR:[NLH]/UI:[NR]/S:[UC]/C:[HLN]/I:[HLN]/A:[HLN]")


def _roundup(x: float) -> float:
    """CVSS v3.1 명세 Appendix A의 Roundup (부동소수점 오차 방지 버전)."""
    i = round(x * 100000)
    if i % 10000 == 0:
        return i / 100000.0
    return (math.floor(i / 10000) + 1) / 10.0


def severity(score: float) -> str:
    if score == 0:
        return "None"
    if score < 4.0:
        return "Low"
    if score < 7.0:
        return "Medium"
    if score < 9.0:
        return "High"
    return "Critical"


def cvss_calculator(vector: str) -> dict:
    m = VECTOR_RE.search(vector.strip())
    if not m:
        return {"error": "유효한 CVSS v3.1 벡터가 아닙니다. 예: CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}
    parts = dict(p.split(":") for p in m.group(0).split("/") if not p.startswith("CVSS"))
    missing = [k for k in _REQUIRED if k not in parts]
    if missing:
        return {"error": f"누락된 지표: {missing}"}
    s = parts["S"]
    iss = 1 - (1 - _W["CIA"][parts["C"]]) * (1 - _W["CIA"][parts["I"]]) * (1 - _W["CIA"][parts["A"]])
    impact = 6.42 * iss if s == "U" else 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    expl = 8.22 * _W["AV"][parts["AV"]] * _W["AC"][parts["AC"]] * _PR[s][parts["PR"]] * _W["UI"][parts["UI"]]
    if impact <= 0:
        base = 0.0
    elif s == "U":
        base = _roundup(min(impact + expl, 10))
    else:
        base = _roundup(min(1.08 * (impact + expl), 10))
    return {
        "vector": "CVSS:3.1/" + "/".join(f"{k}:{parts[k]}" for k in _REQUIRED),
        "base_score": base,
        "severity": severity(base),
        "impact_subscore": round(max(impact, 0), 2),
        "exploitability_subscore": round(expl, 2),
        "reference": "FIRST CVSS v3.1 Specification, Section 7 (https://www.first.org/cvss/v3.1/specification-document)",
    }


# ------------------------------------------------------------------ CWE
class CweLookup:
    def __init__(self, path: Path):
        self.data: dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))

    def __call__(self, cwe_id: str) -> dict:
        m = re.search(r"(\d+)", str(cwe_id))
        if not m:
            return {"error": "CWE 번호를 찾을 수 없습니다. 예: CWE-89"}
        key = f"CWE-{int(m.group(1))}"
        hit = self.data.get(key)
        if not hit:
            return {"id": key, "found": False,
                    "message": "OWASP Top 10 2021에 매핑되지 않은 CWE입니다.",
                    "url": f"https://cwe.mitre.org/data/definitions/{int(m.group(1))}.html"}
        return {**hit, "found": True, "url": f"https://cwe.mitre.org/data/definitions/{int(m.group(1))}.html"}


# ------------------------------------------------------------------ Password policy
class PasswordPolicy:
    """OWASP Authentication Cheat Sheet 'Implement Proper Password Strength Controls' 규칙.

    - MFA 사용 시 8자 미만, 미사용 시 15자 미만이면 약함
    - 흔한/유출된 비밀번호 차단 (SecLists 상위 1,000개 목록)
    - 문자 조합 규칙(대문자·특수문자 강제)은 요구하지 않음
    """

    def __init__(self, path: Path):
        self.common = {
            w.strip().lower() for w in path.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")
        }

    def __call__(self, password: str, mfa_enabled: bool = False) -> dict:
        min_len = 8 if mfa_enabled else 15
        issues = []
        if len(password) < min_len:
            issues.append(f"길이 {len(password)}자 — MFA {'사용' if mfa_enabled else '미사용'} 시 최소 {min_len}자 권장")
        if password.lower() in self.common:
            issues.append("흔히 쓰이는 비밀번호 목록(상위 1,000개)에 포함됨")
        if len(set(password)) <= 2 and len(password) > 0:
            issues.append("같은 문자 반복")
        return {
            "length": len(password),
            "mfa_enabled": mfa_enabled,
            "min_length_required": min_len,
            "passes": not issues,
            "issues": issues,
            "note": "OWASP는 대/소문자·숫자·특수문자 조합 강제 대신 길이와 차단 목록 검사를 권고합니다.",
            "source_doc": "cs-authentication",
        }


def mask_args(name: str, args: dict) -> dict:
    """로그·트레이스에 비밀번호 원문이 남지 않도록 마스킹."""
    if name == "password_policy_check" and "password" in args:
        return {**args, "password": "*" * len(str(args["password"]))}
    return args


# ------------------------------------------------------------------ Schemas
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "OWASP Top 10 2021 및 OWASP Cheat Sheet 문서에서 질문과 관련된 근거를 검색한다. 보안 개념·대응 방법 질문에는 반드시 먼저 호출한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 질의(한국어/영어 모두 가능)"},
                    "k": {"type": "integer", "description": "반환할 문서 조각 수(1~8)", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvss_calculator",
            "description": "CVSS v3.1 벡터 문자열로 Base Score와 심각도를 계산한다.",
            "parameters": {
                "type": "object",
                "properties": {"vector": {"type": "string", "description": "예: CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}},
                "required": ["vector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cwe_lookup",
            "description": "CWE 번호의 이름과, 매핑된 OWASP Top 10 2021 카테고리를 조회한다.",
            "parameters": {
                "type": "object",
                "properties": {"cwe_id": {"type": "string", "description": "예: CWE-89"}},
                "required": ["cwe_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "password_policy_check",
            "description": "비밀번호가 OWASP 인증 가이드의 강도 기준(길이, 흔한 비밀번호 차단)을 만족하는지 검사한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "password": {"type": "string", "description": "검사할 비밀번호"},
                    "mfa_enabled": {"type": "boolean", "description": "MFA 사용 여부", "default": False},
                },
                "required": ["password"],
            },
        },
    },
]


def build_registry(index, settings) -> dict[str, Callable[..., dict]]:
    cwe = CweLookup(settings.cwe_file)
    pw = PasswordPolicy(settings.passwords_file)

    def search_docs(query: str, k: int = settings.top_k) -> dict:
        k = max(1, min(int(k or settings.top_k), 8))
        hits = index.search(query, k=k)
        return {"results": [
            {"chunk_id": h.chunk.chunk_id, "title": h.chunk.title, "section": h.chunk.section,
             "url": h.chunk.url, "score": round(h.score, 4), "text": h.chunk.text}
            for h in hits
        ]}

    return {
        "search_docs": search_docs,
        "cvss_calculator": cvss_calculator,
        "cwe_lookup": cwe,
        "password_policy_check": pw,
    }
