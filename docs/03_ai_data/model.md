# 당고킬러 모델 정의 및 B 서비스 계약

작성 기준: 2026-10-01 KST까지 확인한 Slack 합의와 지정 API 명세서의 공통 규칙·모듈 간 호출 규약. 담당: 홍서윤(B).

이 문서는 모델 입력·라벨 정의, 기여도 의미, 위협도 기준과 내부 호출 계약을 정리한다. **계약 확정과 실제 학습 검증은 별개다.** KNHANES 2022~2024 자료와 제9기 코드북을 대조해 전처리 및 탐색용 1회전을 실행했다. 결과와 검증 한계는 `experiment.md` 및 `submission-status.md`에 기록한다.

## 1. 최신 팀 결정 반영

- `sedentary_time_high`는 독립 factor로 확정됐고 비세라에 연결한다. `physical_activity_low`에 좌식 SHAP을 다시 더하지 않는다. 2024 비교 평가를 거쳐 첫 실험 설정은 당뇨에 `sitting_minutes`, 고혈압에 `dining_out_freq`를 각각 추가한다. sodium 대리변수는 팀 범위에 맞춰 고혈압에만 둔다.
- 사용자 용어는 **HP → 위협도**, **주간 데미지 → 공략 점수**다. 이에 대응하는 DB·함수는 `user_monsters.impact_score`, `weekly_progress`, `impact_source`, `monsters.default_impact_source`, `challenges.progress_value`, `refresh_impact_from_prediction()` 및 `refresh_impact_from_health_record()`다.
- 미진단자의 위협도 근거는 `contribution`, 실측 혈당 스파이크는 `measured`, 진단 질환의 전역 중요도·생활패턴 경로는 `global`이며 `user_monsters.impact_source`에 저장한다.
- B는 예측과 기여도 저장을 커밋한 뒤 D의 `refresh_impact_from_prediction(user_id, prediction_id)`를 호출한다. B가 `user_monsters`를 직접 수정하지 않는다.
- C는 건강정보 저장 뒤 D의 `refresh_impact_from_health_record(user_id, health_record_id)`를 호출한다. D가 스파이크와 진단자 global 경로를 처리한다.
- B는 `get_top_contributions(prediction_id, disease, limit)`와 `get_global_importance(disease, limit)`를 제공한다. 두 내부 함수는 배열을 반환하며 전역 중요도 배열의 각 항목에 `model_version`이 필수다.
- 진단 질환의 전역 중요도 추천과 보너스 챌린지의 `user_challenges.source_prediction_id`는 **NULL**이다. 한 질환만 진단된 사용자의 다른 미진단 질환 개인기여도 추천은 해당 예측 ID를 저장한다. 존재하지 않는 prediction을 만들거나 0을 넣지 않는다.
- 전역 중요도 원값은 factor별 `mean(|grouped SHAP|)`이며 화면용 비교 점수는 `importance / disease_global_max * 100`이다. 질환별 최대값은 `model_version`마다 고정한다.
- 개인 위협도는 factor별 양의 기여만 사용한다: `positive_shap = max(signed_SHAP, 0)`, `threat_score = clip(positive_shap / P95_reference[disease, factor, model_version] * 100, 0, 100)`. P95와 전역 최대값은 버전 고정 artifact metadata에 둔다.
- `threat_eligible`은 저장 단위보다 작은 P95와 표본이 빈약한 양의 SHAP 분포를 거른다. 현재 운영 기준은 `positive_shap_p95 >= 0.00001` 및 `positive_n >= 400`(양의 분포 상위 5%에 기대 관측치 20개 이상)이다. 수치는 임상 cutoff가 아니라 저장 정밀도·추정 가능성 기준이다. 선택 모델 1회전의 24개 질환×factor 조합은 모두 통과했다. 최종값은 [factor별 척도표](factor-scales.md)에 기록한다.
- 진단자 경로의 결합식은 `normalized_score × behavior_weight`다. 2026-10-01 Slack에서 MVP 가중치를 `behavior_weight ∈ {0,1}`로 단순화하는 안에 A가 찬성했다. 사용자별 weight는 유효한 입력이 D가 승인한 행동 조건을 만족하고 적용 가능한 챌린지가 있을 때 1, 유효한 입력이 비대상이거나 적합한 챌린지가 없을 때 0이다. 결측·모름은 건강한 행동으로 간주하지 않으며 미평가로 두고 추천하지 않는다. 수치 행동 cutoff는 D의 조건표 검토가 남아 있어 아직 런타임 값으로 확정하지 않았다.
- 질환별 경로는 독립 계산한다. 미진단 질환은 사용자 기여도 P95 점수, 진단 질환은 `normalized_score × behavior_weight`를 사용한다. 같은 factor에 두 질환 경로가 있으면 각 질환 점수를 따로 계산한 뒤 max를 선택하고, `impact_source`에는 승리한 경로(`contribution` 또는 `global`)를 기록한다. 두 경로 점수를 섞거나 평균 내지 않는다.
- `factor_key=NULL`인 챌린지는 damage 0, XP·보상만 지급한다. 수면 챌린지는 MVP에서 보류한다.

## 2. y 정의

대상은 KNHANES 2022~2024의 만 19세 이상이다. 당뇨·고혈압을 **서로 독립적인 두 이진 분류기**로 학습한다.

| 질환 | 원시 라벨 | y=1 | y=0 | 학습 제외 |
|---|---|---|---|---|
| diabetes | HE_DM_HbA1c | 코드 3 | 유효 코드 1·2 | 결측·비유효·미확인 코드 |
| hypertension | HE_HP | 코드 4 | 유효 코드 1·2·3 | 결측·비유효·미확인 코드 |

`(원시값 == 양성코드).astype(int)`만 쓰면 결측도 0이 되므로 금지한다. 먼저 질환별 유효 라벨 마스크를 적용한다. 진단·약물은 y에 이미 포함된 결과 경로이므로 해당 질환에서 진단·복약 중인 표본을 학습과 평가에서 제외한다. 당뇨는 `DE1_dg=0`, 인슐린 `DE1_31` 및 당뇨약 `DE1_32`가 각각 0 또는 8인 표본, 고혈압은 `DI1_dg=0`, 혈압약 `DI1_2`가 5 또는 8인 표본이다. 한 질환에서 제외돼도 다른 질환의 학습 대상에는 유지할 수 있다.

서비스에서는 질환별 진단·약물 이력을 분리한다. 당뇨 진단 또는 당뇨 관련 약물이 있으면 당뇨 결과만 생략하고, 고혈압은 별도로 평가한다. 고혈압 진단 또는 혈압약 복용이 있으면 고혈압 결과만 생략하고, 당뇨는 별도로 평가한다. **두 질환 모두** 진단/약물 이력이 있거나 진단 여부가 불명확할 때만 예측 대상에서 제외한다. KNHANES 훈련도 질환별로 미진단·미복약 집단을 분리해 검진 라벨 구성요소인 진단·약물 변수가 X로 새지 않게 한다.

모델 출력은 단면자료의 **현재 유병 상태와 관련된 확률 점수**이며 미래 발병 확률, 치료효과, 인과적 위험 감소량이 아니다.

## 3. X 입력 목록

아래 표의 첫 12개 열이 공통 core 입력이다. 2024 비교 평가 뒤 첫 실험 설정은 당뇨에 좌식시간, 고혈압에 외식 빈도 대리변수를 각각 추가했다. 좌식 factor는 걷기와 독립으로 확정됐다. 최신 팀 의견에 따라 채소 후보는 `LS_VEG2`(김치·장아찌 제외)로 별도 평가했고 첫 모델에서는 제외했다. 원시 코드와 변환은 `input-code-map.md` 및 `data.md`에 정리했다.

| 서비스 feature | 원시 연결 | 단위·형식 | factor_key | 채택 상태 |
|---|---|---|---|---|
| age | age | 만 나이 정수 | age | 기본 |
| sex | sex | M/F, 공식 코드 매핑 | sex | 기본 |
| bmi | HE_BMI; 서비스는 kg/(m²) | kg/m² | bmi_high | 기본 |
| waist_cm | HE_wc | cm | waist_high | 기본 |
| smoking_current | sm_presnt | 0/1 | smoking_current | 기본 |
| alcohol_frequency | BD1_11 | 코드북 확인 범주 | alcohol_frequency | 기본 |
| alcohol_amount | BD2_1 | 코드북 확인 범주 | alcohol_amount | 기본 |
| walking_days | BE3_31 | 코드 1~8에서 1을 빼 일/주 0~7 | physical_activity_low | 기본 |
| walking_minutes | BE3_32·BE3_33 | 시간×60+분, 1회 걷기 분. 0일이면 0 | physical_activity_low | 기본 |
| strength_days | BE5_1 | 코드 1~6에서 1을 뺀 0~5; 5는 5일 이상 하한 | strength_activity_low | 기본 |
| family_history_dm | HE_DMfh1~3 | 가족 중 하나라도 예=1, 전부 아니오/외동=0, 그 외 결측 | family_history_dm | 기본 |
| family_history_htn | HE_HPfh1~3 | 가족 중 하나라도 예=1, 전부 아니오/외동=0, 그 외 결측 | family_history_htn | 기본 |
| dining_out_freq | L_OUT_FQ | 코드 1~7 순서 범주; 9 결측 | sodium_behavior | 고혈압 첫 모델에 포함; 외식 빈도 대리 지표 |
| sitting_minutes | BE8_1·BE8_2 | 시간×60+분, 하루 0~1440분 | sedentary_time_high | 당뇨 첫 모델에 포함; 독립 factor |
| vegetable_frequency | LS_VEG2 | 1~9 범주형; 1=하루 3회 이상, 9=월 1회 미만; 99 결측 | vegetable_intake_low | 비교 후보만 평가; 첫 모델에서는 제외 |

키·체중은 서비스 입력과 BMI 계산에 필요하지만 BMI와 중복 입력하지 않는다(B 모델 설계안). 나이·성별·가족력은 설명용이며 챌린지와 위협도 대상이 아니다. 질환별 첫 모델은 당뇨 core 12개+좌식, 고혈압 core 12개+외식 빈도 대리변수를 사용한다. `vegetable_intake_low`는 비교 후보로만 남기며, 외식 빈도와 합쳐 소디를 산출하지 않는다. `N_NA`, `HE_UNa`, 수면 변수는 입력에서 제외한다.

기본 core 12개 및 선택된 추가 feature 어디에도 혈압·혈당·당화혈색소·진단·약물 변수를 포함하지 않는다. 정확한 특수코드와 단위 변환은 [전처리 기록](data.md)에 정리했다.

## 4. 혈압·혈당 제외 이유

혈압·공복혈당·HbA1c는 y를 정의하는 검사값이다. 이 값을 X에 넣으면 정답 판정의 구성요소를 통해 y를 맞히는 데이터 누수가 생긴다. 사용자가 검진값 없이 입력하는 간편 모드와도 맞지 않는다.

모델 입력에서 `sbp`, `dbp`, `fasting_glucose`, `hba1c` 및 대응 원시 검사값과 라벨·진단·약물 변수 전체를 차단한다. 정밀 모드의 중성지방·HDL·총콜레스테롤도 간편 입력 계약 밖이므로 제외한다. 이 수치는 별도 실측 표시·대사증후군 지표 처리에만 쓴다. 스파이크의 위협도에 혈당 SHAP을 만들어 넣지 않는다.

## 5. 기여도 계약

B 제안 기본안은 확률 공간 SHAP이다. 고정된 train background와 explainer 설정을 모델 버전에 묶는다. 각 질환에 대해 `base_value + sum(raw_shap) ≈ probability`를 검증한다. log-odds SHAP을 확률 SHAP처럼 섞지 않는다.

- 여러 raw/one-hot 열이 같은 factor에 속하면 **부호를 유지해 합산**한다. 걷기 일수·시간은 함께, 좌식은 별도다.
- `contribution`은 부호 있는 확률 단위 값이다. 0.02는 모델 설명상의 2 percentage points이며 행동을 하면 2%p 감소한다는 뜻이 아니다.
- `direction`은 양수 `increase`, 음수 또는 0 `decrease`. 0은 ENUM 제약에 따른 저장값이지 보호 효과가 아니다. 모든 지원 factor를 0 포함 저장한다. 기존 ENUM에 없는 `neutral`을 추가하지 않는다.
- `rank`는 질환 내 `abs(contribution)` 내림차순, 동률은 factor_key 오름차순으로 고정한다. 표시 상위 3개에는 수정 불가능 요인도 포함될 수 있다.
- D의 추천은 상위 3개 설명만 읽고 끝내지 않는다. 전체 기여요인 중 수정 가능, 양의 기여도, 실제 risk_condition 충족 요인을 필터링한 다음 최대 3개를 고른다. 건강한 행동을 악화시키는 추천을 하지 않는다.
- 저장은 DECIMAL(8,5)에 맞게 반올림하되 SHAP 가산성 검증은 저장 전 원정밀도로 한다. 0으로 반올림되는 행도 지원 factor 전량 보존을 위해 저장하고 rank를 부여한다.

전역 중요도 원값은 train reference에서 factor별 `mean(abs(signed_group_shap))`다. `sum(mean(abs(raw_shap)))`와 혼동하지 않는다. 화면용 정규화는 질환별 `importance / max(importance) * 100`이며, 최대값과 정규화 값은 `model_version`에 종속된다. 중요도 값과 최대값은 artifact metadata로 버전 고정한다. `importance / sum(importance)` 비율은 쓰지 않는다. D는 전역 중요도와 생활패턴을 결합해 진단자 경로를 계산하며 전역 중요도만으로 개인의 유병 확률을 만들지 않는다.

## 6. 위협도 정규화와 미확정 산식

미진단자 factor별 위협도는 아래 기준으로 계산한다. reference 집단은 선택된 질환별 모델의 2022 training 전체 eligible 표본이며, 집단·모델 버전을 함께 artifact에 고정한다. 2023 validation은 후보 비교에 쓰고 calibration 기준값에는 쓰지 않는다. 2024 비교 평가는 소디 채택 여부와 질환별 입력 변형을 정하는 데 사용했으므로, 그 feature 선택 후 2024는 독립 최종 일반화 평가로 간주할 수 없다. P95 산출에는 2024 자료를 쓰지 않는다.

1. factor의 개인 기여도에서 `positive_shap = max(signed_group_shap, 0)`을 계산한다. 음수 SHAP은 보호 방향 설명으로 남기되 위협도를 만들지 않는다. 정확히 0인 factor는 위협도 0 / `not_contributing`이며 보호 요인으로 설명하지 않는다.
2. 질환 × factor × `model_version`별 2022 training reference 집단의 positive SHAP 분포에서 `P95_reference`를 계산해 artifact metadata에 저장한다.
3. `threat_score = round(100 * clip(positive_shap / P95_reference, 0, 1))`로 0~100 변환한다. 개인별 최대값이나 다른 사용자의 최신값으로 나누지 않는다.
4. `positive_shap_p95 < 0.00001`이면 `DECIMAL(8,5)` contribution 저장 정밀도보다 작으므로, 또는 양수 SHAP 표본이 400개 미만이면 P95 위쪽 기대 관측치가 20개 미만이므로 `threat_eligible=false`로 둔다. 어느 하나라도 해당하면 위협도는 0이며 임의 floor를 나누지 않는다. 그렇지 않으면 true다. 저장 단위·reference 정의가 바뀌면 기준도 다시 확인한다.

Mapping v1의 `risk_condition`은 위험 방향을 설명한 문구이며 확정 숫자 임계값 표가 아니다. MVP `behavior_weight` 척도는 0/1로 정리했지만, BMI·허리둘레·걷기·근력·좌식의 적용 cutoff와 알코올 사용 범위는 D가 초안·팀 검토를 마쳐야 한다. 미진단 추천은 (1) 입력이 승인된 행동 조건에 해당하고, (2) 개인 grouped SHAP이 증가 방향이며, (3) 실제 제공 가능한 챌린지가 있는 경우만 허용한다. 진단자 추천은 개인 SHAP 대신 지원 factor와 승인된 행동 조건으로 0/1 weight를 만든다. 결측·모름은 비대상과 구분해 평가 불가로 처리한다. 챌린지를 수행해도 위협도는 즉시 낮아지지 않는다. 수행은 공략 점수에 기록되고, 위협도는 건강정보 재저장·재평가 때 갱신된다.

소디 factor `sodium_behavior`는 `L_OUT_FQ` 범주를 그대로 모델 입력으로 쓰며, 외식 횟수를 나트륨 mg/g으로 바꾸지 않는다. HTN 2024 비교에서는 AP/AUROC/Brier가 base보다 조금 나아졌지만, 2023 validation은 AP가 낮았고 256명 direction audit에서 범주별 평균 signed SHAP 부호가 달랐다. 그러므로 이 값은 고혈압의 실험 후보로만 유지한다. 외식 빈도 감소 챌린지를 자동 추천할 단조 임계값이나 양의 `behavior_weight`는 이 결과만으로 만들지 않는다. 방향과 코드 범위를 D·팀과 합의하기 전에는 해당 추천 weight를 산출하지 않는다.

진단자 경로는 개인 SHAP이 아니라 전역 중요도와 최신 생활패턴을 사용한다. `normalized_score`는 질환별 전역 중요도 최댓값을 100으로 둔 요인 간 상대값이지 개인 유병 확률이 아니다. 진단자 factor 점수는 `normalized_score × behavior_weight`다. MVP `behavior_weight`는 A가 찬성한 이진값이며 승인된 risk condition과 챌린지를 사용자 입력에 적용해 0/1로 정한다. D의 수치 조건이 승인되면 같은 사용자에서 조건 적용 후 점수 분포를 비교해 보정 필요성을 검토한다. `impact_source`가 바뀌는 두 산식의 변화량을 의료적 위험 감소로 해석하지 않는다. 모델·scale 버전이 바뀐 비교도 구분한다.

재예측에서 요인이 사라져도 기존 `user_monsters` 행과 봉인 등 성취는 보존한다. 지원되는 factor의 유효한 재계산 결과가 0이면 해당 위협도를 0으로 갱신하되 입력 미확인·미지원 모델 때문에 근거가 없으면 0으로 바꾸지 않는다. 최초 비흡연자의 코티니를 자동 생성하지 않는다.

## 7. 내부 함수 계약

| 함수 | 제공 → 호출 | 계약 |
|---|---|---|
| get_top_contributions(prediction_id, disease, limit) | B → D | done 예측에 저장된 기여도만 조회. `[{factor_key, contribution, direction, rank}]` 반환. signed probability 단위. limit=1~100; 추천 필터를 위해 전체 조회 가능 |
| get_global_importance(disease, limit) | B → D | 활성 모델의 고정 artifact에서 조회. 지정 시트 반환은 `[{factor_key, importance, normalized_score, rank, model_version}]`. 원값은 `mean(|grouped SHAP|)`이고, `normalized_score = 100 × importance / disease_global_max`를 B가 계산한다. 질환별 max와 결과는 `model_version`에 고정한다. max가 0이면 score는 0 |
| refresh_impact_from_prediction(user_id, prediction_id) | B → D | 예측+기여도 커밋 뒤 호출. 같은 prediction 재호출 멱등. 예측 버전 고정. B는 D 테이블 직접 쓰지 않음 |
| refresh_impact_from_health_record(user_id, health_record_id) | C → D | C 저장 뒤 1회 호출. measured/global 분기는 D 내부 |

위 반환 형식은 지정 API 명세서의 `모듈 간 호출` 탭 F8·F9 합의와 Slack에서 확인한 `normalized_score` 반환 필드를 따른다. B는 artifact에 고정된 질환별 max로 점수를 계산해 반환하고 D는 이를 최신 행동 weight와 결합한다. 개인 기여도는 요청한 prediction_id의 저장값을 읽으며 재학습 뒤 활성 모델로 다시 계산하지 않는다. 전역 중요도는 현재 활성 모델 버전을 각 반환 항목에 담는다. 제공자는 활성 artifact를 확인하고, 호출자가 캐시하면 버전 변경 시 이전 캐시를 무효화한다.

공개 HTTP 기여도 API는 별도 계층이다. 라우트는 같은 prediction_id의 저장된 메타데이터를 읽어 `success/data` 응답의 prediction_id, disease, model_version, factor_dictionary_version, contribution_unit, items를 구성한다. 내부 함수가 이 metadata 객체를 반환한다고 가정하지 않는다. 공개 응답에 수정 가능 여부를 포함할 경우 해당 예측 버전의 factor 사전에서 보강한다.

호출 실패 때문에 이미 완료된 예측을 실패로 되돌리거나 삭제하지 않는다. 위협도 갱신 재시도 작업을 남긴다. 큐 중복 전달과 이전 예측의 늦은 완료에도 D가 최신 근거 ID를 확인하고 과거 값으로 덮어쓰지 않도록 한다. 내구성 있는 outbox/재시도 저장 위치는 A·C·D와 합의할 구현 항목이다.

## 8. 검증과 남은 결정

기본·소디·좌식 validation 비교는 당뇨·고혈압 각 4개 입력 변형(base, sodium, sitting, sodium_sitting)과 seed 42·43·44, 총 24회로 수행했다. 채소 후보는 6회 추가해 총 30회 validation 탐색이다. 이어 네 변형 24개 run의 2024 평가를 수행해 당뇨는 core+sitting, 고혈압은 core+sodium을 첫 실험 입력으로 선택했다. 전체 결과와 trade-off, 2024 선택 사용 한계는 `experiment.md`에 기록한다. 선택된 모델은 seed 42로 다시 학습하고 각 질환의 전체 eligible 2022 training 표본을 SHAP calibration reference로 사용해 P95와 전역 중요도를 재계산했다. 이 산출물은 로컬 `data/`에만 있고 실험용이며 배포 승인을 의미하지 않는다.

validation에서 sitting 추가 시 평균 AP는 당뇨 +0.0024, 고혈압 +0.0021이었다. 2024 비교 평가 후 첫 모델에는 좌식을 당뇨에만 넣었다. 이는 팀의 factor 분리 결정과 외식 대리변수의 고혈압 한정 범위를 따른 실험 선택이며, 좌식시간 변화의 인과효과를 뜻하지 않는다.

진단자 경로의 `normalized_score × candidate_weight`와 개인 위협도 P95 경로는 같은 validation 사용자로 비교했다. 당시 탐색 가중치 0.25/0.5/0.75/1.0 결과는 [실험 기록](experiment.md)에 있다. 이 비교는 A가 찬성한 binary MVP weight의 사용자 행동 cutoff를 결정하지 않는다. 고정 가중치 숫자를 배포값으로 쓰지 않는다. 남은 것은 D 조건표의 행동 cutoff 검토·팀 승인, 승인된 조건별로 같은 사용자 분포를 다시 집계하는 일이다.

별도 `LS_VEG2` ablation의 vegetable global normalized score는 당뇨 21.17–24.41(rank 6), 고혈압 21.07–24.79(rank 8)였다. 2022 train reference의 positive SHAP P95는 모든 seed에서 양수였다. 다만 base 대비 validation 변화가 당뇨 AUROC −0.00018/AP +0.00239, 고혈압 AUROC −0.00115/AP −0.00729였고 Brier는 고혈압에서 +0.00009 악화됐다. 별도 factor 후보로 보존하되 공통 서비스 입력 필드와 성능을 추가 합의하기 전에는 final X에 포함하지 않는다. 수치는 배포 모델이 아닌 탐색 결과다.

## 근거

- [지정 API 명세서 — B 탭·모듈 간 호출](https://docs.google.com/spreadsheets/d/1YGAncv-rZBLBvrVFjlk7yg1kP7fabZunzYmOZz8C9OE/edit?gid=1286618417#gid=1286618417)
- [9/30 B 파트 모델·X/y·용어 요약](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790755600857999)
- [전역 중요도·개인 위협도 정규화 논의](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790744047761599?thread_ts=1790744047.761599)
- [최신 API·HP 경로 변경 9/28 13:38](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790570304697439)
- [좌식 분리 결정 9/28 11:58](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790564317593679)
- [진단자 NULL이 명시된 ERD SQL 첨부](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790239227750419)
- [기획서 v9·요구사항 v8 첨부](https://2026-ndc9438.slack.com/archives/C0C3FK3311C/p1790150890169639)
- [B 모델 연결 확인 요청](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790154039259709)
- [factor_key v0](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790153877584479)
