import test from "node:test";
import assert from "node:assert/strict";
import { AuthSession } from "../../frontend/shared/auth.mjs";
const response = (status, data) =>
  new Response(
    JSON.stringify(
      status === 200
        ? { success: true, data }
        : {
            success: false,
            error: {
              code: "AUTH_TOKEN_INVALID",
              message: "로그인이 필요합니다.",
            },
          },
    ),
    { status, headers: { "Content-Type": "application/json" } },
  );

test("새로고침 시 쿠키로 한 번 복원하고 내 정보를 확인한 뒤 로그인 상태가 된다", async () => {
  const paths = [];
  const auth = new AuthSession({
    fetchImpl: async (url, options) => {
      paths.push(url);
      if (url.endsWith("/refresh")) {
        assert.equal(options.headers.Authorization, undefined);
        return response(200, { access_token: "restored-token" });
      }
      assert.equal(options.headers.Authorization, "Bearer restored-token");
      return response(200, {
        id: 7,
        nickname: "테스터",
        total_xp: 12,
        level: 1,
      });
    },
  });
  assert.deepEqual(await Promise.all([auth.restore(), auth.restore()]), [
    true,
    true,
  ]);
  assert.equal(auth.signedIn, true);
  assert.equal(auth.user.nickname, "테스터");
  assert.deepEqual(paths, ["/api/v1/auth/refresh", "/api/v1/users/me"]);
});

test("로그인 결과를 공통 세션에 넣고 서버 로그아웃 성공 후 메모리 상태를 지운다", async () => {
  const auth = new AuthSession({
    fetchImpl: async (url, options) => {
      if (url.endsWith("/login")) {
        assert.equal(options.headers.Authorization, undefined);
        return response(200, {
          access_token: "login-token",
          user: { id: 7, nickname: "새 사용자" },
        });
      }
      assert.equal(options.headers.Authorization, "Bearer login-token");
      return response(200, { logged_out: true });
    },
  });
  await auth.login({ email: "tester@example.com", password: "test-only" });
  assert.equal(auth.signedIn, true);
  assert.equal(auth.user.nickname, "새 사용자");
  await auth.logout();
  assert.equal(auth.getAccessToken(), null);
  assert.equal(auth.user, null);
  assert.equal(await auth.restore(), false);
});

test("로그아웃 뒤 도착한 인증 갱신은 이전 토큰을 되살리지 않는다", async () => {
  let release;
  let announce;
  const started = new Promise((resolve) => {
    announce = resolve;
  });
  const refresh = new Promise((resolve) => {
    release = resolve;
  });
  const auth = new AuthSession({
    fetchImpl: async (url, options) => {
      if (url.endsWith("/login"))
        return response(200, { access_token: "old", user: { id: 1 } });
      if (url.endsWith("/logout")) return response(200, { logged_out: true });
      if (url.endsWith("/refresh")) {
        announce();
        return refresh;
      }
      return options.headers.Authorization === "Bearer old"
        ? response(401)
        : response(200, { id: 1 });
    },
  });
  await auth.login({ email: "tester@example.com", password: "test-only" });
  const request = auth.api("/users/me");
  await started;
  await auth.logout();
  release(response(200, { access_token: "late" }));
  await assert.rejects(request, (error) => error.status === 401);
  assert.equal(auth.getAccessToken(), null);
});
