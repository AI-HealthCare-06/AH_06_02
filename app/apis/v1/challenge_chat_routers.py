from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.dependencies.security import get_request_user
from app.dtos.challenges import ChallengeChatRequest, ChallengeSelectRequest
from app.dtos.envelope import ok
from app.models.users import User
from app.services.challenge_chat import ChallengeChatService
from app.services.challenge_goals import display_goal
from app.services.page_index import PageIndex
from app.services.rag_provider import OpenAISelectionProvider
from app.services.recommendations import RecommendationService, challenge_goal_body, target_monster_body

challenge_chat_router = APIRouter(tags=["challenges"])

KEY_LOCATION = "로컬·docker compose 는 저장소 루트 .env, 운영 서버는 ~/project/.env(원본 envs/.prod.env)"


def chat_setup_issue() -> str | None:
    """질의 챗봇이 규칙 추천으로만 답하게 되는 설정 상태를 설명한다. 키 값은 담지 않는다."""
    has_key = bool(config.OPENAI_API_KEY.get_secret_value().strip())
    if config.CHALLENGE_CHAT_ENABLED and not has_key:
        return (
            "CHALLENGE_CHAT_ENABLED=true 인데 OPENAI_API_KEY 가 비어 있어 "
            "질의 챗봇이 규칙 추천(mode=rules)으로만 답합니다. "
            f"{KEY_LOCATION} 에 OPENAI_API_KEY=<키> 를 넣고 서버를 다시 띄우세요."
        )
    if has_key and not config.CHALLENGE_CHAT_ENABLED:
        return (
            "OPENAI_API_KEY 는 있지만 CHALLENGE_CHAT_ENABLED=false 라 "
            "질의 챗봇이 규칙 추천(mode=rules)으로만 답합니다. "
            f"{KEY_LOCATION} 에 CHALLENGE_CHAT_ENABLED=true 를 넣고 서버를 다시 띄우세요."
        )
    return None


async def get_challenge_chat_service() -> ChallengeChatService:
    provider = None
    api_key = config.OPENAI_API_KEY.get_secret_value().strip()
    enabled = config.CHALLENGE_CHAT_ENABLED and bool(api_key)
    if enabled:
        provider = OpenAISelectionProvider(api_key, config.OPENAI_MODEL, base_url=config.OPENAI_BASE_URL)
    return ChallengeChatService(RecommendationService(), await PageIndex.build(), provider, enabled=enabled)


@challenge_chat_router.post("/challenge-chat", status_code=status.HTTP_200_OK)
async def chat_with_challenge_bot(
    request: ChallengeChatRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeChatService, Depends(get_challenge_chat_service)],
) -> dict[str, Any]:
    """질의 챗봇 1단계: 자유 대화. 대화는 클라이언트가 들고 있고 서버는 저장하지 않는다.

    꺼져 있으면 mode=off 로 안내 문장만 준다. 챌린지 선택은 /challenge-chat/select 가 한다.
    """
    result = await service.reply(user, [message.model_dump() for message in request.messages])
    return ok({"mode": result.mode, "reply": result.reply, "sources": result.sources})


@challenge_chat_router.post("/challenge-chat/select", status_code=status.HTTP_200_OK)
async def select_challenges_from_chat(
    request: ChallengeSelectRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeChatService, Depends(get_challenge_chat_service)],
) -> dict[str, Any]:
    """질의 챗봇 2단계: 대화 결과로 챌린지를 고른다 (REQ-CHLG-012).

    AI 는 enum 으로 묶은 코드 중에서만 고르고, 목표 값은 서버가 규칙·마스터 값으로 채워 서빙한다.
    items 의 recommendation_id 로 CHLG-05 시작을 부른다. 실패하면 mode=rules 로 규칙 추천을 그대로 준다.
    """
    try:
        result = await service.select(
            user, [message.model_dump() for message in request.messages], request.answers, request.asked
        )
    except ValueError as exc:
        # 질문 기록(asked)이 알려진 키가 아니거나 중복일 때
        raise AppError(ErrorCode.VALIDATION_ERROR, message=str(exc)) from exc
    generated = result.recommendations
    target = target_monster_body(generated.monster)
    items = []
    for row in generated.items:
        challenge = generated.challenges[row.challenge_id]
        items.append(
            {
                "recommendation_id": row.id,
                "challenge_id": row.challenge_id,
                "challenge_code": challenge.code,
                "title": challenge.title,
                "factor_key": row.factor_key,
                "rank": row.rank,
                "difficulty": challenge.difficulty,
                "verification_type": challenge.verification_type,
                **challenge_goal_body(challenge, row.proposed_goal),
                "context_slots": display_goal(challenge, row.proposed_goal).context_slots,
                "context_label": challenge.context_label,
                "cycle_id": row.cycle_id,
                "target_monster": target,
                "reason": result.reasons.get(row.id),
                "evidence_card_ids": row.evidence_card_ids if result.mode == "conversation" else None,
            }
        )
    return ok(
        {
            "mode": result.mode,
            "answer": result.answer,
            "questions": result.questions,
            "items": items,
            "total": len(items),
            "sources": result.sources,
            "model_version": generated.model_version,
            "remaining_slots": generated.remaining_slots,
        }
    )
