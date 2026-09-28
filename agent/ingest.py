"""문서 로드 → 마크다운 헤딩 단위 분할 → 길이 기준 chunking."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    url: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """(섹션 경로, 본문) 목록. 섹션 경로는 'H2 > H3' 형태."""
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    buf: list[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append((" > ".join(stack[1:]) or (stack[0] if stack else ""), body))
        buf.clear()

    for line in markdown.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            stack[:] = stack[: level - 1] + [m.group(2).strip()]
            continue
        buf.append(line)
    flush()
    return sections


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """문단 경계를 우선 존중하면서 size 이하로 자른다."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= size:
        return [text]
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:  # 너무 긴 문단은 강제 분할
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:size])
            p = p[size - overlap:]
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            tail = cur[-overlap:] if cur and overlap else ""
            cur = f"{tail}\n\n{p}".strip() if tail else p
    if cur:
        chunks.append(cur)
    return chunks


def load_chunks(raw_dir: Path, sources_file: Path, size: int = 900, overlap: int = 150) -> list[Chunk]:
    meta = {s["doc_id"]: s for s in json.loads(sources_file.read_text(encoding="utf-8"))}
    out: list[Chunk] = []
    for path in sorted(raw_dir.glob("*.md")):
        doc_id = path.stem
        info = meta.get(doc_id, {"title": doc_id, "url": ""})
        n = 0
        for section, body in split_sections(path.read_text(encoding="utf-8")):
            for piece in split_text(body, size, overlap):
                if len(piece) < 40:  # 표 구분선 등 의미 없는 조각 제거
                    continue
                out.append(Chunk(f"{doc_id}#{n}", doc_id, info["title"], section, info["url"], piece))
                n += 1
    return out
