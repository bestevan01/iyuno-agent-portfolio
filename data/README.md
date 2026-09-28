# 데이터 출처와 라이선스

| 파일 | 출처 | 라이선스 | 수집일 |
|---|---|---|---|
| `raw/top10-*.md` (11개) | [OWASP Top 10 2021](https://github.com/OWASP/Top10) 영문판 | CC BY-SA 4.0 | 2026-09-28 |
| `raw/cs-*.md` (16개) | [OWASP Cheat Sheet Series](https://github.com/OWASP/CheatSheetSeries) | CC BY-SA 4.0 | 2026-09-28 |
| `cwe_top10.json` | 위 Top 10 문서의 "List of Mapped CWEs" 섹션에서 파싱 (196개) | CC BY-SA 4.0 (파생) | 2026-09-28 |
| `common_passwords.txt` | [SecLists](https://github.com/danielmiessler/SecLists) `xato-net-10-million-passwords-1000.txt` | MIT | 2026-09-28 |
| `index/` | 위 문서를 `intfloat/multilingual-e5-small`로 임베딩한 결과 (1,122 조각 × 384차원) | 원문 라이선스를 따름 | 2026-09-28 |

- 문서별 원본 URL, 커밋 해시, 수집일은 `sources.json`에 있습니다.
- 수집은 `python scripts/fetch_docs.py`로 재현할 수 있습니다. 원본 저장소의 최신 커밋을 받으므로 내용이 조금 달라질 수 있습니다.
- 원문에서 제거한 것은 mkdocs 아이콘 이미지 태그뿐이고, 본문은 수정하지 않았습니다.
- CC BY-SA 4.0 조건에 따라 이 폴더의 문서 파생물은 같은 라이선스로 배포합니다. 코드는 저장소 루트의 MIT 라이선스를 따릅니다.
- 개인정보, 회사 내부자료, 비밀키는 포함하지 않았습니다.
