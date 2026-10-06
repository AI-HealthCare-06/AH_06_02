from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """aerich가 모델에서 만들지 못하는 제약만 직접 쓴다. 기준은 docs/01_planning/erd.sql 이다.

    1. user_attack_cycles.active_user_id 생성 컬럼과 uq_uac_active
       status가 active일 때만 user_id를 담는다. NULL끼리는 충돌하지 않아 사용자당 active 주기가 하나로 강제된다.
    2. fk_uac_target 복합 FK
       uq_um_id_user (3번 migration)를 참조해 같은 사용자 소유의 캐릭터만 공략 대상으로 삼게 한다.
    3. 아직 DB에 없던 나머지 FK
       erd.sql FK 23개 중 3번에서 건 fk_pred_user · fk_pc_pred를 뺀 21개다.
    """
    return """
        ALTER TABLE `user_attack_cycles`
            ADD COLUMN `active_user_id` BIGINT
                GENERATED ALWAYS AS (IF(`status` = 'active', `user_id`, NULL)) STORED
                AFTER `policy_version`,
            ADD UNIQUE KEY `uq_uac_active` (`active_user_id`);
        ALTER TABLE `user_attack_cycles`
            ADD CONSTRAINT `fk_uac_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
            ADD CONSTRAINT `fk_uac_target` FOREIGN KEY (`target_user_monster_id`, `user_id`)
                REFERENCES `user_monsters` (`id`, `user_id`);
        ALTER TABLE `health_records`
            ADD CONSTRAINT `fk_hr_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);
        ALTER TABLE `predictions`
            ADD CONSTRAINT `fk_pred_record` FOREIGN KEY (`health_record_id`) REFERENCES `health_records` (`id`);
        ALTER TABLE `user_monsters`
            ADD CONSTRAINT `fk_um_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
            ADD CONSTRAINT `fk_um_monster` FOREIGN KEY (`monster_id`) REFERENCES `monsters` (`id`),
            ADD CONSTRAINT `fk_um_pred` FOREIGN KEY (`last_prediction_id`) REFERENCES `predictions` (`id`),
            ADD CONSTRAINT `fk_um_record` FOREIGN KEY (`last_health_record_id`) REFERENCES `health_records` (`id`);
        ALTER TABLE `challenge_recommendations`
            ADD CONSTRAINT `fk_cr_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
            ADD CONSTRAINT `fk_cr_ch` FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`),
            ADD CONSTRAINT `fk_cr_cycle` FOREIGN KEY (`cycle_id`) REFERENCES `user_attack_cycles` (`id`);
        ALTER TABLE `user_challenges`
            ADD CONSTRAINT `fk_uc_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
            ADD CONSTRAINT `fk_uc_ch` FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`),
            ADD CONSTRAINT `fk_uc_rec` FOREIGN KEY (`recommendation_id`) REFERENCES `challenge_recommendations` (`id`),
            ADD CONSTRAINT `fk_uc_pred` FOREIGN KEY (`source_prediction_id`) REFERENCES `predictions` (`id`),
            ADD CONSTRAINT `fk_uc_cycle` FOREIGN KEY (`cycle_id`) REFERENCES `user_attack_cycles` (`id`);
        ALTER TABLE `challenge_logs`
            ADD CONSTRAINT `fk_cl_uc` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`);
        ALTER TABLE `user_challenge_occurrences`
            ADD CONSTRAINT `fk_uco_uc` FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`),
            ADD CONSTRAINT `fk_uco_log` FOREIGN KEY (`completed_log_id`) REFERENCES `challenge_logs` (`id`);
        ALTER TABLE `user_rewards`
            ADD CONSTRAINT `fk_ur_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
            ADD CONSTRAINT `fk_ur_reward` FOREIGN KEY (`reward_id`) REFERENCES `rewards` (`id`);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # 기존 인덱스로 받칠 수 없는 FK에는 MySQL이 FK와 같은 이름의 인덱스를 자동으로 만든다.
    # FK를 지워도 그 인덱스는 남으므로 해당 11개는 인덱스까지 지운다.
    return """
        ALTER TABLE `user_rewards` DROP FOREIGN KEY `fk_ur_reward`, DROP FOREIGN KEY `fk_ur_user`;
        ALTER TABLE `user_rewards` DROP INDEX `fk_ur_reward`;
        ALTER TABLE `user_challenge_occurrences` DROP FOREIGN KEY `fk_uco_log`, DROP FOREIGN KEY `fk_uco_uc`;
        ALTER TABLE `challenge_logs` DROP FOREIGN KEY `fk_cl_uc`;
        ALTER TABLE `user_challenges`
            DROP FOREIGN KEY `fk_uc_cycle`,
            DROP FOREIGN KEY `fk_uc_pred`,
            DROP FOREIGN KEY `fk_uc_rec`,
            DROP FOREIGN KEY `fk_uc_ch`,
            DROP FOREIGN KEY `fk_uc_user`;
        ALTER TABLE `user_challenges` DROP INDEX `fk_uc_pred`, DROP INDEX `fk_uc_rec`, DROP INDEX `fk_uc_ch`;
        ALTER TABLE `challenge_recommendations`
            DROP FOREIGN KEY `fk_cr_cycle`,
            DROP FOREIGN KEY `fk_cr_ch`,
            DROP FOREIGN KEY `fk_cr_user`;
        ALTER TABLE `challenge_recommendations` DROP INDEX `fk_cr_cycle`, DROP INDEX `fk_cr_ch`;
        ALTER TABLE `user_monsters`
            DROP FOREIGN KEY `fk_um_record`,
            DROP FOREIGN KEY `fk_um_pred`,
            DROP FOREIGN KEY `fk_um_monster`,
            DROP FOREIGN KEY `fk_um_user`;
        ALTER TABLE `user_monsters` DROP INDEX `fk_um_record`, DROP INDEX `fk_um_pred`, DROP INDEX `fk_um_monster`;
        ALTER TABLE `predictions` DROP FOREIGN KEY `fk_pred_record`;
        ALTER TABLE `predictions` DROP INDEX `fk_pred_record`;
        ALTER TABLE `health_records` DROP FOREIGN KEY `fk_hr_user`;
        ALTER TABLE `user_attack_cycles` DROP FOREIGN KEY `fk_uac_target`, DROP FOREIGN KEY `fk_uac_user`;
        ALTER TABLE `user_attack_cycles` DROP INDEX `fk_uac_target`;
        ALTER TABLE `user_attack_cycles` DROP INDEX `uq_uac_active`, DROP COLUMN `active_user_id`;"""


MODELS_STATE = (
    "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"
    "ssnP6xhpc46XdSoUGPSl/LQ78upN9ejS5tfTwiKzpfx6WuHVJmjblTGwpVYOA1tqpdfOaE"
    "UN7AXdgExr/kISPLjpzpMwVQ3EwSudSUpXiOxB9AYIp6PiC+FXqv9vLSLc8EmLrFfhmyjw"
    "ZEN5s/a9d7EdHFEtCvjUo6Rvdqjv175hWa2oRojZXOh4bgpbWxpEFZaWud3Qvw9fh/cXAv"
    "M9tgnmwSS+7xFqAQp87PmOD6WPByXyS+dwyMvn3fyHUJpFcLLM8q5ugQ6qnlDBkST8t7DT"
    "rlC/I2gGGNLQj7iDQvEag3CbDjPLW6crrqHCVKuYPLKd9B5NDSAi/rbB4QZ8kMvcZ5+gXc"
    "PmIjJUyUABFRu3mAdYogvfo7lp+2naYPJxWT17OU0D5ceCPr/u4d35J+nd+XgGPvfc1MTC"
    "pwuwDksMOUsw6nc3z7PseOw1y2e5p0u8KapatUGSbgri1OxnaQrXPnOdvTuPQ1ttJ4/m2k"
    "nXXBPC1DRHL8Q+n+A467jLeTgop3NQjiuRgdcqwMcIWbVojpLMfJe6sJh+79K0Uizbn+vk"
    "QfqqVfLh9ePt77ePf1wKrK6A5rw+Gze3o8dLQdWI82w83E1/u518uRTcBGLPxnB8Pf06HV"
    "MCnqvp2bia3lB6xVQp7cN4NLqnrXVCNjVQ1StzQ1Q98PfvQViaSOdMKDnsQx1UPe4hi8do"
    "OIFhy5KYPBvX06cJHfYMQ0XnwNNsyDFj6tZCHDT256fh5JHNlX9ukeG4+MKKR7iDLKryzb"
    "8hfZsgmUzHTpS0PkjJ3IM+h7ulVyAknr55goGYvlB47Y9yiWjlWSJa6UtEK65oQMbbuTus"
    "SmEZk3uosrJdFXHe3pJTKuNajPhw3OvXgnvfiKUt3Hqfb9qwEjs6YOgKOJRY75G96244eR"
    "pSBWyNjC2i+tf91+nj9FLYrEzHfDbAqTKjqwsQPxu/D8dPo0uBrfH8Hr9FNbU/Hh5Hd1RV"
    "e7Udsi6zk+05T7WqLSi36beXVqzDPRxQUgTZrwmCGg0fqLIAN5+NyXR2B0IzTGsNQqNMGI"
    "9Hky9UHjjoK6q4GJdF9LdPnFgnh8zavt1sTMtJDvm6uZ2NrpltA6cidA483d9PZ4/cwPEJ"
    "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"
    "SIMU+zi6JRdspcrlv/8fSmXIEw=="
)
