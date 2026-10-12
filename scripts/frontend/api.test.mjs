import test from "node:test";
import assert from "node:assert/strict";
import { createApiClient } from "../../frontend/shared/api.mjs";

const reply = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

test("쓰기 요청은 인증 갱신 후에도 자동으로 다시 보내지 않는다", async () => {
  const calls = [];
  let token = "old";
  const api = createApiClient({
    getToken: () => token,
    setToken: (value) => {
      token = value;
    },
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return url.endsWith("/auth/refresh")
        ? reply(200, { success: true, data: { access_token: "new" } })
        : reply(401, {
            success: false,
            error: { code: "AUTH_TOKEN_EXPIRED", message: "토큰 만료" },
          });
    },
  });
  await assert.rejects(
    api("/user-challenges", {
      method: "POST",
      body: { recommendation_ids: [7] },
    }),
    (error) => error.status === 401,
  );
  assert.equal(
    calls.filter((item) => item.url.endsWith("/user-challenges")).length,
    1,
  );
  assert.equal(token, "new");
  assert.equal(calls[0].options.headers.Authorization, "Bearer old");
});

test("동시에 만료된 조회는 한 번 갱신하고 새 토큰으로 다시 조회한다", async () => {
  let token = "old";
  let refreshes = 0;
  const api = createApiClient({
    getToken: () => token,
    setToken: (value) => {
      token = value;
    },
    fetchImpl: async (url, options) => {
      if (url.endsWith("/auth/refresh")) {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
        return reply(200, { success: true, data: { access_token: "new" } });
      }
      return options.headers.Authorization === "Bearer old"
        ? reply(401, { success: false, error: { code: "AUTH_TOKEN_EXPIRED" } })
        : reply(200, { success: true, data: { count: 1 } });
    },
  });
  assert.deepEqual(
    await Promise.all([api("/monsters/me"), api("/rewards/me")]),
    [{ count: 1 }, { count: 1 }],
  );
  assert.equal(refreshes, 1);
});

test("실패 봉투와 잘못된 응답을 성공 데이터로 취급하지 않는다", async () => {
  const api = createApiClient({
    fetchImpl: async () =>
      reply(200, {
        success: false,
        error: { code: "INTERNAL_ERROR", message: "처리 실패" },
      }),
  });
  await assert.rejects(
    api("/monsters/me"),
    (error) => error.code === "INTERNAL_ERROR",
  );
  const malformed = createApiClient({
    fetchImpl: async () => new Response("응답 아님"),
  });
  await assert.rejects(
    malformed("/monsters/me"),
    (error) => error.code === "RESPONSE",
  );
});

test("인증 갱신 실패는 토큰을 지우고 로그인 요청을 알린다", async () => {
  let token = "old";
  let notified = 0;
  const api = createApiClient({
    getToken: () => token,
    setToken: (value) => {
      token = value;
    },
    onAuthenticationRequired: () => {
      notified += 1;
    },
    fetchImpl: async () =>
      reply(401, { success: false, error: { code: "AUTH_TOKEN_INVALID" } }),
  });
  await assert.rejects(
    api("/user-challenges"),
    (error) => error.status === 401,
  );
  assert.equal(token, null);
  assert.equal(notified, 1);
});

test("공개 로그인 API 실패에는 인증 토큰과 자동 갱신을 붙이지 않는다", async () => {
  const calls = [];
  const api = createApiClient({
    getToken: () => "old-private-token",
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return reply(401, {
        success: false,
        error: {
          code: "AUTH_INVALID_CREDENTIALS",
          message: "이메일 또는 비밀번호를 확인해주세요.",
        },
      });
    },
  });
  await assert.rejects(
    api("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "tester@example.com", password: "test-only" },
    }),
    (error) => error.status === 401,
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.headers.Authorization, undefined);
});

test("사진 업로드 본문은 JSON으로 바꾸지 않고 브라우저가 경계를 정하게 한다", async () => {
  const form = new FormData();
  form.append(
    "photo",
    new Blob(["test-image"], { type: "image/png" }),
    "photo.png",
  );
  let received;
  const api = createApiClient({
    fetchImpl: async (_, options) => {
      received = options;
      return reply(200, {
        success: true,
        data: { evidence_url: "private/photo-ref" },
      });
    },
  });
  await api("/evidence/photos", { method: "POST", body: form });
  assert.equal(received.body, form);
  assert.equal(received.headers["Content-Type"], undefined);
});
