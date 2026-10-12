import {
  FIELD_LABELS,
  STEP_TITLES,
  STEPS,
  bindRoutes,
  buildRequest,
  clearDraft,
  escape,
  formatDateTime,
  hasStep,
  missingDraftHtml,
  numberFieldHtml,
  readNumber,
  readStep,
  saveStep,
  stepOf,
  stepperHtml,
} from "./health-flow.mjs";

/**
 * 3단계 검진정보. v4 시안 health3 화면에서 총콜레스테롤을 뺐다(HLTH-01 입력 제외).
 * 세 단계 초안을 HLTH-01 한 번으로 저장하고 예측 대기로 넘긴다. 예측 접수는 waiting 이 한다.
 */
export function mount({ root, ui, api, auth, router, route, signal }) {
  if (!hasStep(auth, "health") || !hasStep(auth, "health2")) {
    root.innerHTML = missingDraftHtml(route.title);
    return bindRoutes(root, router);
  }
  const saved = readStep(auth, "health3");
  const field = (name, label, unit, decimals = 0) =>
    numberFieldHtml({ name, label, unit, decimals, value: saved[name] });
  root.innerHTML = `<section class="health3">
${stepperHtml("health3")}
<h1>${escape(route.title)}</h1><p class="section-copy">검진 수치가 있으면 알려주세요. 건강검진 결과지의 숫자를 그대로 적으면 돼요.</p>
<form novalidate>
<h2>혈압</h2>
<div class="measurement-fields">${field("sbp", "수축기", "mmHg")}${field("dbp", "이완기", "mmHg")}</div>
<h2 class="section-gap">혈당</h2>
<div class="measurement-fields">${field("fasting_glucose", "공복혈당", "mg/dL")}${field("hba1c", "당화혈색소", "%", 1)}</div>
<h2 class="section-gap">지질</h2>
<div class="measurement-fields">${field("triglyceride", "중성지방", "mg/dL")}${field("hdl", "HDL", "mg/dL")}</div>
<div class="guide-card"><span class="sprite spike" aria-hidden="true"></span><p>혈당 정보는 저장해요.<br><b>스파이크 위협도는 산정 기준이 정해진 뒤 보여드려요.</b></p></div>
<p class="skip-note">이 단계는 건너뛸 수 있어요. 비워두면 간편 모드로 저장되고, 스파이크는 미측정으로 남아요.</p>
<div data-feedback aria-live="polite"></div>
<button class="primary" type="submit">저장하고 예측하기</button>
</form>
<button type="button" class="secondary" data-route="health2">이전</button>
</section>`;
  const form = root.querySelector("form");
  const feedback = root.querySelector("[data-feedback]");
  const submit = form.querySelector('button[type="submit"]');

  function rangeNotices(error) {
    const items = Array.isArray(error.details?.fields) ? error.details.fields : [];
    const steps = new Set();
    const nodes = [ui.notice(error.message, { kind: "error" })];
    items.forEach((item) => {
      const step = stepOf(item.field);
      if (step && step !== "health3") steps.add(step);
      const range = item.min != null && item.max != null ? ` ${item.min}~${item.max} 사이로 입력해주세요.` : "";
      nodes.push(
        ui.notice(`${FIELD_LABELS[item.field] || item.field}:${range}${item.reason ? ` ${item.reason}` : ""}`, {
          kind: "error",
          role: "none",
        }),
      );
    });
    // 앞 단계 필드면 그 화면으로 돌아가 고친다. 초안은 그대로 남아 있다
    steps.forEach((step) =>
      nodes.push(
        ui.button(`${STEP_TITLES[step]}로 돌아가 고치기`, {
          variant: "secondary",
          onClick: () => router.navigate(step),
        }),
      ),
    );
    return nodes;
  }

  /** 연결이 끊기면 저장 여부를 모른다. 자동으로 다시 보내지 않고 서버 목록을 먼저 확인하게 한다. */
  function connectionNotices(error) {
    const check = ui.button("최근 기록 확인하기", { variant: "secondary" });
    check.addEventListener("click", () =>
      ui.runPending(check, async () => {
        try {
          const data = await api("/health-records?page=1&size=1");
          if (signal.aborted) return;
          const latest = data.items?.[0];
          feedback.append(
            ui.notice(
              latest
                ? `가장 최근 기록: ${formatDateTime(latest.recorded_at) || latest.recorded_at}. 방금 저장된 기록이면 다시 누르지 말고 위험도 화면에서 예측을 요청해주세요.`
                : "저장된 기록이 없어요. 다시 눌러 저장해주세요.",
            ),
          );
        } catch (checkError) {
          if (!signal.aborted) feedback.append(ui.notice(checkError.message, { kind: "error" }));
        }
      }),
    );
    return [ui.notice(error.message, { kind: "error" }), check];
  }

  function showError(error) {
    if (error.code === "HLTH_VALUE_OUT_OF_RANGE") feedback.replaceChildren(...rangeNotices(error));
    else if (error.status === 0) feedback.replaceChildren(...connectionNotices(error));
    else if (error.code === "HLTH_PROFILE_INCOMPLETE")
      feedback.replaceChildren(
        ui.notice(error.message, { kind: "error" }),
        ui.notice("회원 정보의 출생연도·성별·키가 있어야 저장할 수 있어요."),
      );
    // 401 을 포함한 나머지. 쓰기는 다시 보내지 않고 입력한 초안은 그대로 둔다
    else feedback.replaceChildren(ui.notice(error.message, { kind: "error" }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    await ui.runPending(submit, async () => {
      feedback.replaceChildren();
      try {
        saveStep(
          auth,
          "health3",
          Object.fromEntries(STEPS.health3.map((name) => [name, readNumber(form.elements.namedItem(name))])),
        );
      } catch (error) {
        feedback.replaceChildren(ui.notice(error.message, { kind: "error" }));
        return;
      }
      let record;
      try {
        record = await api("/health-records", { method: "POST", body: buildRequest(auth) });
      } catch (error) {
        if (!signal.aborted) showError(error);
        return;
      }
      // 기록은 덮어쓸 수 없으므로 초안을 비운다. 뒤로 와도 같은 기록을 다시 보내지 않는다
      clearDraft();
      if (!signal.aborted) await router.navigate(`waiting?record_id=${record.health_record_id}`);
    });
  }
  form.addEventListener("submit", onSubmit);
  const unbindRoutes = bindRoutes(root, router);
  return () => {
    form.removeEventListener("submit", onSubmit);
    unbindRoutes();
  };
}
