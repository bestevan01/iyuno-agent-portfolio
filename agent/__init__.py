"""agentic-knowledge-triage: OWASP 문서 기반 RAG + tool calling 보안 Q&A 에이전트."""
from __future__ import annotations

from functools import lru_cache

from .config import get_settings


@lru_cache(maxsize=1)
def load_agent():
    """저장된 인덱스를 읽어 Agent를 만든다(앱에서 1회만 로드)."""
    from .agent import Agent
    from .retriever import VectorIndex

    s = get_settings()
    index = VectorIndex.load(s.index_dir, s.e5_model, s.retrieval_mode, s.hybrid_alpha)
    return Agent(index, s)
