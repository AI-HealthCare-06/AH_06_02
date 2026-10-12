/** A 담당 로그인·회원가입 화면을 실제 브라우저에서 확인한다. API 응답은 테스트 전용이다. */
import test from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./browser-harness.mjs";

function failure(code, message, status) {
  return { status, json: { success: false, error: { code, message } } };
}

/** 응답은 경로별로 덮어쓸 수 있다. 호출 기록에는 본문과 인증 헤더를 남긴다. */
async function fixture(page, responses = {}) {
  const calls = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const name = url.pathname.replace("/api/v1", "");
    calls.push({
      path: name,
      query: url.searchParams,
      method: request.method(),
      body: request.postData() ? JSON.parse(request.postData()) : undefined,
      authorization: request.headers().authorization,
    });
    const custom = responses[name];
    if (custom) {
      const result = typeof custom === "function" ? custom(request) : custom;
      if (result.status) {
        await route.fulfill(result);
        return;
      }
      await route.fulfill({ json: { success: true, data: result } });
      return;
    }
    if (name === "/auth/refresh") {
      await route.fulfill(
        failure("AUTH_TOKEN_INVALID", "다시 로그인해주세요.", 401),
      );
      return;
    }
    await route.fulfill({ json: { success: true, data: { items: [] } } });
  });
  return calls;
}

async function open(page, dUrl, fragment) {
  await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#${fragment}`, {
    waitUntil: "domcontentloaded",
    timeout: 15000,
  });
}

async function hasHorizontalScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
}

test("로그인 실패는 서버 문구를 그대로 보여주고 의료 고지와 회원가입 이동을 제공한다", async () => {
  await withPage(async (page, dUrl) => {
    page.setDefaultTimeout(5000);
    await fixture(page, {
      "/auth/login": failure(
        "AUTH_INVALID_CREDENTIALS",
        "이메일 또는 비밀번호가 올바르지 않습니다.",
        401,
      ),
    });
    await open(page, dUrl, "login");
    await page.getByRole("heading", { name: "나의 모험" }).waitFor();
    await page.getByText("의학적 진단·치료를 대신하지 않습니다.").waitFor();

    await page.getByLabel("이메일", { exact: true }).fill("a@example.com");
    await page.getByLabel("비밀번호", { exact: true }).fill("wrong-pass1");
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await page
      .getByRole("alert")
      .filter({ hasText: "이메일 또는 비밀번호가 올바르지 않습니다." })
      .waitFor();
    assert.equal(new URL(page.url()).hash, "#login");

    await page.setViewportSize({ width: 320, height: 740 });
    assert.equal(await hasHorizontalScroll(page), false);

    await page.getByRole("button", { name: "회원가입", exact: true }).click();
    await page.waitForURL("**/#signup");
  });
});

const SIGNUP_FIELDS = [
  "email",
  "password",
  "nickname",
  "birth_year",
  "sex",
  "height_cm",
  "motivation_type",
  "dm_diagnosed",
  "htn_diagnosed",
  "dm_medication",
  "htn_medication",
  "disclaimer_agreed",
];
const signedUp = {
  user_id: 9,
  access_token: "signup-access",
  refresh_token: "signup-refresh",
};
const me = { id: 9, nickname: "탐험가 쿠리", total_xp: 0, level: 1 };

async function fillSignup(page, { agree = true, confirm = "dango1234" } = {}) {
  await page.getByLabel("닉네임", { exact: true }).fill("탐험가 쿠리");
  await page.getByLabel("이메일", { exact: true }).fill("kuri@example.com");
  await page.getByLabel("비밀번호", { exact: true }).fill("dango1234");
  await page.getByLabel("비밀번호 확인", { exact: true }).fill(confirm);
  await page.getByRole("button", { name: /여성/ }).click();
  await page.getByLabel("출생연도", { exact: true }).fill("1984");
  await page.getByLabel("키", { exact: true }).fill("162.5");
  await page.getByLabel("고혈압 진단", { exact: true }).selectOption("yes");
  await page.getByLabel("혈당약", { exact: true }).check();
  await page.getByRole("button", { name: /성장형/ }).click();
  if (agree) await page.getByRole("checkbox", { name: /의료 고지/ }).check();
}

test("회원가입은 명세의 필드만 토큰 없이 보내고 공통 세션에 연결한 뒤 건강정보 입력으로 간다", async () => {
  await withPage(async (page, dUrl) => {
    page.setDefaultTimeout(5000);
    const calls = await fixture(page, {
      "/auth/signup": signedUp,
      "/users/me": me,
    });
    await open(page, dUrl, "signup");
    await fillSignup(page);
    await page.getByRole("button", { name: "모험 시작하기" }).click();
    await page.waitForURL("**/#health");

    const signup = calls.filter((call) => call.path === "/auth/signup");
    assert.equal(signup.length, 1);
    assert.equal(signup[0].authorization, undefined);
    assert.deepEqual(
      Object.keys(signup[0].body).sort(),
      [...SIGNUP_FIELDS].sort(),
    );
    assert.deepEqual(signup[0].body, {
      email: "kuri@example.com",
      password: "dango1234",
      nickname: "탐험가 쿠리",
      birth_year: 1984,
      sex: "F",
      height_cm: 162.5,
      motivation_type: "grow",
      dm_diagnosed: false,
      htn_diagnosed: true,
      dm_medication: true,
      htn_medication: false,
      disclaimer_agreed: true,
    });
    const profile = calls.find((call) => call.path === "/users/me");
    assert.equal(profile.authorization, "Bearer signup-access");
    assert.equal(await page.locator("nav.app-nav").isVisible(), true);
    assert.deepEqual(
      await page.evaluate(() => [localStorage.length, sessionStorage.length]),
      [0, 0],
    );
  });
});

test("이메일 중복 확인은 토큰 없이 조회하고 결과를 보여주며 이메일을 바꾸면 결과를 지운다", async () => {
  await withPage(async (page, dUrl) => {
    page.setDefaultTimeout(5000);
    const calls = await fixture(page, {
      "/auth/check-email": (request) => ({
        available:
          new URL(request.url()).searchParams.get("email") !==
          "taken@example.com",
      }),
    });
    await open(page, dUrl, "signup");
    const email = page.getByLabel("이메일", { exact: true });
    const check = page.getByRole("button", { name: "중복 확인" });

    await email.fill("taken@example.com");
    await check.click();
    await page.getByText("이미 가입된 이메일이에요.").waitFor();
    await email.fill("free+1@example.com");
    assert.equal(await page.getByText("이미 가입된 이메일이에요.").count(), 0);
    await check.click();
    await page.getByText("사용할 수 있는 이메일이에요.").waitFor();

    const checks = calls.filter((call) => call.path === "/auth/check-email");
    assert.deepEqual(
      checks.map((call) => [call.query.get("email"), call.authorization]),
      [
        ["taken@example.com", undefined],
        ["free+1@example.com", undefined],
      ],
    );
  });
});

test("의료 고지에 동의하지 않거나 비밀번호 확인이 다르면 가입을 요청하지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    page.setDefaultTimeout(5000);
    const calls = await fixture(page, { "/auth/signup": signedUp });
    await open(page, dUrl, "signup");
    await page.getByText("의학적 진단·치료를 대신하지 않습니다.").waitFor();

    await fillSignup(page, { agree: false });
    await page.getByRole("button", { name: "모험 시작하기" }).click();
    await fillSignup(page, { confirm: "dango9999" });
    await page.getByRole("button", { name: "모험 시작하기" }).click();

    assert.equal(new URL(page.url()).hash, "#signup");
    assert.equal(
      calls.filter((call) => call.path === "/auth/signup").length,
      0,
    );
  });
});

test("가입 실패는 서버 문구를 그대로 보여주고 다시 보내지 않으며 320px에서 가로로 넘치지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    page.setDefaultTimeout(5000);
    const calls = await fixture(page, {
      "/auth/signup": failure(
        "AUTH_EMAIL_DUPLICATED",
        "이미 가입된 이메일입니다.",
        409,
      ),
    });
    await page.setViewportSize({ width: 320, height: 740 });
    await open(page, dUrl, "signup");
    await fillSignup(page);
    assert.equal(await hasHorizontalScroll(page), false);
    await page.getByRole("button", { name: "모험 시작하기" }).click();
    await page
      .getByRole("alert")
      .filter({ hasText: "이미 가입된 이메일입니다." })
      .waitFor();

    assert.equal(
      calls.filter((call) => call.path === "/auth/signup").length,
      1,
    );
    assert.equal(new URL(page.url()).hash, "#signup");
    assert.equal(
      await page.evaluate(() => document.activeElement?.name),
      "email",
    );
    assert.equal(
      await page.getByLabel("비밀번호", { exact: true }).inputValue(),
      "dango1234",
    );
    assert.equal(await hasHorizontalScroll(page), false);
  });
});
