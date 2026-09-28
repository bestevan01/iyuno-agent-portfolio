.PHONY: install fetch index test lint eval eval-ablation eval-llm plot api demo

install:
	pip install -r requirements.txt -r requirements-dev.txt

fetch:          ## 공개 문서 다시 수집
	python scripts/fetch_docs.py

index:          ## e5 임베딩 인덱스 빌드 (data/index)
	python -m agent.build_index

test:
	pytest -v

lint:
	ruff check .

eval:           ## 오프라인 평가 (dev + holdout) 후 그래프 갱신
	AGENT_RETRIEVAL=dense  python -m evaluation.run_eval --set dev     --name offline-dense-dev
	AGENT_RETRIEVAL=hybrid python -m evaluation.run_eval --set dev     --name offline-hybrid-dev
	AGENT_RETRIEVAL=dense  python -m evaluation.run_eval --set holdout --name offline-dense-holdout
	AGENT_RETRIEVAL=hybrid python -m evaluation.run_eval --set holdout --name offline-hybrid-holdout
	python -m evaluation.plot

eval-ablation:  ## 키워드(TF-IDF)만 쓰는 검색과 비교
	python -m agent.build_index --embedder tfidf --out /tmp/idx-tfidf
	AGENT_INDEX_DIR=/tmp/idx-tfidf AGENT_EMBEDDER=tfidf AGENT_RETRIEVAL=dense AGENT_ABSTAIN=0 \
		python -m evaluation.run_eval --set dev --name offline-tfidf-dev
	python -m evaluation.plot

eval-llm:       ## LLM 모드 평가 (LLM_BASE_URL, LLM_MODEL 필요)
	python -m evaluation.run_eval --set dev --name llm-$(subst :,-,$(LLM_MODEL))-dev --judge
	python -m evaluation.plot

api:
	uvicorn app.api:app --reload --port 8000

demo:
	streamlit run app/streamlit_app.py
