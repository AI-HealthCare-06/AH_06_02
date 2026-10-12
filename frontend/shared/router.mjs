/** 구현 담당과 공개 여부는 한 곳에서 고정한다. */
export const ROUTES = Object.freeze({
  login: { title: "로그인", owner: "A", public: true },
  signup: { title: "회원가입", owner: "A", public: true },
  health: { title: "기본 건강정보", owner: "C" },
  health2: { title: "생활습관", owner: "C" },
  health3: { title: "검진정보", owner: "C" },
  waiting: { title: "예측 대기", owner: "C" },
  risk: { title: "현재 위험도", owner: "C" },
  reco: { title: "챌린지 선택", owner: "D" },
  today: { title: "오늘의 공략", owner: "D" },
  progress: { title: "공략 현황", owner: "D" },
  monsters: { title: "몬스터 도감", owner: "D" },
});

export function parseRoute(hash = "") {
  const value = hash.replace(/^#/, "");
  const [name, ...query] = value.split("?");
  const id = Object.hasOwn(ROUTES, name) ? name : "today";
  const params = new URLSearchParams(
    Object.hasOwn(ROUTES, name) ? query.join("?") : "",
  );
  return {
    id,
    params,
    fragment: id + (params.size ? `?${params}` : ""),
    ...ROUTES[id],
  };
}
export function guardRoute(route, signedIn) {
  return route.public || signedIn
    ? { id: route.id, returnTo: null }
    : { id: "login", returnTo: route.fragment };
}

export class HashRouter {
  #version = 0;
  #controller = null;
  #pending = null;
  #listener;
  constructor({
    render,
    isAuthenticated,
    onError = () => {},
    windowObject = window,
  }) {
    this.window = windowObject;
    this.render = render;
    this.isAuthenticated = isAuthenticated;
    this.onError = onError;
    this.#listener = () => {
      void this.#visit();
    };
  }
  async #visit() {
    const version = ++this.#version;
    this.#controller?.abort();
    this.#controller = new AbortController();
    let route = parseRoute(this.window.location.hash);
    const guarded = guardRoute(route, this.isAuthenticated());
    if (guarded.returnTo) {
      this.#pending = guarded.returnTo;
      route = parseRoute("#login");
    }
    const canonical = `#${route.fragment}`;
    if (this.window.location.hash !== canonical)
      this.window.history.replaceState(null, "", canonical);
    this.current = route;
    try {
      await this.render(route, this.#controller.signal);
    } catch (error) {
      if (version === this.#version && error.name !== "AbortError")
        this.onError(error, route);
    }
  }
  async start() {
    this.window.addEventListener("hashchange", this.#listener);
    await this.#visit();
  }
  async navigate(fragment, { replace = false } = {}) {
    const route = parseRoute(`#${String(fragment).replace(/^#/, "")}`);
    this.window.history[replace ? "replaceState" : "pushState"](
      null,
      "",
      `#${route.fragment}`,
    );
    await this.#visit();
  }
  async resume(fallback = "health") {
    const destination = this.#pending || fallback;
    this.#pending = null;
    await this.navigate(destination, { replace: true });
  }
  destroy() {
    ++this.#version;
    this.#controller?.abort();
    this.window.removeEventListener("hashchange", this.#listener);
  }
}
