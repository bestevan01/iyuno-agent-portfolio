"""한국어 보안 용어 → 영어 용어 사전 (질의 확장용).

문서는 영어, 질문은 한국어라서 다국어 임베딩만으로는 음차어('크리덴셜 스터핑')나
업계 관용어('하드코딩')를 놓치는 경우가 있었다(evaluation/error_analysis.md 참고).
질문에 아래 한국어 용어가 있으면 영어 용어를 덧붙여 키워드 검색(TF-IDF)에 사용한다.
"""
from __future__ import annotations

GLOSSARY: dict[str, str] = {
    "크리덴셜 스터핑": "credential stuffing",
    "무차별 대입": "brute force",
    "계정 잠금": "account lockout",
    "비밀번호": "password",
    "패스워드": "password",
    "해시": "hash hashing",
    "솔트": "salt",
    "페퍼": "pepper",
    "시크릿": "secrets",
    "하드코딩": "hardcoded secrets source code",
    "비밀 관리": "secrets management",
    "세션": "session",
    "쿠키": "cookie",
    "토큰": "token",
    "인젝션": "injection",
    "주입": "injection",
    "교차 사이트 스크립팅": "cross site scripting XSS",
    "요청 위조": "request forgery",
    "접근 통제": "access control",
    "접근 제어": "access control",
    "권한 상승": "privilege escalation",
    "최소 권한": "least privilege",
    "인가": "authorization",
    "인증": "authentication",
    "다중 인증": "multi-factor authentication MFA",
    "2단계 인증": "multi-factor authentication MFA",
    "입력값 검증": "input validation",
    "입력 검증": "input validation",
    "허용 목록": "allowlist allow list",
    "차단 목록": "denylist block list",
    "화이트리스트": "allowlist",
    "블랙리스트": "denylist",
    "파일 업로드": "file upload",
    "확장자": "extension",
    "암호화": "encryption cryptographic",
    "전송 계층": "transport layer security TLS",
    "인증서": "certificate",
    "로그": "logging log",
    "모니터링": "monitoring",
    "컨테이너": "container",
    "도커": "docker",
    "의존성": "dependency dependencies",
    "라이브러리": "library component",
    "취약한 구성요소": "vulnerable components",
    "설정 오류": "misconfiguration",
    "보안 설정": "security configuration",
    "안전하지 않은 설계": "insecure design",
    "위협 모델링": "threat modeling",
    "역직렬화": "deserialization",
    "무결성": "integrity",
    "서버 측 요청 위조": "server-side request forgery SSRF",
}


def expand(query: str) -> str:
    extra = [en for ko, en in GLOSSARY.items() if ko in query]
    return query if not extra else f"{query} {' '.join(extra)}"
