# 당고킬러 공통 HTML 프론트

2026-10-12 통합된 `frontend/`를 기준으로 HTML v4의 디자인을 사용한다.
React·Vite·TypeScript의 미사용 초기 템플릿을 제거했다. Node 20 이상이 필요하며 화면 실행에 번들러는 사용하지 않는다.
화면·API·DB가 같은 저장소에 있다. `docs/prototype/당고킬러-모험시안_v4.html`은 11화면의 참고 시안으로 유지한다.

## 실행

백엔드는 기존 안내대로 저장소 루트에서 실행한다.

```bash
docker compose up -d
```

환경을 직접 구성한 경우에는 기존 DB·환경변수·마이그레이션·시드를 준비하고 `uv run uvicorn app.main:app --reload`로 실행할 수 있다.

프론트 개발 서버:

```bash
cd frontend
npm ci
npm run dev
```

화면은 `http://127.0.0.1:5173/`, API는 개발 서버가 `http://127.0.0.1:8000/api/v1`로 전달한다.
브라우저는 같은 출처로 요청하므로 토큰·쿠키를 위해 별도 CORS 설정을 바꾸지 않는다.
포트나 백엔드 주소를 바꾸려면 실행 환경변수 `DANGO_FRONTEND_PORT`, `DANGO_API_ORIGIN`을 지정한다.
개발 서버는 기본적으로 127.0.0.1에만 열린다. 운영에서는 이 개발 서버 대신 FastAPI·Nginx의 `/frontend/` 경로를 사용한다.
FastAPI의 `http://localhost:8000/frontend/`로 직접 열어도 같은 진입점이 동작한다.

## 공통 기반이 맡는 것

| 구성 | 파일 | 역할 |
| --- | --- | --- |
| 화면 틀 | index.html, app.mjs | 헤더·하단 메뉴·내용 영역·공통 사용자 표시 |
| 라우팅 | shared/router.mjs | 11개 화면 이름, 로그인 보호, 원래 화면 복귀, 주소창·뒤로가기 |
| 인증 | shared/auth.mjs | 로그인·서버 로그아웃·쿠키 복원·메모리 세션·계정 경합 방지 |
| API | shared/api.mjs | /api/v1, Bearer, 성공 봉투 해제, 실패·인증 갱신, 파일 본문 |
| UI | shared/components.mjs, components.css | 버튼·입력·카드·로딩·없음·오류·중복 클릭 방지 |

공통 화면 내용은 `data-page-host` 안에만 렌더링한다. 각 페이지가 헤더나 하단 메뉴를 새로 만들지 않는다.
D 네 화면은 `embedded` 모드로 공통 틀 안에 연결되어 있다. D 사이 이동에서는 기존 타이머 상태를 유지한다.
다른 담당 화면으로 이동하거나 로그인 사용자가 바뀌면 이전 D 영역과 수행 중 상태를 정리한다.
새로고침·영역 제거로 미인증 타이머가 사라진 경우에는 새 타이머로 시작한다. 임의로 완료를 인정하지 않는다.

## 담당별 시작 파일

| 담당 | 화면 | 수정 시작점 |
| --- | --- | --- |
| 수빈 / A | login·signup | pages/login.mjs, pages/signup.mjs |
| 병주 / C | health·health2·health3·waiting·risk | pages/각_화면명.mjs |
| 이경 / D | reco·today·progress·monsters | d/screens.mjs, d/model.mjs |

`login`에는 공통 인증을 검증할 최소 로그인 폼을 제공한다. A의 최종 시안·회원가입 흐름 구현 완료를 뜻하지 않는다.
`signup`과 C 다섯 화면은 담당자가 교체할 진입점만 있다. 아직 준비 중임을 표시하며 가상 건강 수치·결과나 저장 동작은 넣지 않는다.
회원가입·건강기록·예측 접수·폴링·결과 표시·사진 업로드의 화면별 처리는 해당 담당자가 이어서 구현한다.

## 페이지 구현 규약

각 파일에서 `mount(context)`를 내보낸다. 아래 예시는 호출 방법을 보여준다. 자신의 화면 진입점에서 작성한다.

```javascript
export function mount({ root, ui, api, auth, router, route, signal }) {
  const title = ui.element('h1', { text: '화면 제목' });
  const field = ui.field('입력 항목', { name: 'input_value', required: true });
  const status = ui.element('div', { attributes: { 'aria-live': 'polite' } });
  const load = ui.button('내 정보 확인', {
    variant: 'secondary',
    onClick: () => ui.runPending(load, async () => {
      try {
        const data = await api('/users/me');
        if (signal.aborted) return;
        status.replaceChildren(ui.notice(data.nickname));
      } catch (error) {
        if (!signal.aborted) status.replaceChildren(ui.notice(error.message, { kind: 'error' }));
      }
    }),
  });
  root.replaceChildren(title, field.wrapper, status, load);
  return () => { /* 타이머·구독·이벤트를 정리한다. */ };
}
```

- `api('/path', {method?, body?})`는 성공 봉투의 `data`를 반환한다. 사용자 ID를 요청에 넣지 않는다.
- 공개 인증 API는 `{auth:false}`로 호출한다. 로그인 자체는 `auth.login({email,password})`로 처리한다.
- 회원가입 성공 결과를 `await auth.acceptLogin(data)`에 전달하면 토큰·내 정보를 공통 세션에 연결한다. `refresh_token`을 별도 저장하지 않는다.
- 이동은 `router.navigate('health2')` 또는 `router.navigate('waiting?prediction_id=501')`로 한다. 다른 담당 페이지로 넘어갈 때 파일 경로나 `location`을 직접 바꾸지 않는다.
- 인증을 마친 로그인 페이지에서는 `router.resume()`로 원래 목적지에 복귀한다.
- `route.params`는 URLSearchParams다. ID 형식·양수 여부는 사용하는 페이지에서도 확인한다. 토큰과 건강정보를 URL에 넣지 않는다.
- 조회는 화면 이탈 시 취소 신호를 받는다. 늦은 응답을 표시하기 전에 `signal.aborted`를 확인한다.
- 쓰기는 자동 재전송·자동 취소하지 않는다. 연결이 끊기면 서버 목록을 확인한 뒤 사용자가 재시도한다.
- `ui.runPending(button, work)`는 처리 중 표시와 중복 실행 방지를 맡는다.
- `ui.element`와 `ui.notice`는 텍스트를 안전하게 넣는다. 서버 문자열을 직접 innerHTML에 넣지 않는다.

## 인증·오류·날짜 규칙

공통 액세스 토큰은 메모리에만 둔다. localStorage·sessionStorage에 새로 저장하지 않는다.
새로고침은 AUTH-04의 서버 HttpOnly 쿠키로 복원한 뒤 USER-01로 본인을 확인한다.
로그아웃 뒤 늦게 도착한 갱신 응답이 이전 토큰을 다시 넣지 못하도록 세션 버전을 확인한다.
조회는 401일 때 한 번 갱신 후 다시 읽는다. 시작·저장·중단 등의 쓰기는 자동 재전송하지 않는다.
로그아웃 API 실패를 성공처럼 표시하지 않는다. 토큰·비밀번호를 로그로 남기지 않는다.

예측 완료 직후에만 제한적으로 재시도한다. 폴링이 done 으로 바뀐 뒤 첫 호출에서
404 PRED_NOT_FOUND 또는 409 CHLG_RECOMMENDATION_UNAVAILABLE 이 나면 1초 간격으로
2회까지 다시 호출한다. 그 밖에는 재시도하지 않는다.
409 CHLG_RECOMMENDATION_UNAVAILABLE 은 갱신 대기뿐 아니라 아티팩트 부재·후보 없음·
슬롯 부족도 함께 덮는 코드다. 두 번 더 시도해도 실패하면 error.message 를 그대로
보여준다. 409 를 코드별로 나누는 것은 2단계 후보다.

공통 컨텍스트의 `predictionReady`가 완료 직후 추천 호출을 관리한다. C의 폴링 화면은
실제 `pending` → `done` 전환을 확인한 뒤 아래처럼 연결한다.

```javascript
predictionReady.markDone(result); // result.status === 'done', 양의 정수 prediction_id 확인
router.navigate('reco');
```

D 화면은 이 표시가 있던 첫 추천 호출만 재시도한다. 완료 표시는 메모리에만 보관하며
5초가 지나거나 첫 요청이 사용하거나 로그인 상태가 바뀌면 만료된다.
화면 이탈·계정 변경 이후에는 예약된 재시도를 보내지 않는다.
일반 추천 오류나 시작·대상 변경·인증 쓰기에는 자동 재시도를 적용하지 않는다.
C 폴링 화면 자체는 C 담당자가 구현해야 하며, 서버의 `done` 확인 없이 완료 표시를 만들지 않는다.

API 타임스탬프는 오프셋을 포함해 해석한다. UTC로 고정해서 9시간을 중복 추가하지 않는다.
KST 달력 날짜 `YYYY-MM-DD`는 날짜 자체를 유지한다. `위험도`·`위협도`·`공략 점수`·봉인은 루트 지침을 따른다.
PRED 상태는 실제 API의 `pending`·`done`·`failed`를 사용한다. HTTP 200만으로 추론 완료를 판단하지 않는다.
의료 고지와 이미 진단/복약해 제외된 질환을 확률 0으로 채우지 않는 처리는 C 결과 화면에서 지킨다. 그 자리에 대신 넣을 표시 문구는 AGENTS.md 의 "Never do this" 를 따른다.

## 사진 업로드 연결

사진 업로드 API가 준비되면 C의 함수를 `startApplication`의 `uploadPhoto` 옵션에 전달하거나
기본 시작 전에 `window.dangoEvidence.uploadPhoto`를 제공한다.
입력은 File이고 출력은 `{evidence_url: 비공개_참조값}`이다. 업로드 실패 시 수행 로그를 만들지 않는다.
`api()`에 FormData를 넘길 수 있다. multipart의 Content-Type은 브라우저가 정하므로 직접 붙이지 않는다.
아직 없는 업로드 API를 있다고 가정해서 호출하지 않는다.

## 검증

```bash
npm run test:unit
npx playwright install chromium
npm run test:browser
```

단위 검사는 API·인증·라우트·점수·타이머·개발 서버 프록시를 확인한다.
브라우저 검사는 공통 로그인·쿠키 복원·원래 화면 복귀·뒤로가기·늦은 응답·320px 화면과 D의 시작·인증·보상·도감을 확인한다.
브라우저 테스트의 API 응답은 테스트 파일에만 있다. 실제 서비스 화면에 가상 데이터 모드는 없다.
앱·DB 검사는 저장소 루트의 기존 `scripts/ci` 명령을 사용한다. 운영 배포와 실제 워커 포함 통합 검증은 별도다.

## 기존 자료

API·요구사항·DB·설계는 저장소 루트 `docs/`를 참조한다. 원본 시트의 사본을 여기 만들지 않는다.
기존 v4 폰트·이미지와 라이선스는 `d/assets/`에 있으며 모든 공통 화면에서 같은 CSS를 사용한다.
모델 PR과 D 추천 최신성/복약 보완은 별도 작업이다. 이 공통 기반 패치에 그 후속 코드를 중복으로 넣지 않는다.
