/** 텍스트는 DOM의 textContent로 넣어 서버 값이 HTML로 실행되지 않게 한다. */
export function element(
  tag,
  { className, text, attributes = {} } = {},
  ...children
) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  Object.entries(attributes).forEach(([key, value]) => {
    if (value != null && value !== false)
      node.setAttribute(key, value === true ? "" : String(value));
  });
  children
    .flat()
    .filter(Boolean)
    .forEach((child) => node.append(child));
  return node;
}
export function button(
  label,
  { variant = "primary", type = "button", onClick, disabled = false } = {},
) {
  const node = element("button", {
    className: variant,
    text: label,
    attributes: { type },
  });
  node.disabled = disabled;
  if (onClick) node.addEventListener("click", onClick);
  return node;
}
let fieldNumber = 0;
export function field(
  label,
  { name, type = "text", required = false, autocomplete, placeholder } = {},
) {
  const id = `dango-field-${++fieldNumber}`;
  const input = element("input", {
    attributes: { id, name, type, required, autocomplete, placeholder },
  });
  const wrapper = element(
    "label",
    { className: "stack-field", attributes: { for: id } },
    element("span", { text: label }),
    input,
  );
  return { wrapper, input };
}
export function card(...children) {
  return element("section", { className: "ui-card" }, ...children);
}
export function notice(
  message,
  { kind = "info", role = kind === "error" ? "alert" : "status" } = {},
) {
  return element("p", {
    className: `ui-notice ${kind}`,
    text: message,
    attributes: { role },
  });
}
export function loading(message = "내용을 불러오고 있어요.") {
  return element(
    "div",
    { className: "loading", attributes: { role: "status" } },
    element("span", {
      className: "spinner",
      attributes: { "aria-hidden": true },
    }),
    element("p", { text: message }),
  );
}
export function statePanel(
  title,
  message,
  { action, label = "다시 확인하기", kind = "empty" } = {},
) {
  return element(
    "section",
    {
      className: "status-panel",
      attributes: { role: kind === "error" ? "alert" : "status" },
    },
    element("h2", { text: title }),
    element("p", { text: message }),
    action && button(label, { variant: "secondary", onClick: action }),
  );
}
const pending = new WeakSet();
export async function runPending(
  buttonElement,
  work,
  label = "처리 중이에요…",
) {
  if (pending.has(buttonElement)) return;
  const text = buttonElement.textContent;
  const disabled = buttonElement.disabled;
  pending.add(buttonElement);
  buttonElement.disabled = true;
  buttonElement.textContent = label;
  buttonElement.setAttribute("aria-busy", "true");
  try {
    return await work();
  } finally {
    pending.delete(buttonElement);
    buttonElement.disabled = disabled;
    buttonElement.textContent = text;
    buttonElement.removeAttribute("aria-busy");
  }
}
export function pendingPage({ root, route, ui = { element, statePanel } }) {
  root.replaceChildren(
    ui.element("h1", { text: route.title }),
    ui.statePanel("화면을 준비하고 있어요", "잠시 후 다시 확인해주세요."),
  );
}
