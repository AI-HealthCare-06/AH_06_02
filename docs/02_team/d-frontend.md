# D HTML 화면 연결 (2026-10-12)

> 2026-10-20 서비스 화면을 v5로 바꾸면서 이 문서가 설명하는 v4 D 화면(`frontend/d/`)은 지웠다. 지우기 전 코드는 커밋 `218dd51`에서 볼 수 있다. 같은 기능은 v5(`frontend/v5/app.mjs`)에 있다. 이 문서는 당시 구현 기록으로 남긴다.

이경 담당 `reco` · `today` · `progress` · `monsters`를 HTML v4 디자인으로 구현했다.
React나 번들러 없이 ES 모듈을 사용한다. 시안의 가상 위험도·점수·보상 로직은 포함하지 않는다.
기준 커밋은 main `fc6a645`이고 작업 브랜치는 `feature/d-html-api-20261012`다.

이후 통합된 main `b7b65b3` 기준 공통 기반에서는 `/frontend/`를 기본 진입점으로 사용한다.
현재 실행·담당자 연결 규약은 [frontend/README.md](../../frontend/README.md)를 우선한다.
아래 독립 D 진입점과 인증 연결 예시는 최초 전달본의 별도 실행 방법이다.

## 화면과 API

| 화면 | 사용 API | 구현 |
| --- | --- | --- |
| reco | CHLG-01·02·03·04·05, MNSTR-01 | 서버 선택 한도, 목표·난이도·XP 안내, 선택·시작, 안전 확인, 거절·쿨다운·제외·다시 켜기 |
| today | CHLG-06·07, MNSTR-01 | 오늘 실제 예정 기회, 점심·저녁·독립 회차, 타이머·직접 확인·사진 연결, 서버 인정 결과 안내 |
| progress | CHLG-06·09, MNSTR-01, RWRD-01, USER-06 | 주기·예정 기회 수행률·경험치·보상·중단·지난 챌린지 |
| monsters | MNSTR-01, RWRD-01 | 서버 마스터 목록, 7가지 상태, 미측정과 0 구분, 현재 공략 대상, 봉인 기록·보상 |

공략 점수 145는 `145 / 100`으로 표시하고 게이지만 100에서 멈춘다.
위협도는 수행 성공으로 차감하지 않는다. 기간 종료는 습관 형성이나 새 봉인을 뜻하지 않는다.
독립 회차는 앞 회차부터 인증한다. 서버가 CHLG-07의 해당 날짜 첫 남은 기회에 기록하기 때문이다.
타이머는 실제 경과 시간을 사용하며 일시정지 시간을 제외한다. 부족분과 초과시간은 다른 회차로 넘기지 않는다.
새로고침하면 미인증 타이머는 초기화된다. 완료·XP·보상은 서버 응답과 재조회로 확인한다.

## 실행

기존 DB·환경변수 준비 후:

```bash
uv sync --group app --group dev
uv run uvicorn app.main:app --reload
```

`http://localhost:8000/frontend/d/#reco` 또는 `#today`, `#progress`, `#monsters`로 연다.
실제 추천은 활성 모델 아티팩트와 건강기록·예측 또는 진단자 근거가 있어야 한다.
모델 PR #38·#39와 예측 워커 통합은 이 변경에 포함하지 않는다. 아티팩트 버전을 프론트에 하드코딩하지 않는다.
사진 업로드 연결 전에는 사진 인증 불가를 표시하고, 서버가 허용한 경우에만 사용자가 직접 확인 대체를 고를 수 있다.

## 공통 인증·라우팅 연결

공통 페이지에서는 `v4.css`, `screens.css`를 적용하고 D 화면 영역을 하나 제공한다.
`boot.mjs`는 독립 진입점용이다. 공통 라우터에서는 아래 방식으로 직접 붙인다.

```javascript
import { mountDangoScreens } from '/frontend/d/screens.mjs';

const screens = mountDangoScreens(document.querySelector('#dango-screens'), {
  embedded: true,
  request: commonApiRequest,
  navigate: commonNavigate,
  uploadPhoto: uploadEvidencePhoto,
});
// D 화면으로 이동할 때 screens.show('today') 등 호출.
// 영역을 제거할 때 screens.destroy() 호출.
```

`request(path, {method?, body?})`는 `/api/v1` 기준 경로를 받고 성공 봉투의 `data`를 반환한다.
실패는 `status`·`code`가 있는 오류를 던진다. 공통 클라이언트가 아직 없으면 `frontend/shared/api.mjs`를 사용할 수 있다.
이 클라이언트는 조회 인증 만료 시 한 번 갱신한다. 시작·기록·중단 등의 쓰기 요청은 자동 재전송하지 않는다.

독립 진입점의 연결 규약:

```javascript
window.dangoAuth = {
  getAccessToken: () => commonAccessToken,
  setAccessToken: token => { commonAccessToken = token; },
};
window.dangoNavigate = page => commonNavigate(page);
```

공통 인증을 연결하지 않은 독립 진입점은 `sessionStorage['dango.access_token']`을 읽는다.
공통 인증 제공자가 있으면 그 제공자의 `null`도 그대로 따른다. 이전 저장 토큰으로 대체하지 않는다.
리프레시 토큰은 AUTH-03의 기존 HttpOnly 쿠키를 사용한다. `user_id`는 보내지 않는다.
로그인·로그아웃·계정 변경 시 `window.dispatchEvent(new Event('dango:auth-changed'))`를 호출하면
이전 사용자 화면·타이머·선택을 지우고 다시 조회한다.
`dango:authentication-required`는 재로그인이 필요하다는 알림이다.
`dango:navigate` 이벤트의 `detail.page`로 다른 화면 이동을 받을 수도 있다. 처리하면 `preventDefault()`로 기본 이동을 막는다.
기본 다른 화면 URL은 `/frontend/#login`·`#risk`·`#health`다. 실제 공통 진입점에 맞게
`window.dangoConfig.routes` 또는 이동 함수를 연결해야 한다. A·C 화면은 이 작업에서 새로 만들지 않는다.

## 병주님 사진·배포 연결

C 사진 업로드 함수를 아래 형태로 연결한다. D는 파일을 올린 다음 받은 비공개 참조값만 CHLG-07에 전달한다.
업로드 실패 시 수행 기록과 보상을 만들지 않는다.

```javascript
window.dangoEvidence = {
  uploadPhoto: async file => {
    const result = await uploadCPhoto(file);
    // C 업로드 API 호출 결과의 비공개 참조값을 반환한다.
    return { evidence_url: result.evidence_url };
  },
};
```

`app/main.py`가 `/frontend`를 정적으로 제공한다. `app/Dockerfile`에 프론트 복사를 추가했고
Nginx 설정 세 곳에 `/frontend/` 프록시를 추가했다. HTTPS 설정의 HTTP 경로는 HTTPS로 이동한다.
실제 이미지 빌드·Nginx 실행·운영 배포는 이 환경에서 검증하지 못했다.

## 추가한 API 조회 필드

새 테이블·컬럼·마이그레이션은 없다. RWRD-01은 기존 명세대로 구현했다.
아래 추가 응답 필드는 팀 API 시트에 반영할 내용이다. 원본 시트의 사본은 직접 수정하지 않았다.

| API | 추가 필드 | 용도 |
| --- | --- | --- |
| CHLG-01 | data.remaining_slots | 서버가 계산한 이번 시작 한도 |
| CHLG-01·02 카드 | daily_target_count, target_value, unit, daily_xp, safety_check_required, manual_fallback_allowed | 시작 전 목표·안전 안내 |
| CHLG-02 카드 | suppressed_until_manual | 제외 카드의 직접 복원 |
| CHLG-06 항목 | status, unit, manual_fallback_allowed, today_date, today_occurrences | 상태·스냅샷 단위·KST 오늘 실제 기회 |

`today_occurrences`는 `[{occurrence_id, slot_code, sequence_no, status}]`다.
`slot_code`는 `lunch`·`dinner` 또는 독립 회차의 빈 문자열이며, 완료된 기회도 해당 미션의 오늘 목록에 포함한다.
재시작 시 이전에 완료해 새 미션에서 제외된 기회는 되살리지 않는다.
`unit`은 새로 시작하는 미션의 기존 `goal_config_snapshot` JSON에 함께 저장한다.
기존 미션에 단위 스냅샷이 없으면 마스터 단위를 읽는다.

CHLG-10 대상 변경은 현재 시트에서 제안 상태이고 main에 구현이 없다.
이 화면의 도감은 현재 대상을 확인한다. 변경 성공처럼 보이는 버튼이나 임의 API 호출은 넣지 않았다.

## 검증

```bash
./scripts/ci/run_test.sh
./scripts/ci/code_fommatting.sh
./scripts/ci/check_mypy.sh
npm ci --prefix frontend
npm run test:unit --prefix frontend
cd frontend
npx playwright install chromium
npm run test:browser
```

브라우저 테스트의 API 응답은 테스트 파일에만 있다. 제품 화면에는 가상 데이터 모드가 없다.
타이머·일시정지·KST 날짜·점수 표시, 인증 만료·쓰기 재전송 방지, 시작→기록→보상→도감,
중단 취소·확인, 제외 복원, 다른 사용자 저장 토큰 차단, 공통 메뉴 상태 보존을 검증한다.
Python 테스트는 이 실행 환경에 MySQL/Docker가 없어 CI 진입점에 임시 SQLite 어댑터를 사용했다.
MySQL 행 잠금 동시성 테스트 1개는 제외했다. 정상 CI에서는 기존 MySQL 명령으로 확인해야 한다.
타입 검사에는 이 환경에 누락된 `pandas-stubs`를 임시 설치했으며 프로젝트 의존성은 변경하지 않았다.

이번 실행 결과: 앱 272개 통과·MySQL 동시성 1개 제외, 프론트 단위 7개·브라우저 6개 통과, Ruff·포맷 검사 통과, Mypy 126개 소스 검사 통과.

기존 v4의 폰트·그림 네 파일은 용량이 500 KB를 넘는다. 대용량 파일 훅에는 해당 네 파일명만 예외로 등록했고, 다른 파일과 원시자료 검사는 유지한다.
