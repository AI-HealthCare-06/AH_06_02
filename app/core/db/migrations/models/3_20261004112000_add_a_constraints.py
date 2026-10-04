from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """A 파트 제약 조건. aerich가 모델에서 만들지 못하는 것만 직접 쓴다.

    1. user_monsters (id, user_id) 유니크
       공략 주기가 같은 사용자 소유의 캐릭터만 대상으로 삼도록 복합 FK를 걸기 위한 선행 조건이다.
       복합 FK 자체는 user_attack_cycles 테이블이 생긴 뒤에 추가한다.
    2. A 소유 테이블의 FK
       predictions, prediction_contributions. 나머지 FK는 아래 주석 참고.
    """
    return """
        ALTER TABLE `user_monsters`
            ADD UNIQUE KEY `uq_um_id_user` (`id`, `user_id`);
        ALTER TABLE `predictions`
            ADD CONSTRAINT `fk_pred_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);
        ALTER TABLE `prediction_contributions`
            ADD CONSTRAINT `fk_pc_pred` FOREIGN KEY (`prediction_id`) REFERENCES `predictions` (`id`);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `prediction_contributions` DROP FOREIGN KEY `fk_pc_pred`;
        ALTER TABLE `predictions` DROP FOREIGN KEY `fk_pred_user`;
        ALTER TABLE `user_monsters` DROP INDEX `uq_um_id_user`;"""


# ---------------------------------------------------------------------------
# user_attack_cycles 테이블이 생긴 뒤에 이어서 적용할 것 (docs/erd.sql 기준)
#
#   ALTER TABLE `user_attack_cycles`
#       ADD COLUMN `active_user_id` BIGINT
#           GENERATED ALWAYS AS (IF(`status` = 'active', `user_id`, NULL)) STORED,
#       ADD UNIQUE KEY `uq_uac_active` (`active_user_id`);
#
#   ALTER TABLE `user_attack_cycles`
#       ADD CONSTRAINT `fk_uac_target`
#           FOREIGN KEY (`target_user_monster_id`, `user_id`)
#           REFERENCES `user_monsters` (`id`, `user_id`);
#
# 아직 테이블이 없어 걸지 못한 나머지 FK도 같이 남긴다.
#   health_records.user_id, predictions.health_record_id,
#   user_monsters.last_prediction_id, user_monsters.last_health_record_id,
#   user_challenges.*, challenge_logs.user_challenge_id,
#   challenge_recommendations.*, user_rewards.*,
#   user_challenge_occurrences.*
# ---------------------------------------------------------------------------


MODELS_STATE = (
    "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"
)
