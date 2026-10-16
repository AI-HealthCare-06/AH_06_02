import { createEvidenceUploader } from "./shared/evidence.mjs";
import { AuthSession } from "./shared/auth.mjs";
import { HashRouter, ROUTES } from "./shared/router.mjs";
import { PredictionReadiness } from "./shared/prediction-readiness.mjs";
import * as ui from "./shared/components.mjs";
import { mountDangoScreens } from "./d/screens.mjs";

const pageModules = {
  login: () => import("./pages/login.mjs"),
  signup: () => import("./pages/signup.mjs"),
  health: () => import("./pages/health.mjs"),
  health2: () => import("./pages/health2.mjs"),
  health3: () => import("./pages/health3.mjs"),
  waiting: () => import("./pages/waiting.mjs"),
  risk: () => import("./pages/risk.mjs"),
};
const backPages = {
  login: "login",
  signup: "login",
  health: "today",
  health2: "health",
  health3: "health2",
  waiting: "health3",
  risk: "health",
  reco: "monsters",
  today: "reco",
  progress: "today",
  monsters: "today",
};

/** 화면 틀과 세션은 앱이 소유하고 각 페이지는 내용 영역만 사용한다. */
export async function startApplication(
  root,
  {
    fetchImpl = globalThis.fetch,
    uploadPhoto,
    evidencePhotosEnabled = true,
  } = {},
) {
  const auth = new AuthSession({
    fetchImpl,
    dispatch: () => window.dispatchEvent(new Event("dango:auth-changed")),
  });
  const predictionReady = new PredictionReadiness();
  const title = ui.element("span");
  const toolbar = ui.element("div", { className: "topbar common-toolbar" });
  const userName = ui.element("span");
  const userStrip = ui.element("div", { className: "user-strip" });
  const feedback = ui.element("div", {
    className: "common-notice",
    attributes: { "aria-live": "polite" },
  });
  const host = ui.element("div", {
    className: "common-page-host",
    attributes: { "data-page-host": true },
  });
  const nav = ui.element("nav", {
    className: "app-nav",
    attributes: { "aria-label": "앱 메뉴" },
  });
  let dScreens = null;
  let cleanup = null;
  let started = false;
  const router = new HashRouter({
    isAuthenticated: () => auth.signedIn,
    render: async (route, signal) => {
      title.textContent = route.title;
      document.title = `${route.title} · 당고킬러`;
      userName.textContent = `${auth.user?.nickname || ""}님`;
      userStrip.hidden = !auth.signedIn;
      nav.hidden = !auth.signedIn;
      feedback.replaceChildren();
      document.querySelectorAll(".journey a").forEach((link) => {
        link.hidden = !auth.signedIn;
        if (link.hash === `#${route.id}`)
          link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      nav.querySelectorAll("a").forEach((link) => {
        if (link.hash === `#${route.id}`)
          link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      if (route.owner === "D") {
        cleanup?.();
        cleanup = null;
        host.className = "common-page-host d-page-host";
        if (!dScreens)
          dScreens = mountDangoScreens(host, {
            embedded: true,
            request: auth.api,
            generateRecommendations: ({ signal } = {}) =>
              predictionReady.request(
                () =>
                  auth.api("/challenge-recommendations/generate", {
                    method: "POST",
                  }),
                { signal },
              ),
            uploadPhoto:
              uploadPhoto ||
              (evidencePhotosEnabled
                ? createEvidenceUploader(auth.api)
                : undefined),
            navigate: (id) => router.navigate(id),
          });
        await dScreens.show(route.id);
      } else {
        dScreens?.destroy();
        dScreens = null;
        cleanup?.();
        cleanup = null;
        host.className = "common-page-host";
        host.replaceChildren(ui.loading());
        const page = await pageModules[route.id]();
        if (signal.aborted) return;
        const context = {
          root: host,
          route,
          signal,
          ui,
          auth,
          predictionReady,
          router,
          navigate: (id) => router.navigate(id),
          api: (path, options = {}) =>
            auth.api(path, {
              ...(options.method && options.method !== "GET" ? {} : { signal }),
              ...options,
            }),
        };
        const disposer = await page.mount(context);
        if (signal.aborted) {
          if (typeof disposer === "function") disposer();
          return;
        }
        cleanup = typeof disposer === "function" ? disposer : null;
        const heading = host.querySelector("h1, h2");
        if (heading) {
          heading.tabIndex = -1;
          heading.classList.add("screen-title");
          heading.focus({ preventScroll: true });
        }
      }
    },
    onError: (error, route) => {
      if (error.status === 401)
        void router.navigate("login", { replace: true });
      else
        host.replaceChildren(
          ui.statePanel(
            "내용을 불러오지 못했어요",
            "잠시 후 다시 확인해주세요.",
            {
              kind: "error",
              action: () => router.navigate(route.fragment, { replace: true }),
            },
          ),
        );
    },
  });
  const back = ui.button("‹", {
    variant: "back",
    onClick: () => router.navigate(backPages[router.current?.id] || "today"),
  });
  back.setAttribute("aria-label", "이전 화면");
  const reload = ui.button("↻", {
    variant: "reload",
    onClick: () =>
      router.navigate(router.current?.fragment || "today", { replace: true }),
  });
  reload.setAttribute("aria-label", "새로고침");
  toolbar.append(back, title, reload);
  const logout = ui.button("로그아웃", {
    variant: "secondary",
    onClick: () => {
      void ui.runPending(logout, async () => {
        try {
          await auth.logout();
        } catch (error) {
          feedback.replaceChildren(ui.notice(error.message, { kind: "error" }));
        }
      });
    },
  });
  userStrip.append(userName, logout);
  [
    ["risk", "위험도"],
    ["today", "공략"],
    ["monsters", "도감"],
    ["health", "기록"],
  ].forEach(([id, label]) =>
    nav.append(
      ui.element("a", { text: label, attributes: { href: `#${id}` } }),
    ),
  );
  root.replaceChildren(toolbar, userStrip, feedback, host, nav);
  userStrip.hidden = true;
  nav.hidden = true;
  host.replaceChildren(ui.loading("로그인 상태를 확인하고 있어요."));
  const subscription = auth.subscribe(() => {
    predictionReady.clear();
    userName.textContent = `${auth.user?.nickname || ""}님`;
    userStrip.hidden = !auth.signedIn;
    nav.hidden = !auth.signedIn;
    if (started && !auth.signedIn && !router.current?.public)
      void router.navigate(router.current?.fragment || "today", {
        replace: true,
      });
  });
  window.dangoAuth = {
    getAccessToken: () => auth.getAccessToken(),
    setAccessToken: (token) => auth.setAccessToken(token),
  };
  window.dangoNavigate = (id) => router.navigate(id);
  window.dangoPredictionReady = {
    markDone: (data) => predictionReady.markDone(data),
    clear: () => predictionReady.clear(),
  };
  await auth.restore();
  started = true;
  await router.start();
  return {
    auth,
    router,
    destroy() {
      subscription();
      router.destroy();
      dScreens?.destroy();
      cleanup?.();
      root.replaceChildren();
      delete window.dangoAuth;
      delete window.dangoNavigate;
      delete window.dangoPredictionReady;
      predictionReady.clear();
    },
  };
}

const root = document.querySelector("[data-dango-app]");
if (root)
  void startApplication(root, {
    uploadPhoto: window.dangoEvidence?.uploadPhoto
      ? (file, context) => window.dangoEvidence.uploadPhoto(file, context)
      : undefined,
    evidencePhotosEnabled: window.dangoConfig?.evidencePhotosEnabled !== false,
  }).catch(() =>
    root.replaceChildren(
      ui.statePanel(
        "화면을 열지 못했어요",
        "새로고침한 뒤 다시 시도해주세요.",
        { kind: "error" },
      ),
    ),
  );
