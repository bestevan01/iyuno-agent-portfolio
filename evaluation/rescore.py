"""저장된 문항별 결과(per_question.jsonl)로 지표를 다시 계산한다(모델 재실행 없음).

지표 정의를 고쳤을 때 모든 실행을 같은 기준으로 맞추기 위해 쓴다.
    python -m evaluation.rescore
"""
from __future__ import annotations

import json

from evaluation.run_eval import EVAL, aggregate, is_abstain


def main() -> None:
    for d in sorted((EVAL / "results").iterdir()):
        mf, pf = d / "metrics.json", d / "per_question.jsonl"
        if not (mf.exists() and pf.exists()):
            continue
        old = json.loads(mf.read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in open(pf, encoding="utf-8")]
        for r in rows:
            if "abstained" in r:
                r["abstained"] = is_abstain(r["answer"], r["citations"])
        new = aggregate(rows, old["run"], old["set"], old["config"], old["config"].get("top_k", 4))
        new["created"] = old["created"]
        new["rescored"] = True
        mf.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        with open(pf, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{d.name:28s} false_abstain {old['answer']['false_abstain_rate']} -> {new['answer']['false_abstain_rate']}"
              f" | oos {old['out_of_scope']['abstain_accuracy']} -> {new['out_of_scope']['abstain_accuracy']}")


if __name__ == "__main__":
    main()
