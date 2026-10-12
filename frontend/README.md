# 당고킬러 프론트엔드

당고킬러 서비스의 화면을 만드는 곳입니다. 백엔드·DB·AI 워커는 이 저장소 루트에 있습니다.

원래 `subin-1122/DangoKiller` 로 따로 있던 것을 2026년 10월 12일에 여기로 합쳤습니다. 파일만 복사해서 옮겼으므로 원본 레포의 커밋 기록은 거기 남아 있습니다.

## 시작하기

```bash
cd frontend
npm install
npm run dev
```

백엔드를 함께 띄우려면 저장소 루트에서 `docker compose up -d` 를 먼저 실행합니다. API 주소는 `http://localhost:8000/api/v1` 입니다.

## 리액트 여부는 아직 미정

`src/` 에 Vite + React + TypeScript 설정이 들어와 있지만 화면은 아직 하나도 만들지 않았습니다. 시안이 순수 HTML·CSS 라 리액트 없이 가는 선택지도 열려 있습니다. 공통 기반을 만드는 사람이 판단하고, 안 쓰기로 하면 `src/`, `package.json`, `tsconfig*.json`, `vite.config.ts`, `.oxlintrc.json` 을 그때 지웁니다.

## 문서

같은 저장소가 됐으니 사본을 두지 않습니다. 아래 원본을 바로 봅니다.

```
docs/01_planning/api-spec.md         API 명세
docs/01_planning/api-predictions.md  예측 API 명세
docs/01_planning/table-spec.md       테이블 명세
docs/01_planning/requirements.md     요구사항
docs/02_team/design.md               화면 설계
```

이 마크다운들의 원본은 구글 시트입니다. 둘이 다르면 시트가 맞습니다.

화면을 만들 때 지켜야 하는 규칙은 `frontend/AGENTS.md` 에 있습니다. 위험도·위협도·공략 점수 세 숫자를 섞어 쓰는 실수가 제일 잦으니 그것부터 읽습니다.

## 폴더

```
src/                화면과 컴포넌트
public/             favicon, 글꼴, 이미지, 영상
docs/prototype/     당고킬러-모험시안_v4.html (단일 파일 시안)
```

## 디자인 시안

`docs/prototype/당고킬러-모험시안_v4.html` 을 브라우저로 열면 전체 흐름을 볼 수 있습니다. 서버 없이 파일만 열면 됩니다. 11화면이고, 글자와 입력창과 게이지가 전부 실제 HTML·CSS 라 마크업을 그대로 가져다 쓸 수 있습니다.

시안을 만든 사람은 최병주이고, 생활습관과 검진정보 화면, 도감 상태 표시는 배수빈이 더했습니다.

## 글꼴

제목은 Black Han Sans, 본문은 Pretendard 를 씁니다. 둘 다 SIL Open Font License 입니다. 글꼴 파일을 `public/fonts/` 에 둘 때 라이선스 전문도 같은 폴더에 함께 둡니다. 번들로 배포하는 이상 각 사본에 저작권 고지와 라이선스를 넣어야 합니다.

## 여기에 두지 않는 것

국민건강영양조사 원시자료. 보안서약 대상이라 이 저장소 어디에도 올리지 않습니다.

백엔드 코드, 마이그레이션, 모델 학습 코드는 저장소 루트에 있습니다. `frontend/` 안으로 끌고 오지 않습니다.
