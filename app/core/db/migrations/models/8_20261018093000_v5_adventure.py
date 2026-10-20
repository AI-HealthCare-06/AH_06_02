from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE `challenge_timer_sessions` (
  `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `user_challenge_id` BIGINT NOT NULL,
  `occurrence_id` BIGINT NOT NULL UNIQUE,
  `started_at` DATETIME NOT NULL,
  `target_seconds` INT NOT NULL,
  `expires_at` DATETIME NOT NULL,
  `completed_log_id` BIGINT NULL UNIQUE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  FOREIGN KEY (`user_challenge_id`) REFERENCES `user_challenges` (`id`),
  FOREIGN KEY (`occurrence_id`) REFERENCES `user_challenge_occurrences` (`id`),
  FOREIGN KEY (`completed_log_id`) REFERENCES `challenge_logs` (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `reward_draws` (
  `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL,
  `challenge_log_id` BIGINT NOT NULL UNIQUE,
  `cards` JSON NOT NULL,
  `selected_positions` JSON NULL,
  `results` JSON NULL,
  `claimed_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  FOREIGN KEY (`challenge_log_id`) REFERENCES `challenge_logs` (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `adventurer_states` (
  `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `user_id` BIGINT NOT NULL UNIQUE,
  `equipment` JSON NOT NULL,
  `room` JSON NOT NULL,
  `materials` INT NOT NULL DEFAULT 0,
  `item_stage` SMALLINT NOT NULL DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE adventurer_states; DROP TABLE reward_draws; DROP TABLE challenge_timer_sessions;

"""


MODELS_STATE = (
"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"
)
