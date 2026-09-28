"""테스트는 모델 다운로드가 필요 없는 TF-IDF 인덱스로 돌린다(CI 속도·재현성)."""
from __future__ import annotations

import pytest

from agent.agent import Agent
from agent.config import Settings
from agent.ingest import load_chunks
from agent.retriever import VectorIndex, make_embedder


@pytest.fixture(scope="session")
def settings(tmp_path_factory) -> Settings:
    s = Settings()
    s.embedder = "tfidf"
    s.llm_base_url = ""
    s.abstain_threshold = 0.05  # TF-IDF 점수 스케일에 맞춤
    s.db_file = tmp_path_factory.mktemp("db") / "agent.db"
    return s


@pytest.fixture(scope="session")
def index(settings) -> VectorIndex:
    chunks = load_chunks(settings.raw_dir, settings.sources_file, settings.chunk_size, settings.chunk_overlap)
    return VectorIndex.build(chunks, make_embedder("tfidf"))


@pytest.fixture()
def agent(index, settings) -> Agent:
    return Agent(index, settings)
