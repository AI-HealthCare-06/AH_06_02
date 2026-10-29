"""Page Index. 승인 근거 카드·챌린지 마스터·단계표를 페이지 단위로 묶어 태그로 찾는다.

임베딩 없이 태그 부분 일치로 점수를 매긴다. 카드 48장·마스터 33개 규모에서는 이걸로 충분하다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models.challenges import Challenge, Monster
from app.services.challenge_goals import goal_policy
from app.services.rag_cards import EvidenceCard, SituationAnswers, load_cards

CARD_CORPUS = Path(__file__).resolve().parents[2] / "docs/01_planning/chatbot/cards-20261026.json"
MAX_QUERY_LENGTH = 400

PageKind = Literal["card", "challenge", "steps"]


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


class PageIndex:
    def __init__(self, pages: list[Page]) -> None:
        if len({page.page_id for page in pages}) != len(pages):
            raise ValueError("페이지 ID가 중복되었습니다.")
        self.pages = pages
        self.by_id = {page.page_id: page for page in pages}

    @classmethod
    async def build(cls, cards: list[EvidenceCard] | None = None) -> "PageIndex":
        cards = load_cards(CARD_CORPUS) if cards is None else cards
        monsters = {key: monster.name for monster in await Monster.all() for key in (monster.factor_keys or [])}
        pages = [card_page(card) for card in cards]
        for challenge in await Challenge.all().order_by("id"):
            pages.append(challenge_page(challenge, monsters.get(challenge.factor_key or "")))
            steps = steps_page(challenge)
            if steps is not None:
                pages.append(steps)
        return cls(pages)

    def search(
        self,
        query: str,
        allowed_codes: set[str],
        answers: SituationAnswers | None,
        *,
        limit: int = 6,
    ) -> list[Page]:
        """질의와 겹치는 태그 길이 합으로 점수를 낸다. 겹치는 태그가 없으면 돌려주지 않는다.

        카드는 승인된 것과 사용자가 "가능하다"고 답한 챌린지 것만 고른다 (rag_cards.search_cards 와 같은 규칙).
        answers 가 None 이면(자유 대화 단계) 답 확인 없이 승인 카드를 고른다. 선택 단계는 항상 답을 넘긴다.
        마스터·단계표 페이지는 후보 코드의 것만 고른다.
        """
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError("검색 표현은 400자 이하여야 합니다.")
        text = query.casefold()
        scored: list[tuple[int, Page]] = []
        for page in self.pages:
            if page.challenge_code not in allowed_codes:
                continue
            if page.card is not None and (
                page.card.status != "approved" or (answers is not None and not answers.supports(page.challenge_code))
            ):
                continue
            score = sum(len(tag) for tag in page.tags if tag.casefold() in text)
            if score > 0:
                scored.append((score, page))
        scored.sort(key=lambda pair: (-pair[0], pair[1].page_id))
        return [page for _, page in scored[:limit]]

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
