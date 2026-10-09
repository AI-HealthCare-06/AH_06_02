from enum import StrEnum

from tortoise import fields, models


class PredictionStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class RiskGrade(StrEnum):
    LOW = "low"
    CAUTION = "caution"
    HIGH = "high"


class Disease(StrEnum):
    DIABETES = "diabetes"
    HYPERTENSION = "hypertension"


class ContributionDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"


class Prediction(models.Model):
    """위험도 예측 결과. 테이블 명세서 predictions 15컬럼 기준이다.

    홍서윤(B) 이탈로 2026.10.03부터 A(배수빈)가 맡는다.
    """

    id = fields.BigIntField(primary_key=True)
    # Cross-part table IDs stay scalar here. The DB DDL owns the FK constraints,
    # and this module does not import C/D models directly.
    user_id = fields.BigIntField()
    health_record_id = fields.BigIntField(description="어떤 입력으로 예측했는지")

    job_id = fields.CharField(max_length=64, unique=True, description="비동기 작업 식별자 (REQ-PRED-002)")
    status = fields.CharEnumField(
        enum_type=PredictionStatus,
        default=PredictionStatus.PENDING,
        description="추론 상태 (NFR-REL-001)",
    )

    # 확률은 0~1로 저장하고 화면에서 %로 바꾼다
    dm_probability = fields.DecimalField(max_digits=5, decimal_places=4, null=True, description="당뇨 위험 확률")
    dm_grade = fields.CharEnumField(enum_type=RiskGrade, null=True, description="3단계 등급 (REQ-PRED-004)")
    htn_probability = fields.DecimalField(max_digits=5, decimal_places=4, null=True, description="고혈압 위험 확률")
    htn_grade = fields.CharEnumField(enum_type=RiskGrade, null=True)

    metabolic_count = fields.SmallIntField(null=True, description="대사증후군 해당 지표 수 0~5 (REQ-PRED-009)")
    model_version = fields.CharField(
        max_length=64,
        description="모델 버전 고정 (NFR-MODL-002). 실제 값 예시 knhanes-ix-hypertension-base_sodium-s42 는 39자",
    )

    input_snapshot: dict[str, object] | None = fields.JSONField(
        null=True, description="예측 당시 모델 입력 스냅샷. 전처리 전 canonical 값·단위·결측 여부 (REQ-PRED-003)"
    )

    failure: dict[str, object] | None = fields.JSONField(
        null=True,
        description="작업 실패 사유 { code, message, retryable }. PRED-02 응답의 failure 로 그대로 나간다 (NFR-REL-001)",
    )

    predicted_at = fields.DatetimeField(null=True, description="추론 완료 시각")
    created_at = fields.DatetimeField(auto_now_add=True, description="요청 접수 시각")
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "predictions"
        indexes = (("user_id", "created_at"),)


class PredictionContribution(models.Model):
    """위험요인 기여도. 테이블 명세서 prediction_contributions 8컬럼 기준이다.

    예측 1건당 질환 2종 × 요인 N개가 쌓인다.
    """

    id = fields.BigIntField(primary_key=True)
    prediction_id = fields.BigIntField()

    disease = fields.CharEnumField(enum_type=Disease, description="기여도를 산출한 질환 모델")
    factor_key = fields.CharField(max_length=50, description="공통 요인 코드. Feature Dictionary v0 13개")

    contribution = fields.DecimalField(
        max_digits=8,
        decimal_places=5,
        description="정규화 전 signed grouped SHAP. 0 포함 지원 factor 전량 저장",
    )
    direction = fields.CharEnumField(
        enum_type=ContributionDirection,
        description="contribution > 0이면 increase, 0 이하면 decrease",
    )
    rank = fields.SmallIntField(description="질환별 절대 기여도 내림차순. Top3만 화면에 표시 (REQ-PRED-005)")

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "prediction_contributions"
        indexes = (("prediction_id", "disease", "rank"),)
