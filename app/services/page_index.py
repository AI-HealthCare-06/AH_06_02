"""Page Index. 승인 근거 카드·챌린지 마스터·단계표·질문 페이지를 페이지 단위로 묶는다.

트리로 본다: 공략 대상 캐릭터 → 요인(factor_key) → 챌린지 → 페이지(질문·카드·단계표).
질문은 열린 요인 가지 안에서 사용자·주기로 고정한 시드로 랜덤하게 고른다(같은 입력이면 같은 질문).
"""

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models.challenges import Challenge, Monster
from app.services.challenge_goals import goal_policy
from app.services.rag_cards import (
    CODE_BY_ANSWER_KEY,
    EvidenceCard,
    QuestionPage,
    SituationAnswers,
    load_cards,
    question_bank,
)

CARD_CORPUS = Path(__file__).resolve().parents[2] / "docs/01_planning/chatbot/cards-20261026.json"
#: 한 번의 추천에서 묻는 선택형 질문 수
MAX_QUESTIONS = 3

PageKind = Literal["card", "challenge", "steps", "question"]


@dataclass(frozen=True)
class Page:
    page_id: str
    kind: PageKind
    challenge_code: str
    title: str
    body: str
    tags: tuple[str, ...]
    #: 카드 페이지만 채운다
    card: EvidenceCard | None = None
    #: 질문 페이지만 채운다
    question: QuestionPage | None = None
    #: 트리의 요인 가지. 질문을 고를 때 가지를 먼저 고른다
    factor_key: str | None = None


class PageIndex:
    def __init__(self, pages: list[Page]) -> None:
        if len({page.page_id for page in pages}) != len(pages):
            raise ValueError("페이지 ID가 중복되었습니다.")
        self.pages = pages
        self.by_id = {page.page_id: page for page in pages}

    @classmethod
    async def build(
        cls, cards: list[EvidenceCard] | None = None, questions: list[QuestionPage] | None = None
    ) -> "PageIndex":
        cards = load_cards(CARD_CORPUS) if cards is None else cards
        questions = list(question_bank()) if questions is None else questions
        monsters = {key: monster.name for monster in await Monster.all() for key in (monster.factor_keys or [])}
        pages = [card_page(card) for card in cards]
        factors: dict[str, str | None] = {}
        for challenge in await Challenge.all().order_by("id"):
            factors[challenge.code] = challenge.factor_key
            pages.append(challenge_page(challenge, monsters.get(challenge.factor_key or "")))
            steps = steps_page(challenge)
            if steps is not None:
                pages.append(steps)
        pages += [question_page(question, factors) for question in questions]
        return cls(pages)

    def next_question(
        self, codes: set[str], answers: SituationAnswers, asked: list[str], seed: str
    ) -> QuestionPage | None:
        """아직 모르는 답 키 중 하나를 골라 그 키의 질문 페이지 한 장을 돌려준다. 더 물을 게 없으면 None.

        열린 가지(후보 코드의 요인) 하나를 먼저 고르고, 그 안에서 답 키·표현을 고른다.
        한 요인에 후보가 많아도 질문이 한 가지에 몰리지 않는다.
        시드는 호출자가 준 값(사용자·주기)과 이미 물은 키로 만든다. 같은 사람이 같은 주기에 같은 순서로 답하면
        같은 질문이 나온다(요구사항: 같은 입력이면 같은 결과).
        """
        known = set(CODE_BY_ANSWER_KEY)
        if len(asked) > MAX_QUESTIONS or len(set(asked)) != len(asked) or any(key not in known for key in asked):
            raise ValueError("질문 기록은 알려진 질문을 중복 없이 최대 세 개까지 사용합니다.")
        if answers.activity_limited or len(asked) >= MAX_QUESTIONS:
            return None
        values = answers.model_dump()
        open_pages = [
            page
            for page in self.pages
            if page.question is not None
            and page.challenge_code in codes
            and values[page.question.answer_key] == "unknown"
            and page.question.answer_key not in asked
        ]
        if not open_pages:
            return None
        rng = random.Random(hashlib.sha256(f"{seed}|{','.join(asked)}".encode()).hexdigest())
        branch = rng.choice(sorted({page.factor_key or "" for page in open_pages}))
        in_branch = [page for page in open_pages if (page.factor_key or "") == branch]
        key = rng.choice(sorted({page.question.answer_key for page in in_branch if page.question is not None}))
        variants = sorted(
            (page for page in in_branch if page.question is not None and page.question.answer_key == key),
            key=lambda page: page.page_id,
        )
        question = rng.choice(variants).question
        assert question is not None
        return question

    def question_page(self, answer_key: str) -> QuestionPage:
        """답 키의 첫 질문 페이지. 이유 문장은 표현과 관계없이 같다(load_questions 가 확인한다)."""
        return next(
            page.question for page in self.pages if page.question is not None and page.question.answer_key == answer_key
        )

    def pages_for(self, codes: set[str], kinds: set[PageKind]) -> list[Page]:
        """검색과 관계없이 후보 챌린지의 마스터·단계표처럼 항상 넘길 페이지."""
        return [page for page in self.pages if page.challenge_code in codes and page.kind in kinds]


def card_page(card: EvidenceCard) -> Page:
    return Page(
        page_id=f"card:{card.card_id}",
        kind="card",
        challenge_code=card.challenge_code,
        title=card.card_id,
        body=card.guidance,
        tags=tuple(card.tags),
        card=card,
    )


def question_page(question: QuestionPage, factors: dict[str, str | None]) -> Page:
    code = CODE_BY_ANSWER_KEY[question.answer_key]
    return Page(
        page_id=f"question:{question.question_id}",
        kind="question",
        challenge_code=code,
        title=question.text,
        body=" / ".join(option.label for option in question.options),
        tags=(),
        question=question,
        factor_key=factors.get(code),
    )


def challenge_page(challenge: Challenge, monster_name: str | None) -> Page:
    tags = [challenge.title, *challenge.title.split()]
    for extra in (challenge.context_label, monster_name, challenge.unit):
        if extra:
            tags.append(extra)
    body = " · ".join(
        part
        for part in (
            challenge.description or challenge.title,
            f"인증 {challenge.verification_type}",
            f"난이도 {challenge.difficulty}",
            f"하루 {challenge.daily_target_count}회",
            f"목표 {challenge.target_value}{challenge.unit or ''}" if challenge.target_value is not None else None,
        )
        if part
    )
    return Page(
        page_id=f"challenge:{challenge.code}",
        kind="challenge",
        challenge_code=challenge.code,
        title=challenge.title,
        body=body,
        tags=tuple(dict.fromkeys(tag for tag in tags if len(tag) >= 2)),
    )


def steps_page(challenge: Challenge) -> Page | None:
    policy = goal_policy(challenge)
    if policy is None:
        return None
    lines = [
        f"{step.level}단계{'(기본)' if step.level == policy.base_level else ''}: {step.title} ({step.difficulty})"
        for step in policy.steps
    ]
    tags = ["단계", "난이도", "쉽게", "어렵", "힘들", "올려", "낮춰", *(step.title for step in policy.steps)]
    return Page(
        page_id=f"steps:{challenge.code}",
        kind="steps",
        challenge_code=challenge.code,
        title=f"{challenge.title} 단계표 {policy.version}",
        body=" / ".join(lines),
        tags=tuple(dict.fromkeys(tags)),
    )
