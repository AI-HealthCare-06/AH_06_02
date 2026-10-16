import { createEvidenceUploader } from "../shared/evidence.mjs";
import { createApiClient } from "../shared/api.mjs";
import { mountDangoScreens } from "./screens.mjs";

const configuration = window.dangoConfig || {};
const tokenKey = "dango.access_token";
const request = createApiClient({
  base: configuration.apiBase || "/api/v1",
  getToken: () =>
    window.dangoAuth?.getAccessToken
      ? window.dangoAuth.getAccessToken()
      : sessionStorage.getItem(tokenKey),
  setToken: (token) => {
    if (window.dangoAuth?.setAccessToken)
      return window.dangoAuth.setAccessToken(token);
    if (token) sessionStorage.setItem(tokenKey, token);
    else sessionStorage.removeItem(tokenKey);
  },
  onAuthenticationRequired: () =>
    window.dispatchEvent(new CustomEvent("dango:authentication-required")),
});

mountDangoScreens(document.querySelector("[data-dango-screens]"), {
  request,
  onPageChange: (page) => {
    document.querySelectorAll(".journey a").forEach((link) => {
      if (link.hash === `#${page}`) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  },
  navigate: (page) => {
    const event = new CustomEvent("dango:navigate", {
      detail: { page },
      cancelable: true,
    });
    if (!window.dispatchEvent(event)) return;
    if (window.dangoNavigate) return window.dangoNavigate(page);
    location.assign(
      configuration.routes?.[page] || `/frontend/#${encodeURIComponent(page)}`,
    );
  },
  uploadPhoto: window.dangoEvidence?.uploadPhoto
    ? (file, context) => window.dangoEvidence.uploadPhoto(file, context)
    : configuration.evidencePhotosEnabled !== false
      ? createEvidenceUploader(request)
      : undefined,
});
