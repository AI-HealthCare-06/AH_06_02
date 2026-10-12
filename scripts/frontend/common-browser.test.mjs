import test from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./browser-harness.mjs";

async function fixture(page, { authenticated = false } = {}) {
  const calls = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push({
      path: url.pathname,
      method: request.method(),
      body: request.postData(),
      authorization: request.headers().authorization,
    });
    let data;
    if (url.pathname.endsWith("/auth/refresh") && !authenticated) {
      await route.fulfill({
        status: 401,
        json: {
          success: false,
          error: {
            code: "AUTH_TOKEN_INVALID",
            message: "다시 로그인해주세요.",
          },
        },
      });
      return;
    }
    if (url.pathname.endsWith("/auth/refresh"))
      data = { access_token: "restored" };
    else if (url.pathname.endsWith("/auth/login")) {
      authenticated = true;
      data = {
        access_token: "login-token",
        user: { id: 3, nickname: "공통 테스터", total_xp: 0, level: 1 },
      };
    } else if (url.pathname.endsWith("/auth/logout")) {
      authenticated = false;
      data = { logged_out: true };
    } else if (url.pathname.endsWith("/users/me"))
      data = { id: 3, nickname: "공통 테스터", total_xp: 0, level: 1 };
    else if (url.pathname.endsWith("/users/me/level"))
      data = { level: 1, total_xp: 0, current_level_xp: 0, next_level_xp: 100 };
    else data = { items: [], total: 0 };
    await route.fulfill({ json: { success: true, data } });
  });
  return calls;
}

test("공통 진입점은 로그인 보호·원래 화면 복귀·한 벌의 메뉴·D 이동을 제공한다", async () => {
  await withPage(async (page, dUrl) => {
    page.setDefaultTimeout(5000);
    const calls = await fixture(page);
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#monsters`, {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.getByLabel("이메일", { exact: true }).fill("tester@example.com");
    await page.getByLabel("비밀번호", { exact: true }).fill("test-only");
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page.waitForURL("**/#monsters");
    await page.getByRole("heading", { name: /몬스터의 약점/ }).waitFor();
    assert.equal(
      calls.filter((call) => call.path.endsWith("/monsters/me")).length,
      1,
    );
    assert.equal(await page.locator(".topbar").count(), 1);
    assert.equal(await page.locator("nav.app-nav").count(), 1);
    assert.equal(await page.locator("nav.bottom-nav").count(), 0);
    await page
      .getByRole("button", { name: "챌린지 고르기", exact: true })
      .click();
    await page.waitForURL("**/#reco");
    assert.equal(
      await page.locator(".common-toolbar span").textContent(),
      "챌린지 선택",
    );
    calls.length = 0;
    await page.locator('nav.app-nav a[href="#today"]').click();
    await page
      .getByRole("heading", { name: "오늘의 공략을 시작해요." })
      .waitFor();
    assert.equal(
      calls.filter((call) => call.path.endsWith("/monsters/me")).length,
      1,
    );
    assert.equal(
      calls.filter((call) => call.path.endsWith("/user-challenges")).length,
      1,
    );
    await page.setViewportSize({ width: 320, height: 740 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await page.getByLabel("이메일", { exact: true }).waitFor();
    assert.equal(await page.locator("nav.app-nav").isVisible(), false);
    assert.equal(await page.evaluate(() => localStorage.length), 0);
  });
});

test("쿠키 복원과 브라우저 뒤로가기는 예측 ID를 보존하고 새 작업을 만들지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    const calls = await fixture(page, { authenticated: true });
    const url = dUrl.replace("/frontend/d/", "/frontend/");
    await page.goto(`${url}#waiting?prediction_id=501`, {
      waitUntil: "domcontentloaded",
    });
    await page
      .getByRole("heading", { name: "예측 대기", exact: true })
      .waitFor();
    assert.equal(
      calls.filter((call) => call.path.endsWith("/auth/refresh")).length,
      1,
    );
    assert.equal(
      calls.filter((call) => call.path.endsWith("/users/me")).length,
      1,
    );
    await page.locator('nav.app-nav a[href="#health"]').click();
    await page
      .getByRole("heading", { name: "기본 건강정보", exact: true })
      .waitFor();
    await page.goBack();
    await page
      .getByRole("heading", { name: "예측 대기", exact: true })
      .waitFor();
    assert.equal(new URL(page.url()).hash, "#waiting?prediction_id=501");
    assert.equal(
      calls.some(
        (call) => call.path.endsWith("/predictions") && call.method === "POST",
      ),
      false,
    );
  });
});

test("느린 이전 화면의 응답이 도착해도 새 담당자 화면을 덮지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    await fixture(page, { authenticated: true });
    let announce;
    let release;
    const started = new Promise((resolve) => {
      announce = resolve;
    });
    const delayed = new Promise((resolve) => {
      release = resolve;
    });
    await page.route("**/api/v1/monsters/me", async (route) => {
      announce();
      await delayed;
      await route.fulfill({ json: { success: true, data: { items: [] } } });
    });
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#monsters`, {
      waitUntil: "domcontentloaded",
    });
    await started;
    await page.locator('nav.app-nav a[href="#health"]').click();
    await page
      .getByRole("heading", { name: "기본 건강정보", exact: true })
      .waitFor();
    release();
    await page
      .getByRole("heading", { name: "기본 건강정보", exact: true })
      .waitFor();
    assert.equal(new URL(page.url()).hash, "#health");
    assert.equal(await page.locator("[data-content]").count(), 0);
  });
});
