import test from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./browser-harness.mjs";

/** 예정일·대상 변경·재시도 계약을 실제 DOM과 HTTP 요청으로 확인한다. 응답은 테스트 전용이다. */
async function fixture(
  page,
  { recommendationError, recommendationReason, impactExplanation } = {},
) {
  let changed = false;
  const calls = [];
  const targets = () => [
    {
      monster_id: 1,
      user_monster_id: 11,
      code: "viscera",
      name: "비세라",
      state: "rage",
      impact_score: 80,
      impact_explanation: impactExplanation,
      weekly_progress: 135,
      seal_count: 2,
      is_target: !changed,
      target_change_allowed: true,
    },
    {
      monster_id: 2,
      user_monster_id: 12,
      code: "cotinine",
      name: "코티니",
      state: "caution",
      impact_score: 45,
      weekly_progress: 10,
      seal_count: 1,
      is_target: changed,
      target_change_allowed: true,
    },
  ];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    calls.push({
      path,
      method: request.method(),
      body: request.postDataJSON(),
    });
    let data = { items: [], total: 0 };
    if (path.endsWith("/auth/refresh")) data = { access_token: "test-token" };
    else if (path.endsWith("/users/me"))
      data = { id: 3, nickname: "계약 테스터" };
    else if (path.endsWith("/monsters/me")) data = { items: targets() };
    else if (path.endsWith("/attack-cycles/current/target")) {
      changed = true;
      data = { cycle_id: 1, target_user_monster_id: 12, monster: targets()[1] };
    } else if (path.endsWith("/challenge-recommendations/generate")) {
      if (recommendationError)
        return route.fulfill({
          status: 409,
          json: {
            success: false,
            error: {
              code: "CHLG_RECOMMENDATION_UNAVAILABLE",
              reason: recommendationReason,
              message: recommendationError,
            },
          },
        });
      data = {
        items: [
          {
            recommendation_id: 7,
            challenge_id: 1,
            title: "한 정거장 먼저 내려 걷기",
            context_type: "event",
            verification_type: "manual",
            daily_target_count: 1,
            difficulty: "normal",
            target_monster: targets().find((item) => item.is_target),
          },
        ],
        remaining_slots: 2,
        cycle_end_date: "2026-11-08",
      };
    } else if (path.endsWith("/user-challenges") && request.method() === "POST")
      data = { items: [{ user_challenge_id: 21 }], active_count: 1 };
    await route.fulfill({ json: { success: true, data } });
  });
  return calls;
}

test("이용일 확인 카드만 예정일을 받고 중복 없이 KST 날짜를 시작 요청에 보낸다", async () => {
  await withPage(async (page, dUrl) => {
    const calls = await fixture(page);
    await page.clock.install({ time: new Date("2026-10-12T03:00:00Z") });
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#reco`);
    await page.locator("[data-pick='7']").click();
    await page.getByRole("button", { name: "선택한 챌린지 시작하기" }).click();
    await page.getByText("예정 이용일을 한 날짜 이상 확인해주세요.").waitFor();
    assert.equal(
      calls.filter(
        (call) =>
          call.method === "POST" && call.path.endsWith("/user-challenges"),
      ).length,
      0,
    );
    const date = page.getByLabel("예정 이용일", { exact: true });
    await date.fill("2026-11-09");
    await page.getByRole("button", { name: "이용일 추가" }).click();
    await page
      .getByText("오늘부터 주기 종료일까지의 이용일을 선택해주세요.")
      .waitFor();
    for (const day of ["2026-10-15", "2026-10-13", "2026-10-13"]) {
      await date.fill(day);
      await page.getByRole("button", { name: "이용일 추가" }).click();
    }
    assert.equal(await page.locator("[data-remove-date]").count(), 2);
    await page.setViewportSize({ width: 320, height: 740 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.getByRole("button", { name: "선택한 챌린지 시작하기" }).click();
    await page.waitForURL("**/#today");
    const starts = calls.filter(
      (call) =>
        call.method === "POST" && call.path.endsWith("/user-challenges"),
    );
    assert.equal(starts.length, 1);
    assert.deepEqual(starts[0].body, {
      recommendation_ids: [7],
      scheduled_dates: ["2026-10-13", "2026-10-15"],
    });
  });
});

test("도감은 본인 대상 ID로 변경하고 새 대상을 표시하며 기존 공략 점수를 보존한다", async () => {
  await withPage(async (page, dUrl) => {
    const calls = await fixture(page);
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#monsters`);
    await page.locator("[data-monster='2']").click();
    await page.getByRole("button", { name: "이 몬스터 공략하기" }).click();
    await page
      .getByText(
        "시작 전 공략 대상을 변경했어요. 새 대상의 챌린지를 골라주세요.",
      )
      .waitFor();
    assert.deepEqual(
      calls.find((call) => call.path.endsWith("/attack-cycles/current/target"))
        .body,
      { user_monster_id: 12 },
    );
    await page.locator("[data-monster='2'] .target-mark").waitFor();
    await page.locator("[data-monster='1']").click();
    await page.getByText(/이번 주 공략 점수 135/).waitFor();
    await page.getByRole("button", { name: "도감으로 돌아가기" }).click();
  });
});

test("완료 직후 추천만 두 번 더 호출하고 최종 서버 오류를 화면에 표시한다", async () => {
  await withPage(async (page, dUrl) => {
    const error = "확인한 모델의 아티팩트가 준비되지 않았습니다.";
    const calls = await fixture(page, { recommendationError: error });
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#risk`);
    await page.getByRole("heading", { name: "현재 위험도" }).waitFor();
    await page.evaluate(() => {
      window.dangoPredictionReady.markDone({
        prediction_id: 501,
        status: "done",
      });
      window.dangoNavigate("reco");
    });
    await page.getByText(error, { exact: true }).waitFor();
    const generates = () =>
      calls.filter((call) =>
        call.path.endsWith("/challenge-recommendations/generate"),
      );
    assert.equal(generates().length, 3);
    await page.getByRole("button", { name: "다시 확인하기" }).click();
    await page.getByText(error, { exact: true }).waitFor();
    assert.equal(generates().length, 4);
  });
});

test("추가 후보가 없으면 진행 중인 공략으로 안내하고 재시도하지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    const calls = await fixture(page, {
      recommendationError:
        "현재 공략 대상에 추가로 추천할 챌린지가 없어요. 진행 중인 챌린지를 이어가세요.",
      recommendationReason: "no_additional_candidates",
    });
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#reco`);
    await page
      .getByRole("heading", { name: "진행 중인 공략을 이어가세요" })
      .waitFor();
    await page.getByRole("button", { name: "진행 중인 공략 보기" }).click();
    await page.waitForURL("**/#today");
    assert.equal(
      calls.filter((call) =>
        call.path.endsWith("/challenge-recommendations/generate"),
      ).length,
      1,
    );
  });
});

test("도감은 서버가 저장한 대표 산정 요인을 표시한다", async () => {
  await withPage(async (page, dUrl) => {
    await fixture(page, {
      impactExplanation: {
        status: "available",
        model_version: "stored-test-model",
        winners: [
          {
            disease: "diabetes",
            factor_key: "bmi_high",
            score: 80,
            source: "contribution",
          },
          {
            disease: "hypertension",
            factor_key: "physical_activity_low",
            score: 80,
            source: "global",
          },
        ],
      },
    });
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#monsters`);
    await page
      .getByText(
        "현재 위협도를 대표하는 요인: 당뇨 · 체질량지수, 고혈압 · 신체활동",
      )
      .waitFor();
  });
});
