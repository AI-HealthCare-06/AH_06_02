# 당고킬러 v5 프론트

서비스 화면은 v5다(2026-10-20 팀 합의). Node 20 이상이 필요하며 화면 실행에 번들러는 사용하지 않는다.
화면·API·DB가 같은 저장소에 있다. v4 앱 코드는 #65에서 지웠고, 지우기 전 코드는 커밋 `218dd51`에서 볼 수 있다. v4 시안 HTML(`docs/prototype/당고킬러-모험시안_v4.html`)은 참고용으로만 남긴다.

## 실행

백엔드는 저장소 루트에서 실행한다.

```bash
docker compose up -d
```

환경을 직접 구성한 경우에는 DB·환경변수·마이그레이션·시드를 준비하고 `uv run uvicorn app.main:app --reload`로 실행한다. 예측까지 확인하려면 예측 워커도 띄운다(루트 README 참고).

프론트 개발 서버:

```bash
cd frontend
npm ci
npm run dev
```

`http://127.0.0.1:5173/frontend/`를 연다. API는 개발 서버가 `http://127.0.0.1:8000/api/v1`로 전달한다.
브라우저는 같은 출처로 요청하므로 토큰·쿠키를 위해 CORS 설정을 바꾸지 않는다.
포트나 백엔드 주소를 바꾸려면 실행 환경변수 `DANGO_FRONTEND_PORT`, `DANGO_API_ORIGIN`을 지정한다.
개발 서버는 127.0.0.1에만 열린다. 운영에서는 FastAPI·Nginx의 `/frontend/` 경로를 사용한다. 일반 정적 서버만으로는 실제 API를 호출할 수 없다.

입력 없이 화면만 검토하려면 주소에 `?demo=1`을 붙인다(`/frontend/?demo=1#login`). 이 모드는 API를 부르지 않고, 새로고침하면 기록이 초기화된다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `index.html` | 서비스 입구. v5 HTML로 넘기며 주소의 화면 이름(`#login` 등)과 `?demo=1`을 이어받는다 |
| `docs/prototype/당고킬러-모험시안_v5.html` | 화면 마크업·스타일과 `?demo=1` 체험 모드. 기본 모드에서는 `v5/app.mjs`를 불러온다 |
| `v5/app.mjs` | 실제 연결 모드. 화면 이동(주소의 `#화면이름`), 인증, API 호출, 화면 그리기 |
| `v5/live.css` | 실제 연결 모드에서만 쓰는 스타일 |
| `v5/item-preview.json` | 꾸미기 후보 70종의 이름과 그림 경로(잠긴 미리보기) |
| `shared/auth.mjs` | 로그인·서버 로그아웃·쿠키 복원·메모리 세션·계정 경합 방지 |
| `shared/api.mjs` | `/api/v1`, Bearer, 성공 봉투 해제, 실패·인증 갱신, 파일 본문 |
| `shared/evidence.mjs` | HLTH-03 사진 업로드 |
| `shared/factors.mjs` | 기여요인 이름표와 Top3 표시 |
| `docs/prototype/assets/` | 화면 그림·영상·폰트와 라이선스 |

화면 이름은 `login`·`signup`·`health`·`health2`·`health3`·`waiting`·`risk`·`monsters`·`reco`·`today`·`progress`·`evolution`·`evolution-complete`·`rewards`다. 로그인 전에는 `login`·`signup`과 가입 중의 건강정보·예측 대기 단계만 열린다.

## 구현 규칙

- 실제 연결 모드에는 가상 데이터를 넣지 않는다. API 오류를 예시 결과로 대신 보여주지 않는다.
- 입력 오류는 해당 칸에 표시하고 그 칸으로 옮긴다. 허용 범위와 소수 자릿수는 서버 검증과 같게 계정 생성 전에 확인한다.
- 서버 문자열은 이스케이프한 뒤 넣는다. 사용자 ID를 요청에 넣지 않는다.
- 쓰기(가입·저장·시작·중단·수령)는 자동으로 다시 보내지 않는다. 응답 전에 연결이 끊긴 예측 접수는 다시 보내지 않고 지도에서 결과를 확인하게 한다.
- 이미 진단·복약 중인 질환에는 예측 확률 대신 `진단 관리 중`을 표시한다.
- `위험도`·`위협도`·`공략 점수`·봉인은 루트 [AGENTS.md](../AGENTS.md)를 따른다. 수행해도 `위험도`·`위협도`는 바뀌지 않는다.
- 320px 화면에서 가로로 넘치지 않는다. `prefers-reduced-motion`을 따르고 영상은 멈춘다.

## 인증·오류·날짜 규칙

공통 액세스 토큰은 메모리에만 둔다. 토큰과 개인정보는 localStorage·sessionStorage에 저장하지 않는다. 새로고침 복원에 필요한 식별자(예: 예측 번호)만 sessionStorage에 둘 수 있다.
새로고침은 AUTH-04의 서버 HttpOnly 쿠키로 복원한 뒤 USER-01로 본인을 확인한다.
로그아웃 뒤 늦게 도착한 갱신 응답이 이전 토큰을 다시 넣지 못하도록 세션 버전을 확인한다.
조회는 401일 때 한 번 갱신 후 다시 읽는다. 로그아웃 API 실패를 성공처럼 표시하지 않는다. 토큰·비밀번호를 로그로 남기지 않는다.

API 타임스탬프는 오프셋을 포함해 해석한다. UTC로 고정해서 9시간을 중복 추가하지 않는다.
KST 달력 날짜 `YYYY-MM-DD`는 날짜 자체를 유지한다.
PRED 상태는 실제 API의 `pending`·`done`·`failed`를 사용한다. HTTP 200만으로 추론 완료를 판단하지 않는다.

## 사진 업로드

`shared/evidence.mjs`가 공통 세션의 API 클라이언트로 `photo`와 `user_challenge_id`를 FormData로 보낸다. 클라이언트에서 JPEG/PNG·빈 파일·최대 10 MiB를 검사하며 서버에서도 검증한다.
비공개 증빙 참조값을 받은 뒤에만 해당 미션의 CHLG-07로 수행 기록을 보낸다. 업로드가 실패하면 수행 기록을 만들지 않는다.

## 검증

```bash
npm run test:unit        # API·인증·사진 업로드·개발 서버 프록시
npx playwright install chromium
npm run test:prototype   # ?demo=1 체험 모드
npm run test:v5          # 실제 연결 모드 브라우저 회귀
```

브라우저 테스트의 API 응답은 테스트 파일에만 있다. 앱·DB 검사는 저장소 루트의 `scripts/ci` 명령을 사용한다.

## 참고 자료

API·요구사항·DB·설계는 저장소 루트 `docs/`를 참조한다. 원본 시트의 사본을 여기 만들지 않는다.
v5 연결 범위·추가 계약·보상 규칙·검증 기록은 [docs/02_team/prototype-v5-proposal.md](../docs/02_team/prototype-v5-proposal.md)에 있다.
