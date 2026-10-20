/** v5 실제 연결. 시안 체험은 ?demo=1로 분리하고 서버 응답만 진행 상태로 표시한다. */
import { AuthSession } from "../shared/auth.mjs";
import { createEvidenceUploader } from "../shared/evidence.mjs";
import {
  FACTOR_LABELS,
  FACTOR_MONSTER,
  formatContribution,
  topIncreases,
} from "../shared/factors.mjs";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        ch
      ],
  );
const dateKey = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
const names = {
  login: "로그인",
  signup: "회원가입",
  health: "건강정보 입력",
  health2: "생활습관 입력",
  health3: "검진정보",
  waiting: "예측 대기",
  risk: "모험 지도",
  monsters: "캐릭터 도감",
  reco: "전투와 챌린지",
  today: "오늘의 공략",
  progress: "나의 성장",
  evolution: "캐릭터 변화 도감",
  "evolution-complete": "수행 후 변화",
  rewards: "가방 · 나의 보상",
};
const labels = {
  viscera: "비세라",
  alde: "알데",
  cotinine: "코티니",
  spike: "스파이크",
};
// 건강정보 단계별 서버 필드와 입력칸 이름
const HEALTH_FIELDS = {
  health: { weight_kg: "체중", waist_cm: "허리둘레" },
  health2: {
    alcohol_frequency: "음주 빈도",
    alcohol_amount: "1회 음주량",
    walking_days: "주당 걷기 일수",
    walking_minutes: "1회 걷기 시간",
    strength_days: "주당 근력운동 일수",
    sitting_minutes: "하루 앉아 있는 시간",
    dining_out_freq: "외식 빈도",
  },
  health3: {
    sbp: "수축기 혈압",
    dbp: "이완기 혈압",
    fasting_glucose: "공복혈당",
    hba1c: "당화혈색소",
    triglyceride: "중성지방",
    hdl: "HDL 콜레스테롤",
  },
};
// 서버 허용 범위(app/core/validators/health_validators.py)와 같다. 계정을 만들기 전에 먼저 알린다
const HEALTH_RANGES = {
  weight_kg: [30, 200],
  sbp: [70, 250],
  fasting_glucose: [40, 500],
  walking_days: [0, 7],
  strength_days: [0, 7],
  walking_minutes: [0, 1440],
  sitting_minutes: [0, 1440],
};
// 서버 저장 형식(app/dtos/health_records.py)의 소수 자릿수. 나머지 숫자 칸은 정수만 받는다
const HEALTH_DECIMALS = { weight_kg: 1, waist_cm: 1, hba1c: 1 };
const auth = new AuthSession();
const api = auth.api;
const upload = createEvidenceUploader(api);
let user,
  signupDraft,
  healthRecordId,
  predictionId,
  sex,
  smoking,
  selected,
  village,
  growth = "character",
  bagTab = null,
  month = dateKey().slice(0, 7),
  catalog = [],
  adventurer = {},
  monsters = [],
  missions = [],
  draws = [],
  level = {},
  summary = {},
  calendar = {},
  healthRecords = [],
  previewItems = [],
  active = "login",
  navigation = 0;
// 추천 생성(CHLG-01)이 슬롯 없음으로 거절됐는지. 카드 조회 API 에는 남은 슬롯이 없어 생성 결과로 안다
let slotsFull = false;
const SLOTS_FULL_NOTICE =
  "지금은 챌린지를 더 시작할 수 없어요. 진행 중인 챌린지를 이어가세요.";
let busy = false,
  timerPoll = null,
  pendingPositions = new Set(),
  currentDraw = null,
  history = [];
const timerSessions = new Map();
const asset = (file) => "./assets/" + file;
const button = (text, attrs = "") =>
  `<button type="button" class="secondary-action" ${attrs}>${escape(text)}</button>`;
const art = (key, stage = 1) =>
  `<span class="evolution-art" role="img" aria-label="${escape(labels[key])} ${stage}단계"><span class="evolution-image ${escape(key)}" style="background-position:${(5 - stage) * 25}% ${({ spike: 0, alde: 1, cotinine: 2, viscera: 3 }[key] * 100) / 3}%"></span></span>`;
function avatar() {
  const gear = adventurer.equipment || {};
  return `<div class="avatar-rig"><img class="avatar-base" src="${asset("adventurer-base.webp")}" alt="나의 기본 모험가">${Object.entries(
    gear,
  )
    .map(([slot, code]) => {
      const item = catalog.find((i) => i.code === code);
      return item?.asset
        ? `<img class="avatar-equipment gear-${slot === "shoes" ? "feet" : slot} ${escape(code)}" src="${asset(item.asset)}" alt="${escape(item.name)}">`
        : "";
    })
    .join("")}</div>`;
}
function message(text, error = false) {
  let el = $("#live-feedback");
  if (!el) {
    el = document.createElement("p");
    el.id = "live-feedback";
    el.setAttribute("role", "status");
    $("#screen").prepend(el);
  }
  el.textContent = text;
  el.classList.toggle("error", error);
  el.hidden = !text;
}
// 오류가 난 입력칸에 바로 표시하고 그 칸으로 옮긴다. 화면 위 안내만으로는 어느 칸인지 알 수 없었다
function fieldError(target, text) {
  const error = new Error(text);
  error.field = target;
  return error;
}
function clearFieldErrors() {
  $$(".field-error").forEach((el) => el.remove());
  $$('[aria-invalid="true"]').forEach((el) => {
    el.removeAttribute("aria-invalid");
    el.removeAttribute("aria-describedby");
  });
}
function showFieldError(target, text) {
  clearFieldErrors();
  const id = "field-error-" + Date.now();
  const note = document.createElement("p");
  note.className = "field-error";
  note.id = id;
  note.setAttribute("role", "alert");
  note.textContent = text;
  // 두 칸이 나란한 묶음 안에 끼우면 칸 배치가 깨져서 묶음 아래에 둔다
  const box =
    target.closest(".two-columns") ||
    target.closest("label, [role=group]") ||
    target;
  box.insertAdjacentElement("afterend", note);
  const focusable = target.matches("input, select, button")
    ? target
    : target.querySelector("button, input, select");
  for (const el of new Set([target, focusable].filter(Boolean))) {
    el.setAttribute("aria-invalid", "true");
    el.setAttribute("aria-describedby", id);
  }
  focusable?.focus({ preventScroll: true });
  box.scrollIntoView({ block: "center" });
}
async function run(action, control) {
  if (busy) return;
  busy = true;
  if (control) control.disabled = true;
  const owner = auth.user?.id;
  message("");
  try {
    await action();
  } catch (error) {
    if (error.field) {
      // 지금 화면에 없는 칸이면 그 칸이 있는 단계로 먼저 옮긴다
      const scene = error.field.closest(".scene[data-page]");
      if (scene?.hidden) await go(scene.dataset.page);
      showFieldError(error.field, error.message);
    } else if (
      owner === auth.user?.id ||
      !owner ||
      control?.closest(".login-form")
    )
      message(error.message || "잠시 후 다시 시도해주세요.", true);
  } finally {
    busy = false;
    if (control?.isConnected) control.disabled = false;
  }
}
function syncMotion() {
  const reduced = document.body.classList.contains("reduce-motion");
  $$("video").forEach((v) => {
    if (reduced || v.closest(".scene")?.hidden) v.pause();
    else v.play().catch(() => {});
  });
}
// 예측 대기 중 새로고침해도 결과 확인을 이어가도록 예측 번호를 탭 저장소에도 둔다
const PREDICTION_KEY = "dangokiller.v5.prediction";
function rememberPrediction(id) {
  predictionId = id;
  try {
    if (id) sessionStorage.setItem(PREDICTION_KEY, String(id));
    else sessionStorage.removeItem(PREDICTION_KEY);
  } catch {}
}
function storedPrediction() {
  try {
    return Number(sessionStorage.getItem(PREDICTION_KEY)) || null;
  } catch {
    return null;
  }
}
function reset() {
  user = null;
  signupDraft = null;
  healthRecordId = null;
  slotsFull = false;
  rememberPrediction(null);
  sex = undefined;
  smoking = undefined;
  selected = null;
  village = null;
  monsters = [];
  missions = [];
  draws = [];
  catalog = [];
  adventurer = {};
  timerSessions.clear();
  pendingPositions.clear();
  clearInterval(timerPoll);
  timerPoll = null;
}
// 목록 API 는 한 번에 100건까지만 준다. 오래된 미수령 보상이 밀리지 않게 끝까지 이어 받는다
async function allPages(path) {
  const items = [];
  for (let page = 1; ; page++) {
    const data = await api(`${path}?page=${page}&size=100`);
    items.push(...data.items);
    if (!data.items.length || !(items.length < data.total)) return items;
  }
}
async function load() {
  const owner = auth.user?.id;
  const values = await Promise.all([
    api("/users/me"),
    api("/users/me/level"),
    api("/dashboard/summary"),
    api("/monsters/me"),
    api("/user-challenges?size=100"),
    api("/rewards/catalog"),
    api("/adventurer/me"),
    allPages("/reward-draws"),
  ]);
  if (owner !== auth.user?.id) return false;
  [user, level, summary] = values;
  monsters = values[3].items;
  missions = values[4].items;
  catalog = values[5].items;
  adventurer = values[6];
  draws = values[7];
  syncBagBadge();
  return true;
}
// 받을 보상 카드가 있으면 하단 가방 아이콘에 표시한다
function syncBagBadge() {
  const pending = draws.filter((d) => !d.claimed_at).length;
  $$('#adventure-nav [data-main-target="bag"]').forEach((b) => {
    b.classList.toggle("has-reward", pending > 0);
    if (pending) b.setAttribute("aria-label", `가방, 받을 보상 ${pending}개`);
    else b.removeAttribute("aria-label");
  });
}
function currentMonster() {
  return (
    monsters.find((m) => m.code === village) ||
    monsters.find((m) => m.is_target) ||
    monsters[0]
  );
}
function isAvailable(m) {
  return (
    !!m.user_monster_id &&
    ["rage", "caution", "stable"].includes(m.state) &&
    m.impact_score !== null
  );
}
function stage(m) {
  return Math.min(5, 1 + Math.floor(Number(m?.seal_progress || 0) / 25));
}
async function go(id, push = true) {
  if (!names[id]) id = "risk";
  // 기다릴 저장·예측이 없으면 대기 화면에 머물 이유가 없다 (뒤로가기 등)
  if (id === "waiting" && !healthRecordId && !predictionId) id = "risk";
  if (
    !auth.signedIn &&
    !["login", "signup", "health", "health2", "health3", "waiting"].includes(id)
  )
    id = "login";
  // 로그인된 채로 가입을 마치면 새 계정이 아니라 지금 계정의 정보가 바뀐다
  if (auth.signedIn && id === "signup") {
    await go("risk", push);
    if (active === "risk")
      message(
        "이미 로그인되어 있어요. 새 계정을 만들려면 메뉴에서 로그아웃해주세요.",
      );
    return;
  }
  const ticket = ++navigation;
  clearInterval(timerPoll);
  timerPoll = null;
  if (push && active !== id) history.push(active);
  active = id;
  document.body.dataset.page = id;
  const group = {
    risk: "home",
    reco: "quests",
    today: "quests",
    monsters: "book",
    evolution: "book",
    rewards: "bag",
    progress: "records",
    "evolution-complete": "records",
  }[id];
  $("#phone").classList.toggle("onboarding", !group);
  $("#phone").classList.toggle("home-map", id === "risk");
  $("#adventure-nav").hidden = !group;
  $$(".scene[data-page]").forEach((p) => (p.hidden = p.dataset.page !== id));
  $$("[data-main-target]").forEach((b) =>
    b.setAttribute("aria-current", String(b.dataset.mainTarget === group)),
  );
  $("#screen-name").textContent = names[id];
  $("#chapter-title").textContent = names[id];
  $("#chapter-copy").textContent = "";
  $("#chapter-number").textContent = String(
    Object.keys(names).indexOf(id) + 1,
  ).padStart(2, "0");
  location.hash = id;
  $("#screen").scrollTo({ top: 0 });
  syncMotion();
  message("");
  if (group) {
    const scene = $('.scene[data-page="' + id + '"]');
    scene.classList.add("live-loading");
    message("불러오는 중이에요.");
    if (!(await load()) || ticket !== navigation) return;
    message("");
    if (id === "risk") renderHome();
    if (id === "monsters") await renderBook(ticket);
    if (id === "evolution" || id === "evolution-complete") renderEvolution();
    if (id === "reco") await renderBattle(ticket);
    if (id === "today") await renderToday();
    if (id === "rewards") await renderBag();
    if (id === "progress") await renderGrowth(ticket);
    scene.classList.remove("live-loading");
  } else if (id === "health") fillProfile();
  $$(".user-name").forEach(
    (el) =>
      (el.textContent =
        user?.nickname || signupDraft?.nickname || "나의 모험가"),
  );
}
function riskValue(key) {
  const history = user?.[key + "_diagnosed"] || user?.[key + "_medication"];
  if (history) return ["진단 관리 중", ""];
  const risk = summary.risks?.find(
    (r) => r.disease === (key === "dm" ? "diabetes" : "hypertension"),
  );
  return risk
    ? [
        `${(risk.probability * 100).toFixed(1)}<small>%</small>`,
        "현재 위험도",
        riskDelta(risk.delta),
      ]
    : ["—", "건강정보 입력 후 확인"];
}
// delta 는 같은 모델로 낸 직전 완료 예측 대비 percentage points 다. 없으면(첫 예측·모델 변경) 표시하지 않는다
function riskDelta(delta) {
  if (typeof delta !== "number") return "";
  const rounded = Math.round(delta * 10) / 10;
  return `직전 대비 ${rounded > 0 ? "+" : ""}${rounded}%p`;
}
function renderHome() {
  for (const key of ["dm", "htn"]) {
    const tile = $("#" + key + "-risk"),
      [value, copy, delta] = riskValue(key);
    tile.querySelector("strong").innerHTML = value;
    tile.querySelector("p").textContent = copy;
    tile.querySelector(".live-risk-delta")?.remove();
    if (delta)
      tile
        .querySelector("strong")
        .insertAdjacentHTML(
          "afterend",
          `<span class="live-risk-delta">${escape(delta)}</span>`,
        );
  }
  $("#map-level").textContent = "Lv. " + level.level;
  $("#map-xp-text").textContent =
    `${level.current_level_xp} / ${level.next_level_xp ?? "최고 레벨"}`;
  $("#map-xp-fill").style.width =
    Math.min(
      100,
      level.next_level_xp
        ? (level.current_level_xp / level.next_level_xp) * 100
        : 100,
    ) + "%";
  const target = monsters.find((m) => m.is_target);
  $("#map-score").textContent = String(target?.weekly_progress ?? 0);
  $(".home-risk-summary").setAttribute("aria-label", "현재 위험도");
  $(".risk-summary-label small").textContent = summary.prediction_available
    ? "내 건강정보 기준"
    : "";
  const activeTarget = missions.find((m) => m.target_monster)?.target_monster
    ?.code;
  $$("[data-village-key]").forEach((b) => {
    const m = monsters.find((row) => row.code === b.dataset.villageKey);
    const available =
      m && isAvailable(m) && (!activeTarget || activeTarget === m.code);
    b.disabled = !available;
    b.classList.toggle("locked", !available);
    // 부제는 몬스터 마스터(title)를 따른다. 시안에 박힌 "활동량 · 허리둘레"는 #61 에서 바꾼 부제와 달랐다
    if (m?.title) b.querySelector(".village-plaque span").textContent = m.title;
    b.querySelector(".village-character").innerHTML = art(
      b.dataset.villageKey,
      stage(m),
    );
    b.querySelector(".village-plaque small").textContent =
      "위협도 " +
      (m?.impact_score ?? "산정 대기") +
      (m?.state === "not_contributing"
        ? " · 현재 위험 기여 없음"
        : m?.state === "sealed"
          ? " · 봉인 완료"
          : "");
    b.querySelector(".village-status").textContent = available
      ? m.is_target
        ? "공략 대상"
        : "마을 둘러보기"
      : !m || m.state === "unmeasured"
        ? "잠금 · 산정 대기"
        : activeTarget && activeTarget !== m.code
          ? "잠금 · 다른 마을 공략 중"
          : "잠금 · 현재 공략 대상 아님";
  });
  $("#village-help").textContent = activeTarget
    ? `${labels[activeTarget]} 공략 중이에요. 이번 주기에는 같은 대상을 공략해요.`
    : "공략할 수 있는 마을을 선택해 주세요.";
  $(".map-reselect").hidden = true;
  $(".map-continue").hidden = !target;
}
async function enterVillage(key) {
  if (!monsters.some((m) => m.is_target)) {
    await api("/challenge-recommendations/generate", { method: "POST" });
    await load();
  }
  const m = monsters.find((row) => row.code === key);
  if (!m || !isAvailable(m)) return;
  if (!m.is_target) {
    if (!m.target_change_allowed)
      throw new Error("진행 중인 공략 대상은 주기가 끝난 뒤 바꿀 수 있어요.");
    await api("/attack-cycles/current/target", {
      method: "PATCH",
      body: { user_monster_id: m.user_monster_id },
    });
  }
  village = key;
  selected = null;
  await go("reco");
}
// 추천 생성(CHLG-01). 남은 슬롯은 이 응답으로만 알 수 있어 전투 화면을 그릴 때마다(새로고침 포함) 확인한다.
// 새 추천을 못 만들어도(슬롯이 다 참 등) 진행 중인 챌린지에는 들어가야 하므로 안내 문구만 돌려준다
async function refreshRecommendations() {
  try {
    await api("/challenge-recommendations/generate", { method: "POST" });
    slotsFull = false;
    return "";
  } catch (error) {
    if (error.code !== "CHLG_RECOMMENDATION_UNAVAILABLE") throw error;
    slotsFull = error.details?.reason === "slots_unavailable";
    // 같은 주기 2주차부터 1개를 더 시작할 수 있어 "현재 주기에" 안 된다고 하면 주기 끝까지 막힌 것처럼 읽힌다
    return slotsFull ? SLOTS_FULL_NOTICE : error.message;
  }
}
async function renderBattle(ticket) {
  const m = currentMonster();
  if (!m) {
    message("건강정보를 입력하면 공략할 마을을 준비해요.");
    return;
  }
  village = m.code;
  const notice = await refreshRecommendations();
  if (ticket !== navigation) return;
  // 추천 이력 전체(최신순). 제외한 챌린지 목록도 여기서 모은다
  const history = await allPages("/challenge-recommendations");
  if (ticket !== navigation) return;
  // 챌린지마다 가장 최근 추천만 본다. 최근 추천을 거절했으면 예전 추천이 다시 보이지 않는다
  const cards = history.filter(
    (row, index) =>
      history.findIndex((c) => c.challenge_id === row.challenge_id) === index,
  );
  $("#battle-title").textContent = labels[m.code] + "와의 전투";
  $("#battle-monster-name").textContent = labels[m.code];
  $("#battle-monster-art").innerHTML = art(m.code, stage(m));
  $("#battle-threat").textContent = m.impact_score ?? "산정 대기";
  $("#battle-threat-fill").style.width = (m.impact_score ?? 0) + "%";
  $("#battle-score").textContent = `${m.weekly_progress} / 100`;
  $("#battle-score-fill").style.width = Math.min(100, m.weekly_progress) + "%";
  $(".battle-hero").innerHTML = avatar();
  $(".battle-round").textContent = missions[0]?.cycle_week
    ? `28일의 모험 · ${missions[0].cycle_week}주차`
    : "28일의 모험 · 시작 전";
  $("#battle-caption").textContent = "챌린지 내용을 확인한 뒤 시작해요.";
  const entries = [
    ...missions
      .filter((row) => row.target_monster?.code === m.code)
      .map((row) => ({ ...row, live: true })),
    ...cards
      .filter(
        (row) => row.action === null && row.target_monster?.code === m.code,
      )
      .filter(
        (row) =>
          !missions.some(
            (mission) => mission.challenge_id === row.challenge_id,
          ),
      ),
  ];
  $(".reco-list").innerHTML = entries.length
    ? entries
        .map((card, index) => {
          // 슬롯이 다 차면 아직 시작 안 한 추천은 눌러도 시작할 수 없다
          const locked = slotsFull && !card.live;
          return `<button type="button" class="reco-card${locked ? " is-locked" : ""}" data-live-card="${index}"${locked ? " disabled" : ""}><span class="quest-card-heading"><span class="quest-card-label">${escape(attackName(card))}</span></span><span class="quest-card-subtitle">${escape(card.title)}${card.live ? " · 진행 중" : ""}</span>${locked ? '<span class="quest-card-lock">지금은 추가로 시작할 수 없어요</span>' : ""}</button>`;
        })
        .join("")
    : '<p class="live-empty">지금 시작할 수 있는 챌린지가 없어요. 건강정보를 다시 확인해 주세요.</p>';
  $(".reco-list")._cards = entries;
  renderExcluded(cards.filter((row) => row.suppressed_until_manual));
  if (notice) message(notice);
}
// '해당 없어요'·'직접 다시 켤 때까지'로 뺀 챌린지. 다시 켜기 전까지 추천되지 않는다 (CHLG-03)
function renderExcluded(rows) {
  $(".live-excluded")?.remove();
  if (!rows.length) return;
  $(".reco-list").insertAdjacentHTML(
    "afterend",
    `<section class="live-excluded"><h2>추천에서 제외한 챌린지</h2>${rows.map((row) => `<div class="live-excluded-item"><b>${escape(row.title)}</b>${button("추천 다시 켜기", `data-live-restore="${row.challenge_id}"`)}</div>`).join("")}</section>`,
  );
}
// 선택지가 여럿인 확인 창. 고른 key, 취소하면 null 을 돌려준다.
// 앱이 폼 제출을 모두 막고 진행 중 클릭을 무시하므로 창 안의 클릭은 여기서 직접 처리한다
function choose(title, copy, choices) {
  let dialog = $("#live-choice");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "live-choice";
    dialog.setAttribute("aria-labelledby", "live-choice-title");
    dialog.addEventListener("click", (event) => {
      const option = event.target.closest("[data-choice]");
      if (!option) return;
      event.stopPropagation();
      dialog.close(option.dataset.choice);
    });
    document.body.append(dialog);
  }
  dialog.innerHTML = `<h2 id="live-choice-title">${escape(title)}</h2><p>${escape(copy)}</p><div class="live-choice-options">${choices.map((c) => `<button type="button" data-choice="${escape(c.key)}">${escape(c.text)}</button>`).join("")}<button type="button" class="secondary-action" data-choice="cancel">취소</button></div>`;
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) =>
    dialog.addEventListener(
      "close",
      () =>
        resolve(
          dialog.returnValue && dialog.returnValue !== "cancel"
            ? dialog.returnValue
            : null,
        ),
      { once: true },
    ),
  );
}
// 추천 카드 거절('나중에 할게요')·제외('해당 없어요'). v4 D 화면과 같은 문구·순서를 따른다
async function actOnRecommendation(card, action) {
  const rejected = action === "rejected";
  if (
    !confirm(
      rejected
        ? "나중에 할까요? 다른 챌린지를 선택할 수 있어요."
        : "이 챌린지를 제외할까요? 직접 다시 켜기 전까지 추천에서 제외돼요.",
    )
  )
    return;
  const path = `/challenge-recommendations/${card.recommendation_id}`;
  try {
    await api(path, { method: "PATCH", body: { action } });
  } catch (error) {
    // 같은 챌린지를 3회 연속 거절하면 서버가 재추천 시점을 고르라고 한다
    if (error.code !== "CHLG_INVALID_COOLDOWN") throw error;
    const choice = await choose(
      "언제 다시 추천받을까요?",
      "같은 챌린지를 연속으로 거절해 추천을 잠시 쉬어갈 수 있어요.",
      [
        { key: "7d", text: "7일 후" },
        { key: "30d", text: "30일 후" },
        { key: "until_manual", text: "직접 다시 켤 때까지" },
      ],
    );
    if (!choice) return;
    await api(path, {
      method: "PATCH",
      body: { action, cooldown_choice: choice },
    });
  }
  selected = null;
  await go("reco");
  if (active === "reco") message("선택을 저장했어요.");
}
// 카드 이름은 v5 시안(presentQuestCards)에 정한 공격 이름을 그대로 쓴다. 새 이름을 만들지 않는다
function attackName(card) {
  const byFactor = {
    physical_activity_low: "걷기 공격",
    sedentary_time_high: "휴식 공격",
    strength_activity_low: "근력 공격",
    alcohol_frequency: "금주 공략",
  };
  if (byFactor[card.factor_key]) return byFactor[card.factor_key];
  if (card.factor_key === "alcohol_amount")
    return card.verification_type === "value" ? "기록 공격" : "대체 공격";
  if (card.factor_key === "smoking_current")
    return card.verification_type === "timer" ? "습관 공격" : "기록 공격";
  if (card.verification_type === "value")
    return card.title?.includes("물") ? "음료 공격" : "기록 공격";
  return "습관 공격";
}
// 위험도를 올린 요인 Top3. v4 위험도 화면(#62)과 같은 형식으로 "내 위험요인 보기"에 보여준다
async function topFactorsHtml() {
  if (!summary?.prediction_id) return "";
  let diseases;
  try {
    diseases = (
      await api(`/predictions/${summary.prediction_id}/contributions`)
    ).diseases;
  } catch {
    return "";
  }
  const sections = (diseases || [])
    .map(({ disease, items }) => {
      const rows = topIncreases(items)
        .map((item) => {
          const monster = FACTOR_MONSTER[item.factor_key];
          const tag = !item.modifiable
            ? '<span class="factor-fixed">바꿀 수 없는 요인</span>'
            : monster
              ? `<span class="factor-monster">${escape(monster)}</span>`
              : "";
          return `<div class="factor-card"><strong>${escape(FACTOR_LABELS[item.factor_key] || item.factor_key)}</strong><span class="factor-contrib">${formatContribution(item.contribution)}</span>${tag}</div>`;
        })
        .join("");
      return rows
        ? `<h3>${disease === "diabetes" ? "당뇨" : "고혈압"} 주요 요인</h3><div class="factor-list">${rows}</div>`
        : "";
    })
    .join("");
  return sections
    ? `<section class="live-top-factors"><h2>지금, 이 요인에 주목해 보세요</h2><p class="small-copy">내 위험도를 올린 요인이에요.</p>${sections}</section>`
    : "";
}
async function renderBook(ticket) {
  const area = $('.scene[data-page="monsters"] .panel-pad');
  area.innerHTML = `<h1>내 위험요인 보기</h1><p class="small-copy">위협도와 공략 점수는 서로 다른 값이에요.</p><div class="live-book">${monsters.map((m) => `<article class="live-monster"><button type="button" data-live-evolution="${escape(m.code)}">${art(m.code, stage(m))}<h2>${escape(m.name)}</h2></button><p>위협도 ${m.impact_score ?? "산정 대기"} · 공략 점수 ${m.weekly_progress}</p><p>${escape({ rage: "주의가 필요해요", caution: "살펴볼 요인이에요", stable: "안정", not_contributing: "현재 위험 기여 없음", resolved: "요인 해소됨", sealed: "봉인 완료", unmeasured: "산정 대기" }[m.state])}</p><details><summary>산정 설명</summary><p>${m.impact_explanation?.status === "available" ? escape(m.impact_explanation.winners.map((w) => `${FACTOR_LABELS[w.factor_key] || w.factor_key} ${w.score}`).join(" · ")) : "이 점수의 산정 설명이 아직 없어요."}</p></details>${isAvailable(m) ? button(m.is_target ? "챌린지 보기" : "이 마을 살펴보기", `data-live-village="${m.code}" ${!m.is_target && !m.target_change_allowed ? "disabled" : ""}`) : ""}</article>`).join("")}</div>`;
  const factors = await topFactorsHtml();
  if (ticket !== navigation || !factors) return;
  area.querySelector(".live-book").insertAdjacentHTML("beforebegin", factors);
}
function renderEvolution() {
  const area = $(`.scene[data-page="${active}"] .panel-pad`);
  if (!area) return;
  const m = currentMonster();
  // 외형 단계 기준(REQ-RECO-008)이 정해지기 전에는 서버가 seal_progress 를 주지 않아 외형이 바뀌지 않는다
  const decided = m?.seal_progress != null;
  const note = decided
    ? "공략 진행률에 따라 외형이 변해요. 위험도·위협도는 재측정 후 갱신돼요."
    : "외형이 바뀌는 기준은 아직 정해지지 않았어요. 지금은 단계별 모습을 미리보기로 보여드려요. 위험도·위협도는 재측정 후 갱신돼요.";
  area.innerHTML = `<h1>캐릭터 변화 도감</h1><div class="unified-tabs">${Object.entries(
    labels,
  )
    .map(([key, name]) => button(name, `data-live-evolution="${key}"`))
    .join(
      "",
    )}</div>${decided ? "" : '<h2 class="live-preview-label">단계별 모습 · 미리보기</h2>'}<div class="evolution-strip">${[1, 2, 3, 4, 5].map((step) => `<div>${art(m?.code || "viscera", step)}<b>${step}단계</b></div>`).join("")}</div><p>${note}</p>`;
}
function checkRanges(page) {
  for (const [key, value] of Object.entries(healthValues(page))) {
    const input = $(`.${page} [aria-label="${HEALTH_FIELDS[page][key]}"]`);
    const allowed = HEALTH_DECIMALS[key] ?? 0;
    if ((String(value).split(".")[1] || "").length > allowed)
      throw fieldError(
        input,
        allowed
          ? "소수점 아래 한 자리까지 입력해주세요."
          : "소수점 없이 입력해주세요.",
      );
    const range = HEALTH_RANGES[key];
    if (range && (value < range[0] || value > range[1]))
      throw fieldError(input, `${range[0]}~${range[1]} 사이로 입력해주세요.`);
  }
}
function healthValues(page) {
  const get = (label) => $(`.${page} [aria-label="${label}"]`)?.value;
  const fields = HEALTH_FIELDS[page];
  return Object.fromEntries(
    Object.entries(fields)
      .filter(([, label]) => get(label) !== "")
      .map(([key, label]) => [key, Number(get(label))]),
  );
}
function profile() {
  const field = (key) =>
    $(`[data-page="health"] [data-profile-field="${key}"]`);
  const get = (key) => field(key).value;
  if (!sex)
    throw fieldError($('.health [aria-label="성별"]'), "성별을 선택해주세요.");
  if (get("birth_year") === "")
    throw fieldError(field("birth_year"), "출생연도를 입력해주세요.");
  if (get("height") === "")
    throw fieldError(field("height"), "키를 입력해주세요.");
  for (const key of ["dm", "htn", "dm_med", "htn_med"])
    if (get(key) === "")
      throw fieldError(field(key), "진단·복약 여부를 선택해주세요.");
  // 서버 가입 검증(app/core/validators/user_validators.py)과 같은 범위
  const latest = Number(dateKey().slice(0, 4)) - 14;
  const birth = Number(get("birth_year"));
  if (!Number.isInteger(birth))
    throw fieldError(
      field("birth_year"),
      "출생연도는 소수점 없이 입력해주세요.",
    );
  if (birth < 1900 || birth > latest)
    throw fieldError(
      field("birth_year"),
      `출생연도는 1900~${latest}년 사이로 입력해주세요.`,
    );
  const height = Number(get("height"));
  // 키는 소수점 아래 한 자리로 저장된다(users.height_cm). 자릿수가 더 많으면 서버가 말없이 반올림한다
  if ((String(height).split(".")[1] || "").length > 1)
    throw fieldError(
      field("height"),
      "키는 소수점 아래 한 자리까지 입력해주세요.",
    );
  if (height < 100 || height > 250)
    throw fieldError(field("height"), "키는 100~250cm 사이로 입력해주세요.");
  return {
    birth_year: Number(get("birth_year")),
    height_cm: Number(get("height")),
    sex,
    dm_diagnosed: get("dm") === "yes",
    htn_diagnosed: get("htn") === "yes",
    dm_medication: get("dm_med") === "yes",
    htn_medication: get("htn_med") === "yes",
  };
}
function fillProfile() {
  if (!user) return;
  sex = user.sex;
  const map = {
    birth_year: "birth_year",
    height: "height_cm",
    dm: "dm_diagnosed",
    htn: "htn_diagnosed",
    dm_med: "dm_medication",
    htn_med: "htn_medication",
  };
  for (const [key, field] of Object.entries(map)) {
    const el = $(`[data-page="health"] [data-profile-field="${key}"]`);
    el.value = ["dm", "htn", "dm_med", "htn_med"].includes(key)
      ? user[field]
        ? "yes"
        : "no"
      : (user[field] ?? "");
  }
  $$("[data-profile-sex]").forEach((b) => {
    const picked = (b.dataset.profileSex === "male" ? "M" : "F") === sex;
    b.setAttribute("aria-pressed", String(picked));
    b.classList.toggle("selected", picked);
  });
}
function validateHealth() {
  const body = {
    ...healthValues("health"),
    ...healthValues("health2"),
    ...healthValues("health3"),
  };
  const input = (label) => $(`[aria-label="${label}"]`);
  const required = [
    ["weight_kg", "체중", "체중을 입력해주세요."],
    ["waist_cm", "허리둘레", "허리둘레를 입력해주세요."],
    ["smoking", "현재 흡연 여부", "흡연 여부를 선택해주세요."],
    ["alcohol_frequency", "음주 빈도", "마시는 빈도를 선택해주세요."],
    ["alcohol_amount", "1회 음주량", "한 번에 마시는 양을 선택해주세요."],
    ["walking_days", "주당 걷기 일수", "주당 걷기 일수를 입력해주세요."],
    ["walking_minutes", "1회 걷기 시간", "1회 걷기 시간을 입력해주세요."],
    [
      "strength_days",
      "주당 근력운동 일수",
      "주당 근력운동 일수를 입력해주세요.",
    ],
    [
      "sitting_minutes",
      "하루 앉아 있는 시간",
      "하루 앉아 있는 시간을 입력해주세요.",
    ],
    ["dining_out_freq", "외식 빈도", "외식 빈도를 선택해주세요."],
  ];
  for (const [key, label, text] of required) {
    if (key === "alcohol_amount" && body.alcohol_frequency === 1) continue;
    if (key === "walking_minutes" && body.walking_days === 0) continue;
    const missing =
      key === "smoking" ? smoking === undefined : body[key] === undefined;
    if (missing) throw fieldError(input(label), text);
  }
  ["health", "health2", "health3"].forEach(checkRanges);
  body.smoking_current = smoking;
  if (body.alcohol_frequency === 1) body.alcohol_amount = 0;
  if (body.walking_days === 0) body.walking_minutes = 0;
  const checks = $$(".health2 .medicine input");
  body.family_history_dm = checks[0].checked;
  body.family_history_htn = checks[1].checked;
  body.input_mode = Object.keys(healthValues("health3")).length
    ? "detail"
    : "simple";
  return body;
}
// 서버가 알려준 틀린 필드를 그 입력칸 오류로 바꾼다
function serverFieldError(error) {
  const [first] = error.details?.fields || [];
  if (!first) return error;
  // 형식 검사(Pydantic)는 "SimpleHealthRecordInput.weight_kg" 처럼 입력 모델 이름을 앞에 붙인다
  const key = String(first.field).split(".").pop();
  const profileKey = { birth_year: "birth_year", height_cm: "height" }[key];
  let input = profileKey
    ? $(`[data-page="health"] [data-profile-field="${profileKey}"]`)
    : null;
  for (const [page, fields] of Object.entries(HEALTH_FIELDS))
    if (!input && fields[key])
      input = $(`.${page} [aria-label="${fields[key]}"]`);
  if (!input) return error;
  // 형식 검사 사유는 영어로 오므로 한국어 사유만 그대로 쓴다
  const reason = String(first.reason || "").replace(/^Value error, /, "");
  const text = /[가-힣]/.test(reason)
    ? reason
    : first.min !== undefined
      ? `${first.min}~${first.max} 사이로 입력해주세요.`
      : "입력 형식을 확인해주세요.";
  return fieldError(input, text);
}
async function saveIntake() {
  const values = profile(),
    body = validateHealth();
  if (!auth.signedIn) {
    if (!signupDraft) throw new Error("회원가입 정보를 먼저 입력해주세요.");
    const result = await api("/auth/signup", {
      method: "POST",
      auth: false,
      body: { ...signupDraft, ...values },
    }).catch((error) => {
      throw serverFieldError(error);
    });
    signupDraft = null;
    await auth.acceptLogin(result);
  } else await api("/users/me", { method: "PATCH", body: values });
  if (!healthRecordId)
    healthRecordId = (
      await api("/health-records", { method: "POST", body }).catch((error) => {
        throw serverFieldError(error);
      })
    ).health_record_id;
  await go("waiting");
  if (!predictionId) {
    try {
      rememberPrediction(
        (
          await api("/predictions", {
            method: "POST",
            body: { health_record_id: healthRecordId },
          })
        ).prediction_id,
      );
    } catch (error) {
      if (error.code === "PRED_ALL_DIAGNOSED") {
        healthRecordId = null;
        await go("risk");
        return;
      }
      throw error;
    }
  }
  await pollPrediction();
}
async function pollPrediction() {
  const ticket = navigation;
  message("나의 건강정보로 지도를 준비하고 있어요.");
  for (
    let i = 0;
    i < 60 && active === "waiting" && ticket === navigation;
    i++
  ) {
    const result = await api(`/predictions/${predictionId}`);
    if (result.status === "done") {
      healthRecordId = null;
      rememberPrediction(null);
      await go("risk");
      return;
    }
    if (result.status === "failed")
      throw new Error(
        "예측을 완료하지 못했어요. 입력을 확인한 뒤 다시 시도해주세요.",
      );
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  message("예측을 처리 중이에요. 아래에서 결과를 다시 확인할 수 있어요.");
}
// v4 화면과 같은 안전 안내·난이도 문구를 쓴다
const SAFETY_GUIDE =
  "현재 건강상태에서 무리 없이 수행할 수 있을 때 시작해주세요. 통증이나 불편이 생기면 중단하세요.";
const DIFFICULTIES = { easy: "쉬움", normal: "보통", challenge: "도전" };
// 시작 전 카드 정보. 값이 없는 항목은 빼서 "하루 1회 ·" 처럼 끝이 비지 않게 한다
function cardFacts(card) {
  const goal = [
    `하루 ${card.daily_target_count}회`,
    card.target_value != null
      ? `${Number(card.target_value)}${card.unit || ""}`
      : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const method =
    {
      timer: "타이머",
      photo: "사진 업로드",
      manual: "직접 확인",
      value: "수치 기록",
    }[card.verification_type] || "현재 지원 대기";
  return [
    goal,
    `인증 방법: ${method}`,
    card.context_label ? `상황: ${card.context_label}` : "",
    [
      DIFFICULTIES[card.difficulty]
        ? `난이도 ${DIFFICULTIES[card.difficulty]}`
        : "",
      card.daily_xp ? `하루 목표 ${card.daily_xp} XP` : "",
    ]
      .filter(Boolean)
      .join(" · "),
    "하나의 몬스터를 공략하는 28일 주기예요.",
  ]
    .filter(Boolean)
    .map((line) => `<p>${escape(line)}</p>`)
    .join("");
}
async function renderToday() {
  const area = $(".today .panel-pad");
  const card = selected;
  if (!card) {
    area.innerHTML = `<h1>오늘의 공략</h1>${missions.map((m, index) => `<button type="button" class="live-mission" data-live-mission="${index}"><b>${escape(m.title)}</b><span>${m.completed_count}회 완료 · 수행률 ${m.progress_rate === null ? "—" : Math.round(m.progress_rate * 100) + "%"}</span></button>`).join("") || "<p>진행 중인 챌린지가 없어요.</p>"}${button("챌린지 살펴보기", "data-live-quests")}`;
    return;
  }
  const mission = missions.find((m) => m.challenge_id === card.challenge_id);
  if (!mission) {
    area.innerHTML = `<h1>${escape(card.title)}</h1><p class="small-copy">${escape(card.description || "실천 내용을 확인하고 내 생활에 맞게 시작해요.")}</p><div class="live-details">${cardFacts(card)}</div>${card.safety_check_required ? `<p class="field-help">${SAFETY_GUIDE}</p><label class="live-check"><input type="checkbox" id="live-safety"> 운동 전 안전 안내를 확인했고 무리 없이 수행할 수 있어요.</label>` : ""}${card.context_type === "event" ? '<label>예정 이용일<input id="live-scheduled-date" type="date" min="' + dateKey() + '"></label><p class="small-copy">예정된 이용일을 선택해주세요.</p>' : ""}<button type="button" class="primary" data-live-start>이 챌린지 시작하기</button>${button("다른 챌린지 보기", "data-live-quests")}${card.recommendation_id ? `<div class="live-reco-actions">${button("나중에 할게요", 'data-live-reco="rejected"')}${button("해당 없어요", 'data-live-reco="not_applicable"')}</div>` : ""}`;
    return;
  }
  selected = { ...mission, live: true };
  area.innerHTML = `<h1>${escape(mission.title)}</h1><p class="small-copy">${mission.start_date} ~ ${mission.end_date} · 하루 ${mission.daily_target_count}회</p><p>수행률 ${mission.progress_rate === null ? "—" : Math.round(mission.progress_rate * 100) + "%"} · ${mission.completed_count}회 완료</p><div class="live-occurrences">${mission.today_occurrences.map((o) => `<article class="slot ${o.status === "completed" ? "done" : ""}" data-occurrence="${o.occurrence_id}"><h3>${escape({ lunch: "점심", dinner: "저녁" }[o.slot_code] || o.sequence_no + "회차")}</h3><p>${o.status === "completed" ? "인정 완료" : (mission.target_value != null ? `${Number(mission.target_value)}${escape(mission.unit || "")} · ` : "") + "아직 기록 전"}</p>${o.status === "completed" ? "" : mission.verification_type === "timer" ? `<strong class="live-timer" data-timer-display="${o.occurrence_id}">00:00</strong><button type="button" class="verify" data-live-timer="${o.occurrence_id}">타이머 시작</button><button type="button" class="verify" data-live-complete="${o.occurrence_id}" disabled>시간을 채운 뒤 완료</button>` : mission.verification_type === "photo" ? `<label class="live-photo">사진 선택<input type="file" accept="image/jpeg,image/png" data-photo-for="${o.occurrence_id}"></label><button type="button" class="verify" data-live-complete="${o.occurrence_id}">사진 업로드하고 완료</button>` : mission.verification_type === "manual" ? `<label><input type="checkbox" data-manual-for="${o.occurrence_id}"> 실제로 수행했어요.</label><button type="button" class="verify" data-live-complete="${o.occurrence_id}">수행 기록하기</button>` : "<p>아직 지원하지 않는 인증 방식이에요.</p>"}</article>`).join("") || "<p>오늘 예정된 수행 기회가 없어요.</p>"}</div>${button("보상 확인", 'data-live-bag="draw"')}${button("다른 챌린지 보기", "data-live-quests")}<button type="button" class="danger-link" data-live-stop>챌린지 중단</button>`;
  for (const o of mission.today_occurrences) {
    if (o.timer_session_id && o.status === "planned") {
      const timer = await api(
        `/user-challenges/${mission.user_challenge_id}/timers/${o.timer_session_id}`,
      );
      timerSessions.set(o.occurrence_id, timer);
      paintTimer(o.occurrence_id, timer);
    }
  }
  if (mission.verification_type === "timer")
    timerPoll = setInterval(() => {
      if (!busy) refreshTimers().catch((error) => message(error.message, true));
    }, 3000);
}
function paintTimer(occurrenceId, timer) {
  const display = $(`[data-timer-display="${occurrenceId}"]`);
  if (!display) return;
  const seconds = timer.elapsed_seconds;
  display.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")} / ${Math.ceil(timer.target_seconds / 60)}분`;
  const start = $(`[data-live-timer="${occurrenceId}"]`),
    complete = $(`[data-live-complete="${occurrenceId}"]`);
  start.disabled = true;
  start.textContent = "타이머 진행 중";
  complete.disabled = !timer.ready;
  complete.textContent = timer.ready ? "수행 완료 기록" : "시간을 채운 뒤 완료";
}
async function refreshTimers() {
  const mission = selected;
  if (!mission?.user_challenge_id) return;
  const ticket = navigation;
  for (const o of mission.today_occurrences || []) {
    const prior = timerSessions.get(o.occurrence_id);
    if (!prior || prior.completed) continue;
    const timer = await api(
      `/user-challenges/${mission.user_challenge_id}/timers/${prior.timer_session_id}`,
    );
    if (ticket !== navigation) return;
    timerSessions.set(o.occurrence_id, timer);
    paintTimer(o.occurrence_id, timer);
  }
}
async function startChallenge() {
  const body = { recommendation_ids: [selected.recommendation_id] };
  if (selected.safety_check_required) {
    if (!$("#live-safety").checked)
      throw new Error("운동 전 안전 안내를 확인해주세요.");
    body.safety_confirmed = true;
  }
  if (selected.context_type === "event") {
    const date = $("#live-scheduled-date").value;
    if (!date) throw new Error("예정 이용일을 선택해주세요.");
    body.scheduled_dates = [date];
  }
  await api("/user-challenges", { method: "POST", body });
  await go("today");
  message("챌린지를 시작했어요. 오늘 예정 기회를 확인해주세요.");
}
async function complete(occurrenceId) {
  const mission = selected,
    o = mission.today_occurrences.find((o) => o.occurrence_id === occurrenceId);
  if (!o || o.status !== "planned") return;
  const body = {
    occurred_at: new Date().toISOString(),
    verification_method: mission.verification_type,
  };
  if (o.slot_code) body.context_slot = o.slot_code;
  if (mission.verification_type === "timer") {
    const timer = timerSessions.get(o.occurrence_id);
    if (!timer) throw new Error("타이머를 먼저 시작해주세요.");
    body.timer_session_id = timer.timer_session_id;
  } else if (mission.verification_type === "photo") {
    const file = $(`[data-photo-for="${occurrenceId}"]`).files[0];
    if (!file) throw new Error("실천 사진을 선택해주세요.");
    body.evidence_url = (
      await upload(file, { userChallengeId: mission.user_challenge_id })
    ).evidence_url;
  } else if (
    mission.verification_type === "manual" &&
    !$(`[data-manual-for="${occurrenceId}"]`).checked
  )
    throw new Error("실제 수행 여부를 확인해주세요.");
  const result = await api(
    `/user-challenges/${mission.user_challenge_id}/logs`,
    { method: "POST", body },
  );
  await go("today");
  message(
    result.reward_eligible
      ? `수행을 기록했어요. +${result.xp_granted} XP${result.weekly_progress !== null ? " · 이번 주 공략 점수 " + result.weekly_progress : ""} · 가방에서 보상 카드를 골라보세요.`
      : "기록을 저장했어요. 추가 점수와 보상은 지급되지 않아요.",
  );
}
async function renderBag() {
  // 가방을 새로 열 때 받을 보상이 있으면 카드 뽑기부터 보여준다. 보상함이 비어 보여 헷갈렸다
  if (!bagTab) bagTab = draws.some((d) => !d.claimed_at) ? "draw" : "inventory";
  const content = $("#reward-content");
  $("#reward-page-title").textContent = "나의 보상";
  $("#reward-page-copy").textContent =
    "실천으로 모은 아이템으로 모험가와 방을 꾸며요.";
  $("#reward-mode-caption").textContent = "통합 보상";
  content.innerHTML = `<div class="unified-tabs">${[
    ["inventory", "보상함"],
    ["draw", "카드 뽑기"],
    ["adventurer", "모험가"],
    ["room", "방 꾸미기"],
    ["library", "후보 70종"],
  ]
    .map(([id, label]) =>
      button(label, `data-live-bag="${id}" aria-pressed="${bagTab === id}"`),
    )
    .join(
      "",
    )}</div><p>성장의 조각 ${adventurer.materials}개 · 아이템 ${adventurer.item_stage}단계</p><div id="live-bag-panel"></div>`;
  const panel = $("#live-bag-panel");
  if (bagTab === "draw") {
    renderDraw(panel);
    return;
  }
  if (bagTab === "library") {
    if (!previewItems.length)
      previewItems = await (
        await fetch(new URL("./item-preview.json", import.meta.url))
      ).json();
    panel.innerHTML =
      '<p class="field-help">획득·장착 기능을 준비 중인 아이템 후보예요.</p><div class="avatar-catalog">' +
      previewItems
        .map(
          (i) =>
            `<article class="catalog-card locked"><div class="catalog-art"><img loading="lazy" src="${asset("avatar-library-70/" + i.filename)}" alt="${escape(i.name)}"><span class="item-lock">잠금 · 미리보기</span></div><b>${escape(i.name)}</b></article>`,
        )
        .join("") +
      "</div>";
    return;
  }
  const items = catalog.filter((i) =>
    bagTab === "room"
      ? [
          "bed",
          "computer",
          "chair",
          "light",
          "background",
          "ornament",
        ].includes(i.slot)
      : bagTab === "adventurer"
        ? ["hat", "bag", "hand", "shoes"].includes(i.slot)
        : i.owned && !i.starter,
  );
  const cards = `<div class="reward-grid">${items.map((i) => `<article class="reward-tile ${i.owned ? "" : "locked"}">${i.asset ? `<div class="equipment-thumbnail"><img src="${asset(i.asset)}" alt="${escape(i.name)}" loading="lazy"></div>` : '<span class="live-token" aria-hidden="true">✦</span>'}<h3>${escape(i.name)}</h3><p>${i.starter ? "기본 제공" : i.rarity}</p>${bagTab !== "inventory" ? `<button type="button" class="reward-apply" data-live-equip="${i.code}" ${i.owned ? "" : "disabled"}>${!i.owned ? "🔒 미획득" : (adventurer.equipment?.[i.slot] || adventurer.room?.[i.slot]) === i.code ? "해제하기" : "적용하기"}</button>` : ""}</article>`).join("") || (draws.some((d) => !d.claimed_at) ? `<p>받을 보상 카드가 있어요. 카드를 고르면 여기에 담겨요.</p>${button("카드 고르러 가기", 'data-live-bag="draw"')}` : "<p>아직 획득한 보상이 없어요. 챌린지를 완료하면 카드를 고를 수 있어요.</p>")}</div>`;
  panel.innerHTML =
    bagTab === "room"
      ? `<div class="live-room-layout">${roomArt()}<section>${cards}</section></div>`
      : bagTab === "adventurer"
        ? `<div class="live-avatar-layout"><div class="growth-avatar">${avatar()}<h2>${escape(user.nickname)}</h2></div><section>${cards}</section></div>`
        : cards;
  panel.insertAdjacentHTML(
    "beforeend",
    `<section class="growth-display"><h2>아이템 ${adventurer.item_stage}단계</h2><p>성장의 조각 5개로 다음 단계에 도전해요.</p><button type="button" class="reward-apply" data-live-upgrade ${adventurer.materials < 5 || adventurer.item_stage >= 3 ? "disabled" : ""}>${adventurer.item_stage >= 3 ? "최대 단계" : "단계 상승 · 조각 5개"}</button></section>`,
  );
}
function roomArt() {
  const room = adventurer.room || {};
  return `<div class="room-preview mood-${escape(room.background || "meadow")}"><div class="room-preview-label">나의 방</div><div class="room-stage"><img class="room-base" src="${asset("room-decor-v1/room-base.webp")}" alt="꾸미기 방">${[
    "bed",
    "computer",
    "chair",
    "light",
    "ornament",
  ]
    .map((slot) => {
      const item = catalog.find((i) => i.code === room[slot]);
      return item?.asset
        ? `<img class="room-furniture room-${slot === "computer" ? "desk" : slot}" src="${asset(item.asset)}" alt="${escape(item.name)}">`
        : "";
    })
    .join("")}</div></div>`;
}
function renderDraw(panel) {
  currentDraw = draws.find((d) => !d.claimed_at) || draws[0] || null;
  if (!currentDraw) {
    panel.innerHTML =
      '<div class="growth-empty"><h2>실천이 선물로 돌아와요.</h2><p>예정된 챌린지를 한 번 완료하면 카드 5장 중 3장을 고를 수 있어요.</p></div>';
    return;
  }
  if (currentDraw.claimed_at) {
    panel.innerHTML = `<h2>보상 3개를 받았어요!</h2><div class="reward-results">${currentDraw.results.map((i) => `<article class="draw-result ${i.rarity.toLowerCase()}"><span class="rarity">${i.rarity}</span>${i.asset ? `<div class="equipment-thumbnail"><img src="${asset(i.asset)}" alt=""></div>` : "✦"}<h3>${escape(i.name)}</h3><p>${i.duplicate ? "중복 보상 → " : ""}${i.materials ? "성장의 조각 +" + i.materials : "새 보상 획득"}</p></article>`).join("")}</div>${button("바로 꾸미기", 'data-live-bag="adventurer"')}`;
    return;
  }
  panel.innerHTML = `<h2>5장 중 3장을 골라주세요</h2><p>선택 ${pendingPositions.size} / 3 · 남은 보상 ${draws.filter((d) => !d.claimed_at).length}회</p><div class="live-draw-cards">${[0, 1, 2, 3, 4].map((pos) => `<button type="button" class="live-card-back ${pendingPositions.has(pos) ? "selected" : ""}" data-live-position="${pos}" aria-label="${pos + 1}번째 카드" aria-pressed="${pendingPositions.has(pos)}"><span>✦</span><b>${pendingPositions.has(pos) ? "선택" : "DANGO"}</b></button>`).join("")}</div><button type="button" class="primary" data-live-claim ${pendingPositions.size !== 3 ? "disabled" : ""}>선택한 카드 3장 열기</button>`;
}
async function renderGrowth(ticket) {
  const [records, progress] = await Promise.all([
    allPages("/health-records"),
    api(`/adventure/progress?month=${month}`),
  ]);
  if (ticket !== navigation) return;
  healthRecords = records;
  calendar = progress;
  $$("[data-growth-tab]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.growthTab === growth)),
  );
  const content = $("#growth-content");
  if (growth === "character") {
    content.innerHTML = `<div class="live-avatar-layout"><div class="growth-avatar">${avatar()}</div><section><h1>Lv. ${level.level} ${escape(user.nickname)}</h1><p>경험치 ${level.current_level_xp} / ${level.next_level_xp ?? "최고 레벨"}</p><p>공략 점수 ${currentMonster()?.weekly_progress ?? 0} / 100</p><p>성장의 조각 ${adventurer.materials}개 · 아이템 ${adventurer.item_stage}단계</p>${button("모험가 꾸미기", 'data-live-bag="adventurer"')}${button("방 꾸미기", 'data-live-bag="room"')}${button("보상 카드 열기", 'data-live-bag="draw"')}</section></div>`;
    return;
  }
  if (growth === "health") {
    content.innerHTML = `<h2>나의 건강 데이터</h2>${button("건강정보 다시 입력", 'data-route="health"')}<form id="live-daily"><h3>오늘의 수치 기록</h3><div class="live-daily-fields">${[
      ["weight_kg", "체중 (kg)"],
      ["waist_cm", "허리둘레 (cm)"],
      ["sbp", "수축기 혈압"],
      ["dbp", "이완기 혈압"],
      ["fasting_glucose", "공복혈당"],
    ]
      .map(
        ([key, label]) =>
          `<label>${label}<input type="number" step="${["weight_kg", "waist_cm"].includes(key) ? ".1" : "1"}" name="${key}" min="1"></label>`,
      )
      .join(
        "",
      )}</div><button class="primary" type="submit">기록 저장하기</button></form><div class="live-health-history">${
      healthRecords
        .map(
          (r) =>
            `<article><b>${escape(r.recorded_at.slice(0, 10))}</b><p>${[
              ["weight_kg", "체중", "kg"],
              ["waist_cm", "허리둘레", "cm"],
              ["sbp", "수축기", "mmHg"],
              ["dbp", "이완기", "mmHg"],
              ["fasting_glucose", "공복혈당", "mg/dL"],
            ]
              .filter(([key]) => r[key] !== null)
              .map(([key, label, unit]) => `${label} ${r[key]} ${unit}`)
              .join(" · ")}</p></article>`,
        )
        .join("") || "<p>저장한 건강 기록이 없어요.</p>"
    }</div>`;
    return;
  }
  if (growth === "achievements") {
    const first = new Date(month + "-01T12:00:00Z"),
      count = new Date(
        first.getUTCFullYear(),
        first.getUTCMonth() + 1,
        0,
      ).getDate(),
      offset = first.getUTCDay(),
      stamps = new Map(calendar.days.map((d) => [d.date, d.count]));
    content.innerHTML = `<div class="calendar-toolbar">${button("‹", 'data-live-month="-1" aria-label="이전 달"')}<h2>${month.replace("-", ".")}</h2>${button("›", 'data-live-month="1" aria-label="다음 달"')}</div><div class="calendar-weekdays">${["일", "월", "화", "수", "목", "금", "토"].map((d) => `<span>${d}</span>`).join("")}</div><div class="calendar-grid">${"<span></span>".repeat(offset)}${Array.from(
      { length: count },
      (_, i) => {
        const day = month + "-" + String(i + 1).padStart(2, "0"),
          n = stamps.get(day);
        return `<div class="calendar-day ${n ? "stamped" : ""}" aria-label="${day}, ${n || 0}회 완료"><b>${i + 1}</b>${n ? `<span class="stamp-mark"><span>실천 완료<br>${n}회</span></span>` : ""}</div>`;
      },
    ).join(
      "",
    )}</div><p class="calendar-note">인정된 수행을 완료한 날짜에만 도장이 찍혀요.</p>`;
    return;
  }
  content.innerHTML = `<div class="calendar-toolbar">${button("‹", 'data-live-month="-1"')}<h2>${month} 공략 이력</h2>${button("›", 'data-live-month="1"')}</div><div class="quest-history">${
    calendar.cycles
      .map(
        (c) =>
          `<article class="history-week-card">${art(c.target)}<div><h2>${escape(labels[c.target])} 공략</h2><p>${c.start_date} ~ ${c.end_date} · ${escape({ active: "진행 중", completed: "기간 종료", abandoned: "중단", draft: "시작 전" }[c.status])}</p>${[
            1, 2, 3, 4,
          ]
            .map((week) => {
              const from = new Date(c.start_date + "T00:00:00Z");
              from.setUTCDate(from.getUTCDate() + (week - 1) * 7);
              const start = from.toISOString().slice(0, 10);
              from.setUTCDate(from.getUTCDate() + 6);
              const end = from.toISOString().slice(0, 10);
              if (start.slice(0, 7) > month || end.slice(0, 7) < month)
                return "";
              const items = calendar.missions.filter(
                (m) =>
                  m.cycle_id === c.cycle_id &&
                  m.start_date <= end &&
                  m.end_date >= start,
              );
              return `<h3>${week}주차 · ${start} ~ ${end}</h3><ul>${items.map((m) => `<li>${escape(m.title)} · 이달 ${m.logs.filter((l) => l.date >= start && l.date <= end).length}회 완료${m.status === "abandoned" ? " · 중단" : ""}</li>`).join("") || "<li>선택한 챌린지가 없어요.</li>"}</ul>`;
            })
            .join("")}</div></article>`,
      )
      .join("") || "<p>이 달의 공략 이력이 없어요.</p>"
  }</div>`;
}
function chooseButton(button) {
  if (button.parentElement.getAttribute("aria-invalid")) clearFieldErrors();
  button.parentElement.querySelectorAll("button").forEach((b) => {
    b.classList.toggle("selected", b === button);
    b.setAttribute("aria-pressed", String(b === button));
  });
}
async function click(button) {
  // 메뉴에서 갈 곳을 고르면 메뉴를 닫는다. 모션 끄기 같은 메뉴 안 설정은 그대로 둔다
  const menu = button.closest("#app-menu");
  if (
    menu?.open &&
    (button.dataset.route ||
      button.dataset.mainTarget ||
      button.hasAttribute("data-live-logout"))
  )
    menu.close();
  if (button.dataset.profileSex) {
    sex = button.dataset.profileSex === "male" ? "M" : "F";
    chooseButton(button);
    return;
  }
  if (button.closest(".choice-options")) {
    smoking = button.textContent.trim() === "피워요";
    chooseButton(button);
    return;
  }
  const route = button.dataset.route;
  if (route) {
    if (route === "health") {
      healthRecordId = null;
      rememberPrediction(null);
    }
    await go(route);
    return;
  }
  const main = button.dataset.mainTarget;
  if (main) {
    if (main === "home") await go("risk");
    if (main === "book") await go("monsters");
    if (main === "bag") {
      bagTab = null;
      await go("rewards");
    }
    if (main === "records") await go("progress");
    if (main === "quests") {
      selected = null;
      const target = currentMonster();
      if (target && isAvailable(target)) await enterVillage(target.code);
      else await go("risk");
    }
    return;
  }
  if (button.dataset.villageKey || button.dataset.liveVillage) {
    await enterVillage(button.dataset.villageKey || button.dataset.liveVillage);
    return;
  }
  if (button.dataset.liveEvolution) {
    village = button.dataset.liveEvolution;
    await go("evolution");
    return;
  }
  if (button.hasAttribute("data-reselect")) {
    await go("risk");
    return;
  }
  if (button.hasAttribute("data-live-quests")) {
    selected = null;
    const target = currentMonster();
    if (target && isAvailable(target)) await enterVillage(target.code);
    else await go("risk");
    return;
  }
  if (button.hasAttribute("data-live-card")) {
    selected = $(".reco-list")._cards[Number(button.dataset.liveCard)];
    await go("today");
    return;
  }
  if (button.hasAttribute("data-live-mission")) {
    selected = missions[Number(button.dataset.liveMission)];
    await go("today");
    return;
  }
  if (button.dataset.liveReco) {
    await actOnRecommendation(selected, button.dataset.liveReco);
    return;
  }
  if (button.dataset.liveRestore) {
    const rows = (await allPages("/challenge-recommendations")).filter(
      (row) =>
        row.suppressed_until_manual &&
        row.challenge_id === Number(button.dataset.liveRestore),
    );
    for (const row of rows)
      await api(
        `/challenge-recommendations/${row.recommendation_id}/unsuppress`,
        {
          method: "PATCH",
        },
      );
    await go("reco");
    if (active === "reco") message("다시 추천받을 수 있어요.");
    return;
  }
  if (button.hasAttribute("data-live-start")) {
    await startChallenge();
    return;
  }
  if (button.hasAttribute("data-live-timer")) {
    const id = Number(button.dataset.liveTimer),
      o = selected.today_occurrences.find((o) => o.occurrence_id === id);
    const timer = await api(
      `/user-challenges/${selected.user_challenge_id}/timers`,
      {
        method: "POST",
        body: o.slot_code ? { context_slot: o.slot_code } : {},
      },
    );
    timerSessions.set(id, timer);
    paintTimer(id, timer);
    return;
  }
  if (button.hasAttribute("data-live-complete")) {
    await complete(Number(button.dataset.liveComplete));
    return;
  }
  if (button.hasAttribute("data-live-stop")) {
    if (
      confirm(
        "이 챌린지를 중단할까요? 이전 수행 기록과 XP·공략 점수는 유지돼요.",
      )
    ) {
      await api(`/user-challenges/${selected.user_challenge_id}/stop`, {
        method: "POST",
        body: {},
      });
      selected = null;
      await go("today");
    }
    return;
  }
  if (button.dataset.growthTab || button.dataset.growthOpen) {
    growth = button.dataset.growthTab || button.dataset.growthOpen;
    await go("progress");
    return;
  }
  if (button.dataset.liveBag) {
    bagTab = button.dataset.liveBag;
    await go("rewards");
    return;
  }
  if (button.hasAttribute("data-live-position")) {
    const pos = Number(button.dataset.livePosition);
    if (pendingPositions.has(pos)) pendingPositions.delete(pos);
    else if (pendingPositions.size < 3) pendingPositions.add(pos);
    renderDraw($("#live-bag-panel"));
    return;
  }
  if (button.hasAttribute("data-live-claim")) {
    const drawId = currentDraw.draw_id;
    const receipt = await api(`/reward-draws/${drawId}/claim`, {
      method: "POST",
      body: { positions: [...pendingPositions] },
    });
    pendingPositions.clear();
    await load();
    currentDraw = receipt;
    await renderBag();
    if (receipt.claimed_at) renderDrawReceipt(receipt);
    return;
  }
  if (button.dataset.liveEquip) {
    const item = catalog.find((i) => i.code === button.dataset.liveEquip);
    const section = ["hat", "bag", "hand", "shoes"].includes(item.slot)
      ? "equipment"
      : "room";
    const code =
      adventurer[section]?.[item.slot] === item.code ? null : item.code;
    await api("/adventurer/me", {
      method: "PATCH",
      body: { [section]: { [item.slot]: code } },
    });
    await go("rewards");
    message("꾸미기 설정을 저장했어요.");
    return;
  }
  if (button.hasAttribute("data-live-upgrade")) {
    await api("/adventurer/me/upgrade", { method: "POST" });
    await go("rewards");
    message("아이템이 한 단계 성장했어요.");
    return;
  }
  if (button.hasAttribute("data-live-month")) {
    const first = new Date(month + "-01T12:00:00Z");
    first.setUTCMonth(first.getUTCMonth() + Number(button.dataset.liveMonth));
    month = first.toISOString().slice(0, 7);
    await go("progress");
    return;
  }
  if (button.id === "back-button") {
    await go(history.pop() || "risk", false);
    return;
  }
  if (button.id === "menu-toggle") {
    $("#app-menu").showModal();
    return;
  }
  if (button.id === "menu-close") {
    $("#app-menu").close();
    return;
  }
  if (["motion-toggle", "menu-motion-toggle"].includes(button.id)) {
    document.body.classList.toggle("reduce-motion");
    syncMotion();
    return;
  }
  if (button.hasAttribute("data-medical-open")) {
    $("#medical-dialog").showModal();
    return;
  }
  if (button.id === "medical-close") {
    $("#medical-dialog").close();
    return;
  }
  if (button.hasAttribute("data-live-retry")) {
    if (predictionId) await pollPrediction();
    else await saveIntake();
    return;
  }
  if (button.hasAttribute("data-live-logout")) {
    await auth.logout();
    reset();
    $$("form").forEach((f) => f.reset());
    await go("login");
    return;
  }
}
function renderDrawReceipt(receipt) {
  const remaining = draws.filter((d) => !d.claimed_at).length;
  const panel = $("#live-bag-panel");
  panel.innerHTML = `<h2>보상 3개를 받았어요!</h2><div class="reward-results">${receipt.results.map((i) => `<article class="draw-result ${i.rarity.toLowerCase()}"><span class="rarity">${i.rarity}</span>${i.asset ? `<div class="equipment-thumbnail"><img src="${asset(i.asset)}" alt=""></div>` : "✦"}<h3>${escape(i.name)}</h3><p>${i.duplicate ? "중복 → " : ""}${i.materials ? "성장의 조각 +" + i.materials : "새 보상 획득"}</p></article>`).join("")}</div>${remaining ? button(`다음 보상 고르기 · ${remaining}회`, 'data-live-bag="draw"') : ""}${button("바로 꾸미기", 'data-live-bag="adventurer"')}`;
}
document.addEventListener("click", (event) => {
  const target = event.target.closest("button");
  if (!target || target.disabled) return;
  run(() => click(target), target).finally(() => {
    if (
      target.dataset.liveTimer &&
      timerSessions.has(Number(target.dataset.liveTimer))
    )
      target.disabled = true;
  });
});
document.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  run(async () => {
    if (form.classList.contains("login-form")) {
      const accepted = await auth.login({
        email: form.querySelector('[type="email"]').value.trim(),
        password: form.querySelector('[type="password"]').value,
      });
      if (accepted) {
        form.reset();
        await go("risk");
      }
      return;
    }
    if (form.classList.contains("signup-form")) {
      const passwords = form.querySelectorAll('[type="password"]');
      const email = form.querySelector('[type="email"]');
      if (!$("#nickname").value.trim())
        throw fieldError($("#nickname"), "닉네임을 입력해주세요.");
      if (!email.value || !email.validity.valid)
        throw fieldError(email, "이메일 형식을 확인해주세요.");
      if (!/^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(passwords[0].value))
        throw fieldError(
          passwords[0],
          "비밀번호는 영문·숫자를 포함해 8자 이상 입력해주세요.",
        );
      if (passwords[0].value !== passwords[1].value)
        throw fieldError(passwords[1], "비밀번호가 서로 달라요.");
      if (!form.querySelector('[type="checkbox"]').checked)
        throw fieldError(
          form.querySelector('[type="checkbox"]'),
          "의료 고지 동의가 필요해요.",
        );
      signupDraft = {
        email: form.querySelector('[type="email"]').value.trim(),
        password: passwords[0].value,
        nickname: $("#nickname").value.trim(),
        disclaimer_agreed: true,
      };
      passwords.forEach((p) => (p.value = ""));
      await go("health");
      return;
    }
    if (form.closest(".health")) {
      profile();
      const values = healthValues("health");
      if (!values.weight_kg)
        throw fieldError(
          $('.health [aria-label="체중"]'),
          "체중을 입력해주세요.",
        );
      if (!values.waist_cm)
        throw fieldError(
          $('.health [aria-label="허리둘레"]'),
          "허리둘레를 입력해주세요.",
        );
      checkRanges("health");
      await go("health2");
      return;
    }
    if (form.closest(".health2")) {
      validateHealth();
      await go("health3");
      return;
    }
    if (form.closest(".health3")) {
      await saveIntake();
      return;
    }
    if (form.id === "live-daily") {
      const values = Object.fromEntries(
        [...new FormData(form)]
          .filter(([, v]) => v !== "")
          .map(([k, v]) => [k, Number(v)]),
      );
      if (!Object.keys(values).length)
        throw new Error("건강 수치를 하나 이상 입력해주세요.");
      await api("/health-records", {
        method: "POST",
        body: { input_mode: "daily", ...values },
      });
      await go("progress");
      message("오늘의 건강 기록을 저장했어요.");
    }
  }, form.querySelector('[type="submit"]'));
});
$("#alcohol-frequency").addEventListener("change", (event) => {
  const zero = event.target.value === "1";
  $("#alcohol-amount").closest("label").hidden = zero;
  if (zero) $("#alcohol-amount").value = "";
});
$$("input,select").forEach((el) =>
  el.addEventListener("input", () => {
    message("");
    if (el.getAttribute("aria-invalid")) clearFieldErrors();
  }),
);
const motion = matchMedia("(prefers-reduced-motion: reduce)");
document.body.classList.toggle("reduce-motion", motion.matches);
motion.addEventListener("change", () => {
  document.body.classList.toggle("reduce-motion", motion.matches);
  syncMotion();
});
const css = document.createElement("link");
css.rel = "stylesheet";
css.href = new URL("./live.css", import.meta.url);
document.head.append(css);
$$(
  ".prototype-disclosure,.prototype-banner,.prototype-notice,.prototype-status,.prototype-proposal,.rewards>.hint,.rewards .hint,.preview-note",
).forEach((el) => el.remove());
$(".waiting .waiting-bottom")?.insertAdjacentHTML(
  "beforeend",
  button("결과 다시 확인", "data-live-retry"),
);
$(".health h1")?.nextElementSibling?.replaceChildren(
  document.createTextNode("현재 건강정보를 입력해 주세요."),
);
$('#app-menu [data-route="signup"]')?.remove();
$("#app-menu").insertAdjacentHTML(
  "beforeend",
  button("로그아웃", "data-live-logout"),
);
$$(".required-note").forEach((el) => {
  if (el.textContent.includes("예측")) el.textContent = "*필수";
});
let accountOwner = null;
auth.subscribe((session) => {
  const nextOwner = session.user?.id ?? null;
  if (nextOwner === accountOwner) return;
  const previous = accountOwner;
  accountOwner = nextOwner;
  user = session.user;
  // 처음 로그인될 때(가입 직후 포함)는 입력 중인 건강정보를 지우지 않는다
  if (previous === null) return;
  reset();
  user = session.user;
  $$("form").forEach((form) => form.reset());
  $$("[data-profile-sex],.choice-options button").forEach((b) => {
    b.classList.remove("selected");
    b.setAttribute("aria-pressed", "false");
  });
  if (previous && !nextOwner)
    go("login").catch((error) => message(error.message, true));
});
// 실제 연결 모드는 예측이 끝나면 지도로 자동 이동한다. 시안용 예시 결과 버튼은 가짜 결과로 오해하게 한다
$('[data-page="waiting"] [data-route="risk"]')?.remove();
// 브라우저 뒤로가기·앞으로가기로 주소가 바뀌면 화면도 그 주소로 옮긴다
window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if (id && id !== active)
    go(id, false).catch((error) => message(error.message, true));
});
const initial = location.hash.slice(1);
await run(async () => {
  // 로그인 전에 열 수 있는 첫 화면은 로그인과 회원가입뿐이다. 건강정보 단계는 가입 정보가 있어야 한다
  if (!(await auth.restore()))
    return go(initial === "signup" ? "signup" : "login", false);
  const waiting = storedPrediction();
  if (initial === "waiting" && waiting) {
    predictionId = waiting;
    await go("waiting", false);
    await pollPrediction();
  } else
    await go(names[initial] && initial !== "waiting" ? initial : "risk", false);
});
