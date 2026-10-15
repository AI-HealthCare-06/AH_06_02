import test from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./browser-harness.mjs";

/** 실제 C 대기 화면과 D 추천·수행 화면을 연결한다. 추론·DB 응답은 테스트 전용이다. */
test("건강기록의 예측 접수와 완료 확인 후 추천·시작·수행까지 연결하고 추천 준비 지연만 재시도한다", async () => {
  await withPage(async (page, dUrl) => {
    const calls = [];
    let active = false;
    let completed = false;
    let recommendations = 0;
    await page.clock.install({ time: new Date("2026-10-15T04:00:00Z") });
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      calls.push({
        path,
        method: request.method(),
        body: request.postDataJSON(),
      });
      let data = { items: [], total: 0 };
      if (path.endsWith("/auth/refresh"))
        data = { access_token: "flow-test-token" };
      else if (path.endsWith("/users/me"))
        data = { id: 3, nickname: "흐름 검증" };
      else if (path.endsWith("/predictions"))
        data = { prediction_id: 501, status: "pending" };
      else if (path.endsWith("/predictions/501"))
        data = { prediction_id: 501, status: "done" };
      else if (path.endsWith("/monsters/me"))
        data = {
          items: [
            {
              monster_id: 1,
              user_monster_id: 11,
              code: "viscera",
              name: "비세라",
              title: "체격·활동 관련 요인",
              state: "caution",
              impact_score: 50,
              weekly_progress: completed ? 10 : 0,
              is_target: true,
            },
          ],
        };
      else if (path.endsWith("/challenge-recommendations/generate")) {
        if (++recommendations === 1)
          return route.fulfill({
            status: 404,
            json: {
              success: false,
              error: { code: "PRED_NOT_FOUND", message: "추천 근거 준비 중" },
            },
          });
        data = {
          items: [
            {
              recommendation_id: 7,
              title: "움직임 휴식",
              verification_type: "manual",
              difficulty: "easy",
              daily_target_count: 1,
              target_monster: {
                monster_id: 1,
                code: "viscera",
                name: "비세라",
              },
            },
          ],
          remaining_slots: 2,
        };
      } else if (
        path.endsWith("/user-challenges") &&
        request.method() === "POST"
      ) {
        active = true;
        data = { items: [{ user_challenge_id: 21 }], active_count: 1 };
      } else if (path.endsWith("/user-challenges"))
        data = {
          items: active
            ? [
                {
                  user_challenge_id: 21,
                  title: "움직임 휴식",
                  verification_type: "manual",
                  start_date: "2026-10-15",
                  end_date: "2026-11-11",
                  today_date: "2026-10-15",
                  today_occurrences: [
                    {
                      occurrence_id: 101,
                      sequence_no: 1,
                      status: completed ? "completed" : "planned",
                    },
                  ],
                },
              ]
            : [],
          total: active ? 1 : 0,
        };
      else if (path.endsWith("/logs")) {
        completed = true;
        data = { reward_eligible: true, xp_granted: 10 };
      }
      await route.fulfill({ json: { success: true, data } });
    });
    await page.goto(
      `${dUrl.replace("/frontend/d/", "/frontend/")}#waiting?record_id=31`,
    );
    await page.locator('[data-pick="7"]').click();
    await page.getByRole("button", { name: "선택한 챌린지 시작하기" }).click();
    await page.getByRole("button", { name: "직접 수행 확인하기" }).click();
    await page.getByRole("button", { name: "수행했어요", exact: true }).click();
    await page.getByText("수행을 인정받았어요. 10 XP를 얻었어요.").waitFor();
    assert.equal(recommendations, 2);
    const posts = calls.filter((call) => call.method === "POST");
    assert.deepEqual(
      posts
        .filter((call) => call.path.endsWith("/predictions"))
        .map((call) => call.body),
      [{ health_record_id: 31 }],
    );
    assert.deepEqual(
      posts
        .filter((call) => call.path.endsWith("/user-challenges"))
        .map((call) => call.body),
      [{ recommendation_ids: [7] }],
    );
    assert.equal(posts.filter((call) => call.path.endsWith("/logs")).length, 1);
    assert.equal(
      posts.find((call) => call.path.endsWith("/logs")).body
        .verification_method,
      "manual",
    );
  });
});

test("예측이 실패하면 추천을 생성하지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    let generated = 0;
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data = {};
      if (path.endsWith("/auth/refresh"))
        data = { access_token: "failure-test-token" };
      else if (path.endsWith("/users/me"))
        data = { id: 3, nickname: "실패 검증" };
      else if (path.endsWith("/predictions/501"))
        data = {
          prediction_id: 501,
          status: "failed",
          failure: { message: "예측을 완료하지 못했습니다.", retryable: false },
        };
      else if (path.endsWith("/challenge-recommendations/generate"))
        generated++;
      await route.fulfill({ json: { success: true, data } });
    });
    await page.goto(
      `${dUrl.replace("/frontend/d/", "/frontend/")}#waiting?prediction_id=501`,
    );
    await page.getByText("예측을 완료하지 못했습니다.").waitFor();
    assert.equal(generated, 0);
  });
});
