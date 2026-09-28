# 당고킬러 모델 정의 및 B 서비스 계약

작성 기준: 2026-09-28 13:44 KST까지 확인한 팀 논의와 사용자가 지정한 API 명세서의 공통 규칙·모듈 간 호출 규약. 담당: 홍서윤(B).

이 문서는 9/29 제출용 모델 입력·라벨 정의, 기여도 의미와 내부 호출 계약을 정한다. **입력·출력 계약과 실제 학습 검증은 별개다.** 현재 저장소에는 학습 데이터와 학습된 모델이 없으며 성능·SHAP 안정성·HP 기준값을 아직 측정하지 않았다. 수치 예시는 모두 계약 설명용이다.

## 1. 최신 팀 결정 반영

- `sedentary_time_high`는 독립 factor로 확정됐고 비세라에 연결한다. `physical_activity_low`에 좌식 SHAP을 다시 더하지 않는다. `sitting_minutes`의 실제 모델 채택은 1회전 검증 후 확정한다.
- 미진단자의 HP 출처는 `contribution`, 실측 혈당의 스파이크는 `measured`, 진단자의 전역 중요도 기반 점수는 `global`이다. 개인별 출처는 `user_monsters.hp_source`에 둔다.
- B는 예측과 기여도 저장을 커밋한 뒤 D의 `refresh_hp_from_prediction(user_id, prediction_id)`를 호출한다. B가 `user_monsters`를 직접 수정하지 않는다.
- C는 건강정보 저장 뒤 D의 `refresh_hp_from_health_record(user_id, health_record_id)`를 호출한다. D가 스파이크와 진단자 global 경로를 처리한다.
- B는 `get_top_contributions(prediction_id, disease, limit)`와 `get_global_importance(disease, limit)`를 제공한다. 두 내부 함수는 배열을 반환하며 전역 중요도 배열의 각 항목에 `model_version`이 필수다.
- 진단자의 `user_challenges.source_prediction_id`는 **NULL**이다. 존재하지 않는 prediction을 만들거나 0을 넣지 않는다. 원본 ERD SQL과 진단자 예측 금지 규칙이 일치한다.
- `factor_key=NULL`인 챌린지는 damage 0, XP·보상만 지급한다. 수면 챌린지는 MVP에서 보류한다.

## 2. y 정의

대상은 KNHANES 2022~2024의 만 19세 이상이다. 당뇨·고혈압을 **서로 독립적인 두 이진 분류기**로 학습한다.

| 질환 | 원시 라벨 | y=1 | y=0 | 학습 제외 |
|---|---|---|---|---|
| diabetes | HE_DM_HbA1c | 코드 3 | 유효 코드 1·2 | 결측·비유효·미확인 코드 |
| hypertension | HE_HP | 코드 4 | 유효 코드 1·2·3 | 결측·비유효·미확인 코드 |

`(원시값 == 양성코드).astype(int)`만 쓰면 결측도 0이 되므로 금지한다. 먼저 질환별 유효 라벨 마스크를 적용한다. 한 질환 라벨만 없는 경우 다른 질환의 학습 대상에서는 유지할 수 있다. 의사 진단 변수 `DE1_dg`, `DI1_dg`를 y로 대체하지 않는다. 원시 분류값의 검사·약물 포함 세부 정의는 해당 연도 공식 변수설명서와 대조한다.

서비스에서는 `dm_diagnosed`, `htn_diagnosed`, `dm_medication`, `htn_medication` 중 하나라도 참이면 두 질환 위험도 예측을 제공하지 않는다. 진단 이력이 미확인인 경우에도 임의로 미진단자로 간주하지 않는다. 학습 집단 전체와 서비스의 미진단 대상 집단 차이는 별도 평가 대상이다.

모델 출력은 단면자료의 **현재 유병 상태와 관련된 확률 점수**이며 미래 발병 확률, 치료효과, 인과적 위험 감소량이 아니다.

## 3. X 입력 목록

아래가 B의 서비스 입력 계약이다. 10개 설문 항목은 10개 모델 열을 의미하지 않는다. 기본안은 13개 입력 열이며 좌식 후보를 포함하면 14개 열, 13개 factor다. 모든 수치는 원시 코드를 그대로 쓰기 전에 `data.md`의 검증을 거친다.

| 서비스 feature | 원시 연결 | 단위·형식 | factor_key | 채택 상태 |
|---|---|---|---|---|
| age | age | 만 나이 정수 | age | 기본 |
| sex | sex | M/F, 공식 코드 매핑 | sex | 기본 |
| bmi | HE_BMI; 서비스는 kg/(m²) | kg/m² | bmi_high | 기본 |
| waist_cm | HE_wc | cm | waist_high | 기본 |
| smoking_current | sm_presnt | 0/1 | smoking_current | 기본 |
| alcohol_frequency | BD1_11 | 코드북 확인 범주 | alcohol_frequency | 기본 |
| alcohol_amount | BD2_1 | 코드북 확인 범주 | alcohol_amount | 기본 |
| walking_days | BE3_31 | 일/주 0~7 | physical_activity_low | 기본 |
| walking_minutes | BE3_32·BE3_33 | 1회 분, 시간·분 합성 검증 | physical_activity_low | 기본 |
| strength_days | BE5_1 | 일/주, 코드값과 실제 일수 구별 | strength_activity_low | 기본 |
| family_history_dm | HE_DMfh1~3 | 0/1/unknown | family_history_dm | 기본 |
| family_history_htn | HE_HPfh1~3 | 0/1/unknown | family_history_htn | 기본 |
| dining_out_freq | L_OUT_FQ | 범주 1~7, 낮은 코드가 잦은 외식 | sodium_behavior | 기본·안정성 검증 필요 |
| sitting_minutes | BE8_1 및 해당 연도 분 변수 확인 | 분/일 0~1440 | sedentary_time_high | 독립 factor 확정·feature 검증 대기 |

키·체중은 서비스 입력과 BMI 계산에 필요하지만 기본 모델에서는 BMI와 중복 입력하지 않는다(B 모델 설계안). 나이·성별·가족력은 설명용이며 챌린지와 HP 대상이 아니다. `vegetable_intake_low`와 `LS_VEG` 계열은 후보이며 3개년 공통성·서비스 입력 존재·실험 결과를 확인하기 전 입력 목록에 추가하지 않는다. `N_NA`, `HE_UNa`, 수면 변수는 입력에서 제외한다.

**단위 확인이 필요한 부분:** 팀 문서는 BE8_1을 `sitting_minutes`로 연결하지만 원시값이 시간인지 분인지 아직 검증하지 못했다. 그대로 분으로 복사하지 않는다. 걷기 시간·근력 범주도 동일하게 공식 코드북 확인이 필요하다. 이 부분이 확인되기 전 raw→service 전처리 확정 또는 실제 학습 완료로 표시하지 않는다.

## 4. 혈압·혈당 제외 이유

혈압·공복혈당·HbA1c는 y를 정의하는 검사값이다. 이 값을 X에 넣으면 정답 판정의 구성요소를 통해 y를 맞히는 데이터 누수가 생긴다. 사용자가 검진값 없이 입력하는 간편 모드와도 맞지 않는다.

모델 입력에서 `sbp`, `dbp`, `fasting_glucose`, `hba1c` 및 대응 원시 검사값과 라벨·진단·약물 변수 전체를 차단한다. 정밀 모드의 중성지방·HDL·총콜레스테롤도 간편 입력 계약 밖이므로 제외한다. 이 수치는 별도 실측 표시·대사증후군 지표 처리에만 쓴다. 스파이크의 HP에 혈당 SHAP을 만들어 넣지 않는다.

## 5. 기여도 계약

B 제안 기본안은 확률 공간 SHAP이다. 고정된 train background와 explainer 설정을 모델 버전에 묶는다. 각 질환에 대해 `base_value + sum(raw_shap) ≈ probability`를 검증한다. log-odds SHAP을 확률 SHAP처럼 섞지 않는다.

- 여러 raw/one-hot 열이 같은 factor에 속하면 **부호를 유지해 합산**한다. 걷기 일수·시간은 함께, 좌식은 별도다.
- `contribution`은 부호 있는 확률 단위 값이다. 0.02는 모델 설명상의 2 percentage points이며 행동을 하면 2%p 감소한다는 뜻이 아니다.
- `direction`은 양수 `increase`, 음수 `decrease`. 수치오차 `abs(value)<1e-8`은 0으로 정리하고 설명 목록에서 제외한다. 기존 ENUM에 없는 `neutral`을 추가하지 않는다.
- `rank`는 질환 내 `abs(contribution)` 내림차순, 동률은 factor_key 오름차순으로 고정한다. 표시 상위 3개에는 수정 불가능 요인도 포함될 수 있다.
- D의 추천은 상위 3개 설명만 읽고 끝내지 않는다. 전체 기여요인 중 수정 가능, 양의 기여도, 실제 risk_condition 충족 요인을 필터링한 다음 최대 3개를 고른다. 건강한 행동을 악화시키는 추천을 하지 않는다.
- 저장은 DECIMAL(8,5)에 맞게 반올림하되 SHAP 가산성 검증은 저장 전 원정밀도로 한다. 0으로 반올림되는 행은 표시하지 않는다. rank는 저장·표시 규칙을 적용한 뒤 부여한다.

전역 중요도는 train 기준 factor별 `mean(abs(signed_group_shap))`다. `sum(mean(abs(raw_shap)))`와 혼동하지 않는다. 모든 factor의 중요도 합을 분모로 하는 `normalized_importance`와 수정 가능 여부는 모델 artifact에 보관한다. 공식 내부 반환에는 7절의 네 필드만 포함한다. D는 factor 사전의 수정 가능 여부와 생활패턴을 결합한다. 전역 중요도만으로 개인 위험 확률을 만들어서는 안 된다.

## 6. HP 정규화 권고안

아래는 **B 제안이며 팀 승인·train 기준값 산출 대기**다. 요청 시점 다른 사용자의 현재 값으로 min-max를 계산하지 않는다.

1. 질환 d·캐릭터 m별로 연결된 수정 가능 factor의 `max(contribution,0)`을 합쳐 `score[d,m]`을 만든다. 스파이크는 실측이므로 제외한다.
2. train에서 동일 계산한 score의 양수 값 95백분위수를 `scale[d,m]`로 고정한다.
3. `hp[d,m] = round(100 * clip(score[d,m]/scale[d,m],0,1))`.
4. 공통 캐릭터는 질환별 정규화 후 `max(hp[diabetes,m], hp[hypertension,m])`를 사용한다. 확률 공간이 같아도 질환별 분포가 달라 원 SHAP을 그냥 합치지 않는다.
5. scale이 없거나 양수 표본이 없으면 0 HP를 만들지 않고 미산출로 반환한다. 결측을 건강함으로 해석하지 않는다.

HP 0~39 안정, 40~69 경계, 70~100 분노로 경계 중복을 없앤다(B 제안). 봉인은 별도 D 판정이며 `HP<40`만으로 봉인하지 않는다. 최신 논의의 '28일 중 factor 성공일 20일 이상'은 팀 최종 합의 대기다.

진단자 global 점수는 개인 SHAP과 다른 점수다. D가 전역 중요도와 생활패턴으로 계산한 `factor_score`의 단위·0~100 변환은 별도 확정해야 한다. `normalized_importance*100`을 개인 HP라고 쓰지 않는다. `hp_source`가 바뀌는 두 점수의 변화량을 위험 감소로 비교하지 않는다. 모델/scale 버전이 바뀐 비교도 구분한다.

재예측에서 요인이 사라지면 기존 user_monsters 행·seal_count 등 성취는 보존하는 안을 권고한다. 유효한 재계산 결과가 0이면 HP 0을 반영하되 입력 미확인·미지원 모델 때문에 요인이 없으면 0으로 바꾸지 않는다. 최초 비흡연자의 코티니를 자동 생성하지 않는다.

## 7. 내부 함수 계약

| 함수 | 제공 → 호출 | 계약 |
|---|---|---|
| get_top_contributions(prediction_id, disease, limit) | B → D | done 예측에 저장된 기여도만 조회. `[{factor_key, contribution, direction, rank}]` 반환. signed probability 단위. limit=1~100; 추천 필터를 위해 전체 조회 가능 |
| get_global_importance(disease, limit) | B → D | 활성 모델의 고정 artifact에서 조회. `[{factor_key, importance, rank, model_version}]` 반환. 질환·모델 버전·limit별 캐시 |
| refresh_hp_from_prediction(user_id, prediction_id) | D → B | 예측+기여도 커밋 뒤 호출. 같은 prediction 재호출 멱등. 예측 버전 고정. B는 D 테이블 직접 쓰지 않음 |
| refresh_hp_from_health_record(user_id, health_record_id) | D → C | C 저장 뒤 1회 호출. measured/global 분기는 D 내부 |

위 반환 형식은 지정 API 명세서의 `모듈 간 호출` 탭 F8·F9를 따른다. 개인 기여도는 요청한 prediction_id의 저장된 값을 읽으며 재학습 뒤에도 활성 모델로 다시 계산하지 않는다. 전역 중요도는 현재 활성 모델의 버전을 각 반환 항목에 담는다. 제공자는 조회마다 활성 artifact를 확인하고, 호출자가 캐시하는 경우 활성 버전 변경 시 이전 캐시를 무효화한다. 모델 교체 감지·캐시 저장소 연결 자체는 후속 구현이다.

공개 HTTP 기여도 API는 별도 계층이다. 라우트는 같은 prediction_id의 저장된 메타데이터를 읽어 `success/data` 응답의 prediction_id, disease, model_version, factor_dictionary_version, contribution_unit, items를 구성한다. 내부 함수가 이 metadata 객체를 반환한다고 가정하지 않는다. 공개 응답에 수정 가능 여부를 포함할 경우 해당 예측 버전의 factor 사전에서 보강한다.

호출 실패 때문에 이미 완료된 예측을 실패로 되돌리거나 삭제하지 않는다. HP 갱신 재시도 작업을 남긴다. 큐 중복 전달과 이전 예측의 늦은 완료에도 D가 최신 근거 ID를 확인하고 과거 값으로 덮어쓰지 않도록 한다. 내구성 있는 outbox/재시도 저장 위치는 A·C·D와 합의할 구현 항목이다.

## 8. 검증과 미완료 항목

실제 1회전 실행·성능·기여도 수치는 아직 없다. `scripts/model/run_baseline.py`는 코드북에 맞게 준비된 canonical CSV를 받아 시간 분할 실험과 좌식/채소 ablation을 수행하도록 준비한다. 실행 전 `data.md`의 단위·특수코드 검증과 `experiment.md`의 조건을 충족해야 한다.

좌식 factor 구조는 유지하며 실패한 feature를 채택했다고 보고하지 않는다. `vegetable_intake_low`는 미채택 상태를 유지한다. 소디 fallback은 불안정성이 확인되었을 때 별도 버전·HP 출처 규칙 합의 후 적용한다.

## 근거

- [지정 API 명세서 — 공통 규칙·모듈 간 호출 F8·F9](https://docs.google.com/spreadsheets/d/1KZMhGHa7s2y3XSPKfA2rcTeJgTsUVi7c/edit?gid=1571297883#gid=1571297883)
- [최신 API·HP 경로 변경 9/28 13:38](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790570304697439)
- [좌식 분리 결정 9/28 11:58](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790564317593679)
- [진단자 NULL이 명시된 ERD SQL 첨부](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790239227750419)
- [기획서 v9·요구사항 v8 첨부](https://2026-ndc9438.slack.com/archives/C0C3FK3311C/p1790150890169639)
- [B 모델 연결 확인 요청](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790154039259709)
- [factor_key v0](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790153877584479)
