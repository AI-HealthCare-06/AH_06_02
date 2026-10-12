/** AUTH-03 로그인. v4 시안의 첫 화면 구성을 공통 인증 위에 얹는다. */
const CAST = ["viscera", "sodi", "alde", "cotinine", "spike"];

/** 시안의 모션 꺼짐 상태와 같다. 영상 대신 정지 배경과 몬스터 일행을 둔다. */
function hero(ui) {
  return ui.element(
    "div",
    { className: "login-art art" },
    ui.element("div", { className: "hero-shade" }),
    ui.element(
      "div",
      { className: "hero-copy" },
      ui.element(
        "div",
        { className: "brand-title", text: "DangoKiller" },
        ui.element("span", { text: "당고킬러" }),
      ),
      ui.element("p", {
        className: "hero-kicker",
        text: "작은 실천으로 시작하는",
      }),
      ui.element("h1", { text: "나의 모험" }),
      ui.element(
        "p",
        { className: "hero-sub" },
        "오늘도, 작은 퀘스트가",
        ui.element("br"),
        "더 가벼운 내일을 만들어가요.",
      ),
    ),
    ui.element(
      "div",
      { className: "hero-fallback-cast", attributes: { "aria-hidden": true } },
      CAST.map((code) => ui.element("span", { className: `sprite ${code}` })),
    ),
  );
}

function shell(ui, label, options) {
  const input = ui.element("input", {
    attributes: { ...options, required: true, "aria-label": label },
  });
  return {
    wrapper: ui.element("label", { className: "input-shell" }, input),
    input,
  };
}

export function mount({ root, ui, auth, router, signal }) {
  const email = shell(ui, "이메일", {
    name: "email",
    type: "email",
    autocomplete: "username",
    placeholder: "이메일을 입력해 주세요",
  });
  const password = shell(ui, "비밀번호", {
    name: "password",
    type: "password",
    autocomplete: "current-password",
    placeholder: "비밀번호를 입력해 주세요",
  });
  const submit = ui.button("로그인", { type: "submit" });
  const feedback = ui.element("div", { attributes: { "aria-live": "polite" } });
  const toSignup = ui.button("회원가입", {
    variant: "text-link",
    onClick: () => router.navigate("signup"),
  });
  const form = ui.element(
    "form",
    { className: "login-form panel-pad" },
    email.wrapper,
    password.wrapper,
    feedback,
    submit,
    ui.element(
      "div",
      { className: "inline-links" },
      ui.element("span", { text: "아직 계정이 없으신가요?" }),
      toSignup,
    ),
    ui.element(
      "div",
      { className: "medical-note" },
      ui.element(
        "p",
        {},
        "당고킬러의 건강 관련 정보는 참고용이며,",
        ui.element("br"),
        "의학적 진단·치료를 대신하지 않습니다.",
      ),
    ),
  );
  async function onSubmit(event) {
    event.preventDefault();
    await ui.runPending(submit, async () => {
      feedback.replaceChildren();
      try {
        const signedIn = await auth.login({
          email: email.input.value.trim(),
          password: password.input.value,
        });
        password.input.value = "";
        if (!signal.aborted && signedIn) await router.resume();
      } catch (error) {
        if (!signal.aborted)
          feedback.replaceChildren(
            ui.notice(
              error.message ||
                "로그인하지 못했어요. 잠시 후 다시 시도해주세요.",
              { kind: "error" },
            ),
          );
      }
    });
  }
  form.addEventListener("submit", onSubmit);
  root.replaceChildren(
    ui.element("div", { className: "auth-page" }, hero(ui), form),
  );
  return () => {
    password.input.value = "";
    form.removeEventListener("submit", onSubmit);
  };
}
