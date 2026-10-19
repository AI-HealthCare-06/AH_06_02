import assert from "node:assert/strict";
import test from "node:test";
import { withPage } from "./browser-harness.mjs";

const path = `/frontend/docs/prototype/${encodeURIComponent("당고킬러-모험시안_v5.html")}`;
const hat = {
  code: "explorer-hat",
  name: "모험가의 모자",
  slot: "hat",
  rarity: "COMMON",
  asset: "equipment-hat.webp",
  owned: false,
};
const mission = {
  user_challenge_id: 21,
  challenge_id: 2,
  title: "식후 걷기",
  verification_type: "timer",
  start_date: "2026-10-18",
  end_date: "2026-11-14",
  daily_target_count: 1,
  target_value: 10,
  unit: "분",
  progress_rate: 0,
  completed_count: 0,
  target_monster: { code: "viscera" },
  today_occurrences: [
    {
      occurrence_id: 101,
      slot_code: "lunch",
      sequence_no: 1,
      status: "planned",
      timer_session_id: 77,
    },
  ],
};
async function mock(page, state = {}) {
  const calls = [];
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      p = url.pathname.replace("/api/v1", ""),
      body = req.postDataJSON();
    calls.push({ path: p, method: req.method(), body });
    let data = { items: [] };
    if (p === "/auth/refresh") data = { access_token: "v5-test-token" };
    else if (p === "/users/me")
      data = {
        id: 1,
        nickname: "검증 모험가",
        sex: "M",
        dm_diagnosed: false,
        htn_diagnosed: false,
      };
    else if (p === "/users/me/level")
      data = { level: 1, total_xp: 0, current_level_xp: 0, next_level_xp: 100 };
    else if (p === "/dashboard/summary")
      data = {
        prediction_available: true,
        risks: [
          { disease: "diabetes", probability: 0.075 },
          { disease: "hypertension", probability: 0.12 },
        ],
      };
    else if (p === "/monsters/me")
      data = {
        items: [
          {
            code: "viscera",
            name: "비세라",
            user_monster_id: 11,
            is_target: true,
            state: "caution",
            impact_score: 41,
            weekly_progress: state.completed ? 10 : 0,
            seal_progress: 0,
          },
          {
            code: "alde",
            name: "알데",
            user_monster_id: 12,
            is_target: false,
            state: "unmeasured",
            impact_score: null,
            weekly_progress: 0,
          },
        ],
      };
    else if (p === "/user-challenges")
      data = {
        items: state.mission
          ? [
              {
                ...mission,
                completed_count: state.completed ? 1 : 0,
                today_occurrences: mission.today_occurrences.map((o) => ({
                  ...o,
                  status: state.completed ? "completed" : "planned",
                })),
              },
            ]
          : [],
      };
    else if (p === "/rewards/catalog")
      data = { items: [{ ...hat, owned: !!state.claimed }] };
    else if (p === "/adventurer/me") {
      if (req.method() === "PATCH") state.equipment = body.equipment;
      data = {
        equipment: state.equipment || {},
        room: {},
        materials: 0,
        item_stage: 1,
      };
    } else if (p === "/reward-draws")
      data = {
        items: state.draw
          ? [
              {
                draw_id: 8,
                challenge_log_id: 5,
                card_count: 5,
                claimed_at: state.claimed ? "2026-10-18T12:00:00+09:00" : null,
                results: state.claimed
                  ? [{ ...hat, duplicate: false, materials: 0 }]
                  : null,
              },
            ]
          : [],
      };
    else if (p === "/reward-draws/8/claim") {
      state.claimed = true;
      data = {
        draw_id: 8,
        claimed_at: "2026-10-18T12:00:00+09:00",
        results: [{ ...hat, duplicate: false, materials: 0 }],
      };
    } else if (p === "/user-challenges/21/timers/77")
      data = {
        timer_session_id: 77,
        occurrence_id: 101,
        target_seconds: 600,
        elapsed_seconds: state.ready ? 600 : 12,
        ready: !!state.ready,
      };
    else if (p === "/user-challenges/21/logs") {
      state.completed = true;
      data = {
        reward_eligible: true,
        xp_granted: 18,
        weekly_progress: 10,
        reward_draw_id: 8,
      };
    } else if (p === "/health-records") data = { items: [] };
    else if (p === "/adventure/progress")
      data = { days: [], missions: [], cycles: [] };
    else throw new Error("예상하지 않은 API: " + p);
    if (state.offline && p === "/dashboard/summary")
      return route.fulfill({
        status: 503,
        json: {
          success: false,
          error: { code: "INTERNAL_ERROR", message: "검증 중 연결 오류" },
        },
      });
    await route.fulfill({ json: { success: true, data } });
  });
  return calls;
}

test("실제 연결 모드 지도는 서버 위험도·위협도만 표시하고 미산정 마을은 잠근다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(
      await page
        .locator('[data-village-key="viscera"] .village-plaque small')
        .textContent(),
      "위협도 41",
    );
    assert.equal(
      await page.locator('[data-village-key="alde"]').isDisabled(),
      true,
    );
    assert.equal(await page.locator(".prototype-status").count(), 0);
    assert.equal(await page.getByText("시안 예시", { exact: true }).count(), 0);
    await page.setViewportSize({ width: 320, height: 800 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
  }));

test("API 오류에서는 시안 확률을 보여주지 않는다", async () =>
  withPage(async (page, base) => {
    await mock(page, { offline: true });
    await page.goto(new URL(path + "#risk", base).href);
    await page.getByText("검증 중 연결 오류", { exact: true }).waitFor();
    assert.equal(await page.locator("#dm-risk").isVisible(), false);
  }));

test("새로고침한 타이머는 서버 세션을 복원하고 기기 시간을 바꿔도 조기 완료되지 않는다", async () =>
  withPage(async (page, base) => {
    const state = { mission: true, ready: false };
    const calls = await mock(page, state);
    await page.clock.install({ time: new Date("2026-10-18T03:00:00Z") });
    await page.goto(new URL(path + "#today", base).href);
    await page.getByRole("button", { name: "식후 걷기", exact: false }).click();
    await page.getByText("00:12 / 10분", { exact: true }).waitFor();
    await page.clock.runFor(660000);
    assert.equal(
      await page
        .getByRole("button", { name: "시간을 채운 뒤 완료", exact: true })
        .isDisabled(),
      true,
    );
    assert.equal(
      calls.some((c) => c.path.endsWith("/timers") && c.method === "POST"),
      false,
    );
    state.ready = true;
    await page.clock.runFor(3000);
    await page
      .getByRole("button", { name: "수행 완료 기록", exact: true })
      .click();
    await page.getByText(/수행을 기록했어요/).waitFor();
    const completed = calls.find((c) => c.path.endsWith("/logs"));
    assert.equal(completed.body.timer_session_id, 77);
    assert.equal(completed.body.value, undefined);
  }));

test("카드 3장 선택은 서버 수령 후 장착하며 새로고침 후 장착을 복원한다", async () =>
  withPage(async (page, base) => {
    const state = { draw: true };
    const calls = await mock(page, state);
    await page.goto(new URL(path + "#rewards", base).href);
    await page.getByRole("button", { name: "카드 뽑기", exact: true }).click();
    for (const index of [0, 2, 4])
      await page
        .getByRole("button", { name: `${index + 1}번째 카드`, exact: true })
        .click();
    await page
      .getByRole("button", { name: "선택한 카드 3장 열기", exact: true })
      .click();
    await page.getByText("보상 3개를 받았어요!", { exact: true }).waitFor();
    assert.deepEqual(
      calls.find((c) => c.path.endsWith("/claim")).body.positions,
      [0, 2, 4],
    );
    await page
      .getByRole("button", { name: "바로 꾸미기", exact: true })
      .click();
    await page.getByRole("button", { name: "적용하기", exact: true }).click();
    await page
      .getByText("꾸미기 설정을 저장했어요.", { exact: true })
      .waitFor();
    assert.deepEqual(state.equipment, { hat: "explorer-hat" });
    await page.reload();
    await page.getByRole("button", { name: "모험가", exact: true }).click();
    await page.getByRole("button", { name: "해제하기", exact: true }).waitFor();
    assert.equal(await page.locator(".avatar-rig .gear-hat").count(), 1);
  }));

test("320px에서도 가방·후보 도감·성장 달력이 가로로 넘치지 않는다", async () =>
  withPage(async (page, base) => {
    await mock(page, { mission: true, draw: true });
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(new URL(path + "#rewards", base).href);
    for (const tab of ["카드 뽑기", "모험가", "방 꾸미기", "후보 70종"]) {
      await page.getByRole("button", { name: tab, exact: true }).click();
      await page.locator(".scene:not([hidden]):not(.live-loading)").waitFor();
      if (tab === "후보 70종")
        await page.getByText("기본 갈색 헝클머리", { exact: true }).waitFor();
      assert.equal(
        await page.evaluate(
          () =>
            document.querySelector("#screen").scrollWidth <=
            document.querySelector("#screen").clientWidth,
        ),
        true,
        tab,
      );
    }
    await page.getByRole("button", { name: "나의 성장", exact: true }).click();
    for (const tab of ["캐릭터", "건강 데이터", "업적", "히스토리"]) {
      await page.getByRole("button", { name: tab, exact: true }).click();
      await page.locator(".scene:not([hidden]):not(.live-loading)").waitFor();

      assert.equal(
        await page.evaluate(
          () =>
            document.querySelector("#screen").scrollWidth <=
            document.querySelector("#screen").clientWidth,
        ),
        true,
        tab,
      );
    }
  }));
