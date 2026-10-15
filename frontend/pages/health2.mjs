import {
  bindRoutes,
  escape,
  hasStep,
  missingDraftHtml,
  numberFieldHtml,
  readNumber,
  readSelect,
  readStep,
  saveStep,
  selectHtml,
  stepperHtml,
} from "./health-flow.mjs";

// 선택지 문구는 docs/03_ai_data/input-code-map.md 의 KNHANES 코드 의미를 따른다. 값은 코드 그대로 보낸다.
// 원 문항은 최근 1년이고 서비스는 최근 4주를 묻는다(근사).
const NON_DRINKER = 1;
const ALCOHOL_FREQUENCY = [
  [1, "최근 4주 동안 마시지 않음"],
  [2, "월 1회 미만"],
  [3, "월 1회 정도"],
  [4, "월 2~4회"],
  [5, "주 2~3회"],
  [6, "주 4회 이상"],
];
const ALCOHOL_AMOUNT = [
  [1, "1~2잔"],
  [2, "3~4잔"],
  [3, "5~6잔"],
  [4, "7~9잔"],
  [5, "10잔 이상"],
];
// 외식 빈도는 역순이다. 1이 가장 잦고 7이 거의 안 함
const DINING_OUT = [
  [1, "하루 2회 이상"],
  [2, "하루 1회"],
  [3, "주 5~6회"],
  [4, "주 3~4회"],
  [5, "주 1~2회"],
  [6, "월 1~3회"],
  [7, "월 1회 미만"],
];

function smokingButton(value, label, saved) {
  const on = saved === value;
  return `<button type="button" data-smoking="${value}"${on ? ' class="selected"' : ""} aria-pressed="${on}">${label}</button>`;
}

/** 2단계 생활습관(최근 4주). v4 시안 health2 화면을 명세에 맞췄다. 저장하지 않고 초안에만 담는다. */
export function mount({ root, ui, auth, router, route, signal }) {
  if (!hasStep(auth, "health")) {
    root.innerHTML = missingDraftHtml(route.title);
    return bindRoutes(root, router);
  }
  const saved = readStep(auth, "health2");
  // 처음에는 흡연 여부를 고르지 않은 상태로 둔다. 시안의 기본 선택은 가상 응답이라 쓰지 않는다
  let smoking = typeof saved.smoking_current === "boolean" ? saved.smoking_current : null;
  root.innerHTML = `<section class="health2">
${stepperHtml("health2")}
<h1>${escape(route.title)}</h1><p class="section-copy">생활습관을 알려주세요. 예측에 쓰이는 값이 대부분 여기에서 나와요.</p>
<form novalidate>
<h2>흡연</h2>
<div class="choice-options" role="group" aria-label="현재 흡연 여부">${smokingButton(true, "피워요", smoking)}${smokingButton(false, "안 피워요", smoking)}</div>
<h2>음주</h2><p class="small-copy">최근 4주 기준으로 선택해 주세요.</p>
<div class="diagnoses">${selectHtml({ name: "alcohol_frequency", label: "마시는 빈도", options: ALCOHOL_FREQUENCY, value: saved.alcohol_frequency })}${selectHtml({ name: "alcohol_amount", label: "한 번에 마시는 양", options: ALCOHOL_AMOUNT, value: saved.alcohol_amount })}</div>
<h2 class="section-gap">활동량</h2>
<div class="measurement-fields">
${numberFieldHtml({ name: "walking_days", label: "주당 걷기", unit: "일", value: saved.walking_days })}
${numberFieldHtml({ name: "walking_minutes", label: "1회 걷기", unit: "분", value: saved.walking_minutes })}
${numberFieldHtml({ name: "strength_days", label: "주당 근력운동", unit: "일", value: saved.strength_days })}
${numberFieldHtml({ name: "sitting_minutes", label: "하루 앉은 시간", unit: "분", value: saved.sitting_minutes })}
</div>
<h2 class="section-gap">식생활</h2>
<p class="small-copy">최근 4주 기준으로 선택해 주세요.</p>
<div class="diagnoses">${selectHtml({ name: "dining_out_freq", label: "외식 빈도", options: DINING_OUT, value: saved.dining_out_freq })}</div>
<div class="guide-card"><span class="sprite sodi" aria-hidden="true"></span><p>습관은 바꿀 수 있는 값이에요.<br><b>여기가 공략의 출발점이 돼요!</b></p></div>
<div data-feedback aria-live="polite"></div>
<button class="primary" type="submit">다음</button>
</form>
<button type="button" class="secondary" data-route="health">이전</button>
</section>`;
  const form = root.querySelector("form");
  const feedback = root.querySelector("[data-feedback]");
  const submit = form.querySelector('button[type="submit"]');
  const frequency = form.elements.namedItem("alcohol_frequency");
  const amount = form.elements.namedItem("alcohol_amount");
  const field = (name) => form.elements.namedItem(name);

  // 최근 안 마심이면 음주량은 묻지 않는다. 서버는 이때만 음주량 0을 받는다
  function syncAmount() {
    const nonDrinker = readSelect(frequency) === NON_DRINKER;
    // .diagnoses label 의 display:flex 가 hidden 속성을 이기므로 style 로 숨긴다
    amount.closest("label").style.display = nonDrinker ? "none" : "";
    if (nonDrinker) amount.value = "";
  }
  function onSmoking(event) {
    const button = event.target.closest("[data-smoking]");
    if (!button) return;
    const value = button.dataset.smoking === "true";
    smoking = smoking === value ? null : value;
    form.querySelectorAll("[data-smoking]").forEach((item) => {
      const on = smoking === (item.dataset.smoking === "true");
      item.classList.toggle("selected", on);
      item.setAttribute("aria-pressed", String(on));
    });
  }
  // 현재 폼 값을 초안 객체로 만든다. 흡연은 폼 필드가 아니라 클로저 변수이고,
  // 음주량에는 NON_DRINKER 규칙이 있어서 STEPS 일괄 처리 대신 직접 만든다
  function draft() {
    const alcoholFrequency = readSelect(frequency);
    return {
      smoking_current: smoking,
      alcohol_frequency: alcoholFrequency,
      alcohol_amount: alcoholFrequency === NON_DRINKER ? 0 : readSelect(amount),
      walking_days: readNumber(field("walking_days")),
      walking_minutes: readNumber(field("walking_minutes")),
      strength_days: readNumber(field("strength_days")),
      sitting_minutes: readNumber(field("sitting_minutes")),
      dining_out_freq: readSelect(field("dining_out_freq")),
    };
  }
  async function onSubmit(event) {
    event.preventDefault();
    await ui.runPending(submit, async () => {
      feedback.replaceChildren();
      try {
        saveStep(auth, "health2", draft());
      } catch (error) {
        feedback.replaceChildren(ui.notice(error.message, { kind: "error" }));
        return;
      }
      if (!signal.aborted) await router.navigate("health3");
    });
  }
  syncAmount();
  frequency.addEventListener("change", syncAmount);
  form.addEventListener("click", onSmoking);
  form.addEventListener("submit", onSubmit);
  // 이전으로 돌아갈 때 입력 중인 값을 초안에 보관한다. 돌아오면 readStep 으로 복원된다
  const backButton = root.querySelector('[data-route="health"]');
  function onBack() {
    try {
      saveStep(auth, "health2", draft());
    } catch {
      // 잘못된 입력이 있어도 이전 이동은 막지 않는다
    }
  }
  backButton?.addEventListener("click", onBack);
  const unbindRoutes = bindRoutes(root, router);
  return () => {
    frequency.removeEventListener("change", syncAmount);
    form.removeEventListener("click", onSmoking);
    form.removeEventListener("submit", onSubmit);
    backButton?.removeEventListener("click", onBack);
    unbindRoutes();
  };
}
