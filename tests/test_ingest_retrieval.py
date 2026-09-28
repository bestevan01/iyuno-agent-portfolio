from agent.glossary import expand
from agent.ingest import split_sections, split_text


def test_split_sections_keeps_heading_path():
    md = "# Title\n\nintro\n\n## A\n\ntext a\n\n### A1\n\ntext a1\n\n## B\n\ntext b"
    secs = dict(split_sections(md))
    assert secs["A"] == "text a"
    assert secs["A > A1"] == "text a1"
    assert "B" in secs


def test_split_text_respects_size():
    text = "\n\n".join(["word " * 50] * 10)
    parts = split_text(text, size=600, overlap=100)
    assert len(parts) > 1
    assert all(len(p) <= 700 for p in parts)


def test_corpus_has_at_least_20_docs(index):
    assert len({c.doc_id for c in index.chunks}) >= 20


def test_english_query_hits_expected_doc(index):
    top = index.search("server side request forgery allowlist", k=4)
    assert any(h.chunk.doc_id in {"cs-server-side-request-forgery-prevention", "top10-a10"} for h in top)
    top = index.search("Argon2id password hashing", k=3)
    assert top[0].chunk.doc_id == "cs-password-storage"


def test_glossary_expansion():
    assert "credential stuffing" in expand("크리덴셜 스터핑 대응법")
    assert expand("hello") == "hello"
