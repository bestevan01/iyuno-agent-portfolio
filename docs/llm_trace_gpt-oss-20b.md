# LLM 모드 실행 기록 — `gpt-oss:20b`

- 생성: 2026-09-28 13:53 · 엔드포인트: Ollama(OpenAI 호환) · 검색: hybrid
- 스크립트: `scripts/llm_trace.py` · 비밀번호 인자는 기록 단계에서 `*`로 가려집니다.

## 1. SSRF를 막으려면 어떻게 해야 하나요?

`3.2초 · 토큰 1,981+406 · 대체 경로 아니오`

**모델이 호출한 도구**

- `search_docs({"k": 5, "query": "SSRF mitigation OWASP"})` — 299 ms

**답변**

> SSRF를 방지하려면 먼저 클라이언트가 제공한 URL을 **정규화하고 검증**해야 합니다.  
> 허용 목록(positive allow‑list)을 사용해 스킴, 포트, 도메인만 허용하고, **다른 모든 요청은 차단**합니다.  
> 응답을 그대로 클라이언트에 전달하지 말고, **HTTP 리다이렉션을 비활성화**합니다.  
> DNS 재바인딩·TOCTOU 같은 공격을 막기 위해 URL 일관성을 확인하고, 필요 시 **타임스탬프 기반 검증**을 적용합니다.  
> 클라우드 환경에서는 IMDSv2 같은 메타데이터 서비스 보호를 활용해 추가 방어를 강화합니다. [1][2]

**출처**

- [1] [A10:2021 – Server-Side Request Forgery (SSRF) — References](https://github.com/OWASP/Top10/blob/3a31f35346c3f4e90f350395124382fa53af2afe/2021/docs/en/A10_2021-Server-Side_Request_Forgery_(SSRF).md)
- [2] [A10:2021 – Server-Side Request Forgery (SSRF) — How to Prevent > **From Application layer:**](https://github.com/OWASP/Top10/blob/3a31f35346c3f4e90f350395124382fa53af2afe/2021/docs/en/A10_2021-Server-Side_Request_Forgery_(SSRF).md)

## 2. 반사형 XSS 취약점의 CVSS 벡터가 AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N 인데 몇 점이고 심각도는?

`4.5초 · 토큰 1,388+639 · 대체 경로 아니오`

**모델이 호출한 도구**

- `cvss_calculator({"vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N"})` — 0 ms

**답변**

> 반사형 XSS의 CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N 벡터는 **기준 점수 6.1**이며, **심각도는 Medium**입니다.  
> 이 값은 CVSS v3.1 사양에 따라 계산된 결과입니다.  
> [1]

## 3. CWE-352가 뭔지, OWASP Top 10 몇 번에 해당하는지 알려줘

`7.2초 · 토큰 1,951+1,024 · 대체 경로 아니오`

**모델이 호출한 도구**

- `search_docs({"k": 5, "query": "CWE-352 OWASP Top 10 2021 mapping"})` — 42 ms

**답변**

> CWE‑352는 **Cross‑Site Request Forgery (CSRF)**로, 다른 사이트에서 사용자를 가장해 요청을 보내는 공격을 말합니다. [3]  
> OWASP Top 10 2021에서는 이 취약점이 **A01:2021 Broken Access Control**에 매핑됩니다. [5]  
> 즉, CSRF는 접근 제어가 제대로 이루어지지 않아 발생하는 문제로 분류됩니다.

**출처**

- [3] [A01:2021 – Broken Access Control — List of Mapped CWEs](https://github.com/OWASP/Top10/blob/3a31f35346c3f4e90f350395124382fa53af2afe/2021/docs/en/A01_2021-Broken_Access_Control.md)
- [5] [A01:2021 – Broken Access Control — Overview](https://github.com/OWASP/Top10/blob/3a31f35346c3f4e90f350395124382fa53af2afe/2021/docs/en/A01_2021-Broken_Access_Control.md)

## 4. 비밀번호 "qwerty123" 써도 되나요? MFA는 안 써요.

`4.3초 · 토큰 2,372+546 · 대체 경로 아니오`

**모델이 호출한 도구**

- `password_policy_check({"mfa_enabled": false, "password": "*********"})` — 0 ms
- `search_docs({"k": 1, "query": "OWASP 인증 가이드 비밀번호 길이 15자"})` — 36 ms

**답변**

> 비밀번호는 9자이며, OWASP 인증 가이드에서는 MFA가 없을 경우 최소 15자 권장합니다. 또한 “qwerty123”은 흔히 사용되는 비밀번호 목록에 포함돼 있어 차단 대상입니다. 따라서 현재 비밀번호는 보안 기준을 충족하지 못합니다. 비밀번호를 15자 이상으로 늘리고 대·소문자·숫자·특수문자 조합을 포함하도록 변경하시기 바랍니다. 이러한 권고는 OWASP 인증 가이드에 명시되어 있습니다. [1]

**출처**

- [1] [A07:2021 – Identification and Authentication Failures — References](https://github.com/OWASP/Top10/blob/3a31f35346c3f4e90f350395124382fa53af2afe/2021/docs/en/A07_2021-Identification_and_Authentication_Failures.md)

## 5. 김치찌개를 맛있게 끓이는 방법을 알려줘

`1.1초 · 토큰 587+143 · 대체 경로 아니오`

**모델이 호출한 도구**

- (도구 호출 없음)

**답변**

> 제공된 문서에서 확인되지 않습니다.
