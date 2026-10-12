/** 공통 인증 진입점. A 담당자가 시안·회원가입 흐름을 확장한다. */
export function mount({ root, ui, auth, router, signal }) {
  const heading = ui.element("h1", { text: "모험을 이어가요." });
  const copy = ui.element("p", {
    className: "small-copy",
    text: "로그인하고 오늘의 작은 공략을 시작하세요.",
  });
  const email = ui.field("이메일", {
    name: "email",
    type: "email",
    required: true,
    autocomplete: "username",
  });
  const password = ui.field("비밀번호", {
    name: "password",
    type: "password",
    required: true,
    autocomplete: "current-password",
  });
  const submit = ui.button("로그인", { type: "submit" });
  const feedback = ui.element("div", { attributes: { "aria-live": "polite" } });
  const form = ui.element(
    "form",
    { className: "common-login" },
    email.wrapper,
    password.wrapper,
    feedback,
    submit,
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
    heading,
    copy,
    form,
    ui.button("회원가입", {
      variant: "secondary",
      onClick: () => router.navigate("signup"),
    }),
  );
  return () => {
    password.input.value = "";
    form.removeEventListener("submit", onSubmit);
  };
}
