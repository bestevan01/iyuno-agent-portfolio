"""환경변수 기반 설정. 비밀키는 코드에 두지 않고 .env / 환경변수로만 받는다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    raw_dir: Path = ROOT / "data" / "raw"
    index_dir: Path = field(default_factory=lambda: Path(_env("AGENT_INDEX_DIR", str(ROOT / "data" / "index"))))
    sources_file: Path = ROOT / "data" / "sources.json"
    cwe_file: Path = ROOT / "data" / "cwe_top10.json"
    passwords_file: Path = ROOT / "data" / "common_passwords.txt"
    db_file: Path = field(default_factory=lambda: Path(_env("AGENT_DB", str(ROOT / "data" / "agent.db"))))

    # 임베딩: "e5"(다국어, 한국어 질문 지원) 또는 "tfidf"(경량, CI용)
    embedder: str = field(default_factory=lambda: _env("AGENT_EMBEDDER", "e5"))
    e5_model: str = field(default_factory=lambda: _env("AGENT_E5_MODEL", "intfloat/multilingual-e5-small"))
    chunk_size: int = 900       # 문자 기준
    chunk_overlap: int = 150
    top_k: int = 4
    retrieval_mode: str = field(default_factory=lambda: _env("AGENT_RETRIEVAL", "hybrid"))  # dense | hybrid
    hybrid_alpha: float = field(default_factory=lambda: float(_env("AGENT_HYBRID_ALPHA", "0.3")))
    # 최고 검색 점수가 이 값보다 낮으면 "문서에서 확인되지 않음"으로 답변 거절(범위 밖 질문 대응)
    abstain_threshold: float = field(default_factory=lambda: float(_env("AGENT_ABSTAIN", "0.78")))

    # LLM: OpenAI 호환 엔드포인트(Ollama /v1, vLLM, OpenAI 등). 비어 있으면 오프라인 모드.
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", "ollama"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "qwen3.5:9b"))
    # 1M 토큰당 USD 비용(로컬 모델은 0). 비용 지표 계산용.
    price_in_per_m: float = field(default_factory=lambda: float(_env("LLM_PRICE_IN_PER_M", "0")))
    price_out_per_m: float = field(default_factory=lambda: float(_env("LLM_PRICE_OUT_PER_M", "0")))
    max_steps: int = 4

    @property
    def use_llm(self) -> bool:
        return bool(self.llm_base_url)


def get_settings() -> Settings:
    return Settings()
