import {
  ActivityTimer,
  cycleView,
  kstDate,
  kstTimestamp,
  scoreView,
} from "./model.mjs";

const PAGES = {
  reco: "챌린지 선택",
  today: "오늘의 공략",
  progress: "공략 현황",
  monsters: "몬스터 도감",
};
const STATES = {
  rage: ["매우 주의", "danger"],
  caution: ["주의", "caution"],
  stable: ["안정", "stable"],
  not_contributing: ["현재 기여 없음", "neutral"],
  resolved: ["요인 해소됨", "resolved"],
  sealed: ["봉인 완료", "sealed"],
  unmeasured: ["미측정", "neutral"],
};
const DIFFICULTIES = { easy: "쉬움", normal: "보통", challenge: "도전" };
const METHODS = {
  timer: "타이머",
  manual: "직접 확인",
  photo: "사진 인증",
  value: "수치 기록",
  time: "시간 기록",
  system: "자동 인증",
};
const SLOTS = { lunch: "점심", dinner: "저녁" };
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const number = (value) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const sprite = (code) =>
  `<span class="sprite ${["viscera", "alde", "cotinine", "spike", "sodi"].includes(code) ? code : ""}" aria-hidden="true"></span>`;
const badge = (state) => {
  const [label, kind] = STATES[state] || STATES.unmeasured;
  return `<span class="badge ${kind}">${label}</span>`;
};
const meter = (label, text, fill, attr = "") =>
  `<div class="meter"><div class="meter-row"><span>${escape(label)}</span><b>${escape(text)}</b></div><div class="meter-rail"><i ${attr} style="--fill:${Math.max(0, Math.min(100, fill || 0))}%"></i></div></div>`;
const score = (target) => {
  const view = scoreView(target?.weekly_progress);
  return meter("이번 주 공략 점수", view.text, view.fill, "data-score-fill");
};
const goal = (card) =>
  [
    card.target_value == null ? null : `${card.target_value}${card.unit || ""}`,
    METHODS[card.verification_type] || "인증",
    card.context_label,
  ]
    .filter(Boolean)
    .join(" · ");

function monsterCard(item, target = false) {
  const impact = number(item.impact_score);
  return `<${target ? 'div class="target-card"' : `button class="monster-card" data-monster="${item.monster_id}"`}>
    ${sprite(item.code)}<div><h3>${escape(item.name)} ${badge(item.state)} ${item.is_target ? '<span class="target-mark">공략 대상</span>' : ""}</h3>
    <p>${escape(item.title || "위험요인 캐릭터")}</p><div class="threat-label">위협도 <b>${impact === null ? "—" : impact}</b></div>
    <div class="threat-rail"><i style="--fill:${impact === null ? 0 : Math.max(0, Math.min(100, impact))}%"></i></div></div></${target ? "div" : "button"}>`;
}

function errorMessage(error) {
  if (error.status === 401)
    return [
      "로그인이 필요해요",
      "다시 로그인한 뒤 공략을 이어가세요.",
      "login",
    ];
  const messages = {
    PRED_NOT_FOUND: [
      "예측 결과를 확인하고 있어요",
      "현재 건강기록과 맞는 예측 결과가 필요해요. 결과 확인 후 다시 추천받아주세요.",
      "risk",
    ],
    CHLG_RECOMMENDATION_UNAVAILABLE: [
      "지금 추천 가능한 챌린지가 없어요",
      "추천 근거를 준비 중이거나 이번 주기에 더 시작할 수 있는 챌린지가 없어요. 잠시 후 다시 확인해주세요.",
      null,
    ],
    CHLG_LOG_DUPLICATED: [
      "이미 기록된 회차예요",
      "새로고침해 오늘 남은 기회를 확인해주세요.",
      null,
    ],
    CHLG_NOT_ACTIVE: [
      "기간이 끝났거나 중단된 챌린지예요",
      "공략 현황을 확인하고 새로운 챌린지를 골라주세요.",
      null,
    ],
    CHLG_LIMIT_EXCEEDED: [
      "추가로 시작할 수 없어요",
      "진행 중인 챌린지와 주기별 추가 가능 횟수를 확인해주세요.",
      null,
    ],
    CHLG_VERIFICATION_FAILED: [
      "수행 내용을 확인해주세요",
      "목표 시간과 인증 방식을 다시 확인해주세요.",
      null,
    ],
  };
  if (messages[error.code]) {
    const [title, copy, route] = messages[error.code];
    return [title, error.message || copy, route];
  }
  if (error.status === 0)
    return [
      "연결이 끊겼어요",
      "처리 결과를 확인하지 못했어요. 목록을 새로고침한 뒤 확인해주세요.",
      null,
    ];
  return [
    "내용을 불러오지 못했어요",
    error.status >= 400 && error.status < 500
      ? error.message || "입력 내용을 확인해주세요."
      : "잠시 후 다시 시도해주세요.",
    null,
  ];
}

/** 공통 페이지 안에 D 화면만 붙인다. 인증·다른 화면 이동·사진 업로드는 호출자가 연결한다. */
export function mountDangoScreens(
  root,
  {
    request,
    navigate = () => {},
    onPageChange = () => {},
    uploadPhoto,
    generateRecommendations = () =>
      request("/challenge-recommendations/generate", { method: "POST" }),
    now = () => new Date(),
    clock,
    embedded = false,
  } = {},
) {
  if (!root || typeof request !== "function")
    throw new Error("화면 영역과 API 호출 함수를 전달해주세요.");
  const state = {
    page: "today",
    mode: "loading",
    version: 0,
    cards: [],
    excluded: [],
    authEpoch: 0,
    selected: new Set(),
    scheduledDates: new Set(),
    scheduleEnd: null,
    capacity: 0,
    monsters: [],
    missions: [],
    history: [],
    rewards: [],
    level: null,
    experimental: false,
    message: "",
    error: null,
    busy: false,
    timers: new Map(),
  };
  root.innerHTML = embedded
    ? `<div data-message role="status" aria-live="polite" hidden></div><div class="screen" data-content></div><dialog class="dango-dialog" aria-labelledby="d-dialog-title"></dialog>`
    : `<div class="topbar"><button type="button" data-back aria-label="이전 화면">‹</button><span data-screen-name></span><button type="button" data-reload aria-label="새로고침">↻</button></div>
    <div data-message role="status" aria-live="polite" hidden></div><div class="screen" data-content></div>
    <nav class="bottom-nav" aria-label="앱 메뉴">${Object.entries(PAGES)
      .map(
        ([key, label]) => `<a href="#${key}" data-route="${key}">${label}</a>`,
      )
      .join("")}</nav>
    <dialog class="dango-dialog" aria-labelledby="d-dialog-title"></dialog>`;
  const content = root.querySelector("[data-content]");
  const dialog = root.querySelector("dialog");
  let dialogListener;
  let loadController;

  function scheduleLimit() {
    if (state.scheduleEnd) return state.scheduleEnd;
    const date = new Date(`${kstDate(now())}T12:00:00+09:00`);
    date.setTime(date.getTime() + 27 * 86400000);
    return kstDate(date);
  }
  function needsSchedule() {
    return state.cards.some(
      (card) =>
        state.selected.has(card.recommendation_id) &&
        card.context_type === "event",
    );
  }

  async function collection(path) {
    const items = [];
    let page = 1;
    while (true) {
      const data = await request(
        `${path}${path.includes("?") ? "&" : "?"}page=${page}&size=100`,
      );
      if (!Array.isArray(data.items))
        throw new Error("목록 응답을 확인해주세요.");
      items.push(...data.items);
      if (items.length >= data.total || !data.items.length) return items;
      page += 1;
    }
  }

  function target() {
    return (
      state.monsters.find((item) => item.is_target) ||
      state.monsters.find(
        (item) =>
          item.monster_id === state.cards[0]?.target_monster?.monster_id,
      )
    );
  }
  function message(text = "", isError = false) {
    state.message = text;
    const element = root.querySelector("[data-message]");
    element.hidden = !text;
    element.className = `notice-message${isError ? " error" : ""}`;
    element.textContent = text;
  }
  function empty(title, copy, route = "reco") {
    return `<div class="status-panel"><h2>${escape(title)}</h2><p>${escape(copy)}</p><button class="secondary" data-route="${route}">${route === "reco" ? "챌린지 고르기" : "공략 현황 보기"}</button></div>`;
  }
  function excludedCards() {
    const groups = new Map();
    state.excluded.forEach((card) => {
      if (!groups.has(card.challenge_id)) groups.set(card.challenge_id, card);
    });
    if (!groups.size) return "";
    return `<h2 class="history-title">추천에서 제외한 챌린지</h2>${[...groups.values()].map((card) => `<div class="mission-card"><h3>${escape(card.title)}</h3><button class="secondary" data-restore="${card.challenge_id}">추천 다시 켜기</button></div>`).join("")}`;
  }
  function renderReco() {
    return `<h1>공략 대상과 함께할<br>챌린지를 골라요.</h1><p class="small-copy">하나의 몬스터를 공략하는 28일 주기예요.</p>
      ${target() ? monsterCard(target(), true) : ""}<button class="target-swap" data-route="monsters">도감에서 공략 대상 확인하기</button>
      ${state.experimental ? '<p class="pending-note">실험 모델의 추천 결과예요.</p>' : ""}
      <div class="pick-bar"><span>이번에 시작 가능한 챌린지</span><span>선택 <b data-pick-count>${state.selected.size}</b> / ${state.capacity}</span></div>
      <div class="reco-list">${state.cards
        .map(
          (
            card,
          ) => `<article class="reco-card ${state.selected.has(card.recommendation_id) ? "selected" : ""}">
        <button type="button" class="select-card" data-pick="${card.recommendation_id}" aria-pressed="${state.selected.has(card.recommendation_id)}">
        <div class="reco-head"><h3>${escape(card.title)}</h3><span class="badge ${card.difficulty === "challenge" ? "danger" : "neutral"}">${DIFFICULTIES[card.difficulty] || "챌린지"}</span></div>
        <p class="reco-why">${escape(card.description || "공략 대상의 위험요인에 맞춰 추천했어요.")}</p>
        <div class="reco-meta"><span class="chip">하루 ${escape(card.daily_target_count)}회</span><span class="chip">${escape(goal(card))}</span>${number(card.daily_xp) !== null ? `<span class="chip xp">하루 목표 ${card.daily_xp} XP</span>` : ""}</div></button>
        <div class="card-actions"><button data-reject="${card.recommendation_id}">나중에 할게요</button><button data-exclude="${card.recommendation_id}">해당 없어요</button></div></article>`,
        )
        .join("")}</div>
      ${!state.cards.length ? '<div class="status-panel"><p>추천 카드를 모두 확인했어요.</p><button class="secondary" data-generate>다른 챌린지 추천받기</button></div>' : ""}
      ${
        needsSchedule()
          ? `<section class="ui-card"><h2>예정 이용일 확인</h2><p class="hint">실제로 이용할 날짜만 추가해주세요. 선택한 날만 수행 기회로 잡습니다.</p><label class="stack-field">예정 이용일<input type="date" data-schedule-date min="${kstDate(now())}" max="${scheduleLimit()}"></label><button class="secondary" data-add-date>이용일 추가</button><div>${[
              ...state.scheduledDates,
            ]
              .sort()
              .map(
                (day) =>
                  `<button class="secondary" data-remove-date="${day}">${day} 삭제</button>`,
              )
              .join("")}</div></section>`
          : ""
      }
      <p class="hint">1주차에는 최대 2개, 2주차부터 주기당 1개를 더 시작할 수 있어요. 동시 진행은 최대 3개예요.</p>
      <button class="primary" data-start ${state.selected.size ? "" : "disabled"}>선택한 챌린지 시작하기</button>${excludedCards()}`;
  }
  function getTimer(occurrenceId) {
    if (!state.timers.has(occurrenceId))
      state.timers.set(occurrenceId, new ActivityTimer(clock));
    return state.timers.get(occurrenceId);
  }
  function renderOccurrence(mission, item) {
    const done = item.status === "completed";
    const planned = item.status === "planned";
    const earlier =
      !item.slot_code &&
      mission.today_occurrences.some(
        (other) =>
          other.status === "planned" && other.sequence_no < item.sequence_no,
      );
    const currentDate = mission.today_date === kstDate(now());
    const usable = planned && !earlier && currentDate;
    const title = `${mission.title} · ${SLOTS[item.slot_code] || `${item.sequence_no}회차`}`;
    let controls = "";
    if (usable && mission.verification_type === "timer") {
      const timer = getTimer(item.occurrence_id);
      controls = `<div class="slot-controls"><output class="timer-number" data-timer-output="${item.occurrence_id}" aria-label="수행 시간">${timer.display}</output>
        <div class="timer-actions"><button data-timer-start="${item.occurrence_id}">${timer.running ? "일시정지" : "타이머 시작"}</button>
        <button class="secondary" data-timer-submit="${item.occurrence_id}" ${timer.ready(mission.target_value) ? "" : "disabled"}>수행 인증하기</button></div><p class="hint">회차별로 ${escape(mission.target_value ?? "—")}${escape(mission.unit || "분")} 이상 수행하면 인증할 수 있어요.</p></div>`;
    } else if (usable && mission.verification_type === "manual")
      controls = `<div class="slot-controls"><button class="secondary" data-manual="${item.occurrence_id}">직접 수행 확인하기</button></div>`;
    else if (usable && mission.verification_type === "photo")
      controls = `<div class="slot-controls photo-controls">
      ${uploadPhoto ? `<label>수행 사진 선택<input type="file" accept="image/*" capture="environment" data-photo="${item.occurrence_id}"></label><button class="secondary" data-upload="${item.occurrence_id}">사진으로 인증하기</button>` : '<p class="hint">지금은 사진 인증을 사용할 수 없어요. 잠시 후 다시 확인해주세요.</p>'}
      ${mission.manual_fallback_allowed ? `<button class="secondary" data-fallback="${item.occurrence_id}">직접 수행 확인으로 대체</button>` : ""}</div>`;
    else if (usable)
      controls =
        '<div class="slot-controls"><p class="hint">이 인증 방식은 아직 사용할 수 없어요.</p></div>';
    const label = done
      ? "인정 완료"
      : !currentDate
        ? "새로고침 필요"
        : earlier
          ? "앞 회차부터 수행해주세요"
          : planned
            ? goal(mission)
            : item.status === "skipped"
              ? "건너뛴 기회"
              : "종료된 기회";
    const dailyCloseHint = usable && ["오늘 외식 안 하기", "오늘 술 안 마시기", "오늘 안 피우기"].includes(mission.title)
      ? '<p class="hint">해당 날짜의 하루를 마친 뒤 기록해주세요.</p>'
      : "";
    return `<article class="slot-wrap"><div class="slot ${done ? "done" : ""}"><div><h4>${escape(title)}</h4><p>${escape(label)}</p></div>${done ? '<span class="badge stable">완료</span>' : ""}</div>${dailyCloseHint}${controls}</article>`;
  }
  function renderToday() {
    if (!state.missions.length)
      return `<h1>오늘의 공략을 시작해요.</h1>${empty("진행 중인 챌린지가 없어요", "내게 맞는 챌린지를 골라 작은 실천을 시작하세요.")}`;
    const first = state.missions[0];
    const view = cycleView(first, first.today_date || kstDate(now()));
    const remaining = state.missions.reduce(
      (count, mission) =>
        count +
        (mission.today_occurrences || []).filter(
          (item) => item.status === "planned",
        ).length,
      0,
    );
    return `<div class="day-head"><b>${view.day}일차 / ${view.length}일</b><span>오늘 남은 기회 ${remaining}회</span></div>
      <h1>오늘의 공략이<br>기다리고 있어요.</h1><p class="small-copy">인정된 수행만 공략 점수에 들어가요.</p>
      <div class="slot-list">${state.missions.map((mission) => (mission.today_occurrences || []).map((item) => renderOccurrence(mission, item)).join("")).join("")}</div>
      ${!remaining ? '<p class="hint">오늘 남은 예정 기회가 없어요. 이미 인정한 기회는 다시 수행해도 추가 보상이 없어요.</p>' : ""}
      ${score(target())}<p class="hint">타이머의 부족분과 초과시간은 다른 회차로 넘어가지 않아요.</p><button class="primary" data-route="progress">공략 현황 보기</button>`;
  }
  function missionCard(item, historical = false) {
    const rate = number(item.progress_rate);
    const label = historical
      ? item.status === "abandoned"
        ? "중단"
        : "기간 종료"
      : `${item.cycle_week || 1}주차`;
    return `<article class="mission-card"><h3>${escape(item.title)} <span class="badge neutral">${label}</span></h3>
      <p>${escape(item.start_date)} ~ ${escape(item.end_date)}<br>인정 완료 ${escape(item.completed_count)} / 예정 ${escape(item.scheduled_opportunity_count)}회</p>
      ${meter("예정 기회 수행률", rate === null ? "미평가" : `${(rate * 100).toFixed(1)}%`, rate === null ? 0 : rate * 100)}
      <p>습관 형성: ${item.habit_established == null ? "미평가" : item.habit_established ? "평가 완료" : "평가 결과 없음"}</p>
      ${historical ? "" : `<button class="secondary" data-stop="${item.user_challenge_id}">챌린지 중단</button>`}</article>`;
  }
  function rewards() {
    return `<h2 class="history-title">내가 얻은 보상</h2><div class="reward-list">${state.rewards.length ? state.rewards.map((item) => `<div class="owned"><span class="gem" aria-hidden="true">◇</span><div><h4>${escape(item.name)}</h4><p>${item.motivation_type === "grow" ? "성장형" : item.motivation_type === "decorate" ? "장식형" : "수집형"} · ${escape(item.item_level)}단계</p></div></div>`).join("") : '<p class="hint">아직 획득한 보상이 없어요.</p>'}</div>`;
  }
  function renderProgress() {
    const first = state.missions[0];
    const view = first
      ? cycleView(first, first.today_date || kstDate(now()))
      : null;
    const level = state.level;
    const max = number(level?.next_level_xp);
    return `<h1>${first ? `${escape(first.target_monster?.name || "챌린지")} 공략,<br>${view.day}일째 이어가는 중이에요.` : "나의 공략 현황이에요."}</h1>
      <p class="small-copy">공략 점수는 월요일 0시에 초기화돼요.</p>${score(target())}
      ${view ? meter("공략 주기 진행", `${view.day}일 / ${view.length}일`, (view.day / view.length) * 100) : empty("진행 중인 챌린지가 없어요", "지난 기록을 확인하고 새로운 챌린지를 골라보세요.")}
      ${level ? meter(`레벨 ${level.level} · 경험치`, max === null ? `${level.total_xp} XP` : `${level.current_level_xp} / ${max} XP`, max ? (level.current_level_xp / max) * 100 : 100) : ""}
      ${state.missions.map((item) => missionCard(item)).join("")}${rewards()}
      <p class="hint">위협도와 위험도는 재측정 때 달라져요. 수행을 인정받으면 이번 주 공략 점수가 올라가요.</p>
      ${state.history.length ? `<h2 class="history-title">지난 챌린지</h2>${state.history.map((item) => missionCard(item, true)).join("")}` : ""}
      <button class="primary" data-route="reco">챌린지 추천받기</button>`;
  }
  function renderMonsters() {
    return `<h1>몬스터의 약점을 공략하며<br>작은 변화를 이어가요.</h1><p class="small-copy">위협도는 현재 기록 기준이에요. 공략 점수와는 별개예요.</p>
      <div class="monster-list">${state.monsters.map((item) => monsterCard(item)).join("")}</div>
      ${!state.monsters.length ? '<div class="status-panel"><p>아직 표시할 몬스터가 없어요. 건강정보를 기록한 뒤 다시 확인해주세요.</p><button class="secondary" data-route="health">건강정보 기록하기</button></div>' : ""}
      ${score(target())}${rewards()}<div class="state-legend"><h4>도감 상태</h4><ul>${Object.entries(
        STATES,
      )
        .map(([key]) => `<li>${badge(key)}</li>`)
        .join(
          "",
        )}</ul><p class="legend-note">위협도 0은 현재 기여 없음, 값이 없으면 미측정이에요. 28일 기간 종료로 새 봉인이 생기지는 않아요.</p></div>
      <button class="primary" data-route="reco">챌린지 고르기</button>`;
  }
  function render() {
    const screenName = root.querySelector("[data-screen-name]");
    if (screenName) screenName.textContent = PAGES[state.page];
    onPageChange(state.page);
    root.querySelectorAll("[data-route]").forEach((link) => {
      const route = link.dataset.route || link.hash?.slice(1);
      if (route === state.page) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    if (state.mode === "loading")
      content.innerHTML =
        '<div class="loading" role="status"><span class="spinner" aria-hidden="true"></span><p>공략 내용을 불러오고 있어요.</p></div>';
    else if (state.mode === "error") {
      const [title, copy, route] = errorMessage(state.error);
      content.innerHTML = `<section class="scene"><div class="panel-pad"><div class="status-panel" role="alert"><h2>${escape(title)}</h2><p>${escape(copy)}</p>${route ? `<button class="primary" data-route="${route}">${route === "login" ? "로그인하기" : "예측 결과 확인하기"}</button>` : ""}<button class="secondary" data-reload>다시 확인하기</button></div>${state.page === "reco" ? excludedCards() : ""}</div></section>`;
    } else
      content.innerHTML = `<section class="scene ${state.page}"><div class="panel-pad">${{ reco: renderReco, today: renderToday, progress: renderProgress, monsters: renderMonsters }[state.page]()}</div></section>`;
    const title = content.querySelector("h1, h2");
    if (title) {
      title.classList.add("screen-title");
      title.tabIndex = -1;
    }
    if (state.busy)
      root
        .querySelectorAll("button:not([data-dialog-choice])")
        .forEach((button) => {
          button.disabled = true;
        });
  }

  async function load(page = state.page) {
    if (!PAGES[page]) return navigate(page);
    const version = ++state.version;
    loadController?.abort();
    loadController = new AbortController();
    const signal = loadController.signal;
    state.page = page;
    state.mode = "loading";
    state.error = null;
    state.selected.clear();
    state.scheduledDates.clear();
    render();
    try {
      const monsters = await request("/monsters/me");
      let data;
      if (page === "reco") {
        const history = await collection("/challenge-recommendations");
        if (version !== state.version) return;
        state.excluded = history.filter((card) => card.suppressed_until_manual);
        data = await generateRecommendations({ signal });
      } else if (page === "today")
        data = await collection("/user-challenges?status=active");
      else if (page === "progress")
        data = await Promise.all([
          collection("/user-challenges?status=active"),
          collection("/user-challenges?status=abandoned"),
          collection("/user-challenges?status=graduated"),
          collection("/rewards/me"),
          request("/users/me/level"),
        ]);
      else data = await collection("/rewards/me");
      if (version !== state.version) return;
      state.monsters = monsters.items;
      if (page === "reco") {
        state.cards = data.items;
        state.scheduleEnd = data.cycle_end_date || null;
        state.capacity = Number.isInteger(data.remaining_slots)
          ? Math.max(0, Math.min(3, data.remaining_slots))
          : 0;
        state.experimental = data.model_experimental === true;
        if (!Number.isInteger(data.remaining_slots))
          throw new Error("선택 가능 개수를 확인할 수 없습니다.");
      } else if (page === "today") state.missions = data;
      else if (page === "progress")
        [state.missions, state.history, state.rewards, state.level] = [
          data[0],
          [...data[1], ...data[2]].sort((a, b) =>
            b.end_date.localeCompare(a.end_date),
          ),
          data[3],
          data[4],
        ];
      else state.rewards = data;
      state.mode = "ready";
      render();
    } catch (error) {
      if (version !== state.version) return;
      if (error.status === 401) {
        state.cards = [];
        state.excluded = [];
        state.missions = [];
        state.history = [];
        state.monsters = [];
        state.rewards = [];
        state.level = null;
        state.timers.clear();
      }
      state.error = error;
      state.mode = "error";
      render();
    }
  }
  async function show(page) {
    if (!PAGES[page]) return navigate(page);
    if (location.hash !== `#${page}`) {
      history.pushState(null, "", `#${page}`);
    }
    await load(page);
    content.querySelector(".screen-title")?.focus({ preventScroll: true });
  }
  function ask(title, copy, choices = [{ key: "confirm", text: "확인" }]) {
    if (dialog.open) return Promise.resolve(null);
    dialog.innerHTML = `<h2 id="d-dialog-title">${escape(title)}</h2><p>${escape(copy)}</p><div class="dialog-choices">${choices.map((item) => `<button data-dialog-choice="${item.key}">${escape(item.text)}</button>`).join("")}</div><button class="secondary" data-dialog-choice="cancel">취소</button>`;
    return new Promise((resolve) => {
      dialogListener = () => {
        dialog.removeEventListener("close", dialogListener);
        resolve(
          dialog.returnValue === "cancel" ? null : dialog.returnValue || null,
        );
      };
      dialog.addEventListener("close", dialogListener);
      dialog.returnValue = "";
      dialog.showModal();
    });
  }
  function findOccurrence(id) {
    for (const mission of state.missions) {
      const item = (mission.today_occurrences || []).find(
        (occurrence) => occurrence.occurrence_id === id,
      );
      if (item) return { mission, item };
    }
    return null;
  }
  async function mutate(operation, after) {
    if (state.busy) return;
    const identity = state.authEpoch;
    state.busy = true;
    root
      .querySelectorAll("button:not([data-dialog-choice])")
      .forEach((button) => {
        button.disabled = true;
      });
    try {
      const result = await operation();
      if (identity !== state.authEpoch) return;
      state.busy = false;
      await after?.(result);
    } catch (error) {
      if (identity !== state.authEpoch) return;
      state.busy = false;
      // 결과가 불분명한 쓰기 요청은 재전송하지 않고 현재 목록을 다시 읽는다.
      if (state.page === "reco") {
        try {
          const listed = await collection("/challenge-recommendations");
          const available = new Set(
            listed
              .filter((card) => card.action == null)
              .map((card) => card.recommendation_id),
          );
          state.cards = state.cards.filter((card) =>
            available.has(card.recommendation_id),
          );
          state.selected.clear();
          render();
        } catch {
          state.mode = "error";
          state.error = error;
          render();
        }
      } else await load(state.page);
      message(errorMessage(error)[1], true);
    } finally {
      if (identity === state.authEpoch) state.busy = false;
    }
  }
  async function start() {
    if (!state.selected.size || state.selected.size > state.capacity) return;
    const ids = [...state.selected];
    if (needsSchedule() && !state.scheduledDates.size) {
      message("예정 이용일을 한 날짜 이상 확인해주세요.", true);
      return;
    }
    const needsSafety = state.cards.some(
      (card) =>
        ids.includes(card.recommendation_id) && card.safety_check_required,
    );
    let safety;
    if (needsSafety) {
      if (
        !(await ask(
          "안전하게 수행할 수 있나요?",
          "현재 건강상태에서 무리 없이 수행할 수 있을 때 시작해주세요. 통증이나 불편이 생기면 중단하세요.",
          [{ key: "confirm", text: "확인하고 시작하기" }],
        ))
      )
        return;
      safety = true;
    }
    await mutate(
      () =>
        request("/user-challenges", {
          method: "POST",
          body: {
            recommendation_ids: ids,
            ...(safety ? { safety_confirmed: true } : {}),
            ...(needsSchedule()
              ? { scheduled_dates: [...state.scheduledDates].sort() }
              : {}),
          },
        }),
      async () => {
        state.timers.clear();
        message("챌린지를 시작했어요. 오늘 예정 기회를 확인해주세요.");
        if (embedded) await navigate("today");
        else await show("today");
      },
    );
  }
  async function act(id, action) {
    if (
      !(await ask(
        action === "rejected" ? "나중에 할까요?" : "이 챌린지를 제외할까요?",
        action === "rejected"
          ? "다른 챌린지를 선택할 수 있어요."
          : "직접 다시 켜기 전까지 추천에서 제외돼요.",
      ))
    )
      return;
    await mutate(
      async () => {
        const body = { action };
        try {
          return await request(`/challenge-recommendations/${id}`, {
            method: "PATCH",
            body,
          });
        } catch (error) {
          if (error.code !== "CHLG_INVALID_COOLDOWN") throw error;
          const choice = await ask(
            "언제 다시 추천받을까요?",
            "같은 챌린지를 연속으로 거절해 추천을 잠시 쉬어갈 수 있어요.",
            [
              { key: "7d", text: "7일 후" },
              { key: "30d", text: "30일 후" },
              { key: "until_manual", text: "직접 다시 켤 때까지" },
            ],
          );
          if (!choice) return null;
          return request(`/challenge-recommendations/${id}`, {
            method: "PATCH",
            body: { action, cooldown_choice: choice },
          });
        }
      },
      (result) => {
        if (result) {
          const card = state.cards.find(
            (item) => item.recommendation_id === id,
          );
          if (card && result.suppressed_until_manual) state.excluded.push(card);
          state.cards = state.cards.filter(
            (card) => card.recommendation_id !== id,
          );
          state.selected.delete(id);
        }
        render();
        if (result) message("선택을 저장했어요.");
      },
    );
  }
  async function record(id, method, extra = {}) {
    const entry = findOccurrence(id);
    if (!entry || entry.item.status !== "planned") return;
    if (entry.mission.today_date !== kstDate(now())) {
      await load("today");
      message("날짜가 바뀌어 오늘의 기회를 다시 불러왔어요.");
      return;
    }
    await mutate(
      () =>
        request(`/user-challenges/${entry.mission.user_challenge_id}/logs`, {
          method: "POST",
          body: {
            occurred_at: kstTimestamp(now()),
            verification_method: method,
            ...(entry.item.slot_code
              ? { context_slot: entry.item.slot_code }
              : {}),
            ...extra,
          },
        }),
      async (result) => {
        state.timers.delete(id);
        await load("today");
        let text = result.reward_eligible
          ? `수행을 인정받았어요. ${result.xp_granted} XP를 얻었어요.`
          : "기록을 저장했어요. 추가 점수와 보상은 없어요.";
        if (result.level_up) text += ` 레벨 ${result.new_level}이 되었어요.`;
        if (result.reward) text += ` ${result.reward.name}를 얻었어요.`;
        message(text);
      },
    );
  }
  async function handleClick(event) {
    const button = event.target.closest("button, a[data-route]");
    if (!button || !root.contains(button)) return;
    if (button.dataset.dialogChoice) {
      dialog.close(button.dataset.dialogChoice);
      return;
    }
    if (state.busy) {
      event.preventDefault();
      return;
    }
    if (button.dataset.route) {
      event.preventDefault();
      message();
      if (embedded) await navigate(button.dataset.route);
      else await show(button.dataset.route);
      return;
    }
    if (
      button.hasAttribute("data-reload") ||
      button.hasAttribute("data-generate")
    ) {
      message();
      await load();
      return;
    }
    if (button.hasAttribute("data-back")) {
      await show(state.page === "today" ? "reco" : "today");
      return;
    }
    if (button.dataset.pick) {
      const id = Number(button.dataset.pick);
      if (state.selected.has(id)) state.selected.delete(id);
      else if (state.selected.size < state.capacity) state.selected.add(id);
      else {
        message(
          `이번에는 최대 ${state.capacity}개까지 선택할 수 있어요.`,
          true,
        );
        return;
      }
      if (!needsSchedule()) state.scheduledDates.clear();
      render();
      root.querySelector(`[data-pick="${id}"]`)?.focus({ preventScroll: true });
      return;
    }
    if (button.hasAttribute("data-add-date")) {
      const input = root.querySelector("[data-schedule-date]");
      const day = input?.value;
      if (!day || day < kstDate(now()) || day > scheduleLimit()) {
        message("오늘부터 주기 종료일까지의 이용일을 선택해주세요.", true);
        return;
      }
      state.scheduledDates.add(day);
      render();
      return;
    }
    if (button.dataset.removeDate) {
      state.scheduledDates.delete(button.dataset.removeDate);
      render();
      return;
    }
    if (button.dataset.restore) {
      const cards = state.excluded.filter(
        (card) => card.challenge_id === Number(button.dataset.restore),
      );
      await mutate(
        async () => {
          for (const card of cards)
            await request(
              `/challenge-recommendations/${card.recommendation_id}/unsuppress`,
              { method: "PATCH" },
            );
        },
        async () => {
          await load("reco");
          message("다시 추천받을 수 있어요.");
        },
      );
      return;
    }
    if (button.hasAttribute("data-start")) {
      await start();
      return;
    }
    if (button.dataset.reject || button.dataset.exclude) {
      await act(
        Number(button.dataset.reject || button.dataset.exclude),
        button.dataset.reject ? "rejected" : "not_applicable",
      );
      return;
    }
    if (button.dataset.timerStart) {
      const timer = getTimer(Number(button.dataset.timerStart));
      if (timer.running) timer.pause();
      else {
        state.timers.forEach((other) => other.pause());
        timer.start();
      }
      render();
      return;
    }
    if (button.dataset.timerSubmit) {
      const id = Number(button.dataset.timerSubmit);
      const entry = findOccurrence(id);
      const timer = getTimer(id);
      if (!entry || !timer.ready(entry.mission.target_value)) return;
      timer.pause();
      await record(id, "timer", { value: timer.minutes });
      return;
    }
    if (button.dataset.manual || button.dataset.fallback) {
      const id = Number(button.dataset.manual || button.dataset.fallback);
      if (
        await ask(
          "실제로 수행했나요?",
          "이번 회차의 목표를 수행한 경우에만 확인해주세요.",
          [{ key: "confirm", text: "수행했어요" }],
        )
      )
        await record(
          id,
          button.dataset.fallback ? "manual_fallback" : "manual",
        );
      return;
    }
    if (button.dataset.upload) {
      const id = Number(button.dataset.upload);
      const file = root.querySelector(`[data-photo="${id}"]`)?.files[0];
      if (!file) {
        message("수행 사진을 먼저 골라주세요.", true);
        return;
      }
      if (!uploadPhoto) return;
      if (
        !(await ask(
          "이 사진으로 인증할까요?",
          "실제 수행 사진을 올려 인증해요. 사진 내용의 AI 판별은 하지 않아요.",
        ))
      )
        return;
      state.busy = true;
      button.disabled = true;
      try {
        const uploaded = await uploadPhoto(file);
        if (
          typeof uploaded?.evidence_url !== "string" ||
          !uploaded.evidence_url
        )
          throw new Error("사진 참조값이 없습니다.");
        state.busy = false;
        await record(id, "photo", { evidence_url: uploaded.evidence_url });
      } catch {
        message("사진을 올리지 못했어요. 다시 시도해주세요.", true);
        state.busy = false;
        render();
      }
      return;
    }
    if (button.dataset.stop) {
      if (
        !(await ask(
          "챌린지를 중단할까요?",
          "이미 인정받은 수행과 보상은 남아요. 다시 시작해도 주기 종료일과 추가 가능 횟수는 바뀌지 않아요.",
          [{ key: "confirm", text: "중단하기" }],
        ))
      )
        return;
      await mutate(
        () =>
          request(`/user-challenges/${button.dataset.stop}/stop`, {
            method: "POST",
            body: {},
          }),
        async () => {
          state.timers.clear();
          await load("progress");
          message("챌린지를 중단했어요.");
        },
      );
      return;
    }
    if (button.dataset.monster) {
      const item = state.monsters.find(
        (monster) => monster.monster_id === Number(button.dataset.monster),
      );
      if (!item) return;
      const stateLabel = (STATES[item.state] || STATES.unmeasured)[0];
      const sealed = item.sealed_at
        ? ` 봉인 기록: ${item.sealed_at.slice(0, 10)} · ${item.seal_count}회.`
        : "";
      const choice = await ask(
        item.name,
        `${stateLabel}. 위협도 ${item.impact_score == null ? "미측정" : item.impact_score}. 이번 주 공략 점수 ${item.weekly_progress}. ${item.is_target ? "현재 공략 대상이에요." : ""}${sealed} 위협도는 재측정 결과로 갱신돼요.`,
        [
          ...(item.target_change_allowed &&
          !item.is_target &&
          Number.isInteger(item.user_monster_id)
            ? [{ key: "change", text: "이 몬스터 공략하기" }]
            : []),
          { key: "confirm", text: "도감으로 돌아가기" },
        ],
      );
      if (choice === "change")
        await mutate(
          () =>
            request("/attack-cycles/current/target", {
              method: "PATCH",
              body: { user_monster_id: item.user_monster_id },
            }),
          async () => {
            await load("monsters");
            message(
              "시작 전 공략 대상을 변경했어요. 새 대상의 챌린지를 골라주세요.",
            );
          },
        );
    }
  }
  const clickListener = (event) => {
    void handleClick(event).catch(() => {
      state.busy = false;
      message("요청을 완료하지 못했어요. 새로고침해 확인해주세요.", true);
    });
  };
  const hashListener = () => {
    const page = location.hash.slice(1);
    if (PAGES[page]) {
      message();
      void load(page);
    }
  };
  const authListener = () => {
    ++state.authEpoch;
    state.busy = false;
    if (dialog.open) dialog.close("cancel");
    state.timers.clear();
    state.selected.clear();
    state.cards = [];
    state.excluded = [];
    state.missions = [];
    state.monsters = [];
    state.history = [];
    state.rewards = [];
    state.level = null;
    message();
    void load();
  };
  root.addEventListener("click", clickListener);
  if (!embedded) window.addEventListener("hashchange", hashListener);
  window.addEventListener("dango:auth-changed", authListener);
  const ticking = setInterval(() => {
    if (state.busy) return;
    root.querySelectorAll("[data-timer-output]").forEach((output) => {
      const id = Number(output.dataset.timerOutput);
      const timer = getTimer(id);
      const entry = findOccurrence(id);
      output.textContent = timer.display;
      const submit = root.querySelector(`[data-timer-submit="${id}"]`);
      if (submit && entry)
        submit.disabled =
          !timer.ready(entry.mission.target_value) ||
          entry.mission.today_date !== kstDate(now());
    });
  }, 250);
  if (!embedded)
    void load(PAGES[location.hash.slice(1)] ? location.hash.slice(1) : "today");
  return {
    show,
    reload: () => load(),
    destroy() {
      loadController?.abort();
      clearInterval(ticking);
      ++state.version;
      ++state.authEpoch;
      root.removeEventListener("click", clickListener);
      window.removeEventListener("hashchange", hashListener);
      window.removeEventListener("dango:auth-changed", authListener);
      if (dialog.open) dialog.close("cancel");
      state.timers.clear();
      root.replaceChildren();
    },
  };
}
