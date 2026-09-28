"""임베딩 + numpy 벡터 인덱스.

- E5Embedder: intfloat/multilingual-e5-small (384차원, 한국어 질문 ↔ 영문 문서 교차 검색 가능)
- TfidfEmbedder: 외부 모델 다운로드가 필요 없는 경량 대안(CI·테스트용)

인덱스는 data/index/ 에 embeddings.npy + chunks.jsonl + meta.json 으로 저장한다.
벡터 수가 수천 개 수준이라 별도 벡터 DB 없이 정규화 벡터의 내적(cosine)으로 충분하다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .glossary import expand
from .ingest import Chunk


class E5Embedder:
    name = "e5"

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        from sentence_transformers import SentenceTransformer  # 무거운 import는 지연

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> None:  # 사전학습 모델이라 fit 불필요
        return None

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self.model.encode([f"passage: {t}" for t in texts], normalize_embeddings=True,
                                 batch_size=32, show_progress_bar=False).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.model.encode([f"query: {text}"], normalize_embeddings=True)[0].astype(np.float32)


class TfidfEmbedder:
    name = "tfidf"

    def __init__(self, **_):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, stop_words="english")

    def fit(self, texts: list[str]) -> None:
        self.vec.fit(texts)

    def _norm(self, m) -> np.ndarray:
        a = m.toarray().astype(np.float32)
        n = np.linalg.norm(a, axis=1, keepdims=True)
        n[n == 0] = 1
        return a / n

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._norm(self.vec.transform(texts))

    def embed_query(self, text: str) -> np.ndarray:
        return self._norm(self.vec.transform([text]))[0]


def make_embedder(kind: str, e5_model: str = "intfloat/multilingual-e5-small"):
    if kind == "e5":
        return E5Embedder(e5_model)
    if kind == "tfidf":
        return TfidfEmbedder()
    raise ValueError(f"unknown embedder: {kind}")


def passage_text(c: Chunk) -> str:
    return f"{c.title} | {c.section}\n{c.text}"


@dataclass
class Hit:
    chunk: Chunk
    score: float
    rank: int


class VectorIndex:
    def __init__(self, embedder, chunks: list[Chunk], vectors: np.ndarray,
                 mode: str = "hybrid", alpha: float = 0.3):
        self.embedder = embedder
        self.chunks = chunks
        self.vectors = vectors
        self.mode = mode      # "dense" | "hybrid"
        self.alpha = alpha    # hybrid에서 키워드 점수 가중치
        self._lex = None

    def _lexical(self) -> TfidfEmbedder:
        if self._lex is None:
            self._lex = TfidfEmbedder()
            texts = [passage_text(c) for c in self.chunks]
            self._lex.fit(texts)
            self._lex_vecs = self._lex.embed_passages(texts)
        return self._lex

    # ---------- build / persist ----------
    @classmethod
    def build(cls, chunks: list[Chunk], embedder) -> "VectorIndex":
        texts = [passage_text(c) for c in chunks]
        embedder.fit(texts)
        return cls(embedder, chunks, embedder.embed_passages(texts))

    def save(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        np.save(index_dir / "embeddings.npy", self.vectors)
        with open(index_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        (index_dir / "meta.json").write_text(json.dumps({
            "embedder": self.embedder.name,
            "model": getattr(self.embedder, "model_name", None),
            "n_chunks": len(self.chunks),
            "dim": int(self.vectors.shape[1]),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, index_dir: Path, e5_model: str = "intfloat/multilingual-e5-small",
             mode: str = "hybrid", alpha: float = 0.3) -> "VectorIndex":
        meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))
        chunks = [Chunk(**json.loads(line)) for line in open(index_dir / "chunks.jsonl", encoding="utf-8")]
        embedder = make_embedder(meta["embedder"], meta.get("model") or e5_model)
        if meta["embedder"] == "tfidf":  # TF-IDF는 어휘사전을 다시 fit
            embedder.fit([passage_text(c) for c in chunks])
        return cls(embedder, chunks, np.load(index_dir / "embeddings.npy"), mode, alpha)

    # ---------- search ----------
    def scores(self, query: str) -> np.ndarray:
        dense = self.vectors @ self.embedder.embed_query(query)
        if self.mode == "dense" or self.embedder.name == "tfidf":
            return dense
        lex = self._lexical()
        return dense + self.alpha * (self._lex_vecs @ lex.embed_query(expand(query)))

    def search(self, query: str, k: int = 4, doc_filter: str | None = None) -> list[Hit]:
        scores = self.scores(query)
        order = np.argsort(-scores)
        hits: list[Hit] = []
        for i in order:
            c = self.chunks[int(i)]
            if doc_filter and not c.doc_id.startswith(doc_filter):
                continue
            hits.append(Hit(c, float(scores[i]), len(hits) + 1))
            if len(hits) >= k:
                break
        return hits
