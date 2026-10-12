/** AUTH-01 이메일 중복 확인 · AUTH-02 회원가입. v4 시안의 회원가입 화면에 명세 필드를 더한다. */
const SEXES = [
  ["M", "♂ 남성"],
  ["F", "♀ 여성"],
];
const REWARDS = [
  ["collect", "◈", "수집형", ["몬스터 도감", "배지 모으기"]],
  ["grow", "❧", "성장형", ["캐릭터 성장", "칭호 달성"]],
  ["decorate", "✦", "꾸미기형", ["나만의 공간", "테마 꾸미기"]],
];
// 허용 범위는 서버 검증과 같다. 출생연도 1900년 이후·만 14세 이상, 키 100~250cm (REQ-HLTH-003)
const MIN_BIRTH_YEAR = 1900;
const MIN_AGE = 14;
const HEIGHT_RANGE = { min: "100", max: "250", step: "0.1" };

function thisYearInKst() {
  return Number(
    new Intl.DateTimeFormat("en", {
      timeZone: "Asia/Seoul",
      year: "numeric",
    }).format(new Date()),
  );
}

function art(ui) {
  return ui.element(
    "div",
    { className: "signup-art art" },
    ui.element("img", {
      className: "landscape",
      attributes: { src: "d/assets/v4-4.png", alt: "" },
    }),
    ui.element(
      "div",
      { className: "signup-copy" },
      ui.element("h1", { text: "회원가입" }),
      ui.element(
        "p",
        {},
        "좋은 습관이 특별한 모험이 되는",
        ui.element("br"),
        "당신을 환영해요!",
      ),
    ),
  );
}

function numberField(ui, label, unit, attributes) {
  const input = ui.element("input", {
    attributes: {
      type: "number",
      required: true,
      inputmode: "decimal",
      "aria-label": label,
      ...attributes,
    },
  });
  const wrapper = ui.element(
    "label",
    { className: "number-field" },
    ui.element("span", { text: label }),
    input,
    ui.element("em", { text: unit }),
  );
  return { wrapper, input };
}

/** 한 묶음에서 하나만 고르는 버튼. 시안처럼 selected 와 aria-pressed 를 함께 바꾼다. */
function choiceGroup(ui, className, label, items, initial) {
  let value = initial;
  const buttons = items.map(([key, ...content]) => {
    const node = ui.element(
      "button",
      {
        className: className === "reward-options" ? "reward" : "",
        attributes: {
          type: "button",
          "aria-pressed": String(key === value),
          "data-value": key,
        },
      },
      ...content,
    );
    return node;
  });
  function select(key) {
    value = key;
    buttons.forEach((node) => {
      const on = node.dataset.value === key;
      node.classList.toggle("selected", on);
      node.setAttribute("aria-pressed", String(on));
    });
  }
  if (value) select(value);
  const group = ui.element(
    "div",
    { className, attributes: { role: "group", "aria-label": label } },
    buttons,
  );
  function onClick(event) {
    const node = event.target.closest("button");
    if (node && group.contains(node)) select(node.dataset.value);
  }
  group.addEventListener("click", onClick);
  return {
    group,
    get value() {
      return value;
    },
    focus: () => buttons[0].focus(),
    dispose: () => group.removeEventListener("click", onClick),
  };
}

function diagnosisSelect(ui, label) {
  const select = ui.element(
    "select",
    { attributes: { "aria-label": label } },
    ui.element("option", { text: "아니요", attributes: { value: "no" } }),
    ui.element("option", { text: "예", attributes: { value: "yes" } }),
  );
  return { wrapper: ui.element("label", { text: label }, select), select };
}

function medicine(ui, label) {
  const input = ui.element("input", { attributes: { type: "checkbox" } });
  return { wrapper: ui.element("label", {}, input, ` ${label}`), input };
}

export function mount({ root, ui, api, auth, router, signal }) {
  const nickname = ui.field("닉네임", {
    name: "nickname",
    required: true,
    autocomplete: "nickname",
    placeholder: "탐험가 쿠리",
  });
  nickname.input.maxLength = 50;
  const email = ui.field("이메일", {
    name: "email",
    type: "email",
    required: true,
    autocomplete: "email",
    placeholder: "dango@explorer.com",
  });
  email.input.maxLength = 255;
  const emailStatus = ui.element("div", {
    attributes: { "aria-live": "polite" },
  });
  const checkEmail = ui.button("중복 확인", {
    variant: "secondary",
    onClick: () => void onCheckEmail(),
  });
  const password = ui.field("비밀번호", {
    name: "password",
    type: "password",
    required: true,
    autocomplete: "new-password",
    placeholder: "8자 이상",
  });
  const confirm = ui.field("비밀번호 확인", {
    name: "password_confirm",
    type: "password",
    required: true,
    autocomplete: "new-password",
    placeholder: "한 번 더 입력",
  });
  const sex = choiceGroup(ui, "sex-options", "성별", SEXES, null);
  const birthYear = numberField(ui, "출생연도", "년", {
    name: "birth_year",
    inputmode: "numeric",
    min: String(MIN_BIRTH_YEAR),
    max: String(thisYearInKst() - MIN_AGE),
    step: "1",
  });
  const height = numberField(ui, "키", "cm", {
    name: "height_cm",
    ...HEIGHT_RANGE,
    placeholder: "175",
  });
  const dmDiagnosed = diagnosisSelect(ui, "당뇨 진단");
  const htnDiagnosed = diagnosisSelect(ui, "고혈압 진단");
  const htnMedication = medicine(ui, "혈압약");
  const dmMedication = medicine(ui, "혈당약");
  const reward = choiceGroup(
    ui,
    "reward-options",
    "보상 선호",
    REWARDS.map(([key, icon, name, lines]) => [
      key,
      ui.element("span", { text: icon, attributes: { "aria-hidden": true } }),
      ui.element("b", { text: name }),
      ui.element("small", {}, lines[0], ui.element("br"), lines[1]),
    ]),
    "collect",
  );
  const disclaimer = ui.element("input", {
    attributes: { type: "checkbox", name: "disclaimer_agreed", required: true },
  });
  const submit = ui.button("모험 시작하기", { type: "submit" });
  const feedback = ui.element("div", { attributes: { "aria-live": "polite" } });

  const form = ui.element(
    "form",
    { className: "panel-pad signup-form" },
    nickname.wrapper,
    ui.element("div", { className: "email-check" }, email.wrapper, checkEmail),
    emailStatus,
    ui.element(
      "div",
      { className: "two-columns" },
      password.wrapper,
      confirm.wrapper,
    ),
    ui.element("p", {
      className: "small-copy",
      text: "비밀번호는 8자 이상이며 영문과 숫자를 각각 1자 이상 포함해야 해요.",
    }),
    ui.element("h2", { text: "기본 정보를 알려주세요" }),
    sex.group,
    ui.element(
      "div",
      { className: "measurement-fields" },
      birthYear.wrapper,
      height.wrapper,
    ),
    ui.element("h2", { text: "진단 여부를 선택해 주세요" }),
    ui.element("p", {
      className: "small-copy",
      text: "의사에게 진단받은 사항이 있나요?",
    }),
    ui.element(
      "div",
      { className: "diagnoses" },
      dmDiagnosed.wrapper,
      htnDiagnosed.wrapper,
    ),
    ui.element(
      "div",
      { className: "medicine" },
      ui.element("p", { text: "복용 중인 약이 있나요?" }),
      htnMedication.wrapper,
      dmMedication.wrapper,
    ),
    ui.element("h2", { text: "어떤 보상이 가장 마음에 드나요?" }),
    ui.element("p", {
      className: "small-copy",
      text: "선택한 보상은 게임 경험에 반영돼요.",
    }),
    reward.group,
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
    ui.element(
      "label",
      { className: "consent" },
      disclaimer,
      ui.element(
        "span",
        {},
        ui.element("b", { text: "(필수)" }),
        " 개인정보·의료 고지를 확인했습니다.",
      ),
    ),
    feedback,
    submit,
  );

  function showError(target, message) {
    target.replaceChildren(ui.notice(message, { kind: "error" }));
  }
  function clearPasswords() {
    password.input.value = "";
    confirm.input.value = "";
  }

  async function onCheckEmail() {
    if (!email.input.reportValidity()) return;
    const value = email.input.value.trim();
    await ui.runPending(checkEmail, async () => {
      emailStatus.replaceChildren();
      try {
        const { available } = await api(
          `/auth/check-email?email=${encodeURIComponent(value)}`,
          { auth: false },
        );
        if (signal.aborted || email.input.value.trim() !== value) return;
        emailStatus.replaceChildren(
          available
            ? ui.notice("사용할 수 있는 이메일이에요.", { kind: "success" })
            : ui.notice("이미 가입된 이메일이에요.", { kind: "error" }),
        );
      } catch (error) {
        if (!signal.aborted) showError(emailStatus, error.message);
      }
    });
  }
  const onEmailInput = () => emailStatus.replaceChildren();
  const onConfirmInput = () => confirm.input.setCustomValidity("");

  async function onSubmit(event) {
    event.preventDefault();
    feedback.replaceChildren();
    if (confirm.input.value !== password.input.value) {
      confirm.input.setCustomValidity("비밀번호가 서로 달라요.");
      confirm.input.reportValidity();
      return;
    }
    if (!sex.value) {
      showError(feedback, "성별을 선택해 주세요.");
      sex.focus();
      return;
    }
    const body = {
      email: email.input.value.trim(),
      password: password.input.value,
      nickname: nickname.input.value.trim(),
      birth_year: Number(birthYear.input.value),
      sex: sex.value,
      height_cm: Number(height.input.value),
      motivation_type: reward.value,
      dm_diagnosed: dmDiagnosed.select.value === "yes",
      htn_diagnosed: htnDiagnosed.select.value === "yes",
      dm_medication: dmMedication.input.checked,
      htn_medication: htnMedication.input.checked,
      disclaimer_agreed: disclaimer.checked,
    };
    await ui.runPending(submit, async () => {
      try {
        const data = await api("/auth/signup", {
          method: "POST",
          body,
          auth: false,
        });
        clearPasswords();
        const signedIn = await auth.acceptLogin(data);
        if (!signal.aborted && signedIn) await router.navigate("health");
      } catch (error) {
        if (signal.aborted) return;
        showError(feedback, error.message);
        if (error.code === "AUTH_EMAIL_DUPLICATED") email.input.focus();
        else if (error.code === "AUTH_WEAK_PASSWORD") password.input.focus();
      }
    });
  }

  email.input.addEventListener("input", onEmailInput);
  confirm.input.addEventListener("input", onConfirmInput);
  form.addEventListener("submit", onSubmit);
  root.replaceChildren(
    ui.element("div", { className: "auth-page" }, art(ui), form),
  );
  return () => {
    clearPasswords();
    sex.dispose();
    reward.dispose();
    email.input.removeEventListener("input", onEmailInput);
    confirm.input.removeEventListener("input", onConfirmInput);
    form.removeEventListener("submit", onSubmit);
  };
}
