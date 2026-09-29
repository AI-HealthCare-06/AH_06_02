# 당고킬러 Design Guide v0

> 기준: Figma `Hi-Fi v1 · 대표 4화면 · 2026-09-29`  
> 대상 화면: 03 현재 위험도 / 04 위험요인 도감 / 05 챌린지 추천 / 07 수행 인증  
> 목적: 팀원이 각자 프론트엔드를 구현하더라도 같은 시각 규칙과 UX 언어를 유지하기 위한 공통 기준
>
> 시각적 Source of Truth는 Figma `Hi-Fi v1`이다. 이 문서는 Figma에서 직접 드러나지 않는 의미·상태·구현 규칙을 보완한다. Figma와 본 문서가 충돌하면 임의 판단하지 않고 팀에 확인한다.

---

## 1. 기본 원칙

1. 건강정보가 게임 요소보다 우선한다.
2. 위험도(질환 예측 확률), 위협도, 공략 점수는 서로 다른 값으로 명확히 구분한다.
3. 위험을 과도하게 자극적으로 표현하지 않는다.
4. 게임 요소는 접근성을 높이는 보조 수단으로 사용한다.
5. 의료 고지와 안전 안내는 눈에 띄되 공포감을 주지 않는 톤을 사용한다.
6. 동일 의미에는 동일한 색·형태·간격 규칙을 사용한다.

---

## 2. Typography

- 기본 폰트: `Noto Sans KR`
- 화면 제목: Bold / 24px
- 카드 제목: Bold / 15–18px
- 본문: Regular / 12–14px
- 보조 설명: Regular / 11–12px
- Badge / Pill: Medium / 11px
- 숫자 강조:
  - 주요 확률: Bold / 28px
  - 타이머: Bold / 52px

### 사용 규칙
- 제목은 한 화면에서 1개를 원칙으로 한다.
- 숫자는 단위를 함께 표시한다.
- `위협도 72`, `공략 점수 40`, `고혈압 위험 31%`처럼 이름을 생략하지 않는다.

---

## 3. Color

### Base
- Canvas: `#F1F5EF`
- Screen background: `#F9F9F6`
- Surface/Card: `#FFFFFF`
- Primary text: `#1F2B3A`
- Secondary text: `#64707A`
- Border: `#E0E3DE`

### Semantic
- Primary / CTA: Deep Navy `#1F2B3A`
- Game / Accent: Purple fill `#705EE0` / text `#5542B5` / soft `#F0ECFE`
- Success / Completion: Mint fill `#2E7A57` / text `#235F40` / soft `#E6F7ED`
- Caution / Behavioral factor: Amber fill `#B87826` / text `#7A4A12` / soft `#FBF0D4`
- Elevated risk / Attention: Coral fill `#C7544D` / text `#9E342F` / soft `#FDE8E3`
- Informational / Prediction: Blue fill `#5C85DB` / text `#315C9E` / soft `#E8F0FE`

### 캐릭터 색상
캐릭터 고유색은 **아이콘·아바타·테두리 등 식별 요소에만 사용**한다. 수치·게이지·상태 텍스트에는 semantic color를 사용한다.
- 스파이크 `#F59E0B`
- 알데 `#A855F7`
- 코티니 `#64748B`
- 비세라 `#E11D48`
- 소디 `#0891B2`

### 의미 고정
- Coral: 높은 위협·주의가 필요한 값
- Purple: 공략 점수·게임 진행. 텍스트는 Purple text token `#5542B5`를 사용한다.
- Mint: 완료·안전 확인·성공
- Amber: 의료 고지·생활행동 주의
- Blue: 예측 정보·정보성 상태

### 대비 규칙
- Secondary text `#64707A`는 11px 이하 보조 설명에서 장문 사용을 피하고, 핵심 정보에는 Primary text를 사용한다.
- 흰 배경의 본문/핵심 텍스트에는 fill용 색상보다 진한 text token을 사용한다.
- 특히 의료 고지, 예측 수치, 경고·성공 라벨은 text token을 우선한다.
- 색만으로 상태를 전달하지 않고 반드시 텍스트 라벨을 함께 사용한다.

---

## 4. Spacing & Radius

### Spacing scale
`8 / 12 / 16 / 20 / 24`

권장:
- 같은 그룹 내부: 8–12
- 카드 내부: 14–16
- 카드 간 간격: 14–16
- 화면 좌우 padding: 20
- 주요 섹션 간: 20–24

### Radius
- Button: 14px
- Card: 18px
- Screen: 28px
- Pill/Badge: full rounded

---

## 5. Button

### Primary
- Deep navy background
- White text
- Bold 14px
- 높이 약 44–48px
- 주요 진행 CTA에만 사용

예:
- `내 위험요인 보기`
- `약점 공략하러 가기`
- `선택한 2개 시작하기`
- `타이머 시작`

### Secondary
- Neutral light gray background
- Deep navy text

예:
- `이 추천은 나와 맞지 않아요`
- `오늘 기록 보기`

한 화면에서 Primary CTA는 원칙적으로 1개만 둔다.

---

## 6. Card

- Surface: white
- Border: 1px light gray
- Radius: 18px
- Padding: 14–16px
- 카드 내부 정보는 제목 → 핵심 값 → 설명 순서

상태 카드는 semantic background를 사용할 수 있다.
- Success: Mint soft
- Warning: Amber soft
- Prediction: Blue soft
- Game: Purple soft

---

## 7. 위협도 / 공략 점수

### 현재 위협도
- 내부 척도: 0–100
- 재예측/재측정 시 갱신
- 화면에서는 분모를 표시하지 않는다.
- Coral text token `#9E342F` 중심 표현
- 예: `위협도 72`

### 주간 공략 점수
- 주간 목표: 100
- 월요일 00:00 KST 초기화
- 100 초과 시 계속 누적
- 100 미달 불이익 없음
- Purple text token `#5542B5` 사용
- 퍼센트 기호 사용 금지
- 예: `이번 주 공략 점수 40 / 100`

### 금지
- 위협도와 공략 점수를 동일 막대에 겹쳐 표현하지 않는다.
- `공략 점수 40 → 위협도 -40`처럼 직접 차감 관계로 보이게 하지 않는다.

재측정 시:
`위협도 78 / 공략 40 → 재측정 → 새 위협도 56`
처럼 별도 전환으로 표현한다.

---

## 8. 질환 예측 화면

03 현재 위험도 화면은 B/C 구현의 시각 기준이 된다.

반드시 포함:
- 질환별 상태
- 미진단 질환의 예측 확률
- 진단 질환의 `진단 관리 중` 상태
- 주요 기여요인
- 의료 고지

### 부분 진단자
- 당뇨만 진단: 당뇨는 `진단 관리 중`, 고혈압만 예측
- 고혈압만 진단: 고혈압은 `진단 관리 중`, 당뇨만 예측
- 둘 다 진단: 예측 확률 화면 생략
- 둘 다 미진단: 두 질환 모두 예측

---

## 9. 챌린지 카드

카드 기본 정보:
- 챌린지 제목
- 난이도
- 인증 방식
- 간단한 추천 이유
- 지급 공략 점수

난이도 Badge:
- `쉬움` (`easy`)
- `보통` (`normal`)
- `도전` (`challenge`)

인증 방식 Badge:
- `MANUAL`
- `PHOTO`
- `TIMER`
- `VALUE`
- `TIME`
- `SYSTEM`

`해당 없음`은 실패나 거절과 다른 개념이므로 시각적으로 중립적으로 표현한다.

---

## 10. 인증 화면

07 수행 인증 기준:
- 현재 챌린지명
- 오늘 목표
- 이번 주 진행 상황
- 인증 방식
- 완료 시 보상
- Primary CTA

### TIMER
- 남은 시간을 가장 크게 표시
- 중간 종료는 완료로 인정하지 않음

### PHOTO
- AI 판정 없음
- 수행 증빙 업로드
- 비공개 저장
- `evidence_url`만 로그에 연결

---

## 11. 의료·안전 안내

### 의료 고지
- Amber soft background
- `의료 고지` 라벨
- 진단이 아니라는 사실을 명확히 표시

### 운동 전 안전 확인
- 운동형 챌린지 시작 직전에 표시
- 안전 확인 답변은 저장하지 않음
- `safety_confirmed=true`는 시작 시점 서버 검증용

---

## 12. 화면별 구현 기준

### 03 현재 위험도
핵심: 확률 / 기여요인 / 의료 고지

### 04 위험요인 도감
핵심: 캐릭터 / 현재 위협도 / 이번 주 공략 점수 / 봉인 상태

봉인 관련 API 응답값 `state`, `sealed_at`, `seal_count`를 카드에서 표현한다.

### 05 챌린지 추천
핵심: 추천 카드 / 난이도 / 인증 방식 / 선택 / 해당 없음

### 07 수행 인증
핵심: 수행 상태 / 인증 / 공략 점수 / XP

### 08 수행 완료
별도 디자인 페이지보다 07의 `completed state` variant로 구현

---

## 13. 공통 상태 규칙

### Loading
- 비동기 예측은 `queued` / `running` 상태를 구분한다.
- 진행 문구 + spinner/skeleton 등 명확한 대기 표현을 사용한다.
- 폴링 기준: 2초 간격 / 최대 20회.
- 시간 초과 시 동일 작업 상태를 다시 확인할 수 있게 하고 자동 중복 제출하지 않는다.

### Error
- 내부 에러 코드 원문을 사용자에게 그대로 노출하지 않는다.
- 사용자가 해결 가능한 설명 + 재시도 또는 이전 화면 CTA를 함께 제공한다.
- validation / network / failed 상태를 구분하되 화면 톤은 일관되게 유지한다.

### Empty
- 오류가 아니라 정상적인 ‘없음’ 상태를 구분한다.
- 예: 아직 챌린지를 시작하지 않음, 캐릭터 미등장, 기록 없음.
- 설명 + 다음 행동 CTA를 제공한다.

---

## 14. 구현 시 금지사항

- 화면마다 다른 폰트 사용
- 임의의 primary color 추가
- 위협도/공략 점수를 동일 막대에 겹쳐 표현
- 건강 위험을 게임 보상처럼 과장
- 사진 인증을 AI 분석 결과처럼 표현
- 임의의 medical claim 추가
- 버튼, radius, spacing을 화면마다 다르게 적용

---

## 15. 앞으로 확정할 항목

아래는 현재 v0에서 고정하지 않는다.

- 캐릭터 최종 일러스트 스타일
- 전체 14화면의 세부 Hi-Fi
- Dark mode
- animation duration/easing
- behavior_weight 상세 계산식
- 소디 최종 위협도 산출 방식

위 항목이 바뀌더라도 본 문서의 공통 시각 규칙은 유지하고 필요한 항목만 갱신한다.
