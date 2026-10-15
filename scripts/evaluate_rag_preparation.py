"""승인 테스트 fixture의 검색·검증을 평가한다. 실서비스 LLM 품질이나 건강 효과 평가가 아니다."""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.services.attack_cycles import cycle_end_for
from app.services.rag_cards import (
    EvidenceCard,
    SituationAnswers,
    load_cards,
    questions_for,
    search_cards,
    validate_selection,
)

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/01_planning/chatbot"


def evaluate() -> dict[str, Any]:
    draft = load_cards(FOLDER / "cards-draft-20261012.json")
    # 운영 파일은 그대로 두고 평가 인스턴스에만 승인 상태를 부여한다.
    cards = [
        EvidenceCard.model_validate(card.model_dump() | {"status": "approved", "approved_by": "평가 fixture"})
        for card in draft
    ]
    cases = json.loads((FOLDER / "golden-cases-20261012.json").read_text(encoding="utf-8"))
    results = []
    for case in cases:
        answers = SituationAnswers.model_validate(case["answers"])
        codes = set(case["allowed_codes"])
        kind = case["kind"]
        observed: object
        if kind in {"search", "empty", "draft_excluded"}:
            found = search_cards(draft if kind == "draft_excluded" else cards, case["query"], codes, answers)
            observed = [card.card_id for card in found]
            passed = case["expected"] in observed if kind == "search" else observed == []
        elif kind == "questions":
            observed = [item["key"] for item in questions_for(codes, answers, case["asked"])]
            passed = observed == case["expected"]
        elif kind == "cycle_end":
            start, added = date(2026, 10, 12), date(2026, 10, 19)
            end = cycle_end_for(start)
            observed = {"end_date": str(end), "added_duration": (end - added).days + 1}
            passed = observed == case["expected"]
        else:
            try:
                validate_selection(case["output"], cards[:1], codes, answers)
                observed, passed = "accepted", False
            except ValueError:
                observed, passed = "rejected", True
        results.append({"case_id": case["case_id"], "kind": kind, "passed": passed, "observed": observed})
    return {
        "scope": "승인 테스트 fixture의 결정적 태그 검색·출력 검증·주기 계약. 실제 LLM 호출 없음.",
        "production_card_status": "12개 전부 draft; 운영 승인 완료를 뜻하지 않음",
        "cases": results,
        "passed": sum(item["passed"] for item in results),
        "total": len(results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 준비 기능의 고정 평가 사례를 실행한다.")
    parser.add_argument("--output", type=Path, default=FOLDER / "evaluation-fixture-20261012.json")
    args = parser.parse_args()
    report = evaluate()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"평가 fixture: {report['passed']}/{report['total']} 통과. 실제 LLM·운영 승인 평가는 별도입니다.")
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
