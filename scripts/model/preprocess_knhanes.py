"""Reproducible KNHANES IX adult input; all person-level output stays under data/.

Run it with the experiment dependencies attached:
    uv run --group model python scripts/model/preprocess_knhanes.py ...
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

VERSION = "knhanes-ix-v3"
RAW_COLUMNS = [
    "ID",
    "year",
    "age",
    "sex",
    "HE_BMI",
    "HE_wc",
    "sm_presnt",
    "BD1",
    "BD1_11",
    "BD2_1",
    "BE3_31",
    "BE3_32",
    "BE3_33",
    "BE5_1",
    "BE8_1",
    "BE8_2",
    "HE_DMfh1",
    "HE_DMfh2",
    "HE_DMfh3",
    "HE_HPfh1",
    "HE_HPfh2",
    "HE_HPfh3",
    "HE_DM_HbA1c",
    "HE_HP",
    "HE_sbp",
    "HE_dbp",
    "L_OUT_FQ",
    "LS_VEG2",
    "DE1_dg",
    "DI1_dg",
    "DE1_31",
    "DE1_32",
    "DI1_2",
]


def category(values, valid, missing):
    unexpected = set(values.dropna().unique()) - set(valid) - set(missing)
    if unexpected:
        raise ValueError(f"Unexpected codes in {values.name}: {sorted(unexpected)}")
    return values.where(values.isin(valid))


# 원시 파일과 코드 분포로 대조를 마친 제8기 연도. 그 밖의 2022년 이전 연도는 받지 않는다.
EIGHTH_CYCLE_YEARS = {2019}


def hypertension_code(frame):
    """HE_HP 를 제9기 4단계 정의로 맞춘다.

    제8기는 1 정상 · 2 전단계(120~139/80~89) · 3 고혈압 의 3단계이고,
    제9기는 1 정상 · 2 주의(120~129/<80) · 3 전단계(130~139/80~89) · 4 고혈압 이다.
    제8기 3 은 제9기 4 와 같은 정의라 그대로 옮기고, 제8기 2 는 측정 혈압으로 주의와 전단계를 가른다.
    """
    unverified = sorted(set(frame.year[frame.year.lt(2022) & ~frame.year.isin(EIGHTH_CYCLE_YEARS)]))
    if unverified:
        raise ValueError(f"코드북 대조를 하지 않은 연도: {unverified}")
    eighth = frame.year.isin(EIGHTH_CYCLE_YEARS)
    ninth_codes = category(frame.HE_HP[~eighth], [1, 2, 3, 4], [])
    eighth_codes = category(frame.HE_HP[eighth], [1, 2, 3], [])
    pre = eighth_codes.eq(2)
    sbp, dbp = frame.HE_sbp[eighth], frame.HE_dbp[eighth]
    if (pre & (sbp.isna() | dbp.isna())).any():
        raise ValueError("제8기 HE_HP 전단계인데 측정 혈압이 없어 제9기 코드로 나눌 수 없다")
    caution = sbp.lt(130) & dbp.lt(80)
    mapped = eighth_codes.map({1: 1, 3: 4}).mask(pre & caution, 2).mask(pre & ~caution, 3)
    return pd.concat([ninth_codes, mapped]).reindex(frame.index)


def minutes(hours, mins):
    hours = hours.mask(hours.isin([88, 99]))
    mins = mins.mask(mins.isin([88, 99]))
    total = hours * 60 + mins
    return total.where(hours.between(0, 24) & mins.between(0, 59) & total.between(0, 1440))


def family_history(frame, prefix):
    parents = [category(frame[prefix + str(i)], [0, 1], [9]) for i in [1, 2]]
    sibling = category(frame[prefix + "3"], [0, 1, 8], [9]).replace(8, 0)
    relatives = pd.concat([*parents, sibling], axis=1)
    # Sibling code 8 is an only child, not an unknown disease status.
    result = pd.Series(np.nan, index=frame.index)
    result.loc[relatives.eq(0).all(axis=1)] = 0
    result.loc[relatives.eq(1).any(axis=1)] = 1
    return result


def canonicalize(raw):
    frame = raw.loc[raw.age.ge(19)].copy()
    out = pd.DataFrame(index=frame.index)
    out["survey_year"] = frame.year.astype(int)
    out["age"] = frame.age
    out["sex"] = category(frame.sex, [1, 2], []).map({1: "M", 2: "F"})
    out["bmi"] = frame.HE_BMI.where(frame.HE_BMI.gt(0))
    out["waist_cm"] = frame.HE_wc.where(frame.HE_wc.gt(0))
    out["smoking_current"] = category(frame.sm_presnt, [0, 1], [])
    lifetime = category(frame.BD1, [1, 2], [8, 9])
    frequency = category(frame.BD1_11, range(1, 7), [8, 9])
    frequency = frequency.mask(lifetime.eq(1) & frame.BD1_11.eq(8), 1)
    out["alcohol_frequency"] = frequency
    amount = category(frame.BD2_1, range(1, 6), [8, 9])
    out["alcohol_amount"] = amount.mask(frequency.eq(1) & frame.BD2_1.eq(8), 0)
    out["walking_days"] = category(frame.BE3_31, range(1, 9), [88, 99]) - 1
    # 88/88 is skipped for verified no-walking (BE3_31=1); 99 means unknown.
    # Mask special time codes first, then set zero only when no walking is confirmed.
    out["walking_minutes"] = minutes(frame.BE3_32, frame.BE3_33).mask(out.walking_days.eq(0), 0)
    # Code 6 means >=5 days: retain lower bound 5, never invent an exact 6 or 7.
    out["strength_days"] = category(frame.BE5_1, range(1, 7), [8, 9]) - 1
    out["sitting_minutes"] = minutes(frame.BE8_1, frame.BE8_2)
    out["dining_out_freq"] = category(frame.L_OUT_FQ, range(1, 8), [9])
    # Exclude kimchi/pickles to keep this candidate distinct from sodium_behavior.
    out["vegetable_frequency"] = category(frame.LS_VEG2, range(1, 10), [99])
    out["family_history_dm"] = family_history(frame, "HE_DMfh")
    out["family_history_htn"] = family_history(frame, "HE_HPfh")
    out["HE_DM_HbA1c"] = category(frame.HE_DM_HbA1c, [1, 2, 3], [])
    out["HE_HP"] = hypertension_code(frame)
    # Evaluation masks only. Never expose diagnosis/medication as model features.
    out["eligible_diabetes"] = frame.DE1_dg.eq(0) & frame.DE1_31.isin([0, 8]) & frame.DE1_32.isin([0, 8])
    out["eligible_hypertension"] = frame.DI1_dg.eq(0) & frame.DI1_2.isin([5, 8])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/canonical.csv"))
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=[2022, 2023, 2024],
        help="Survey years to read from --raw as HN<yy>_ALL.sav",
    )
    args = parser.parse_args()
    frames, audits = [], []
    for year in args.years:
        path = args.raw / f"HN{str(year)[2:]}_ALL.sav"
        raw, _ = pyreadstat.read_sav(path, usecols=RAW_COLUMNS)
        if raw.ID.isna().any() or raw.ID.duplicated().any() or not raw.year.eq(year).all():
            raise ValueError(f"Unexpected identity/year in {path.name}")
        canonical = canonicalize(raw)
        frames.append(canonical)
        audits.append(
            {
                "year": year,
                "raw_n": len(raw),
                "adult_n": len(canonical),
                "duplicate_id_n": 0,
                "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "missing_fraction": canonical.isna().mean().to_dict(),
                "label_counts": {
                    k: {str(v): int(n) for v, n in canonical[k].value_counts().items()}
                    for k in ["HE_DM_HbA1c", "HE_HP"]
                },
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(args.out, index=False)
    audit = {
        "preprocessing_version": VERSION,
        "years": audits,
        "canonical_sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
    }
    args.out.with_suffix(".audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"adult_n": sum(a["adult_n"] for a in audits), "output": str(args.out)}))


if __name__ == "__main__":
    main()
