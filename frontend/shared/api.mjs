/** 공통 봉투 처리. 사용자 ID는 전달하지 않고 토큰으로 인증한다. */
export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function createApiClient({
  base = "/api/v1",
  getToken = () => null,
  getRevision = () => 0,
  setToken = () => {},
  onAuthenticationRequired = () => {},
  fetchImpl = globalThis.fetch,
} = {}) {
  let refreshing = null;
  let refreshingRevision = null;
  async function send(path, options = {}) {
    const headers = { Accept: "application/json", ...options.headers };
    const { auth = true, ...fetchOptions } = options;
    const token = auth ? await getToken() : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    const multipart =
      typeof FormData !== "undefined" && options.body instanceof FormData;
    if (options.body !== undefined && !multipart)
      headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetchImpl(`${base}${path}`, {
        ...fetchOptions,
        headers,
        credentials: "same-origin",
        body:
          options.body === undefined
            ? undefined
            : multipart
              ? options.body
              : JSON.stringify(options.body),
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new ApiError(
        0,
        "NETWORK",
        "연결이 끊겼어요. 새로고침해 처리 결과를 확인해주세요.",
      );
    }
    let body;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        response.status,
        "RESPONSE",
        "응답을 확인하지 못했어요. 잠시 후 다시 확인해주세요.",
      );
    }
    if (!response.ok || body.success !== true) {
      throw new ApiError(
        response.status,
        body.error?.code,
        body.error?.message || "요청을 완료하지 못했어요.",
        body.error || {},
      );
    }
    return body.data;
  }
  async function refresh(revision) {
    if (!refreshing || refreshingRevision !== revision) {
      const promise = send("/auth/refresh", { method: "POST", auth: false })
        .then(async (data) => {
          if (revision !== getRevision())
            throw new ApiError(
              401,
              "SESSION_CHANGED",
              "로그인 상태가 바뀌었어요.",
            );
          await setToken(data.access_token);
        })
        .finally(() => {
          if (refreshing === promise) refreshing = null;
        });
      refreshing = promise;
      refreshingRevision = revision;
    }
    return refreshing;
  }
  return async function request(path, options = {}) {
    const revision = getRevision();
    try {
      return await send(path, options);
    } catch (error) {
      if (error.status !== 401 || options.auth === false) throw error;
      if (revision !== getRevision()) throw error;
      try {
        await refresh(revision);
      } catch {
        if (revision !== getRevision())
          throw new ApiError(
            401,
            "SESSION_CHANGED",
            "로그인 상태가 바뀌었어요.",
          );
        await setToken(null);
        onAuthenticationRequired();
        throw new ApiError(
          401,
          error.code,
          "로그인이 필요해요. 다시 로그인해주세요.",
        );
      }
      if ((options.method || "GET").toUpperCase() !== "GET") {
        throw new ApiError(
          401,
          error.code,
          "로그인을 갱신했어요. 목록을 확인한 뒤 다시 눌러주세요.",
        );
      }
      try {
        return await send(path, options);
      } catch (retryError) {
        if (retryError.status === 401 && revision === getRevision()) {
          await setToken(null);
          onAuthenticationRequired();
        }
        throw retryError;
      }
    }
  };
}
