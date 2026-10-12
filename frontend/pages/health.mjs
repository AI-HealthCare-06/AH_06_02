import {
  STEPS,
  bindRoutes,
  escape,
  hasStep,
  numberFieldHtml,
  readNumber,
  readStep,
  saveStep,
  stepperHtml,
} from "./health-flow.mjs";

const SEX_LABELS = { M: "남성", F: "여성" };

/**
 * 1단계 기본 건강정보. v4 시안 health 화면을 명세에 맞췄다.
 * 출생연도·성별·키·진단은 users 프로필 값이라(회원가입 AUTH-02) 여기서는 확인만 한다(HLTH-01).
 */
export function mount({ root, ui, api, auth, router, route, signal }) {
  const saved = readStep(auth, "health");
  root.innerHTML = `<section class="health">
${stepperHtml("health")}
<h1>${escape(route.title)}</h1><p class="section-copy">기본 정보를 알려주세요. 내 생활에 맞는 모험을 준비하는 첫걸음이에요.</p>
<div data-profile aria-live="polite"></div>
<button type="button" class="secondary" data-load-latest>최근 기록 불러오기</button>
<form novalidate>
<div class="measurement-fields">
${numberFieldHtml({ name: "weight_kg", label: "체중", unit: "kg", decimals: 1, value: saved.weight_kg })}
${numberFieldHtml({ name: "waist_cm", label: "허리둘레", unit: "cm", decimals: 1, value: saved.waist_cm })}
</div>
<div class="medicine section-gap"><p>가족 중에 진단받은 분이 있나요?</p><label><input type="checkbox" name="family_history_dm"${saved.family_history_dm ? " checked" : ""}> 당뇨</label><label><input type="checkbox" name="family_history_htn"${saved.family_history_htn ? " checked" : ""}> 고혈압</label></div>
<div class="guide-card"><span class="sprite spike" aria-hidden="true"></span><p>정확한 정보가<br><b>더 좋은 가이드를 만드는 시작이에요!</b></p></div>
<div data-feedback aria-live="polite"></div>
<button class="primary" type="submit">다음</button>
</form>
</section>`;
  const form = root.querySelector("form");
  const profile = root.querySelector("[data-profile]");
  const feedback = root.querySelector("[data-feedback]");
  const submit = form.querySelector('button[type="submit"]');
  const loadLatest = root.querySelector("[data-load-latest]");
  const input = (name) => form.elements.namedItem(name);
  profile.replaceChildren(ui.loading("회원 정보를 확인하고 있어요."));

  function renderProfile(user) {
    const missing = [];
    if (user.birth_year == null) missing.push("출생연도");
    if (!user.sex) missing.push("성별");
    if (user.height_cm == null) missing.push("키");
    const parts = [
      user.birth_year != null && `${user.birth_year}년생`,
      user.sex && (SEX_LABELS[user.sex] || String(user.sex)),
      user.height_cm != null && `키 ${Number(user.height_cm)}cm`,
    ].filter(Boolean);
    const nodes = [];
    if (parts.length) nodes.push(ui.notice(`회원 정보: ${parts.join(" · ")}`));
    // TODO(A 배수빈): 프로필 수정 화면이 생기면 연결한다. 지금은 회원가입에서만 입력한다
    if (missing.length)
      nodes.push(
        ui.notice(`회원 정보에 ${missing.join("·")}가 없으면 건강정보를 저장할 수 없어요.`, { kind: "error" }),
      );
    profile.replaceChildren(...nodes);
  }

  void (async () => {
    try {
      const user = await api("/users/me");
      if (!signal.aborted) renderProfile(user);
    } catch (error) {
      if (!signal.aborted) profile.replaceChildren(ui.notice(error.message, { kind: "error" }));
    }
  })();

  function onLoadLatest() {
    return ui.runPending(loadLatest, async () => {
      feedback.replaceChildren();
      try {
        const data = await api("/health-records?page=1&size=1");
        if (signal.aborted) return;
        const record = data.items?.[0];
        if (!record) {
          feedback.replaceChildren(ui.notice("불러올 이전 기록이 없어요."));
          return;
        }
        input("weight_kg").value = record.weight_kg ?? "";
        input("waist_cm").value = record.waist_cm ?? "";
        input("family_history_dm").checked = record.family_history_dm === true;
        input("family_history_htn").checked = record.family_history_htn === true;
        // 생활습관은 이번에 아직 입력하지 않았을 때만 채운다. 검진 수치는 옛 결과지라 옮기지 않는다
        if (!hasStep(auth, "health2"))
          saveStep(auth, "health2", Object.fromEntries(STEPS.health2.map((key) => [key, record[key]])));
        feedback.replaceChildren(
          ui.notice("최근 기록을 불러왔어요. 새 기록으로 저장되니 달라진 값은 고쳐주세요.", { kind: "success" }),
        );
      } catch (error) {
        if (!signal.aborted) feedback.replaceChildren(ui.notice(error.message, { kind: "error" }));
      }
    });
  }

  async function onSubmit(event) {
    event.preventDefault();
    await ui.runPending(submit, async () => {
      feedback.replaceChildren();
      try {
        saveStep(auth, "health", {
          weight_kg: readNumber(input("weight_kg")),
          waist_cm: readNumber(input("waist_cm")),
          family_history_dm: input("family_history_dm").checked,
          family_history_htn: input("family_history_htn").checked,
        });
      } catch (error) {
        feedback.replaceChildren(ui.notice(error.message, { kind: "error" }));
        return;
      }
      if (!signal.aborted) await router.navigate("health2");
    });
  }
  form.addEventListener("submit", onSubmit);
  loadLatest.addEventListener("click", onLoadLatest);
  const unbindRoutes = bindRoutes(root, router);
  return () => {
    form.removeEventListener("submit", onSubmit);
    loadLatest.removeEventListener("click", onLoadLatest);
    unbindRoutes();
  };
}
