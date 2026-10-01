# 예측 모델 입력·정답 정의

담당: B · 홍서윤. 자세한 전처리 근거와 서비스 계약은 [모델 계약](03_ai_data/model.md), 원시 변수 처리표는 [KNHANES 입력 코드표](03_ai_data/input-code-map.md)를 따른다.

## X: 첫 학습 입력

| 입력 | 형식·단위 | KNHANES 원 변수 | 설명 요인 |
|---|---|---|---|
| age | 만 나이(년) | `age` | `age` |
| sex | M/F | `sex` | `sex` |
| bmi | kg/m² | `HE_BMI` | `bmi_high` |
| waist_cm | cm | `HE_wc` | `waist_high` |
| smoking_current | 0/1 | `sm_presnt` | `smoking_current` |
| alcohol_frequency | 1~6 범주 | `BD1_11` | `alcohol_frequency` |
| alcohol_amount | 0~5 범주 | `BD2_1` | `alcohol_amount` |
| walking_days | 0~7일/주 | `BE3_31`을 0부터 시작하도록 변환 | `physical_activity_low` |
| walking_minutes | 분/회 | `BE3_32`, `BE3_33` | `physical_activity_low` |
| strength_days | 0~5일/주(5는 5일 이상) | `BE5_1`을 변환 | `strength_activity_low` |
| family_history_dm | 0/1 | `HE_DMfh1~3` | `family_history_dm` |
| family_history_htn | 0/1 | `HE_HPfh1~3` | `family_history_htn` |

첫 비교 실험은 위 12개에 `sitting_minutes`를 별도 입력으로 더한 경우와 뺀 경우를 비교했다. `sitting_minutes`는 하루 좌식 시간(분, 0~1440)이며 SHAP은 `sedentary_time_high`에 따로 합산한다. 걷기 SHAP과 합치지 않는다. 이 이름만으로 고정 고위험 분기값을 뜻하지 않으며 임계값은 별도 확정이 필요하다.

혈압, 공복혈당, HbA1c, 진단력 및 해당 질환 약물은 X에서 제외한다. 당뇨와 고혈압 y를 정하는 검사·진단 구성요소가 X에도 들어가면 정답 누수가 발생하고, 사용자가 검진 결과를 입력하지 않는 간편 입력 흐름과도 맞지 않기 때문이다.

## y: 질환별 이진 라벨

성인 만 19세 이상을 대상으로 질환마다 별도 분류기를 학습한다. KNHANES 유효 라벨이 없으면 해당 질환 학습·평가에서 제외한다.

| 모델 | KNHANES 라벨 | y=1 | y=0 |
|---|---|---|---|
| 당뇨 | `HE_DM_HbA1c` | 3 | 1 또는 2 |
| 고혈압 | `HE_HP` | 4 | 1, 2 또는 3 |

해당 질환의 기존 진단·복약자는 그 질환 모델에서 제외한다. 당뇨 모델은 `DE1_dg=0`, `DE1_31`과 `DE1_32`가 각각 0 또는 8인 경우, 고혈압 모델은 `DI1_dg=0`, `DI1_2`가 5 또는 8인 경우만 eligible하다. 한 질환에서 제외되어도 다른 질환 학습에는 남을 수 있다.

모델은 단면자료에서 현재 유병 상태와 관련된 확률 점수를 추정한다. 미래 발병, 인과효과, 개인의 임상 진단을 뜻하지 않는다.
