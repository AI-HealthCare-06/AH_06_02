/**
 * C 건강정보 입력 초안. health → health2 → health3 의 값을 모아 HLTH-01 한 번으로 보낸다.
 * 건강기록은 덮어쓰지 않으므로 단계마다 저장하지 않는다. 메모리에만 두고 새로고침하면 사라진다(1단계).
 * localStorage·sessionStorage·URL 에 건강정보를 넣지 않는다.
 */

export const STEPS = Object.freeze({
  health: ["weight_kg", "waist_cm", "family_history_dm", "family_history_htn"],
  health2: [
    "smoking_current",
    "alcohol_frequency",
    "alcohol_amount",
    "walking_days",
    "walking_minutes",
    "strength_days",
    "sitting_minutes",
    "dining_out_freq",
  ],
  health3: ["sbp", "dbp", "fasting_glucose", "hba1c", "triglyceride", "hdl"],
});

/** 하나라도 있으면 detail 이다. 비면 simple 로 보내고 이 키들은 아예 뺀다(extra="forbid"). */
export const MEASURED_FIELDS = STEPS.health3;

export const FIELD_LABELS = Object.freeze({
  weight_kg: "체중",
  waist_cm: "허리둘레",
  family_history_dm: "당뇨 가족력",
  family_history_htn: "고혈압 가족력",
  smoking_current: "현재 흡연",
  alcohol_frequency: "음주 빈도",
  alcohol_amount: "1회 음주량",
  walking_days: "주당 걷기",
  walking_minutes: "1회 걷기",
  strength_days: "주당 근력운동",
  sitting_minutes: "하루 앉은 시간",
  dining_out_freq: "외식 빈도",
  sbp: "수축기 혈압",
  dbp: "이완기 혈압",
  fasting_glucose: "공복혈당",
  hba1c: "당화혈색소",
  triglyceride: "중성지방",
  hdl: "HDL",
});

export const STEP_TITLES = Object.freeze({
  health: "기본정보",
  health2: "생활습관",
  health3: "검진정보",
});

export function stepOf(field) {
  return Object.keys(STEPS).find((step) => STEPS[step].includes(field));
}

let owner = null;
let values = {};
let completed = new Set();
/** 같은 건강기록으로 예측을 두 번 접수하지 않도록 이번 세션의 접수 결과를 기억한다. */
const predictions = new Map();
const submitting = new Set();
/** 이 세션에서 pending 을 직접 확인한 예측 ID. done 전환일 때만 완료 표시를 만든다. */
const pendingSeen = new Set();

function ownerOf(auth) {
  return auth?.user?.id ?? null;
}

/** 다른 사용자로 바뀌었으면 이전 초안과 접수 기록을 버린다. */
function sync(auth) {
  const current = ownerOf(auth);
  if (current !== owner) {
    owner = current;
    values = {};
    completed = new Set();
    predictions.clear();
    submitting.clear();
    pendingSeen.clear();
  }
}

export function readStep(auth, step) {
  sync(auth);
  return Object.fromEntries(
    STEPS[step].filter((key) => key in values).map((key) => [key, values[key]]),
  );
}

/** 그 단계의 값을 통째로 바꾼다. 비운 칸은 초안에서도 지운다. */
export function saveStep(auth, step, stepValues) {
  sync(auth);
  for (const key of STEPS[step]) {
    const value = stepValues[key];
    if (value === null || value === undefined) delete values[key];
    else values[key] = value;
  }
  completed.add(step);
}

export function hasStep(auth, step) {
  sync(auth);
  return completed.has(step);
}

export function clearDraft() {
  values = {};
  completed = new Set();
}

/** HLTH-01 본문. 값이 없는 키는 보내지 않는다. */
export function buildRequest(auth) {
  sync(auth);
  const detail = MEASURED_FIELDS.some((key) => key in values);
  const body = { input_mode: detail ? "detail" : "simple" };
  for (const step of ["health", "health2", ...(detail ? ["health3"] : [])])
    for (const key of STEPS[step]) if (key in values) body[key] = values[key];
  return body;
}

export function predictionFor(auth, recordId) {
  sync(auth);
  return predictions.get(recordId) ?? null;
}

export function rememberPrediction(auth, recordId, predictionId) {
  sync(auth);
  predictions.set(recordId, predictionId);
}

export function notePending(auth, predictionId) {
  sync(auth);
  pendingSeen.add(predictionId);
}

/** pending 을 본 예측이면 true 를 돌려주고 지운다. 완료 표시는 한 번만 만든다. */
export function takePending(auth, predictionId) {
  sync(auth);
  return pendingSeen.delete(predictionId);
}

/** 접수 요청이 진행 중이면 false. 끝나면 반드시 release 를 부른다. */
export function claimSubmission(auth, recordId) {
  sync(auth);
  if (submitting.has(recordId)) return false;
  submitting.add(recordId);
  return true;
}

export function releaseSubmission(recordId) {
  submitting.delete(recordId);
}

/** route.params 의 ID. 양의 정수가 아니면 null. */
export function positiveId(raw) {
  return typeof raw === "string" && /^[1-9]\d{0,14}$/.test(raw)
    ? Number(raw)
    : null;
}

// ---- 화면 조각. v4 시안 마크업을 템플릿 리터럴로 쓴다(D screens.mjs 와 같은 방식). ----

export const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );

/** 시안의 버튼 화살표. */
export const ARROW =
  '<span><svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></span>';

export function stepperHtml(active) {
  return `<div class="stepper">${Object.entries(STEP_TITLES)
    .map(
      ([step, title], index) =>
        `${index ? "<i></i>" : ""}<div class="step${step === active ? " active" : ""}"${step === active ? ' aria-current="step"' : ""}><b>${index + 1}</b><span>${title}</span></div>`,
    )
    .join("")}</div>`;
}

/** 숫자 입력. decimals 는 허용 소수 자릿수(0이면 정수). 범위 판정은 서버가 한다. 가상 예시값은 넣지 않는다. */
export function numberFieldHtml({ name, label, unit, decimals = 0, value }) {
  return `<label class="number-field"><span>${escape(label)}</span><input type="number" name="${name}" inputmode="${decimals ? "decimal" : "numeric"}" step="${decimals ? "0.1" : "1"}" data-decimals="${decimals}" data-label="${escape(label)}" aria-label="${escape(label)}" value="${value ?? ""}"><em>${escape(unit)}</em></label>`;
}

/** 시안의 select. options 는 [코드, 문구]. 빈 값은 미응답이다. */
export function selectHtml({ name, label, options, value }) {
  return `<label>${escape(label)}<select name="${name}" aria-label="${escape(label)}"><option value="">선택해주세요</option>${options
    .map(
      ([code, text]) =>
        `<option value="${code}"${value === code ? " selected" : ""}>${escape(text)}</option>`,
    )
    .join("")}</select></label>`;
}

/** 빈 칸은 null. 형식이 틀리면 오류 문구를 던진다. */
export function readNumber(input) {
  const label = input.dataset.label || input.name;
  const decimals = Number(input.dataset.decimals || 0);
  const raw = input.value.trim();
  if (raw === "") {
    if (input.validity?.badInput) throw new Error(`${label}: 숫자로 입력해주세요.`);
    return null;
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${label}: 숫자로 입력해주세요.`);
  const [, fraction = ""] = raw.split(".");
  if (decimals === 0 && !Number.isInteger(value))
    throw new Error(`${label}: 정수로 입력해주세요.`);
  if (fraction.length > decimals)
    throw new Error(`${label}: 소수 ${decimals}자리까지 입력해주세요.`);
  return value;
}

export function readSelect(select) {
  return select.value === "" ? null : Number(select.value);
}

/** 앞 단계 입력이 없을 때(새로고침 등) 처음부터 다시 받도록 안내한다. */
export function missingDraftHtml(title) {
  return `<section class="health"><h1>${escape(title)}</h1><div class="status-panel" role="status"><h2>앞 단계 입력이 없어요</h2><p>입력한 내용은 이 화면에만 잠시 보관돼요. 기본정보부터 다시 입력해주세요.</p><button type="button" class="primary" data-route="health">기본정보 입력하기 ${ARROW}</button></div></section>`;
}

/** data-route 버튼을 공통 라우터로 잇는다. 정리 함수를 돌려준다. */
export function bindRoutes(root, router) {
  const listener = (event) => {
    const button = event.target.closest("[data-route]");
    if (!button || !root.contains(button)) return;
    event.preventDefault();
    void router.navigate(button.dataset.route);
  };
  root.addEventListener("click", listener);
  return () => root.removeEventListener("click", listener);
}

/** API 시각은 오프셋을 포함해 해석하고 한국 시간으로 보여준다. */
export function formatDateTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
