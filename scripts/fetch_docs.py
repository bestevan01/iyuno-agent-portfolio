"""공개 문서 수집 스크립트.

OWASP Top 10 2021(영문)과 OWASP Cheat Sheet Series 일부를 GitHub에서 받아
data/raw/ 에 저장하고, 출처·라이선스·커밋·수집일을 data/sources.json 에 기록한다.
또한 Top 10 문서의 "List of Mapped CWEs" 섹션을 파싱해 data/cwe_top10.json 을 만든다.

사용법:
    python scripts/fetch_docs.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATA = ROOT / "data"

TOP10_REPO = "https://github.com/OWASP/Top10.git"
CS_REPO = "https://github.com/OWASP/CheatSheetSeries.git"

TOP10_FILES = [
    "A00_2021_Introduction.md",
    "A01_2021-Broken_Access_Control.md",
    "A02_2021-Cryptographic_Failures.md",
    "A03_2021-Injection.md",
    "A04_2021-Insecure_Design.md",
    "A05_2021-Security_Misconfiguration.md",
    "A06_2021-Vulnerable_and_Outdated_Components.md",
    "A07_2021-Identification_and_Authentication_Failures.md",
    "A08_2021-Software_and_Data_Integrity_Failures.md",
    "A09_2021-Security_Logging_and_Monitoring_Failures.md",
    "A10_2021-Server-Side_Request_Forgery_(SSRF).md",
]

CHEATSHEETS = [
    "Password_Storage",
    "Authentication",
    "Multifactor_Authentication",
    "Session_Management",
    "Authorization",
    "SQL_Injection_Prevention",
    "Cross_Site_Scripting_Prevention",
    "Cross-Site_Request_Forgery_Prevention",
    "Server_Side_Request_Forgery_Prevention",
    "Input_Validation",
    "File_Upload",
    "Logging",
    "Secrets_Management",
    "Transport_Layer_Security",
    "Docker_Security",
    "Vulnerable_Dependency_Management",
]

PASSWORD_LIST_URL = (
    "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
    "Passwords/Common-Credentials/xato-net-10-million-passwords-1000.txt"
)


def sparse_clone(url: str, subdir: str, dest: Path) -> str:
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", url, str(dest)],
        check=True,
    )
    subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", subdir], check=True)
    return subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def clean_markdown(text: str) -> str:
    # mkdocs 속성·아이콘 이미지 제거
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)(\{[^}]*\})?", "", text)
    return text.strip() + "\n"


def parse_cwes(doc_id: str, title: str, text: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    m = re.search(r"## List of Mapped CWEs(.*)", text, re.S)
    if not m:
        return out
    block = re.sub(r"\s*\n\s*", " ", m.group(1))
    for cm in re.finditer(r"\[CWE-(\d+):?\s+([^\]]+)\]", block):
        cid = f"CWE-{cm.group(1)}"
        out[cid] = {"id": cid, "name": cm.group(2).strip(), "top10": title, "doc_id": doc_id}
    return out


def main() -> None:
    today = dt.date.today().isoformat()
    RAW.mkdir(parents=True, exist_ok=True)
    sources = []
    cwe_map: dict[str, dict] = {}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        top10_commit = sparse_clone(TOP10_REPO, "2021/docs/en", tmp / "top10")
        for name in TOP10_FILES:
            src = tmp / "top10" / "2021" / "docs" / "en" / name
            text = clean_markdown(src.read_text(encoding="utf-8"))
            doc_id = "top10-" + name.split("_")[0].lower()
            title = text.splitlines()[0].lstrip("# ").strip()
            (RAW / f"{doc_id}.md").write_text(text, encoding="utf-8")
            cwe_map.update(parse_cwes(doc_id, title, text))
            sources.append({
                "doc_id": doc_id,
                "title": title,
                "url": f"https://github.com/OWASP/Top10/blob/{top10_commit}/2021/docs/en/{name}",
                "publisher": "OWASP Foundation",
                "license": "CC BY-SA 4.0",
                "commit": top10_commit,
                "retrieved": today,
            })

        cs_commit = sparse_clone(CS_REPO, "cheatsheets", tmp / "cs")
        for name in CHEATSHEETS:
            fname = f"{name}_Cheat_Sheet.md"
            text = clean_markdown((tmp / "cs" / "cheatsheets" / fname).read_text(encoding="utf-8"))
            doc_id = "cs-" + name.lower().replace("_", "-")
            title = text.splitlines()[0].lstrip("# ").strip()
            (RAW / f"{doc_id}.md").write_text(text, encoding="utf-8")
            sources.append({
                "doc_id": doc_id,
                "title": title,
                "url": f"https://cheatsheetseries.owasp.org/cheatsheets/{fname.replace('.md', '.html')}",
                "publisher": "OWASP Foundation",
                "license": "CC BY-SA 4.0",
                "commit": cs_commit,
                "retrieved": today,
            })

    (DATA / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "cwe_top10.json").write_text(
        json.dumps(dict(sorted(cwe_map.items(), key=lambda kv: int(kv[0][4:]))), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with urllib.request.urlopen(PASSWORD_LIST_URL, timeout=30) as r:
        words = [w.strip() for w in r.read().decode("utf-8", "ignore").splitlines() if w.strip()]
    (DATA / "common_passwords.txt").write_text(
        "# Source: SecLists (MIT License) xato-net-10-million-passwords-1000.txt, retrieved "
        + today + "\n" + "\n".join(words) + "\n",
        encoding="utf-8",
    )
    print(f"docs={len(sources)} cwes={len(cwe_map)} passwords={len(words)}")


if __name__ == "__main__":
    main()
