"""로컬에 띄운 API 를 상대로 전체 흐름을 한 번 돌려보는 스모크 스크립트.

    docker compose up -d fastapi
    uv run python -m scripts.seed.seed_challenges
    uv run python -m scripts.seed.seed_monsters
    uv run python -m scripts.seed.seed_rewards
    uv run python -m scripts.smoke [--base-url http://localhost:8000]

단위 테스트가 아니라 실제 서버에 HTTP 요청을 보낸다. 실행할 때마다 새 계정을 만든다.
한 단계가 실패해도 멈추지 않고 이유를 적은 뒤 다음 단계로 간다. 값을 우회하거나 지어내지 않는다.
앞 단계 결과가 없어 요청 자체를 만들 수 없는 단계는 BLOCKED 로 표시한다.
"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core import config

REPO_ROOT = Path(__file__).resolve().parents[1]

KST = ZoneInfo("Asia/Seoul")
PASSWORD = "smoke1234"

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


@dataclass
class Step:
    name: str
    outcome: str = BLOCKED
    status: int | None = None
    notes: list[str] = field(default_factory=list)
    #: 요약에 보일 첫 실패 이유. 뒤따른 요청이 성공해도 덮어쓰지 않는다
    reason: str | None = None

    def fail(self, reason: str, status: int | None = None) -> None:
        self.outcome = FAIL
        if self.reason is None:
            self.reason = reason
            if status is not None:
                self.status = status


@dataclass
class Context:
    email: str
    token: str | None = None
    health_record_id: int | None = None
    monsters: list[dict[str, Any]] = field(default_factory=list)
    recommendation_ids: list[int] = field(default_factory=list)
    user_challenge_id: int | None = None
    context_slots: list[str] = field(default_factory=list)


class Smoke:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=15)
        self.ctx = Context(email=f"smoke+{time.strftime('%Y%m%d%H%M%S')}@example.com")
        self.steps: list[Step] = []

    # ------------------------------------------------------------ 공통

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.ctx.token}"} if self.ctx.token else {}

    def _call(self, step: Step, method: str, path: str, **kwargs: Any) -> dict[str, Any] | None:
        """요청을 보내고 봉투를 돌려준다. 네트워크·JSON 오류도 실패 이유로 남긴다."""
        try:
            response = self.client.request(method, path, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            step.fail(f"요청 실패 {method} {path}: {exc!r}")
            step.notes.append(f"요청 실패 {method} {path}: {exc!r}")
            return None
        if step.reason is None:
            step.status = response.status_code
        try:
            body: dict[str, Any] = response.json()
        except ValueError:
            step.fail(f"{method} {path} 응답이 JSON 이 아님", response.status_code)
            step.notes.append(f"{method} {path} → {response.status_code} JSON 이 아님: {response.text[:200]!r}")
            return None
        step.notes.append(f"{method} {path} → {response.status_code}")
        if not body.get("success"):
            error = body.get("error") or {}
            step.fail(f"{method} {path} → {error.get('code')}", response.status_code)
            step.notes.append(f"error.code={error.get('code')} message={error.get('message')!r}")
            extra = {key: value for key, value in error.items() if key not in ("code", "message")}
            if extra:
                step.notes.append(f"error 부가 필드: {extra}")
            if response.status_code >= 500:
                # 서버는 내부 예외를 응답에 싣지 않는다. 원인은 서버 로그에 있다
                step.notes.append("진단: 5xx 는 서버 내부 오류다. docker logs fastapi 로 원인을 확인한다")
        return body

    def _blocked(self, step: Step, reason: str) -> None:
        step.outcome = BLOCKED
        step.reason = f"요청을 보내지 않음: {reason}"
        step.notes.append(step.reason)

    def run(self) -> int:
        for name, action in [
            ("1. 회원가입", self.signup),
            ("2. 로그인", self.login),
            ("3. 건강정보 입력", self.health_record),
            ("4. 예측 조회", self.prediction),
            ("5. 도감 조회", self.monsters),
            ("6. 챌린지 추천", self.recommendations),
            ("7. 챌린지 시작", self.start),
            ("8. 수행 기록", self.log),
            ("9. 챌린지 조회", self.list_challenges),
            ("10. 챌린지 종료", self.stop),
        ]:
            step = Step(name)
            self.steps.append(step)
            print(f"\n=== {name}")
            try:
                action(step)
            except Exception as exc:  # 스모크는 끝까지 돈다
                step.fail(f"스크립트 예외: {exc!r}")
                step.notes.append(f"스크립트 예외: {exc!r}")
            for note in step.notes:
                print(f"  {note}")
            print(f"  → {step.outcome}")
        return self.summary()

    def summary(self) -> int:
        print("\n" + "=" * 60)
        print(f"요약 · 계정 {self.ctx.email} · {datetime.now(KST).isoformat(timespec='seconds')}")
        print("=" * 60)
        for step in self.steps:
            mark = {PASS: "✓", FAIL: "✗", BLOCKED: "–"}[step.outcome]
            status = step.status if step.status is not None else "-"
            print(f"{mark} {step.outcome:<7} {status!s:>4}  {step.name}")
            if step.outcome != PASS:
                print(f"{'':16}{step.reason or (step.notes[-1] if step.notes else '')}")
                for note in step.notes:
                    if note.startswith("진단"):
                        print(f"{'':16}{note}")
        counts = {outcome: sum(step.outcome == outcome for step in self.steps) for outcome in (PASS, FAIL, BLOCKED)}
        print(f"\nPASS {counts[PASS]} · FAIL {counts[FAIL]} · BLOCKED {counts[BLOCKED]}")
        return 0 if counts[PASS] == len(self.steps) else 1

    # ------------------------------------------------------------ 단계

    def signup(self, step: Step) -> None:
        body = {
            "email": self.ctx.email,
            "password": PASSWORD,
            "nickname": "스모크",
            "birth_year": 1990,
            "sex": "F",
            "height_cm": 164.0,
            # 글루코 블레이드(grow 아이템) 지급 조건을 보려고 성장형을 고른다
            "motivation_type": "grow",
            "dm_diagnosed": False,
            "htn_diagnosed": False,
            "dm_medication": False,
            "htn_medication": False,
            "disclaimer_agreed": True,
        }
        envelope = self._call(step, "POST", "/api/v1/auth/signup", json=body)
        if envelope and envelope.get("success"):
            step.outcome = PASS
            step.notes.append(f"email={self.ctx.email} user_id={envelope['data'].get('user_id')}")

    def login(self, step: Step) -> None:
        envelope = self._call(step, "POST", "/api/v1/auth/login", json={"email": self.ctx.email, "password": PASSWORD})
        if envelope and envelope.get("success"):
            self.ctx.token = envelope["data"].get("access_token")
            if self.ctx.token:
                step.outcome = PASS
            else:
                step.fail("access_token 없음")
            step.notes.append(f"access_token {'받음' if self.ctx.token else '없음'}")

    def health_record(self, step: Step) -> None:
        if not self.ctx.token:
            return self._blocked(step, "토큰 없음")
        body = {
            "input_mode": "simple",
            "weight_kg": 62.0,
            "waist_cm": 80.0,
            "smoking_current": False,
            "alcohol_frequency": 3,
            "alcohol_amount": 2,
            "walking_days": 2,
            "walking_minutes": 20,
            "strength_days": 0,
            "sitting_minutes": 540,
            "family_history_dm": True,
            "family_history_htn": False,
            "dining_out_freq": 3,
        }
        envelope = self._call(step, "POST", "/api/v1/health-records", json=body)
        if envelope and envelope.get("success"):
            data = envelope["data"]
            self.ctx.health_record_id = data.get("health_record_id")
            step.outcome = PASS
            step.notes.append(
                f"health_record_id={data.get('health_record_id')} bmi={data.get('bmi')} "
                f"recorded_at={data.get('recorded_at')}"
            )

    def prediction(self, step: Step) -> None:
        # 조회(PRED-02)에는 prediction_id 가 필요해 먼저 접수(PRED-01)를 보낸다
        if not self.ctx.health_record_id:
            return self._blocked(step, "health_record_id 없음")
        envelope = self._call(step, "POST", "/api/v1/predictions", json={"health_record_id": self.ctx.health_record_id})
        if envelope is None or not envelope.get("success"):
            if step.status == 404:
                step.notes.append("진단: 서버에 /api/v1/predictions 라우터가 없다 (PRED-01 미구현)")
            return None
        prediction_id = envelope["data"].get("prediction_id")
        step.notes.append(f"접수 prediction_id={prediction_id} status={envelope['data'].get('status')}")
        polled = self._call(step, "GET", f"/api/v1/predictions/{prediction_id}")
        if polled and polled.get("success"):
            step.outcome = PASS
            step.notes.append(f"status={polled['data'].get('status')} results={polled['data'].get('results')}")
        return None

    def monsters(self, step: Step) -> None:
        if not self.ctx.token:
            return self._blocked(step, "토큰 없음")
        envelope = self._call(step, "GET", "/api/v1/monsters/me")
        if not envelope or not envelope.get("success"):
            return None
        items = envelope["data"].get("items", [])
        self.ctx.monsters = items
        step.notes.append(f"몬스터 {len(items)}종")
        for item in items:
            step.notes.append(
                f"  {item.get('code'):<9} state={item.get('state')} impact_score={item.get('impact_score')} "
                f"is_target={item.get('is_target')} weekly_progress={item.get('weekly_progress')}"
            )
        if items:
            step.outcome = PASS
        else:
            step.fail("monsters 마스터 비어 있음")
            step.notes.append("진단: monsters 마스터가 비어 있다. seed_monsters 를 먼저 돌려야 한다")
        return None

    def recommendations(self, step: Step) -> None:
        if not self.ctx.token:
            return self._blocked(step, "토큰 없음")
        envelope = self._call(step, "POST", "/api/v1/challenge-recommendations/generate")
        if envelope and envelope.get("success"):
            data = envelope["data"]
            self.ctx.recommendation_ids = [item["recommendation_id"] for item in data.get("items", [])]
            step.notes.append(f"카드 {data.get('total')}장 model_version={data.get('model_version')}")
            for item in data.get("items", []):
                step.notes.append(
                    f"  #{item.get('rank')} {item.get('title')} factor={item.get('factor_key')} "
                    f"score={item.get('factor_score')} target={item.get('target_monster')}"
                )
        elif envelope and (envelope.get("error") or {}).get("code") == "CHLG_RECOMMENDATION_UNAVAILABLE":
            self._diagnose_unavailable(step)
        listed = self._call(step, "GET", "/api/v1/challenge-recommendations")
        if listed and listed.get("success"):
            step.notes.append(f"추천 카드 조회 total={listed['data'].get('total')}")
        if self.ctx.recommendation_ids:
            step.outcome = PASS
        else:
            step.fail("추천 카드 없음")
        return None

    def _diagnose_unavailable(self, step: Step) -> None:
        """CHLG_RECOMMENDATION_UNAVAILABLE 은 원인이 여러 개고 응답만으로는 구별되지 않는다.

        서버는 아티팩트 → 공략 대상 → 남은 슬롯 → 후보 순으로 확인하고 처음 걸린 곳에서 같은 코드로 끝난다.
        API 로 확인할 수 있는 것과 없는 것을 나눠 적는다.
        """
        step.notes.append(
            "진단: 서버는 아티팩트 → 공략 대상 → 남은 슬롯 → 후보 순으로 보고 처음 걸린 곳에서 이 코드로 끝난다"
        )
        measured = [item for item in self.ctx.monsters if item.get("impact_score") is not None]
        if self.ctx.monsters and not measured:
            states = sorted({str(item.get("state")) for item in self.ctx.monsters})
            step.notes.append(
                f"진단(확인됨): 도감 {len(self.ctx.monsters)}종 모두 impact_score=NULL, state={states}. "
                "select_target 은 impact_score 가 있는 rage·caution·stable 만 고르므로 아티팩트가 있어도 공략 대상을 못 고른다"
            )
        local = REPO_ROOT / config.MODEL_ARTIFACT_PATH
        step.notes.append(
            f"진단(호스트 파일): {config.MODEL_ARTIFACT_PATH} {'있음' if local.is_file() else '없음'}. "
            "서버가 컨테이너면 컨테이너 안 경로를 따로 봐야 한다. 응답만으로는 어느 원인에서 끝났는지 알 수 없다"
        )

    def start(self, step: Step) -> None:
        if not self.ctx.recommendation_ids:
            return self._blocked(step, "추천 카드 없음 (6단계 실패)")
        envelope = self._call(
            step,
            "POST",
            "/api/v1/user-challenges",
            json={"recommendation_ids": self.ctx.recommendation_ids[:1], "safety_confirmed": True},
        )
        if envelope and envelope.get("success"):
            [item] = envelope["data"]["items"]
            self.ctx.user_challenge_id = item.get("user_challenge_id")
            step.outcome = PASS
            step.notes.append(
                f"user_challenge_id={item.get('user_challenge_id')} cycle_id={item.get('cycle_id')} "
                f"{item.get('start_date')}~{item.get('end_date')} goal={item.get('goal_config_snapshot')}"
            )
        return None

    def log(self, step: Step) -> None:
        if not self.ctx.user_challenge_id:
            return self._blocked(step, "진행 중 챌린지 없음 (7단계 실패)")
        detail = self._find_mission()
        body: dict[str, Any] = {"occurred_at": datetime.now(KST).isoformat()}
        verification = (detail or {}).get("verification_type")
        body["verification_method"] = verification or "manual"
        if verification == "timer":
            body["value"] = (detail or {}).get("target_value") or 0
        if self.ctx.context_slots:
            body["context_slot"] = self.ctx.context_slots[0]
        envelope = self._call(step, "POST", f"/api/v1/user-challenges/{self.ctx.user_challenge_id}/logs", json=body)
        if envelope and envelope.get("success"):
            data = envelope["data"]
            step.outcome = PASS
            step.notes.append(
                f"xp_granted={data.get('xp_granted')} weekly_progress={data.get('weekly_progress')} "
                f"level_up={data.get('level_up')} reward={data.get('reward')}"
            )
            if data.get("reward") is None:
                step.notes.append("reward=null (글루코 블레이드는 CH_WALK_AFTER_MEAL 첫 인정 완료 + grow 일 때만)")
        return None

    def _find_mission(self) -> dict[str, Any] | None:
        listed = self.client.get("/api/v1/user-challenges", headers=self._headers())
        for item in listed.json().get("data", {}).get("items", []):
            if item.get("user_challenge_id") == self.ctx.user_challenge_id:
                if item.get("context_type") == "meal":
                    self.ctx.context_slots = ["lunch", "dinner"]
                return dict(item)
        return None

    def list_challenges(self, step: Step) -> None:
        if not self.ctx.token:
            return self._blocked(step, "토큰 없음")
        envelope = self._call(step, "GET", "/api/v1/user-challenges")
        if envelope and envelope.get("success"):
            items = envelope["data"].get("items", [])
            step.notes.append(f"진행 중 {len(items)}개")
            for item in items:
                step.notes.append(
                    f"  {item.get('title')} cycle_week={item.get('cycle_week')} "
                    f"completed={item.get('completed_count')}/{item.get('scheduled_opportunity_count')} "
                    f"progress_rate={item.get('progress_rate')}"
                )
            step.outcome = PASS
            if not items:
                # 조회 API 는 성공했다. 다만 앞 단계가 막혀 확인할 챌린지가 없다
                step.notes.append("진행 중 챌린지 0개 — 7단계가 막혀 진행률·주차를 확인할 대상이 없음")
        return None

    def stop(self, step: Step) -> None:
        if not self.ctx.user_challenge_id:
            return self._blocked(step, "진행 중 챌린지 없음 (7단계 실패)")
        envelope = self._call(
            step,
            "POST",
            f"/api/v1/user-challenges/{self.ctx.user_challenge_id}/stop",
            json={"stop_reason": "스모크 테스트 종료"},
        )
        if envelope and envelope.get("success"):
            step.outcome = PASS
            step.notes.append(
                f"status={envelope['data'].get('status')} stopped_at={envelope['data'].get('stopped_at')}"
            )
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 API 전체 흐름 스모크")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    sys.exit(Smoke(args.base_url).run())


if __name__ == "__main__":
    main()
