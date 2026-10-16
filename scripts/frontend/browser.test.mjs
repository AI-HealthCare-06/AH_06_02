/** 실제 브라우저에서 확인한다. API 응답은 테스트 전용이며 제품에는 포함하지 않는다. */
import test from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./browser-harness.mjs";

const cards = [
  {
    recommendation_id: 7,
    challenge_id: 1,
    title: "식후 걷기",
    description: "식후 10분 걷기",
    verification_type: "timer",
    target_value: 10,
    unit: "분",
    daily_target_count: 2,
    daily_xp: 36,
    difficulty: "challenge",
    safety_check_required: false,
    cycle_id: 1,
    target_monster: { monster_id: 1, code: "viscera", name: "비세라" },
  },
];
const monster = {
  monster_id: 1,
  code: "viscera",
  name: "비세라",
  title: "비만·복부 요인",
  state: "rage",
  impact_score: 72,
  weekly_progress: 135,
  is_target: true,
  seal_count: 0,
};

async function fixture(page) {
  let active = false;
  let completed = false;
  let points = 135;
  const writes = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    let data;
    if (request.method() !== "GET")
      writes.push({ path: url.pathname, body: request.postDataJSON() });
    if (url.pathname.endsWith("/challenge-recommendations/generate"))
      data = {
        items: cards,
        total: 1,
        remaining_slots: 2,
        model_version: "test-model",
        model_experimental: true,
      };
    else if (
      url.pathname.endsWith("/challenge-recommendations") &&
      request.method() === "GET"
    )
      data = { items: [], total: 0 };
    else if (url.pathname.endsWith("/monsters/me"))
      data = {
        items: [
          { ...monster, weekly_progress: points },
          {
            monster_id: 2,
            code: "spike",
            name: "스파이크",
            impact_score: null,
            state: "unmeasured",
            weekly_progress: 0,
            is_target: false,
          },
        ],
      };
    else if (
      url.pathname.endsWith("/user-challenges") &&
      request.method() === "POST"
    ) {
      active = true;
      data = { items: [{ user_challenge_id: 11 }], active_count: 1 };
    } else if (url.pathname.endsWith("/user-challenges"))
      data = {
        items:
          active && url.searchParams.get("status") === "active"
            ? [
                {
                  user_challenge_id: 11,
                  challenge_id: 1,
                  title: "식후 걷기",
                  verification_type: "timer",
                  target_value: 10,
                  unit: "분",
                  start_date: "2026-10-12",
                  end_date: "2026-11-08",
                  today_date: "2026-10-12",
                  cycle_id: 1,
                  cycle_week: 1,
                  target_monster: cards[0].target_monster,
                  daily_target_count: 2,
                  completed_count: completed ? 1 : 0,
                  scheduled_opportunity_count: 56,
                  progress_rate: completed ? 1 / 56 : 0,
                  habit_established: null,
                  today_occurrences: [
                    {
                      occurrence_id: 101,
                      slot_code: "lunch",
                      sequence_no: 1,
                      status: completed ? "completed" : "planned",
                    },
                    {
                      occurrence_id: 102,
                      slot_code: "dinner",
                      sequence_no: 1,
                      status: "planned",
                    },
                  ],
                },
              ]
            : [],
        total: active ? 1 : 0,
      };
    else if (url.pathname.endsWith("/logs") && request.method() === "POST") {
      completed = true;
      points += 10;
      data = {
        log_id: 8,
        result: "done",
        reward_eligible: true,
        xp_granted: 18,
        weekly_progress: points,
        level_up: false,
        reward: {
          reward_id: 3,
          code: "gluco_blade",
          name: "글루코 블레이드",
          reward_kind: "item",
        },
      };
    } else if (url.pathname.endsWith("/users/me/level"))
      data = {
        level: 2,
        total_xp: 154,
        current_level_xp: 54,
        next_level_xp: 120,
      };
    else if (url.pathname.endsWith("/rewards/me"))
      data = {
        items: completed
          ? [
              {
                reward_id: 3,
                code: "gluco_blade",
                name: "글루코 블레이드",
                motivation_type: "grow",
                reward_kind: "item",
                item_level: 1,
                acquired_at: "2026-10-12T12:00:00+09:00",
              },
            ]
          : [],
        total: completed ? 1 : 0,
      };
    else if (url.pathname.endsWith("/stop")) {
      active = false;
      data = { user_challenge_id: 11, status: "abandoned" };
    } else {
      await route.fulfill({
        status: 404,
        json: {
          success: false,
          error: { code: "NOT_FOUND", message: "찾을 수 없습니다." },
        },
      });
      return;
    }
    await route.fulfill({ status: 200, json: { success: true, data } });
  });
  return writes;
}

test("네 화면은 서버 결과로 시작·타이머·점수·보상·도감 상태를 연결한다", async () => {
  await withPage(async (page, url) => {
    page.setDefaultTimeout(3000);
    await page.clock.install({ time: new Date("2026-10-12T03:00:00Z") });
    const writes = await fixture(page);
    await page.goto(`${url}#reco`);
    await page.getByRole("button", { name: /식후 걷기.*하루 2회/ }).click();
    await page.getByRole("button", { name: "선택한 챌린지 시작하기" }).click();
    await page.waitForURL("**/#today");
    await page.locator('[data-timer-start="101"]').click();
    assert.equal(
      await page.locator('[data-timer-submit="101"]').isDisabled(),
      true,
    );
    assert.equal(
      writes.filter((item) => item.path.endsWith("/logs")).length,
      0,
    );
    await page.clock.fastForward(600000);
    await page.locator('[data-timer-submit="101"]').click();
    await page
      .getByText("글루코 블레이드를 얻었어요.", { exact: false })
      .waitFor();
    assert.equal(
      writes.find((item) => item.path.endsWith("/logs")).body.value,
      10,
    );
    assert.equal(
      writes.find((item) => item.path.endsWith("/logs")).body.context_slot,
      "lunch",
    );
    await page.locator('.bottom-nav a[href="#progress"]').click();
    await page.getByText("145 / 100", { exact: true }).waitFor();
    assert.equal(
      await page.locator("[data-score-fill]").getAttribute("style"),
      "--fill:100%",
    );
    await page.getByText("글루코 블레이드", { exact: true }).waitFor();
    await page.screenshot({
      path: process.env.D_SCREENSHOTS_DIR
        ? `${process.env.D_SCREENSHOTS_DIR}/progress-desktop.png`
        : "/tmp/d-progress.png",
      fullPage: true,
    });
    await page.locator('.bottom-nav a[href="#monsters"]').click();
    await page.getByRole("button", { name: /스파이크.*산정 보류/ }).waitFor();
    assert.equal(
      await page.locator('[data-monster="1"] b').textContent(),
      "72",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.screenshot({
      path: process.env.D_SCREENSHOTS_DIR
        ? `${process.env.D_SCREENSHOTS_DIR}/monsters-mobile.png`
        : "/tmp/d-monsters.png",
      fullPage: true,
    });
  });
});

test("실패와 재로그인 화면에는 시안의 가상 데이터와 서버 내부 문구가 나타나지 않는다", async () => {
  await withPage(async (page, url) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({
        status: 401,
        json: {
          success: false,
          error: { code: "AUTH_TOKEN_INVALID", message: "내부 스택 비밀" },
        },
      }),
    );
    await page.goto(`${url}#progress`);
    await page.getByRole("button", { name: "로그인하기" }).waitFor();
    const text = await page.locator("main").innerText();
    assert.equal(text.includes("내부 스택 비밀"), false);
    assert.equal(text.includes("54 / 120"), false);
    assert.equal(text.includes("비세라"), false);
  });
});

test("중단은 확인 후 한 번만 요청하고 서버 목록을 다시 조회한다", async () => {
  await withPage(async (page, url) => {
    await page.clock.install({ time: new Date("2026-10-12T03:00:00Z") });
    const writes = await fixture(page);
    await page.goto(`${url}#reco`);
    await page.locator('[data-pick="7"]').click();
    await page.locator("[data-start]").click();
    await page.waitForURL("**/#today");
    await page.locator('.bottom-nav a[href="#progress"]').click();
    await page
      .getByRole("button", { name: "챌린지 중단", exact: true })
      .click();
    await page.getByRole("button", { name: "취소", exact: true }).click();
    assert.equal(
      writes.filter((item) => item.path.endsWith("/stop")).length,
      0,
    );
    await page
      .getByRole("button", { name: "챌린지 중단", exact: true })
      .click();
    await page.getByRole("button", { name: "중단하기", exact: true }).click();
    await page.getByText("챌린지를 중단했어요.", { exact: true }).waitFor();
    assert.equal(
      writes.filter((item) => item.path.endsWith("/stop")).length,
      1,
    );
    await page
      .getByRole("heading", { name: "진행 중인 챌린지가 없어요" })
      .waitFor();
  });
});

test("추천에서 제외한 챌린지는 사용자가 직접 다시 켤 수 있다", async () => {
  await withPage(async (page, url) => {
    await fixture(page);
    let suppressed = true;
    await page.route("**/api/v1/challenge-recommendations**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith("/unsuppress")) {
        suppressed = false;
        await route.fulfill({
          json: {
            success: true,
            data: { recommendation_id: 7, suppressed_until_manual: false },
          },
        });
      } else if (path.endsWith("/generate") && suppressed)
        await route.fulfill({
          status: 409,
          json: {
            success: false,
            error: {
              code: "CHLG_RECOMMENDATION_UNAVAILABLE",
              message: "추천 없음",
            },
          },
        });
      else if (request.method() === "GET")
        await route.fulfill({
          json: {
            success: true,
            data: {
              items: [
                {
                  ...cards[0],
                  action: "not_applicable",
                  suppressed_until_manual: suppressed,
                },
              ],
              total: 1,
            },
          },
        });
      else await route.fallback();
    });
    await page.goto(`${url}#reco`);
    await page
      .getByRole("button", { name: "추천 다시 켜기" })
      .click({ timeout: 2500 });
    await page.locator('[data-pick="7"]').waitFor();
    assert.equal(suppressed, false);
  });
});

test("공통 인증이 로그아웃 상태면 예전 저장 토큰을 다시 사용하지 않는다", async () => {
  await withPage(async (page, url) => {
    const authorizations = [];
    await page.addInitScript(() => {
      window.dangoAuth = {
        getAccessToken: () => null,
        setAccessToken: () => {},
      };
      sessionStorage.setItem("dango.access_token", "previous-user-token");
    });
    await page.route("**/api/v1/**", async (route) => {
      authorizations.push(route.request().headers().authorization);
      await route.fulfill({
        status: 401,
        json: { success: false, error: { code: "AUTH_TOKEN_INVALID" } },
      });
    });
    await page.goto(`${url}#today`);
    await page.getByRole("button", { name: "로그인하기" }).waitFor();
    assert.equal(
      authorizations.some((value) => value?.includes("previous-user-token")),
      false,
    );
  });
});

test("D 화면 이동은 다른 담당자의 메뉴 상태를 바꾸지 않는다", async () => {
  await withPage(async (page, url) => {
    await fixture(page);
    await page.addInitScript(() =>
      document.addEventListener("DOMContentLoaded", () => {
        const link = document.createElement("a");
        link.dataset.route = "login";
        link.dataset.externalNav = "true";
        link.setAttribute("aria-current", "page");
        link.hidden = true;
        document.body.append(link);
      }),
    );
    await page.goto(`${url}#today`);
    await page
      .getByRole("heading", { name: "오늘의 공략을 시작해요." })
      .waitFor();
    assert.equal(
      await page.locator("[data-external-nav]").getAttribute("aria-current"),
      "page",
    );
  });
});
