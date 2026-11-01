"""OpenAI 키를 넣은 뒤 질의 챗봇이 실제로 동작하는지 확인한다.

    uv run python -m scripts.rag.check_openai                                   # 1·2단계
    uv run python -m scripts.rag.check_openai --base-url http://localhost:8000  # 3단계까지

1. 설정: 저장소 루트 .env 에서 OPENAI_API_KEY · OPENAI_MODEL · CHALLENGE_CHAT_ENABLED 를 읽는다. 키 값은 출력하지 않는다
2. 직접 호출: 개인정보가 없는 고정 예시 문맥으로 대화(자유 문장) 한 번, 판단(라벨 1토큰 logprobs) 한 번을 부르고
   판단 출력이 후보 라벨의 확률로 나오는지 본다. 모델·API 가 logprobs 를 주지 않으면 여기서 FAIL 이다
3. 서버 흐름: 띄워 둔 API 에 새 계정으로 가입 → 건강정보 → 예측 → 선택형 질문(/challenge-chat/select)에 차례로 답하고
   → 대화(/challenge-chat) → 다시 선택을 불러 mode=conversation 이고 서빙 JSON 에 규칙 값이 채워졌는지 본다.
   서버·워커·시드가 준비돼 있어야 한다(scripts/smoke.py 와 같은 전제). 서버는 .env 를 고친 뒤 다시 띄운다

2단계는 실제 요금이 드는 호출을 두 번 보낸다. 3단계는 실행할 때마다 로컬 DB 에 계정을 하나 만든다.
"""

import argparse
import asyncio
import sys
import time
from typing import Any

import httpx

from app.core import config
from app.services.challenge_selections import candidate_labels, validate_judgment
from app.services.page_index import CARD_CORPUS
from app.services.rag_cards import load_cards
from app.services.rag_provider import OpenAISelectionProvider

KEY_HELP = (
    "저장소 루트 .env(로컬·docker compose) 또는 envs/.prod.env(배포)에 OPENAI_API_KEY=<키> 를 넣으세요. "
    "예시는 envs/example.local.env 에 있습니다."
)
#: 상태 코드별로 먼저 볼 설정
HTTP_HINTS = {
    401: "키가 틀렸거나 폐기됐습니다. OPENAI_API_KEY 를 다시 확인하세요.",
    403: "이 키의 프로젝트에서 모델 사용 권한이 없습니다. OpenAI 대시보드의 프로젝트 권한을 확인하세요.",
    404: "모델 이름을 찾지 못했습니다. OPENAI_MODEL(기본 gpt-4o)을 확인하세요.",
    429: "요청 한도나 잔액이 부족합니다. OpenAI 대시보드의 Billing·Limits 를 확인하세요.",
}
#: 예시 문맥. 실제 사용자 값이 아니다
WALK = "CH_WALK_AFTER_MEAL"
STAIRS = "CH_STAIRS"
SAMPLE_MESSAGES = [
    {"role": "user", "content": "점심 먹고 사무실 근처를 걸을 시간이 있어요. 뭘 해 보면 좋을까요?"},
]
#: 3단계에서 질문에 줄 답. 선택지 중 챌린지를 남기는 첫 값(yes·both·three)을 골라 후보가 넓게 남게 한다
KEEP_VALUES = ("yes", "both", "three")
QUERY = "점심 저녁 식후 걷기나 계단 오르기처럼 부담 없이 시작할 수 있는 걸 추천해 주세요"


def check_settings() -> str | None:
    print("=== 1. 설정")
    key = config.OPENAI_API_KEY.get_secret_value().strip()
    print(f"  OPENAI_API_KEY        {'있음 (' + str(len(key)) + '자, 값은 출력하지 않음)' if key else '없음'}")
    print(f"  OPENAI_MODEL          {config.OPENAI_MODEL}")
    print(f"  OPENAI_BASE_URL       {config.OPENAI_BASE_URL}")
    print(f"  CHALLENGE_CHAT_ENABLED {config.CHALLENGE_CHAT_ENABLED}")
    if not key:
        print(f"  → FAIL  OPENAI_API_KEY 가 비어 있습니다. {KEY_HELP}")
        print("          키가 없어도 서버는 규칙 추천(mode=rules)으로 계속 동작합니다.")
        return None
    if not config.CHALLENGE_CHAT_ENABLED:
        print(
            "  주의: CHALLENGE_CHAT_ENABLED=false 라 서버의 질의 챗봇은 규칙 추천으로만 답합니다. "
            "2단계는 그대로 진행합니다."
        )
    print("  → PASS")
    return key


def sample_context() -> tuple[dict[str, Any], dict[str, str]]:
    corpus = [card for card in load_cards(CARD_CORPUS) if card.status == "approved"]
    cards = [card for code in (WALK, STAIRS) for card in corpus if card.challenge_code == code][:4]
    labels = candidate_labels({WALK, STAIRS})
    goals = {
        WALK: ("식후 걷기", "식후", "challenge", {"target_value": 10.0, "unit": "분", "daily_target_count": 2}),
        STAIRS: ("계단 이용하기", "이동", "normal", {"target_value": None, "unit": None, "daily_target_count": 1}),
    }
    context = {
        "conversation": SAMPLE_MESSAGES,
        "answers": {"meal_walk": "both", "stairs": "yes"},
        "cohort": {"monster": "viscera", "state": "normal", "is_target": True, "active": [], "history": []},
        "candidates": [
            {
                "label": label,
                "challenge_code": code,
                "title": goals[code][0],
                "context_label": goals[code][1],
                "difficulty": goals[code][2],
                "served_goal": goals[code][3],
            }
            for label, code in labels.items()
        ],
        "cards": [{"card_id": c.card_id, "challenge_code": c.challenge_code, "guidance": c.guidance} for c in cards],
    }
    return context, labels


def http_failure(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        # 응답의 error.code·type 만 보인다. message 에는 키 일부가 섞일 수 있어 출력하지 않는다
        try:
            error = exc.response.json().get("error") or {}
        except ValueError:
            error = {}
        status = exc.response.status_code
        hint = HTTP_HINTS.get(status, "OpenAI 응답 상태를 확인하세요.")
        return f"HTTP {status} code={error.get('code')} type={error.get('type')} → {hint}"
    if isinstance(exc, httpx.TimeoutException):
        return "12초 안에 응답이 없습니다. 네트워크·프록시를 확인하세요."
    if isinstance(exc, httpx.HTTPError):
        return f"연결 실패 {type(exc).__name__}. OPENAI_BASE_URL·네트워크를 확인하세요."
    return str(exc)


async def check_direct_call(key: str) -> bool:
    print(f"\n=== 2. 직접 호출 ({config.OPENAI_MODEL}, 예시 문맥 · 개인정보 없음)")
    provider = OpenAISelectionProvider(key, config.OPENAI_MODEL, base_url=config.OPENAI_BASE_URL)
    context, labels = sample_context()
    started = time.monotonic()
    try:
        reply = await provider.chat(
            {"candidates": context["candidates"], "pages": [{"body": c["guidance"]} for c in context["cards"]]},
            SAMPLE_MESSAGES,
        )
    except (httpx.HTTPError, ValueError) as exc:
        print(f"  [대화] → FAIL  {http_failure(exc)}")
        return False
    print(f"  [대화] {time.monotonic() - started:.1f}초 · {reply!r}")
    started = time.monotonic()
    try:
        raw = await provider.judge(context, list(labels))
        probabilities = validate_judgment(raw, labels)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"  [판단] → FAIL  {http_failure(exc)}")
        print("          logprobs 가 없다는 오류면 OPENAI_MODEL 이 logprobs 를 지원하는지 확인하세요(gpt-4o 지원).")
        return False
    shown = " · ".join(f"{code} {value:.2f}" for code, value in sorted(probabilities.items(), key=lambda x: -x[1]))
    print(f"  [판단] {time.monotonic() - started:.1f}초 · 라벨 확률 {raw} → {shown}")
    print("  → PASS")
    return True


def check_server_flow(base_url: str) -> bool:
    print(f"\n=== 3. 서버 흐름 ({base_url})")
    client = httpx.Client(base_url=base_url + "/api/v1", timeout=40)
    email = f"chat-check+{time.strftime('%Y%m%d%H%M%S')}@example.com"

    def call(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = client.request(method, path, **kwargs)
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"{method} {path} → {response.status_code} {(body.get('error') or {}).get('code')}")
        return body["data"]

    try:
        signup = {
            "email": email, "password": "check1234", "nickname": "챗확인", "birth_year": 1975, "sex": "M",
            "height_cm": 172.0, "motivation_type": "grow", "dm_diagnosed": False, "htn_diagnosed": False,
            "dm_medication": False, "htn_medication": False, "disclaimer_agreed": True,
        }  # fmt: skip
        call("POST", "/auth/signup", json=signup)
        token = call("POST", "/auth/login", json={"email": email, "password": "check1234"})["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        record = {
            "input_mode": "simple", "weight_kg": 82.0, "waist_cm": 94.0, "smoking_current": True,
            "alcohol_frequency": 1, "alcohol_amount": 1, "walking_days": 2, "walking_minutes": 20,
            "strength_days": 0, "sitting_minutes": 480, "family_history_dm": False, "family_history_htn": False,
            "dining_out_freq": 3,
        }  # fmt: skip
        record_id = call("POST", "/health-records", json=record)["health_record_id"]
        prediction_id = call("POST", "/predictions", json={"health_record_id": record_id})["prediction_id"]
        status = "queued"
        for _ in range(60):
            status = call("GET", f"/predictions/{prediction_id}")["status"]
            if status in ("done", "failed"):
                break
            time.sleep(1)
        print(f"  계정 {email} · 예측 {prediction_id} {status}")
        if status != "done":
            print("  → FAIL  예측이 끝나지 않았습니다. ai_worker 가 떠 있는지 확인하세요.")
            return False
        answers: dict[str, str] = {}
        asked: list[str] = []
        data = call("POST", "/challenge-chat/select", json={})
        while data["mode"] == "ask" and len(asked) < 4:
            [question] = data["questions"]
            value = next(o["value"] for o in question["options"] if o["value"] in KEEP_VALUES)
            print(f"  [질문] {question['question_id']} {question['text']!r} → {value}")
            answers[question["key"]] = value
            asked.append(question["key"])
            data = call("POST", "/challenge-chat/select", json={"answers": answers, "asked": asked})
        messages = [{"role": "user", "content": QUERY}]
        chat = call("POST", "/challenge-chat", json={"messages": messages})
        print(f"  [대화] mode={chat['mode']} reply={chat['reply']!r}")
        messages.append({"role": "assistant", "content": chat["reply"][:400]})
        body = {"messages": messages, "answers": answers, "asked": asked}
        data = call("POST", "/challenge-chat/select", json=body)
    except (RuntimeError, httpx.HTTPError, KeyError) as exc:
        print(f"  → FAIL  {exc}")
        return False
    print(f"  [선택] mode={data['mode']} sources={len(data['sources'])}")
    for item in data["items"]:
        print(
            f"  #{item['rank']} {item['challenge_code']} level={item.get('goal_level')} "
            f"target={item['target_value']}{item['unit'] or ''}×{item['daily_target_count']} "
            f"slots={item['context_slots']} 카드={item['evidence_card_ids']} reason={item['reason']!r}"
        )
    if data["mode"] == "conversation":
        print("  → PASS")
        return True
    print(
        "  → FAIL  규칙 추천으로 답했습니다. 서버 로그에서 시작 시 경고와 "
        "'질의 챗봇 모델 호출·검증 실패: <종류>' 줄을 확인하세요. .env 를 고쳤다면 서버를 다시 띄워야 합니다."
    )
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI 키·질의 챗봇 동작 확인")
    parser.add_argument("--base-url", help="띄워 둔 API 주소. 주면 3단계(서버 흐름)까지 본다")
    args = parser.parse_args()
    key = check_settings()
    if key is None:
        sys.exit(1)
    ok = asyncio.run(check_direct_call(key))
    if ok and args.base_url:
        ok = check_server_flow(args.base_url.rstrip("/"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
