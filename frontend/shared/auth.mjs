import { createApiClient } from "./api.mjs";

/** 액세스 토큰은 메모리에 두고 새로고침은 서버의 HttpOnly 쿠키로 복원한다. */
export class AuthSession {
  #token = null;
  #user = null;
  #revision = 0;
  #attempted = false;
  #restorePromise = null;
  #listeners = new Set();

  constructor({
    base = "/api/v1",
    fetchImpl = globalThis.fetch,
    dispatch = () => {},
  } = {}) {
    this.dispatch = dispatch;
    this.api = createApiClient({
      base,
      fetchImpl,
      getToken: () => this.getAccessToken(),
      getRevision: () => this.#revision,
      setToken: (token) => this.setAccessToken(token),
      onAuthenticationRequired: () => this.clear(),
    });
  }
  get signedIn() {
    return Boolean(this.#token && this.#user);
  }
  get user() {
    return this.#user;
  }
  getAccessToken() {
    return this.#token;
  }
  setAccessToken(token) {
    this.#token = typeof token === "string" && token ? token : null;
  }
  subscribe(listener) {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }
  #notify() {
    this.#listeners.forEach((listener) => listener(this));
    this.dispatch();
  }
  clear() {
    ++this.#revision;
    this.#token = null;
    this.#user = null;
    this.#attempted = true;
    this.#notify();
  }
  async login(credentials) {
    const revision = ++this.#revision;
    const data = await this.api("/auth/login", {
      method: "POST",
      body: credentials,
      auth: false,
    });
    return this.acceptLogin(data, revision);
  }
  async acceptLogin(data, revision = ++this.#revision) {
    if (revision !== this.#revision) return false;
    this.setAccessToken(data.access_token);
    const user = data.user || (await this.api("/users/me"));
    if (revision !== this.#revision) return false;
    this.#user = Object.freeze({ ...user });
    this.#attempted = true;
    this.#notify();
    return this.signedIn;
  }
  async logout() {
    await this.api("/auth/logout", { method: "POST" });
    this.clear();
  }
  async restore({ force = false } = {}) {
    if (this.#restorePromise) return this.#restorePromise;
    if (this.#attempted && !force) return this.signedIn;
    this.#attempted = true;
    const revision = this.#revision;
    this.#restorePromise = (async () => {
      try {
        const data = await this.api("/auth/refresh", {
          method: "POST",
          auth: false,
        });
        if (revision !== this.#revision) return false;
        this.setAccessToken(data.access_token);
        const user = await this.api("/users/me");
        if (revision !== this.#revision) return false;
        this.#user = Object.freeze({ ...user });
        this.#notify();
        return this.signedIn;
      } catch {
        if (revision === this.#revision) {
          this.#token = null;
          this.#user = null;
          this.#notify();
        }
        return false;
      } finally {
        this.#restorePromise = null;
      }
    })();
    return this.#restorePromise;
  }
}
