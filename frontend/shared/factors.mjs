/** 기여요인(PRED-03) 표시에 쓰는 이름과 몬스터 연결. 위험도 화면과 v5 도감이 함께 쓴다. */

/** factor_key → 한글 라벨 */
export const FACTOR_LABELS = {
  age: "나이",
  sex: "성별",
  family_history_dm: "당뇨 가족력",
  family_history_htn: "고혈압 가족력",
  bmi_high: "높은 체질량지수",
  waist_high: "높은 허리둘레",
  physical_activity_low: "낮은 신체활동",
  strength_activity_low: "낮은 근력활동",
  sedentary_time_high: "긴 좌식시간",
  smoking_current: "흡연",
  alcohol_frequency: "음주 빈도",
  alcohol_amount: "음주량",
  sodium_behavior: "나트륨 섭취 습관",
};

/** factor_key → 연결된 몬스터 */
export const FACTOR_MONSTER = {
  alcohol_frequency: "알데",
  alcohol_amount: "알데",
  smoking_current: "코티니",
  bmi_high: "비세라",
  waist_high: "비세라",
  physical_activity_low: "비세라",
  strength_activity_low: "비세라",
  sedentary_time_high: "비세라",
};

/** 위험을 올린(increase) 요인만 기여도 큰 순서로 3개 */
export function topIncreases(items) {
  return (items || [])
    .filter((item) => item.direction === "increase")
    .sort((a, b) => b.contribution - a.contribution)
    .slice(0, 3);
}

/** 확률 단위 기여도를 %p 로. 0.1%p 보다 작으면 "+0.1%p 미만" */
export function formatContribution(contribution) {
  const value = contribution * 100;
  return value < 0.1 ? "+0.1%p 미만" : `+${value.toFixed(1)}%p`;
}
