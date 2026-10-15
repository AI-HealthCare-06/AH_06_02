import {
  ARROW,
  bindRoutes,
  escape,
  formatDateTime,
} from "./health-flow.mjs";

/** 질환별 표시와 users 의 진단·복약 컬럼 접두사. */
const DISEASES = [
  { disease: "diabetes", prefix: "dm", icon: "♧", label: "당뇨" },
  { disease: "hypertension", prefix: "htn", icon: "♡", label: "고혈압" },
];

/** factor_key → 한글 라벨 */
const FACTOR_LABELS = {
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
const FACTOR_MONSTER = {
  alcohol_frequency: "알데",
  alcohol_amount: "알데",
  smoking_current: "코티니",
  bmi_high: "비세라",
  waist_high: "비세라",
  physical_activity_low: "비세라",
  strength_activity_low: "비세라",
  sedentary_time_high: "비세라",
};

const MEDICAL_NOTICE =
  '<div class="notice"><b>의료 고지</b><p>이 서비스는 의학적 진단·치료를 대신하지 않습니다.<br>정확한 평가는 의료 전문가와 상담해 주세요.</p></div>';

/** 진단 또는 복약 중이면 확률을 보여주지 않는다. DASH-01 은 복약만 있는 질환을 거르지 않으므로 여기서도 거른다. */
function managed(user, prefix) {
  return user?.[`${prefix}_diagnosed`] === true || user?.[`${prefix}_medication`] === true;
}

function signed(value) {
  const rounded = Math.round(value * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded}`;
}

function tile({ icon, label }, risk, isManaged) {
  if (isManaged)
    return `<article class="risk-tile diagnosed"><span>${icon} ${label}</span><strong>진단 관리 중</strong><p>예측 확률을 보여주지 않아요</p></article>`;
  if (!risk)
    return `<article class="risk-tile diagnosed"><span>${icon} ${label} 위험</span><strong>결과 없음</strong><p>완료된 예측이 아직 없어요</p></article>`;
  const percent = Math.round(risk.probability * 100);
  const when = risk.predicted_at ? formatDateTime(risk.predicted_at) : null;
  const meta = [
    "예측 확률",
    // delta 는 직전 완료 예측 대비 percentage points 다
    typeof risk.delta === "number" ? `직전 대비 ${signed(risk.delta)}%p` : null,
    when ? `${when} 기준` : null,
  ].filter(Boolean);
  // grade 는 경계값이 정해지기 전이라 항상 null 이다. 표시하지 않는다(REQ-PRED-004)
  return `<article class="risk-tile"><span>${icon} ${label} 위험</span><strong>${percent}<small>%</small></strong><p>${escape(meta.join(" · "))}</p></article>`;
}

/** PRED-03 기여요인 Top3 렌더링 (increase만, 질환별) */
function factorSection(diseases) {
  if (!diseases || !diseases.length) return "";
  const sections = diseases
    .map(({ disease, items }) => {
      const found = DISEASES.find((d) => d.disease === disease);
      const label = (found || {}).label || disease;
      const increases = (items || [])
        .filter((item) => item.direction === "increase")
        .sort((a, b) => b.contribution - a.contribution)
        .slice(0, 3);
      if (!increases.length) return "";
      const cards = increases
        .map((item) => {
          const name = FACTOR_LABELS[item.factor_key] || item.factor_key;
          const pct = `+${(item.contribution * 100).toFixed(1)}%p`;
          const monster = FACTOR_MONSTER[item.factor_key];
          const tag = item.modifiable
            ? monster
              ? `<button type="button" class="factor-monster" data-route="monsters">${escape(monster)}</button>`
              : ""
            : '<span class="factor-fixed">바꿀 수 없는 요인</span>';
          return `<div class="factor-card"><strong>${escape(name)}</strong><span class="factor-contrib">${pct}</span>${tag}</div>`;
        })
        .join("");
      return `<h3>${escape(label)} 주요 요인</h3><div class="factor-list">${cards}</div>`;
    })
    .join("");
  if (!sections) return "";
  return `<h2>지금, 이 요인에 주목해 보세요</h2><p class="small-copy">생활습관과 연결된 요인을 함께 살펴봐요.</p>${sections}`;
}

/**
 * 현재 위험도. v4 시안 risk 화면에서 예시 수치를 빼고 DASH-01 결과로 채운다.
 * 기여 요인(PRED-03)은 DASH-01의 prediction_id로 조회해 질환별 Top3(increase)를 표시한다.
 * 추이(DASH-02)는 2단계다. 예측 완료 뒤에는 waiting 이 추천으로 보낸다. 이 화면은 하단 메뉴로 직접 들어온다.
 */
export function mount({ root, ui, api, router, route, signal }) {
  root.innerHTML = `<section class="risk"><h1>${escape(route.title)}</h1><div data-body></div>${MEDICAL_NOTICE}</section>`;
  const body = root.querySelector("[data-body]");
  const unbindRoutes = bindRoutes(root, router);

  function render(user, summary, contributions) {
    const latest = summary.latest_health_record;
    const byDisease = Object.fromEntries((summary.risks || []).map((risk) => [risk.disease, risk]));
    const flags = DISEASES.map((item) => managed(user, item.prefix));
    const shown = DISEASES.filter((item, index) => !flags[index] && byDisease[item.disease]);
    const caption = `<p class="section-caption"><span class="user-name">${escape(user.nickname || "")}</span>님의 건강 리포트</p>`;

    if (!latest && !shown.length && !flags.every(Boolean)) {
      body.innerHTML = `${caption}<div class="status-panel" role="status"><h2>아직 건강기록이 없어요</h2><p>건강정보를 기록하면 위험도를 확인할 수 있어요.</p><button type="button" class="primary" data-route="health">건강정보 기록하기 ${ARROW}</button></div>`;
      return;
    }
    let lead;
    if (flags.every(Boolean))
      lead = '<p class="small-copy">두 질환 모두 진단 관리 중이라 예측 확률을 보여주지 않아요. 생활습관 공략은 그대로 이어갈 수 있어요.</p>';
    else if (shown.length) lead = '<p class="small-copy">먼저 공략할 요인을 찾아봐요.</p>';
    else
      lead = `<p class="small-copy">아직 완료된 예측이 없어요.</p>${latest ? `<button type="button" class="primary" data-route="waiting?record_id=${latest.health_record_id}">최근 기록으로 예측 요청하기 ${ARROW}</button>` : ""}`;
    const factors = factorSection(contributions);
    body.innerHTML = `${caption}${lead}
<div class="risk-grid">${DISEASES.map((item, index) => tile(item, byDisease[item.disease], flags[index])).join("")}</div>
${factors}
<button type="button" class="primary" data-route="monsters">내 위험요인 보기 ${ARROW}</button>
<button type="button" class="secondary" data-route="reco">챌린지 고르기</button>`;
  }

  async function load() {
    body.replaceChildren(ui.loading("위험도를 불러오고 있어요."));
    try {
      const [user, summary] = await Promise.all([
        // 진단·복약은 화면 진입 시점의 값을 쓴다. auth.user 는 로그인 시점 값이다
        api("/users/me"),
        api("/dashboard/summary"),
      ]);
      // PRED-03 기여요인 조회 (prediction_id가 있을 때만)
      let contributions = null;
      const predictionId = summary?.prediction_id;
      if (predictionId) {
        try {
          const res = await api(`/predictions/${predictionId}/contributions`);
          contributions = res?.diseases || null;
        } catch {
          // 기여요인 조회 실패는 화면 전체를 막지 않는다
          contributions = null;
        }
      }
      if (!signal.aborted) render(user, summary, contributions);
    } catch (error) {
      if (signal.aborted || error.name === "AbortError") return;
      body.replaceChildren(
        ui.notice(error.message, { kind: "error" }),
        ui.button("다시 확인하기", { variant: "secondary", onClick: () => void load() }),
      );
    }
  }
  void load();
  return unbindRoutes;
}
