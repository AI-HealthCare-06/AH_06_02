import {
  ARROW,
  bindRoutes,
  claimSubmission,
  escape,
  notePending,
  positiveId,
  predictionFor,
  releaseSubmission,
  rememberPrediction,
  takePending,
} from "./health-flow.mjs";

/** 폴링 간격(ms). 처음 1초에서 늘려 5초에서 멈춘다(PRED-02 권고). */
const DELAYS = [1000, 1000, 2000, 2000, 5000];
/** 이보다 오래 pending 이면 나중에 확인하는 길을 연다. 실패로 바꾸지는 않는다. */
const LONG_PENDING_MS = 30000;

const STEP_COPY = [
  ["건강정보 입력 완료", "입력하신 정보를 확인했어요."],
  ["위험요인 분석 중", "나에게 맞는 공략 방향을 준비하고 있어요."],
  ["맞춤 가이드 준비 중", "곧 당신의 모험 지도가 완성돼요."],
];

/**
 * 예측 대기. v4 시안 waiting 화면(영상 자산은 아직 공통 assets 에 없어 뺐다).
 * - waiting?record_id=N  : PRED-01 을 한 번 접수하고 waiting?prediction_id=M 으로 바꾼다.
 * - waiting?prediction_id=M : PRED-02 를 폴링한다. 새로고침·뒤로가기로 다시 접수하지 않는다.
 * pending → done 전환을 직접 확인했을 때만 predictionReady.markDone 후 추천(reco)으로 간다
 * (docs/02_team/d-start-contracts.md "C 폴링 화면 연결"). 추천 첫 호출 재시도는 predictionReady 가 맡는다.
 */
export function mount({ root, ui, api, auth, predictionReady, router, route, signal }) {
  const recordId = positiveId(route.params.get("record_id"));
  const predictionId = positiveId(route.params.get("prediction_id"));
  root.innerHTML = `<section class="waiting">
<div class="waiting-art art" style="height:auto">
<div class="waiting-copy" style="position:static"><p>나의 모험 지도를 만드는 중</p><h1>${escape(route.title)}</h1><p>나의 위험요인을 찾고 있어요.<br>조금만 기다려 주세요. 당신의 맞춤 가이드를 준비하고 있어요.</p></div>
</div>
<div class="waiting-bottom">
<ol class="analysis-steps">${STEP_COPY.map(([title, copy], index) => `<li data-step="${index}"><span>${index + 1}</span><div><b>${title}</b><p>${copy}</p></div></li>`).join("")}</ol>
<div data-status aria-live="polite"></div>
<div data-actions></div>
</div>
</section>`;
  const status = root.querySelector("[data-status]");
  const actions = root.querySelector("[data-actions]");
  const unbindRoutes = bindRoutes(root, router);
  let timer = null;
  let disposed = false;

  /** 0 접수 중, 1 분석 중, 2 완료 */
  function paintSteps(active) {
    root.querySelectorAll("[data-step]").forEach((item) => {
      const index = Number(item.dataset.step);
      item.classList.toggle("done", index < active);
      item.classList.toggle("analysis-active", index === active);
      item.querySelector("span").textContent = index < active ? "✓" : String(index + 1);
    });
  }

  function routeButton(label, target, variant = "primary") {
    return `<button type="button" class="${variant}" data-route="${target}">${escape(label)} ${variant === "primary" ? ARROW : ""}</button>`;
  }

  function show(notices, buttons = "") {
    status.replaceChildren(...notices);
    actions.innerHTML = buttons;
  }

  function actionButton(label, onClick) {
    const button = ui.button(label, { variant: "secondary", onClick: () => ui.runPending(button, onClick) });
    actions.append(button);
  }

  // ---- PRED-01 접수 ----

  async function submit(id) {
    const existing = predictionFor(auth, id);
    if (existing) return router.navigate(`waiting?prediction_id=${existing}`, { replace: true });
    if (!claimSubmission(auth, id)) {
      show([ui.notice("이미 예측을 접수하고 있어요. 잠시 후 위험도 화면에서 확인해주세요.")], routeButton("위험도 보기", "risk"));
      return;
    }
    paintSteps(0);
    show([ui.loading("예측을 접수하고 있어요.")]);
    // 새 예측을 내면 이전 예측의 완료 표시는 버린다
    predictionReady.clear();
    try {
      // 쓰기라 화면을 떠나도 취소하지 않는다. 받은 ID 는 기억해 두고 다시 접수하지 않는다
      const accepted = await api("/predictions", { method: "POST", body: { health_record_id: id } });
      rememberPrediction(auth, id, accepted.prediction_id);
      if (accepted.status === "pending") notePending(auth, accepted.prediction_id);
      if (!signal.aborted)
        await router.navigate(`waiting?prediction_id=${accepted.prediction_id}`, { replace: true });
    } catch (error) {
      if (!signal.aborted) submitError(error, id);
    } finally {
      releaseSubmission(id);
    }
  }

  function submitError(error, id) {
    const message = ui.notice(error.message, { kind: "error" });
    if (error.code === "PRED_ALL_DIAGNOSED")
      show([message, ui.notice("두 질환 모두 진단 관리 중이라 예측하지 않아요.")], routeButton("위험도 보기", "risk"));
    else if (error.code === "HLTH_PROFILE_INCOMPLETE")
      show([message, ui.notice("회원 정보의 출생연도·성별이 있어야 예측할 수 있어요.")]);
    else if (error.code === "PRED_INPUT_INSUFFICIENT")
      // 저장된 건강기록은 고칠 수 없다. 빠진 항목을 채워 새 기록을 만든다
      show(
        [message, ui.notice("저장된 기록은 고칠 수 없어요. 빠진 항목을 채워 새 기록으로 다시 입력해주세요.")],
        routeButton("새 기록으로 다시 입력", "health"),
      );
    else if (error.status === 404)
      show([message, ui.notice("건강기록을 찾지 못했어요.")], routeButton("건강정보 기록하기", "health"));
    else if (error.status === 0)
      // 접수됐는지 알 수 없다. 다시 보내면 예측이 하나 더 생길 수 있어 위험도에서 확인하게 한다
      show([message], routeButton("위험도에서 확인하기", "risk"));
    else {
      show([message]);
      actionButton("다시 요청하기", () => submit(id));
    }
  }

  // ---- PRED-02 폴링 ----

  function poll(id) {
    const started = Date.now();
    let attempt = 0;
    let warned = false;
    paintSteps(1);
    show([ui.loading("위험요인을 분석하고 있어요.")]);

    async function tick() {
      timer = null;
      let data;
      try {
        data = await api(`/predictions/${id}`);
      } catch (error) {
        if (disposed || signal.aborted || error.name === "AbortError") return;
        if (error.status === 404)
          show([ui.notice(error.message, { kind: "error" }), ui.notice("예측을 찾지 못했어요.")], routeButton("위험도 보기", "risk"));
        else {
          show([ui.notice(error.message, { kind: "error" })]);
          actionButton("다시 확인하기", async () => poll(id));
        }
        return;
      }
      if (disposed || signal.aborted) return;
      if (data.status === "done") {
        paintSteps(3);
        done(id, data);
        return;
      }
      if (data.status === "failed") {
        failed(data.failure);
        return;
      }
      if (data.status !== "pending") {
        show([ui.notice("예측 상태를 확인하지 못했어요. 잠시 후 다시 확인해주세요.", { kind: "error" })]);
        actionButton("다시 확인하기", async () => poll(id));
        return;
      }
      notePending(auth, id);
      if (!warned && Date.now() - started >= LONG_PENDING_MS) {
        warned = true;
        show(
          [
            ui.notice("예측이 오래 걸리고 있어요. 나중에 '위험도' 화면에서 확인하세요."),
            ...(data.model_experimental === true ? [experimentalNote()] : []),
          ],
          routeButton("위험도 보기", "risk", "secondary"),
        );
      } else if (!warned) {
        show([ui.loading("위험요인을 분석하고 있어요."), ...(data.model_experimental === true ? [experimentalNote()] : [])]);
      }
      timer = setTimeout(tick, DELAYS[Math.min(attempt++, DELAYS.length - 1)]);
    }
    void tick();
  }

  function done(id, data) {
    // 서버가 준 done 결과로만 완료 표시를 만든다. 이미 끝난 예측을 다시 연 경우에는 만들지 않는다
    if (takePending(auth, id) && predictionReady.markDone({ status: "done", prediction_id: id })) {
      // 뒤로가기로 대기 화면에 돌아와 다시 넘어가지 않게 바꿔 넣는다
      void router.navigate("reco", { replace: true });
      return;
    }
    show(
      [ui.notice("예측이 완료됐어요.")],
      `${routeButton("추천 챌린지 보기", "reco")}${routeButton("위험도 보기", "risk", "secondary")}`,
    );
  }

  function experimentalNote() {
    return ui.element("p", { className: "pending-note", text: "실험 모델로 예측하고 있어요." });
  }

  function failed(failure) {
    paintSteps(1);
    show([ui.notice(failure?.message || "예측에 실패했어요.", { kind: "error" })], routeButton("위험도 보기", "risk", "secondary"));
    if (failure?.retryable)
      // 실패한 예측에는 건강기록 ID 가 없다. 가장 최근 기록으로 다시 접수한다
      actionButton("다시 시도하기", async () => {
        try {
          const summary = await api("/dashboard/summary");
          if (signal.aborted) return;
          const latest = summary.latest_health_record?.health_record_id;
          if (!latest) {
            show([ui.notice("다시 예측할 건강기록이 없어요.")], routeButton("건강정보 기록하기", "health"));
            return;
          }
          // 같은 기록의 이전 접수 결과(실패)를 재사용하지 않는다
          rememberPrediction(auth, latest, null);
          await submit(latest);
        } catch (error) {
          if (!signal.aborted) show([ui.notice(error.message, { kind: "error" })]);
        }
      });
  }

  if (predictionId) poll(predictionId);
  else if (recordId) void submit(recordId);
  else
    show(
      [ui.notice("확인할 예측이 없어요. 위험도 화면에서 최근 결과를 확인해주세요.")],
      routeButton("위험도 보기", "risk"),
    );

  return () => {
    disposed = true;
    if (timer) clearTimeout(timer);
    unbindRoutes();
  };
}
