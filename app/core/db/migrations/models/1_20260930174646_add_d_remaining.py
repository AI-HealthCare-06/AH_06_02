from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `challenge_logs` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_challenge_id` BIGINT NOT NULL,
    `log_date` DATE NOT NULL,
    `occurred_at` DATETIME(6) NOT NULL,
    `sequence_no` SMALLINT NOT NULL DEFAULT 1,
    `context_slot` VARCHAR(6) COMMENT 'LUNCH: lunch\nDINNER: dinner',
    `value` DECIMAL(6,1),
    `unit` VARCHAR(20),
    `result` VARCHAR(7) NOT NULL COMMENT 'DONE: done\nSKIPPED: skipped' DEFAULT 'done',
    `verification_method` VARCHAR(15) NOT NULL COMMENT 'MANUAL: manual\nPHOTO: photo\nTIMER: timer\nVALUE: value\nTIME: time\nSYSTEM: system\nMANUAL_FALLBACK: manual_fallback' DEFAULT 'timer',
    `verification_status` VARCHAR(14) NOT NULL COMMENT 'PENDING: pending\nPASS: pass\nFAIL: fail\nUNCERTAIN: uncertain\nSELF_CONFIRMED: self_confirmed' DEFAULT 'self_confirmed',
    `evidence_url` VARCHAR(255),
    `verification_score` DECIMAL(4,3),
    `fallback_reason` VARCHAR(100),
    `reward_eligible` BOOL NOT NULL DEFAULT 1,
    `xp_granted` SMALLINT NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_challenge_l_user_ch_6c6cc8` (`user_challenge_id`, `log_date`, `context_slot`),
    KEY `idx_challenge_l_user_ch_739c98` (`user_challenge_id`, `log_date`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `challenge_recommendations` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `challenge_id` BIGINT NOT NULL,
    `source_type` VARCHAR(19) NOT NULL COMMENT 'PREDICTION_PERSONAL: prediction_personal\nDIAGNOSIS_GLOBAL: diagnosis_global',
    `factor_key` VARCHAR(50) NOT NULL,
    `factor_score` DECIMAL(8,5),
    `rank` SMALLINT NOT NULL,
    `recommended_at` DATETIME(6) NOT NULL,
    `action` VARCHAR(14) COMMENT 'ACCEPTED: accepted\nREJECTED: rejected\nIGNORED: ignored\nNOT_APPLICABLE: not_applicable',
    `acted_at` DATETIME(6),
    `consecutive_reject_count` SMALLINT NOT NULL DEFAULT 0,
    `cooldown_choice` VARCHAR(12) COMMENT 'DAYS_7: 7d\nDAYS_30: 30d\nUNTIL_MANUAL: until_manual',
    `exclude_until` DATETIME(6),
    `suppressed_until_manual` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_challenge_r_user_id_b78f02` (`user_id`, `recommended_at`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `rewards` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(40) NOT NULL UNIQUE,
    `name` VARCHAR(60) NOT NULL,
    `motivation_type` VARCHAR(8) NOT NULL COMMENT 'COLLECT: collect\nGROW: grow\nDECORATE: decorate',
    `reward_kind` VARCHAR(5) NOT NULL COMMENT 'ITEM: item\nBADGE: badge\nTHEME: theme\nCARD: card',
    `unlock_condition` VARCHAR(120) NOT NULL,
    `required_level` SMALLINT,
    `linked_challenge_code` VARCHAR(40),
    `is_enabled` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `user_rewards` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `reward_id` BIGINT NOT NULL,
    `item_level` SMALLINT NOT NULL DEFAULT 1,
    `acquired_at` DATETIME(6) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_user_reward_user_id_264717` (`user_id`, `reward_id`)
) CHARACTER SET utf8mb4;
        ALTER TABLE `challenges` ADD `safety_check_required` BOOL NOT NULL DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `challenges` DROP COLUMN `safety_check_required`;
        DROP TABLE IF EXISTS `rewards`;
        DROP TABLE IF EXISTS `challenge_logs`;
        DROP TABLE IF EXISTS `challenge_recommendations`;
        DROP TABLE IF EXISTS `user_rewards`;"""


MODELS_STATE = (
    "eJztXetzosgW/1esfJqtm5nCN+abMcyMu0azambv7jpFtU2r3CA4PJJJbe3/fvs0oPIMEC"
    "JqqK3aiU2fBn6n+/R59eGfi7UmEcX41CW6jFcXV5V/LlS0JvQP35XLygXabHbt0GCiucK6"
    "ol2fuWHqCJu0dYEUg9AmiRhYlzemrKm0VbUUBRo1TDvK6nLXZKnyD4uIprYk5oro9MLf32"
    "mzrErkJzHcn5sHcSETRfI8qizBvVm7aD5vWFtfNT+zjnC3uYg1xVqru86bZ3OlqdvesmpC"
    "65KoREcmgeFN3YLHh6dz3tN9I/tJd13sR9yjkcgCWYq597oJMcCaCvjRpzHYCy7hLh9r1U"
    "a7wddbDZ52YU+ybWn/a7/e7t1tQobAcHrxL7uOTGT3YDDucHskugGPFACvt0J6OHp7JD4I"
    "6YP7IXQBi8PQbdiBuJs4OaG4Rj9FhahLEyZ4rdmMwexbd9z72h1/oL1+gbfR6GS25/jQuV"
    "SzrwGwOyBhaaQA0el+mgBWOS4BgLRXJIDsmhdAekeT2GvQC+Kvk9EwHMQ9Eh+Q9yp9wb8l"
    "GZuXFUU2zO/HCWsMivDW8NBrw/ih7IP34bb7Xz+uvcHomqGgGeZSZ6OwAa4pxiAyFw97ix"
    "8a5gg/PCFdEgNXtJoW1Td4aV1b+1uQipYMK3hjeD9nE7k3mEAPbC6sPXZrsWgPI9HOcjGz"
    "pBaPZxZuSdynCv1VbcCvdrsxs+ak2qBNc8Q3aVO1zsP/q/jDzEJSi/ZChOPodVyT6A+pNu"
    "d/qbA7U0lLWwmhrfP2AlegZ52jTR2O245dI41PFz6WF/s0M5X+xxpC7gx/N7hKl95ujhl5"
    "rcrDpQb/C/2ng2Fg3Fi4g1Xsf+FSm4fx6pzzWHChA7egg0vuwzgDSM0mvY4w4S7hWRCeS9"
    "AowbuSJoyDO5hj79pxnwi62W/OVwEGvGi6A7EbLXWkmuLPzQf2nG12mxZDT+pg1hPvsSNn"
    "heJaXp6RTtGp1er1do2rt/hmo91u8txWuQheitMyrvtfQNHwiKSXNQ+yRrKSZsvcEuSzaW"
    "ZEma7qOQ+TDEkLnk17vrJdWqjJllYb+2VBYWrJBhnGk0aF9woZqzRoBwgLVlVAmjYBZBCJ"
    "TD7YAg81mWitYypC5nOQBBw3b+8ziclIjrelTeXD8PP440TofeS4+i9HwyZVxg/s7xQc2q"
    "c5AuY0AG+XOfZy6PCNLAg3k2iXzWjlshnQLeeybq7EZ4L0IMCTNVKUSLHupXxZvIfA7MiV"
    "XFC2dznMSXQnxc0F7LV1nBRkW+zXa+3WVtDDjzjRPrntDgauLN/haZCf4TNVUK01A7JPb4"
    "1UTAKAOqSZJmyuSFbrVdB+EqPntYCS2D/R1o9/fq6IvFyZIl4HUb0hWKYzNHx2euh8kEo2"
    "4SdngAPDK3EoIbAxSN4IvT6dgB8alzaW1BKSTbKPcSOw1NeaKT8ieBAbiYzTNGSYw8lYCp"
    "GiEMyES1D7wKCWYw5XmaCtcaABV5uVD2Ph94/3E2FMdzY+087GJ5jUfOSk5v2ckNaiJKOl"
    "qhkkTJfWNIUgNXxe+0l90M8p7VthH2lZzmsLUDGqxDFcbNtoT/nja14mtBMyIU6zHo0GHi"
    "fAdd+nZw/vb68FV9bs1kdQZK9MNTM7ArTHwA+wK2HqM82u2WxGc+WY2EBn9ppIMmaiJf2q"
    "8NIeAxt2ywLYAD4AW/8Gwwj0wQ7zB8zBpJ8zYx63UAfY02Q+DInnjok9MNMz8ydIfAwM2q"
    "0Qm0GnwQhTM5Ei/gzxqUeq6vskmRT1TLhz4YuCazATFfbogN+LbRJjoTdKY4PmEgfa4auQ"
    "RxLifYk3hrZEh4O3GjGlmZ8Fga0552F+zzHiP1XcKQCzWuJsl+rWXWlbTfMG83RyHbZH8G"
    "3O9tKyXnPm0GG+Rr5pezBb4MEkEu/xOBzc3pJkAytIXhNdREudEElEIYGSG4q9STtF7B4R"
    "Y/jNBmeQT+4fh7bLcJ13N3dHQjk/wHsD9q7Usblk7/Gu02FP86pyr9e8pv1bYTLt3t555N"
    "lNdyrAlRprffa1fmj5lOPtIJU/+tOvFfhZ+Ws0FPyhmm2/6V8X8EzIMjVR1Z5EJO2D5za7"
    "Td4FrS1lVVwgWaE8t8LiaC+s7RD6gqWo7eDAVZ7tWSFOVxaSkOo1FpJodRZ2HMOjhDfSyd"
    "c8Fqui4Qe6uiiGYf7t+EXqpz22xdlGdryGIW67Y3kmYu1AFcJc9VOluRWpHg6xZVrlmK7x"
    "et/AyS1Qw0SmZWR2m22pD+iGQNiUH0moF0LiMA9xxUXD5SwLHwK3W8wRXK1XPQuxk8kl0U"
    "ngkuhEuiQ6fpfEk2yuJB09qRn2Tz/tkS3NAEPc1fifOrfdKKlSZF+VbNcnW75N26cEFzgk"
    "2Sv6/S1PrBNgVIaJ4aXMYVoUkd9D30EaqcqzMytPhLPOAoplrLWRMjLWS1kytlDGsoc/kl"
    "wmumUrsEWRi5CEpt3Fy7isJux2S5badLCk2TLHJcccF0z5Hq7xRSU0SjmGmt4cY4+q1kgS"
    "tW9ER+2DoTxTNpVU8G0JTjOtlk+CIB+NIB9AcP+xUuDoIys2Vn9MSd6Yvu9S05+zWnH79E"
    "Wn7HR70/63/vTPqwoz82Tzeabe9IXpVUWSiTlTJ7ej3/rDL1cVY609UNxnanfQG30dDSiB"
    "grWVpszU69ENpZ9rEqWdDAThjvZWCNkcQfR5Qd9K08UHEsGs8JnvpTrJiZ9/9tRSQ8qrki"
    "k8AxQ97yFIJXSHMG1ZLG+m9kb3QzrtmduTroH7cXfaH9EOkqWzSN5M/f2+O5yytfLDQird"
    "Zp6PYIabSKcqn/iIFCuEM7F5Q37S40kdyuPohJs21EqRNkSfPMQ+jBYUbv+TFBG1JCKiFi"
    "0iakFFA8nKs+hMq0zxh/ARigw0prU1cgn0OSJHlNBziK/4BQj9xIdDr30U6D0SXV446Rev"
    "2rBCBzqg4x38SXqI3/22O7zvUgVsjVQLUf3r7utoOrqqbFaaqc1U8KmMqXQB4pn6rTu4F6"
    "4qTMbb1+xLVFP7czIVbqmq9myYZJ1lJ2slkB9+z9BOfLQC0kNeULTpu2dWrL0jHJBTBBnP"
    "IYwSuhOqLMDFmTocjW+Baaqmr4FpFITBQBh+ofzA+76igmMjOlFev3ACgxyQFYa12Wi6CQ"
    "AGGXLTHws9ZtvoBIN1c393NxpPbQNnSzhTvwhDYQzcsh9RycKYarLTsTGHY/28IT+xYkmE"
    "Aq1KclprPpT4RPWWZIpLnOYSfu74pynSlwzLiIpz1vkITxLT/N129uYk0sdWwN0u0n+1p9"
    "Q5xzGjHDCrcusxzdtGyTFV0p2Hr5Hb/jEOKLZVTQ1LMRiOhgLsmSpVWG4FpvQQ2D2FbwIY"
    "6+TROfif2j2SxDsS7RyJkh6GopkhCvsLtQv2CXOoYHBUVnhuBQy8SgqL3oXlBcfbRh7CIv"
    "PairCLNroGoBpRvqJ46ILUB7TKjwNA2RCJCu+RdhfzEpYblzcjDi2I+SziFaH7u05+WFQ3"
    "Twtw5BiFH704MrDL/KazSIMp85vOlLFHmd800JYXcSlOcP0yUZaTqGjLN8h0+ptVhxJ3t7"
    "FTlOjNRJi3F5deRfviuy816iX672XuVFG5U6GMSY53KPnhFNfT4YDnCNF21QT3kchjQ1ua"
    "uB3kOHGOCyLTHcCHj4axpeuZtlof6WnutSeytyY7jUNNBaJiQjuktYd9pO8tRO3ZTwPQpX"
    "M3umMUXA1ocD/sfb2qKJaKV5AENxxCHFWSVdWJwhYbHs2S4VOm9pSpPfmk9lChC4+ZcaXv"
    "qA8YUpDCQwo3LKQgsZDC5Lf+3Z1wc1UxHuTNxnYZpcU6Tni6ULcjkW4Hlvl+0smamjhaiM"
    "qbIX9lN9SZZrDMVHtU8TPdsK67vd/c4bfRwyzcrSaJFFWjQ0XVQKzIw5XXHQeOGOqQ2RZE"
    "WUBKwULW187y8XL6ThjesPSKDVEllltx151M6E9kGDP1c7c/gHFlOgfo7iuMp93+8KpCd2"
    "Cim5QjlMfC4LPYGw0/98e3bKEGb5iWo40kHG1Ec7QRyMt4lCWmClp6ulK2PrrT3Gre4oSF"
    "d2JjTU+t+IQOcJ5aUOOynlgL2iZS6AQZ6RKIQkhPcsK+yWcLnMAyUeSlPA87rhYbvgqhLo"
    "OEHnx/bkRW8z0sMhhvp3sp31vMv4z3nUVYyPZcHVtcaEywtl5TvQ45jIkOEfm6XiaLFuke"
    "qrc/Iu/Egewowfbm9iIoY0DFxoAyRX7KeM/L8Z7swbUyrpYGZ0OzdGrrvSY/1zdE0Wdo78"
    "bCTb8Hp2TFO2E8GQ3BpbPRofYts7s2RKeGAvh3bvrdL8PRpD8RvwxG19DNKSQtG+JS0eYZ"
    "T1gkOftSjT78Ug2cfinsuHgRq+CNz4s7qGSx3v2k52m385fNxHY7tWAe0lo+Ls2JieU8zB"
    "6f7hacfbGmT5D6NM2fEzF3EkXqEY4+8PbyxrmjLjjG3O31hLspOLIRxmRD7zhTx8KvQo+1"
    "6eR/BLO2Pt0ux9Ak011Sh5bhaCp27+4G/V73esDOxJgitaEUGSPHZVS8IxzhbL6GfbpjKq"
    "j5LlcavBrBFtR8Fe0Jma2UQ9w4784Np2mKpD2pIl5pMn7F+bzAMAXLs5vunxOxfVVpUwnF"
    "/q5zFCROgnDetD8Q3UAvK2Ut2vHYTLKqlkRW1aJlVS3qMHWmAt0B4lJqFZ3JZ202cDzNLZ"
    "u+N9fSnCOKHqU8SVRGFsrIwttGFm4B5PAPhLuXLuMiB2u7U1lL93xjAe+plm7+WZzp09zz"
    "zG4/0AzNQ2FP/RXm4/gCc8aJVk8y0erRE61edNHmonOKWkkAbEUD2Irynj+QsAKA0fVEfG"
    "Q5VBM5Lr/lm5QTkWSDIINAvCF7bC4wyEE/FLxe2+5Nn3neG93eQg1buwOLw10LU2HC4m9z"
    "YhJjpn79804YT4XhhFW7XdHH1U2iGo6/tHhD3XlPUV5v6OQW7RhoZi5FDXZQbqkU0bnluq"
    "QDPBtOx/3re7v68H5nVgJpcs/8wms62Sw9YwZ07jwqK6NclCZ2aWKXxTreFWOPqVjHmKWQ"
    "X4R4Tpwrl3GOEzsBvfSblH6Tc/Cb5F/M9H25A/K3ZteaKT++vq50yDBF50D2RoMBKylNn1"
    "JhNaW/jEd/XFWWuvZE7S2hNxrTfYnaWwRrulMBpeAvhjinjR7oy2ZlhG+IopnQZ8eAZXYI"
    "+Lp7AzXV50hawnHhrwI7L7wicGC41x1T0wk722HBNWMtFT7znK2YdxjtacqaaiIndzXGy1"
    "0NK1ZgV4Ckt3kMq+b9UpFYP3Um93cBPskcv14uq/AF8l2Gf1r9IXKAk/Tv5q9RlB6Ti9Jj"
    "UhrWpcfkXTH2mDwm9wbRYz/h7O1wGec/8ZaZPPBBVafwS3lAtTygepYHJ8sDqofB2XvaPj"
    "XYoeSnZTkVcyJ478RsWsyjRihhj4P9VTXXCimzxr7NHVbMkH2+W3A+3g0ertHt3UBgh8no"
    "atwohJ0m6153h1D2EI6dzZEKtQ8zecBy/tYghVI3U9ea9lKde7VpKk9TI7RPc+74BD8YLB"
    "oq2hirsLLEab897BnqxJSHPLyA+x8Ij4E18UfG4/A8k0P9aUoSe77UnH3aRo7yDmfsdtPL"
    "4gL00ZZn+oo+02dqUJQ5Ayu9lCUjj4CRGSqO+shOMnL0JtVGyzDHWXjDyzDHmTL22MIcMe"
    "dq9y9fvhjieLsDtp6IhnMb+OX/VFsZ5CiDHOfolNyb8qkA9tKVGMdh7B76Cq9IGG9l+2lP"
    "y8Oeh2kNju/slUtd4gM6zS3Vc0jO6zgfdyFLVEdLlhbqHrZDzjk7utuzImsG2/7s4mu7c3"
    "nwORMov7Y7mwffNRkLk9Hgm13GzdCUR3C8T4TuwP5qCVIIK4q0O8Hne7y0dkWSr4tVoz8v"
    "Vg18X8x+xizG9j5haWsXbGu7ky9T3UsPacnKwlmJntADRTgbM33EJTuL9oJROZmtlKKX8r"
    "0VT8zl4P/ZHPifqW4J9VcUTs+9AICCDPM1iSzh9KelZB/6O90A2YpKBnPFPpSiS9lQDxui"
    "BD4uH7H0vp+Dkza4QT8R8qA8UzGkwaAhGWLxu3QI+Xvbqt13FwELkWVqha+RcAQjyF+Zw3"
    "RUWmtIClMZ9DkLeXJsQZ/oiiB7Vy9fDPm8WWkQ38fW2EuXAZ8y4PNOghG7GZ8KXw9ZiXBs"
    "uMck62wVALyUh0O5ehRKHMJO/YMsH3LxkJ6mRnIiGkgin2Npq56FbmkztlDl8t//A8+7Vm"
    "E="
)
