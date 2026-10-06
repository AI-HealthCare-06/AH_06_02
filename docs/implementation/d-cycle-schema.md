# D 공략 주기·예정 기회 모델

기준: main `60f2a0c`의 `table-spec.md`, `erd.sql`, `erd.md`, `AGENTS.md` 및
REQ-RECO-006 / REQ-CHLG-011 / REQ-CHLG-012. 역할별 진행 방식의 D 모델 작업이다.

## 구현 범위

- `UserAttackCycle`: 주기 10개 일반 컬럼. draft의 날짜는 NULL, 정책 버전은 필수.
- `UserChallengeOccurrence`: 예정 기회 10개 컬럼. 슬롯 기본값은 빈 문자열.
  날짜·슬롯·회차 중복 및 같은 완료 로그 재사용을 UNIQUE로 차단한다.
- `UserChallenge`: 누락 8개 컬럼, `graduated` 상태, `cycle_id` 인덱스.
  `habit_established`와 미집계 종료 집계값은 NULL이다.
- `Challenge`: `context_priority`, `personalization_policy` 및 명세의 요인·활성 인덱스.
- `ChallengeRecommendation`: `cycle_id`와 대화·근거·제안 목표 4개 컬럼,
  `conversation` source_type.

관련 ID는 기존 방식대로 스칼라 BigIntField이다. FK는 DDL이 소유한다.
신규 모델은 이미 등록된 `app.models.challenges`에 있어 추가 등록이 필요 없다.
API 연결, 마스터 시드, 습관 판정 및 수행률 계산은 이 변경에 포함되지 않는다.

## 검증 결과 (2026-10-06)

Python 3.13.15, 잠금 파일의 app·dev 의존성을 사용했다.

| 검사 | 결과 |
| --- | --- |
| `uv run ruff check .` | 통과 |
| `uv run ruff format . --check` | 통과, 83개 파일 |
| `uv run mypy .` | 실패: 기존 실험·명세 동기화 스크립트의 의존성/스텁 누락 및 중복 모듈 경로. 수정 전 main도 동일 16개 오류 |
| `uv run mypy app` | 통과, 69개 소스 |
| `uv run pytest -q app` (기존 MySQL fixture) | 실행했으나 MySQL 연결 실패로 79개 setup 오류 |
| 별도 SQLite 메모리 DB 검증 | 전체 79개 통과, 신규 저장 검증 8개 포함 |
| `uv run aerich upgrade` | 실행했으나 MySQL 연결 실패. 빈 MySQL에서 0번부터 재현 검증 미완료 |

SQLite 검증에서는 임시 실행 스크립트에서 테스트 DB 설정 함수만 바꿨다.
저장소의 MySQL fixture/config 및 `.env`는 수정하지 않았다.
신규 검증은 NULL 호환, 목표 JSON 및 DECIMAL 왕복, KST DATE 보존,
기회 중복 차단, 완료 로그 중복 차단, 상태 및 대화형 추천 저장을 확인한다.
SQLite 통과는 MySQL 제약·동시성 검증을 대체하지 않는다.

MySQL 8.0.46 바이너리를 별도 임시 디렉터리에 준비하고 초기화했으나,
실행 환경이 Unix 소켓 생성을 차단해 서버가 시작하지 못했다.

## A 통합 작업

현재 main migration은 0~3이다. 번호를 겹쳐 쓰지 않도록 이 D 변경에는
번호가 붙은 migration을 추가하지 않았다. C의 `health_records` 모델과
D 모델을 통합한 뒤 A가 최신 main 번호를 확인하고 다음 migration을 만든다.

- ORM 변경 migration: 두 테이블 생성, 기존 세 테이블 컬럼·상태·인덱스 보강.
- raw SQL: `active_user_id`, `uq_uac_active`, 복합 FK `fk_uac_target` 및
  `erd.sql`에 있으나 아직 DB에 없는 FK. downgrade는 의존성의 역순.
- Tortoise의 SmallIntField/CharEnumField 생성 SQL과 DDL의 TINYINT/ENUM
  차이는 기존 모델 방식을 유지했으므로, 실제 MySQL DDL 통합 때 대조한다.
- 기존 자료가 있는 DB에서 신규 nullable 컬럼이 NULL로 보존되는지 확인한다.
- 빈 DB에 0번부터 적용하고, 동일 사용자 동시 시작에서 active 주기 1개,
  다른 사용자 캐릭터 지정 거절 및 완료 로그 재사용 거절을 확인한다.
- UTC DATETIME 저장과 KST DATE 경계를 실제 MySQL에서 확인한다.
  공통 ORM의 timezone 설정은 이 D 모델 작업에서 변경하지 않았다.

## 원본에서 정리할 항목

- `requirements.md`의 REQ-CHLG-002에는 아직 "남은 슬롯 수만큼" 문구가 있다.
  사용자 전달 결정 및 AGENTS의 "주기당 1개 추가"와 맞추어 원본 시트에서
  개정 후 사본을 재생성해야 한다.
- 테이블 설명은 준비 draft도 최대 1개라고 하지만 DDL의 draft UNIQUE는
  주석 제안이다. active UNIQUE만 실제 DDL에 있으며, draft 제약은
  A·D 통합 때 확정해야 한다. 임의의 생성 컬럼은 추가하지 않았다.

필수 MySQL 검사와 전체 mypy 문제가 해소되기 전에는 Draft PR로 리뷰한다.
