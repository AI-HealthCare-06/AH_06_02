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
async function fillSignup(
  page,
  {
    walkingDays = "3",
    weight = "70",
    height = "170",
    untilHealth = false,
  } = {},
) {
  await page.locator(".login .text-link[data-route=signup]").click();
  await page.locator("#nickname").fill("새 모험가");
  await page.locator('.signup-form [type="email"]').fill("new@dangokiller.com");
  for (const field of await page
    .locator('.signup-form [type="password"]')
    .all())
    await field.fill("test1234a");
  await page.locator(".signup-form .consent input").check();
  await page.locator('.signup-form [type="submit"]').click();
  await page.getByRole("button", { name: "♂ 남성" }).click();
  await page.getByRole("spinbutton", { name: "출생연도" }).fill("1975");
  await page.getByRole("spinbutton", { name: "키" }).fill(height);
  await page.getByRole("spinbutton", { name: "체중" }).fill(weight);
  await page.getByRole("spinbutton", { name: "허리둘레" }).fill("85");
  await page.locator('.health button[type="submit"]').click();
  if (untilHealth) return;
  await page.getByRole("button", { name: "안 피워요" }).click();
  await page.locator("#alcohol-frequency").selectOption("1");
  await page
    .getByRole("spinbutton", { name: "주당 걷기 일수" })
    .fill(walkingDays);
  await page.getByRole("spinbutton", { name: "1회 걷기 시간" }).fill("30");
  await page.getByRole("spinbutton", { name: "주당 근력운동 일수" }).fill("1");
  await page
    .getByRole("spinbutton", { name: "하루 앉아 있는 시간" })
    .fill("480");
  await page.locator("#dining-out-freq").selectOption("5");
  await page.locator('.health2 button[type="submit"]').click();
}
async function mock(page, state = {}) {
  const calls = [];
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      p = url.pathname.replace("/api/v1", ""),
      body = req.postDataJSON();
    calls.push({ path: p, method: req.method(), body });
    let data = { items: [] };
    if (p === "/auth/refresh" && state.signedOut)
      return route.fulfill({
        status: 401,
        json: {
          success: false,
          error: { code: "UNAUTHORIZED", message: "로그인이 필요합니다." },
        },
      });
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
        prediction_id: 5,
        latest_health_record: { health_record_id: 9 },
        risks: [
          {
            disease: "diabetes",
            probability: 0.075,
            delta: state.dmDelta ?? null,
          },
          { disease: "hypertension", probability: 0.12, delta: null },
        ],
      };
    else if (p === "/monsters/me")
      data = {
        items: [
          {
            code: "viscera",
            name: "비세라",
            title: "체격·활동 관련 요인",
            user_monster_id: 11,
            is_target: true,
            state: "caution",
            impact_score: 41,
            weekly_progress: state.completed ? 10 : 0,
            seal_progress: null,
            impact_explanation: {
              status: "available",
              winners: [
                { disease: "hypertension", factor_key: "bmi_high", score: 41 },
              ],
            },
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
    else if (p === "/user-challenges" && req.method() === "POST") {
      state.mission = true;
      data = { items: [] };
    } else if (p === "/user-challenges")
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
      data = {
        items: [
          { ...hat, owned: !!state.claimed },
          {
            code: "room-basic-bed",
            name: "기본 원목 침대",
            slot: "bed",
            rarity: "COMMON",
            asset: "room-decor-v1/basic-bed.webp",
            starter: true,
            owned: true,
          },
          {
            code: "room-basic-desk",
            name: "기본 컴퓨터 책상",
            slot: "computer",
            rarity: "COMMON",
            asset: "room-decor-v1/basic-desk.webp",
            starter: true,
            owned: true,
          },
          {
            code: "lantern",
            name: "모험가의 등불",
            slot: "ornament",
            rarity: "COMMON",
            asset: "room-decor-v1/lantern.webp",
            starter: false,
            owned: true,
          },
          {
            code: "room-cloud-chair",
            name: "구름 라운지 의자",
            slot: "chair",
            rarity: "RARE",
            asset: "room-decor-v1/cloud-chair.webp",
            starter: false,
            owned: false,
          },
        ],
      };
    else if (p === "/adventurer/me") {
      if (req.method() === "PATCH") state.equipment = body.equipment;
      data = {
        equipment: state.equipment || {},
        room: state.room || {},
        materials: state.materials ?? 0,
        item_stage: state.stage ?? 1,
      };
    } else if (p === "/reward-draws" && state.manyDraws) {
      // 최신순 101건 중 가장 오래된 1건만 아직 받지 않았다
      const page = Number(url.searchParams.get("page") || 1);
      const size = Number(url.searchParams.get("size") || 20);
      const all = Array.from({ length: 101 }, (_, i) => ({
        draw_id: 1000 - i,
        challenge_log_id: 1000 - i,
        card_count: 5,
        claimed_at: i === 100 ? null : "2026-10-01T12:00:00+09:00",
        results: i === 100 ? null : [],
      }));
      data = {
        items: all.slice((page - 1) * size, page * size),
        total: all.length,
        page,
        size,
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
        results: state.drawResult
          ? [state.drawResult]
          : [{ ...hat, duplicate: false, materials: 0 }],
      };
    } else if (/^\/user-challenges\/21\/timers\/77\/(pause|resume)$/.test(p)) {
      state.paused = p.endsWith("/pause");
      data = {
        timer_session_id: 77,
        occurrence_id: 101,
        target_seconds: 600,
        elapsed_seconds: 12,
        ready: false,
        paused: state.paused,
      };
    } else if (p === "/user-challenges/21/timers/77")
      data = {
        timer_session_id: 77,
        occurrence_id: 101,
        target_seconds: 600,
        elapsed_seconds: state.ready ? 600 : 12,
        ready: !!state.ready,
        paused: !!state.paused,
      };
    else if (p === "/user-challenges/21/logs") {
      state.completed = true;
      data = {
        reward_eligible: true,
        xp_granted: 18,
        weekly_progress: 10,
        reward_draw_id: 8,
      };
    } else if (p === "/predictions/5/contributions")
      data = {
        diseases: [
          {
            disease: "diabetes",
            items: [
              {
                factor_key: "age",
                contribution: -0.012,
                direction: "decrease",
                modifiable: false,
              },
              {
                factor_key: "family_history_dm",
                contribution: 0.0117,
                direction: "increase",
                modifiable: false,
              },
              {
                factor_key: "bmi_high",
                contribution: 0.0106,
                direction: "increase",
                modifiable: true,
              },
              {
                factor_key: "smoking_current",
                contribution: 0.0004,
                direction: "increase",
                modifiable: true,
              },
            ],
          },
        ],
      };
    else if (p === "/challenge-recommendations/generate") {
      if (state.full)
        return route.fulfill({
          status: 409,
          json: {
            success: false,
            error: {
              code: "CHLG_RECOMMENDATION_UNAVAILABLE",
              message:
                "현재 주기에 추가로 시작할 수 있는 챌린지가 없어요. 진행 중인 챌린지를 이어가세요.",
              reason: "slots_unavailable",
            },
          },
        });
      // 실제 서버처럼 생성할 때마다 새 추천 행을 만든다. 쿨다운·제외가 없는 거절은 다시 추천된다
      if (state.cards) {
        const latest = state.cards.filter(
          (c, i) =>
            state.cards.findIndex((o) => o.challenge_id === c.challenge_id) ===
            i,
        );
        const again = latest
          .filter((c) => c.action === "rejected" && !c.suppressed_until_manual)
          .map((c) => ({
            ...c,
            recommendation_id: c.recommendation_id + 100,
            action: null,
          }));
        state.cards = [...again, ...state.cards];
      }
      data = { items: state.cards || [] };
    } else if (
      /^\/challenge-recommendations\/\d+\/unsuppress$/.test(p) &&
      req.method() === "PATCH"
    ) {
      const id = Number(p.split("/")[2]);
      state.cards = state.cards.map((c) =>
        c.recommendation_id === id
          ? { ...c, suppressed_until_manual: false }
          : c,
      );
      data = { recommendation_id: id, suppressed_until_manual: false };
    } else if (
      /^\/challenge-recommendations\/\d+$/.test(p) &&
      req.method() === "PATCH"
    ) {
      // 3회 연속 거절이면 서버는 재추천 시점을 고르라고 거절한다
      if (state.cooldownRequired && !body.cooldown_choice)
        return route.fulfill({
          status: 400,
          json: {
            success: false,
            error: {
              code: "CHLG_INVALID_COOLDOWN",
              message: "다시 추천받을 시점을 골라주세요.",
            },
          },
        });
      const id = Number(p.split("/")[2]);
      const suppressed =
        body.action === "not_applicable" ||
        body.cooldown_choice === "until_manual";
      state.cards = state.cards.map((c) =>
        c.recommendation_id === id
          ? {
              ...c,
              action: body.action,
              suppressed_until_manual: suppressed,
            }
          : c,
      );
      data = {
        recommendation_id: id,
        action: body.action,
        cooldown_choice: body.cooldown_choice || null,
        suppressed_until_manual: suppressed,
      };
    } else if (p === "/challenge-recommendations")
      data = { items: state.cards || [] };
    else if (p === "/auth/signup")
      data = {
        access_token: "v5-signup-token",
        user: { id: 2, nickname: body.nickname, sex: body.sex },
      };
    else if (p === "/health-records" && req.method() === "POST") {
      if (state.rejectHealth === "decimal") {
        // 실제 서버(Pydantic)는 입력 모델 이름을 붙인 필드와 영어 사유를 돌려준다
        state.rejectHealth = false;
        return route.fulfill({
          status: 400,
          json: {
            success: false,
            error: {
              code: "VALIDATION_ERROR",
              message: "입력값을 다시 확인해주세요.",
              fields: [
                {
                  field: "SimpleHealthRecordInput.weight_kg",
                  reason:
                    "Decimal input should have no more than 1 decimal place",
                },
              ],
            },
          },
        });
      }
      if (state.rejectHealth) {
        state.rejectHealth = false;
        return route.fulfill({
          status: 400,
          json: {
            success: false,
            error: {
              code: "HLTH_VALUE_OUT_OF_RANGE",
              message: "입력하신 값이 허용 범위를 벗어났습니다.",
              fields: [{ field: "walking_days", min: 0, max: 7 }],
            },
          },
        });
      }
      data = { health_record_id: 9 };
    } else if (p === "/predictions" && req.method() === "POST") {
      // 응답 전에 연결이 끊기면 앱은 접수 여부를 알 수 없다
      if (state.dropPrediction) return route.abort("failed");
      data = { prediction_id: 5 };
    } else if (p === "/predictions/5" && state.failPrediction) {
      state.failPrediction = false;
      data = {
        status: "failed",
        failure: {
          code: "INTERNAL_ERROR",
          message: "예측에 실패했습니다. 다시 시도해주세요.",
          retryable: true,
        },
      };
    } else if (p === "/predictions/5")
      data = { status: state.predicting ? "pending" : "done" };
    else if (p === "/health-records" && state.manyRecords) {
      // 최신순 101건 중 가장 오래된 1건만 체중이 99.9kg 이다
      const page = Number(url.searchParams.get("page") || 1);
      const size = Number(url.searchParams.get("size") || 20);
      const all = Array.from({ length: 101 }, (_, i) => ({
        health_record_id: 500 - i,
        recorded_at: `2026-${i === 100 ? "01-02" : "10-01"}T08:00:00+09:00`,
        input_mode: "daily",
        weight_kg: i === 100 ? 99.9 : 70,
        waist_cm: null,
        sbp: null,
        dbp: null,
        fasting_glucose: null,
      }));
      data = {
        items: all.slice((page - 1) * size, page * size),
        total: all.length,
        page,
        size,
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

test("카드 5장 중 1장을 골라 서버 수령 후 장착하며 새로고침 후 장착을 복원한다", async () =>
  withPage(async (page, base) => {
    const state = { draw: true };
    const calls = await mock(page, state);
    await page.goto(new URL(path + "#rewards", base).href);
    await page.getByRole("button", { name: "카드 뽑기", exact: true }).click();
    await page.getByText("5장 중 1장을 골라주세요", { exact: true }).waitFor();
    // 다른 카드를 누르면 선택이 그 카드로 바뀐다
    for (const index of [0, 2])
      await page
        .getByRole("button", { name: `${index + 1}번째 카드`, exact: true })
        .click();
    assert.equal(
      await page.locator('.live-card-back[aria-pressed="true"]').count(),
      1,
    );
    await page
      .getByRole("button", { name: "선택한 카드 열기", exact: true })
      .click();
    await page.getByText("보상을 받았어요!", { exact: true }).waitFor();
    assert.deepEqual(
      calls.find((c) => c.path.endsWith("/claim")).body.positions,
      [2],
    );
    await page
      .getByRole("button", { name: "바로 꾸미기", exact: true })
      .click();
    await page.getByRole("button", { name: /모험가의 모자 적용하기/ }).click();
    await page
      .getByText("꾸미기 설정을 저장했어요.", { exact: true })
      .waitFor();
    assert.deepEqual(state.equipment, { hat: "explorer-hat" });
    await page.reload();
    await page.getByRole("button", { name: "모험가", exact: true }).click();
    await page
      .getByRole("button", { name: /모험가의 모자 해제하기/ })
      .waitFor();
    assert.equal(await page.locator(".avatar-rig .gear-hat").count(), 1);
  }));

// 꾸미기 화면은 방·모험가가 가장 크고 아이템은 옆(넓은 화면)이나 아래(휴대폰) 띠에 둔다
async function decorateLayout(page) {
  return page.evaluate(() => {
    const stage = document
      .querySelector(".live-decorate-stage")
      .getBoundingClientRect();
    const rail = document
      .querySelector(".live-item-rail")
      .getBoundingClientRect();
    return {
      stage: {
        left: stage.left,
        right: stage.right,
        top: stage.top,
        bottom: stage.bottom,
        width: stage.width,
      },
      rail: { left: rail.left, top: rail.top, width: rail.width },
      overflow: document.documentElement.scrollWidth > innerWidth,
    };
  });
}

for (const [tab, label, subject] of [
  ["room", "방 꾸미기", "방을"],
  ["adventurer", "모험가", "모험가를"],
])
  test(`${label} 화면은 ${subject} 크게 두고 아이템은 옆이나 아래 띠에 둔다`, async () =>
    withPage(async (page, base) => {
      await mock(page, { claimed: true });
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(new URL(path + "#rewards", base).href);
      await page.getByRole("button", { name: label, exact: true }).click();
      await page.locator(".live-item-rail").waitFor();
      const wide = await decorateLayout(page);
      assert.ok(
        wide.rail.left >= wide.stage.right - 1,
        "넓은 화면: 아이템 띠는 오른쪽에 있다",
      );
      assert.ok(
        wide.stage.width >= wide.rail.width * 2.5,
        "넓은 화면: 방·모험가가 아이템 띠보다 훨씬 크다",
      );
      const tile = page.locator(".live-item-rail button", {
        hasText: tab === "room" ? "기본 원목 침대" : "모험가의 모자",
      });
      assert.equal(await tile.count(), 1, "아이템 칸이 버튼이다");
      for (const width of [390, 320]) {
        await page.setViewportSize({ width, height: 844 });
        const narrow = await decorateLayout(page);
        assert.ok(
          narrow.rail.top >= narrow.stage.bottom - 1,
          `${width}px: 아이템 띠는 아래에 있다`,
        );
        assert.ok(
          narrow.stage.width >= width * 0.85,
          `${width}px: 방·모험가가 화면 폭을 거의 채운다`,
        );
        assert.equal(
          narrow.overflow,
          false,
          `${width}px: 가로로 넘치지 않는다`,
        );
      }
    }));

test("방 가구는 방 그림의 바닥 위에 놓이고 책상이 문을 가리지 않는다", async () =>
  withPage(async (page, base) => {
    await mock(page, {
      room: {
        bed: "room-basic-bed",
        computer: "room-basic-desk",
        ornament: "lantern",
      },
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(new URL(path + "#rewards", base).href);
    await page.getByRole("button", { name: "방 꾸미기", exact: true }).click();
    await page.locator(".room-stage .room-ornament").waitFor();
    // 방 그림(5:4) 기준 퍼센트. 바닥 꼭짓점과 문 오른쪽 끝은 room-base.webp 에서 잰 값이다
    const boxes = await page.evaluate(() => {
      const stage = document
        .querySelector(".live-decorate-stage .room-stage")
        .getBoundingClientRect();
      const pct = (el) => {
        const r = el.getBoundingClientRect();
        return {
          left: ((r.left - stage.left) / stage.width) * 100,
          cx: ((r.left + r.width / 2 - stage.left) / stage.width) * 100,
          bottom: ((r.bottom - stage.top) / stage.height) * 100,
        };
      };
      return {
        ratio: stage.width / stage.height,
        ornament: pct(document.querySelector(".room-ornament")),
        desk: pct(document.querySelector(".room-desk")),
        bedWidth:
          (document.querySelector(".room-bed").getBoundingClientRect().width /
            stage.width) *
          100,
      };
    });
    const floor = [
      [50, 32],
      [91, 60],
      [50, 88],
      [11, 56],
    ];
    const inside = (x, y) =>
      floor.every(([x1, y1], i) => {
        const [x2, y2] = floor[(i + 1) % floor.length];
        return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1) >= 0;
      });
    assert.ok(
      Math.abs(boxes.ratio - 1.25) < 0.02,
      "방 틀은 그림과 같은 5:4 다",
    );
    assert.ok(
      inside(boxes.ornament.cx, boxes.ornament.bottom),
      `장식은 바닥 안에 놓인다 (${boxes.ornament.cx.toFixed(1)}, ${boxes.ornament.bottom.toFixed(1)})`,
    );
    assert.ok(
      boxes.desk.left >= 25,
      `책상이 문(19~28%)을 가리지 않는다 (${boxes.desk.left.toFixed(1)})`,
    );
    assert.ok(
      boxes.bedWidth <= 36,
      `가구가 방에 비해 너무 크지 않다 (침대 ${boxes.bedWidth.toFixed(1)}%)`,
    );
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

test("건강정보 입력칸의 예시는 입력값과 구분되게 흐리게 보이고 '예:'로 시작한다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#health", base).href);
    const field = page.getByRole("spinbutton", { name: "출생연도" });
    await field.waitFor();
    const look = await field.evaluate((el) => {
      const value = getComputedStyle(el);
      const hint = getComputedStyle(el, "::placeholder");
      return {
        placeholder: el.placeholder,
        hintWeight: hint.fontWeight,
        valueWeight: value.fontWeight,
        hintColor: hint.color,
        valueColor: value.color,
      };
    });
    assert.match(look.placeholder, /^예: /);
    assert.equal(look.hintWeight, "400");
    assert.notEqual(look.hintColor, look.valueColor);
    for (const label of ["수축기 혈압", "주당 걷기 일수"])
      assert.match(
        await page
          .locator(`[aria-label="${label}"]`)
          .getAttribute("placeholder"),
        /^예: /,
      );
  }));

test("건강정보에서 빠진 칸은 그 칸에 오류를 표시하고 그 칸으로 이동한다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#health", base).href);
    await page.getByRole("button", { name: "♂ 남성" }).click();
    await page.getByRole("spinbutton", { name: "출생연도" }).fill("1975");
    await page.locator('.health button[type="submit"]').click();
    const height = page.getByRole("spinbutton", { name: "키" });
    assert.equal(await height.getAttribute("aria-invalid"), "true");
    assert.equal(
      await height.evaluate((el) => el === document.activeElement),
      true,
    );
    const describedBy = await height.getAttribute("aria-describedby");
    assert.match(
      await page.locator("#" + describedBy).textContent(),
      /키를 입력해주세요/,
    );
    await height.fill("170");
    assert.equal(await height.getAttribute("aria-invalid"), null);
    assert.equal(await page.locator(".field-error").count(), 0);
  }));

test("회원가입은 비밀번호 규칙을 미리 보여주고 틀린 칸에 오류를 표시한다", async () =>
  withPage(async (page, base) => {
    await mock(page, { signedOut: true });
    await page.goto(new URL(path + "#login", base).href);
    await page.locator(".login .text-link[data-route=signup]").click();
    await page
      .getByText("영문과 숫자를 포함해 8자 이상", { exact: false })
      .waitFor();
    await page.locator("#nickname").fill("모험가");
    await page.locator('.signup-form [type="email"]').fill("a@dangokiller.com");
    const [password, confirm] = await page
      .locator('.signup-form [type="password"]')
      .all();
    await password.fill("testtest");
    await confirm.fill("testtest");
    await page.locator(".signup-form .consent input").check();
    await page.locator('.signup-form [type="submit"]').click();
    assert.equal(await password.getAttribute("aria-invalid"), "true");
    assert.equal(
      await password.evaluate((el) => el === document.activeElement),
      true,
    );
    // 오류 문구가 나란한 두 칸 사이에 끼어 배치를 깨지 않는다
    const [left, right] = await Promise.all([
      password.evaluate(
        (el) => el.closest("label").getBoundingClientRect().top,
      ),
      confirm.evaluate((el) => el.closest("label").getBoundingClientRect().top),
    ]);
    assert.equal(Math.round(left), Math.round(right));
  }));

test("검진정보 제목은 선택 단계임을 밝힌다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#health3", base).href);
    await page
      .locator(".health3 h1")
      .filter({ hasText: "검진 수치가 있으면 알려주세요(선택)" })
      .waitFor({ timeout: 3000 });
  }));

test("실제 연결 모드의 예측 대기 화면에는 시안용 예시 결과 버튼이 없다", async () =>
  withPage(async (page, base) => {
    await mock(page, { signedOut: true, predicting: true });
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page.locator('.scene[data-page="waiting"]:not([hidden])').waitFor();
    assert.equal(await page.getByText("예시 결과 보기").count(), 0);
  }));

test("전투 화면은 수행해도 위협도가 바로 줄지 않는 이유를 위협도 옆에 알려준다", async () =>
  withPage(async (page, base) => {
    await mock(page, { mission: true, completed: true });
    await page.goto(new URL(path + "#reco", base).href);
    await page
      .locator("#battle-score")
      .filter({ hasText: "10 / 100" })
      .waitFor();
    const note = page
      .locator(".fighter-panel.opponent")
      .getByText("재측정 때 바뀌어요", { exact: false });
    assert.equal(await note.isVisible(), true);
    assert.equal(await page.locator("#battle-threat").textContent(), "41");
  }));

test("받을 보상이 있으면 가방 아이콘에 표시하고 가방을 카드 뽑기로 연다", async () =>
  withPage(async (page, base) => {
    await mock(page, { draw: true });
    await page.goto(new URL(path + "#risk", base).href);
    const bag = page.locator('#adventure-nav [data-main-target="bag"]');
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(await bag.getAttribute("aria-label"), "가방, 받을 보상 1개");
    await bag.click();
    await page
      .getByText("5장 중 1장을 골라주세요", { exact: true })
      .waitFor({ timeout: 3000 });
    assert.equal(
      await page
        .getByText("아직 획득한 보상이 없어요", { exact: false })
        .count(),
      0,
    );
  }));

const card = (overrides) => ({
  recommendation_id: 31,
  challenge_id: 9,
  title: "계단으로 올라가기",
  description: null,
  factor_key: "physical_activity_low",
  difficulty: "challenge",
  verification_type: "manual",
  context_type: "daily",
  context_label: "이동 시",
  daily_target_count: 1,
  target_value: null,
  unit: null,
  daily_xp: 36,
  safety_check_required: true,
  target_monster: { code: "viscera" },
  action: null,
  ...overrides,
});

test("전투 카드 이름은 시안의 요인별 공격 이름을 쓴다", async () =>
  withPage(async (page, base) => {
    await mock(page, {
      cards: [
        card({
          recommendation_id: 41,
          challenge_id: 4,
          title: "맨몸 근력 10분",
          factor_key: "strength_activity_low",
        }),
        card({
          recommendation_id: 42,
          challenge_id: 5,
          title: "업무 중 움직임 휴식",
          factor_key: "sedentary_time_high",
        }),
        card({
          recommendation_id: 43,
          challenge_id: 6,
          title: "계단으로 올라가기",
        }),
      ],
    });
    await page.goto(new URL(path + "#reco", base).href);
    await page.locator(".reco-card").first().waitFor();
    assert.deepEqual(
      await page.locator(".reco-card .quest-card-label").allTextContents(),
      ["근력 공격", "휴식 공격", "걷기 공격"],
    );
  }));

test("챌린지 상세는 빈 값 없이 목표·XP·난이도와 안전 안내를 보여주고 시작하면 알려준다", async () =>
  withPage(async (page, base) => {
    await mock(page, { cards: [card({ challenge_id: 2 })] });
    await page.goto(new URL(path + "#reco", base).href);
    await page.locator(".reco-card").first().click();
    const details = page.locator(".live-details");
    await details.waitFor();
    const text = (await details.textContent()).replace(/\s+/g, " ");
    assert.doesNotMatch(text, /회 ·\s*(인증|$)/);
    assert.match(text, /하루 목표 36 XP/);
    assert.match(text, /도전/);
    await page
      .getByText("통증이나 불편이 생기면 중단하세요", { exact: false })
      .waitFor();
    await page.locator("#live-safety").check();
    await page.getByRole("button", { name: "이 챌린지 시작하기" }).click();
    await page.getByText("챌린지를 시작했어요", { exact: false }).waitFor();
    assert.equal(
      await page
        .locator("[data-live-stop]")
        .evaluate((el) => el.classList.contains("danger-link")),
      true,
    );
  }));

test("가족력은 해당 없을 때 비워두라는 안내를 바로 아래에 둔다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#health2", base).href);
    const block = page.locator(".health2 .medicine");
    await block.waitFor();
    assert.match(
      await block.textContent(),
      /가족력이 없으면 두 항목 모두 선택하지 않아요/,
    );
    assert.equal(await block.locator(".required-note").count(), 0);
  }));

test("v4 에서 맞춘 문구와 기여요인 Top3 를 v5 에도 보여준다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(
      await page
        .locator('[data-village-key="viscera"] .village-plaque span')
        .textContent(),
      "체격·활동 관련 요인",
    );
    // 가입·검진 화면은 같은 문서 안에 숨겨져 있어 문구만 확인한다
    assert.equal(
      (await page.locator(".signup-form .consent").textContent())
        .replace(/\s+/g, " ")
        .trim(),
      "의료 고지를 확인했습니다.*필수",
    );
    assert.match(
      await page.locator(".health3").textContent(),
      /비워두면 간편 모드로 저장돼요/,
    );
    await page.goto(new URL(path + "#monsters", base).href);
    await page.reload();
    const top = page.locator(".live-top-factors");
    await top.waitFor();
    const rows = await top.locator(".factor-card").allTextContents();
    assert.equal(rows.length, 3);
    assert.match(rows[0], /당뇨 가족력.*\+1\.2%p.*바꿀 수 없는 요인/);
    assert.match(rows[1], /높은 체질량지수.*\+1\.1%p.*비세라/);
    assert.match(rows[2], /흡연.*\+0\.1%p 미만.*코티니/);
  }));

test("도감은 휴대폰 화면에서 두 마리씩 보여주고 산정 설명을 요인 이름으로 쓴다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(new URL(path + "#monsters", base).href);
    const cards = page.locator(".live-monster");
    await cards.first().waitFor();
    const [first, second] = await Promise.all([
      cards.nth(0).boundingBox(),
      cards.nth(1).boundingBox(),
    ]);
    assert.equal(Math.round(first.y), Math.round(second.y));
    await cards.nth(0).locator("summary").click();
    assert.match(
      await cards.nth(0).locator("details").textContent(),
      /높은 체질량지수 41/,
    );
    assert.doesNotMatch(
      await cards.nth(0).locator("details").textContent(),
      /bmi_high/,
    );
    await page.setViewportSize({ width: 320, height: 800 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
  }));

test("로그인된 상태에서는 회원가입 화면 대신 지도로 보내 기존 계정 정보를 덮어쓰지 않는다", async () =>
  withPage(async (page, base) => {
    const calls = await mock(page);
    await page.goto(new URL(path + "#signup", base).href);
    await page
      .locator("#live-feedback")
      .filter({ hasText: "이미 로그인되어 있어요" })
      .waitFor();
    assert.equal(await page.evaluate(() => document.body.dataset.page), "risk");
    assert.equal(await page.locator(".signup-form").isVisible(), false);
    assert.equal(
      await page.locator('#app-menu [data-route="signup"]').count(),
      0,
      "메뉴에서도 회원가입 화면으로 들어가지 않는다",
    );
    assert.equal(
      calls.some((c) => c.path === "/users/me" && c.method === "PATCH"),
      false,
    );
  }));

test("새 챌린지를 더 시작할 수 없어도 퀘스트에서 진행 중인 챌린지로 들어간다", async () =>
  withPage(async (page, base) => {
    await mock(page, { mission: true, full: true });
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    await page.locator('#adventure-nav [data-main-target="quests"]').click();
    await page
      .locator(".reco-card")
      .filter({ hasText: "식후 걷기 · 진행 중" })
      .waitFor();
    assert.equal(await page.evaluate(() => document.body.dataset.page), "reco");
    const notice = await page.locator("#live-feedback").textContent();
    assert.match(notice, /진행 중인 챌린지를 이어가세요/);
    // 같은 주기 2주차부터 1개를 더 시작할 수 있어 주기 전체를 막는 것처럼 말하지 않는다
    assert.doesNotMatch(notice, /현재 주기에|다음 주기/);
  }));

test("가입 중 서버가 건강정보를 거절하면 입력을 지키고 틀린 칸이 있는 단계로 옮긴다", async () =>
  withPage(async (page, origin) => {
    const calls = await mock(page, { signedOut: true, rejectHealth: true });
    await page.goto(new URL(path + "#login", origin).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    const walking = page.getByRole("spinbutton", { name: "주당 걷기 일수" });
    await page.locator(".field-error").waitFor();
    assert.equal(
      await page.evaluate(() => document.body.dataset.page),
      "health2",
    );
    assert.equal(await walking.getAttribute("aria-invalid"), "true");
    assert.match(await page.locator(".field-error").textContent(), /0~7/);
    assert.equal(
      await page.locator('[aria-label="출생연도"]').inputValue(),
      "1975",
      "앞 단계 입력도 그대로 남는다",
    );
    await page.locator('.health2 button[type="submit"]').click();
    await page.locator('.health3 button[type="submit"]').click();
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    const posts = (p) =>
      calls.filter((c) => c.path === p && c.method === "POST").length;
    assert.equal(posts("/auth/signup"), 1, "계정은 한 번만 만든다");
    assert.equal(posts("/health-records"), 2);
  }));

test("허용 범위를 벗어난 값은 계정을 만들기 전에 그 단계에서 알려준다", async () =>
  withPage(async (page, origin) => {
    const calls = await mock(page, { signedOut: true });
    await page.goto(new URL(path + "#login", origin).href);
    await fillSignup(page, { walkingDays: "8" });
    await page.locator(".field-error").waitFor();
    assert.equal(
      await page.evaluate(() => document.body.dataset.page),
      "health2",
    );
    assert.equal(
      await page
        .getByRole("spinbutton", { name: "주당 걷기 일수" })
        .getAttribute("aria-invalid"),
      "true",
    );
    assert.match(await page.locator(".field-error").textContent(), /0~7/);
    assert.equal(
      calls.some((c) => c.path === "/auth/signup"),
      false,
    );
  }));

test("예측 대기 중 새로고침해도 결과 확인을 이어가고 다시 확인 버튼을 보여준다", async () =>
  withPage(async (page, origin) => {
    const state = { signedOut: true, predicting: true };
    const calls = await mock(page, state);
    await page.goto(new URL(path + "#login", origin).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page.locator('.scene[data-page="waiting"]:not([hidden])').waitFor();
    await page
      .locator(".waiting [data-live-retry]")
      .filter({ hasText: "결과 다시 확인" })
      .waitFor();
    // 새로고침해도 로그인 쿠키는 남아 있다
    state.signedOut = false;
    state.predicting = false;
    const before = calls.length;
    await page.reload();
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(
      calls
        .slice(before)
        .some((c) => c.path === "/predictions/5" && c.method === "GET"),
      true,
      "새로고침 뒤에도 같은 예측 결과를 조회한다",
    );
  }));

test("브라우저 뒤로가기·앞으로가기를 하면 주소와 함께 화면도 바뀐다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    await page.locator('#adventure-nav [data-main-target="bag"]').click();
    await page.locator('.scene[data-page="rewards"]:not([hidden])').waitFor();
    await page.goBack();
    await page.locator('.scene[data-page="risk"]:not([hidden])').waitFor();
    assert.equal(await page.evaluate(() => document.body.dataset.page), "risk");
    await page.goForward();
    await page.locator('.scene[data-page="rewards"]:not([hidden])').waitFor();
    assert.equal(new URL(page.url()).hash, "#rewards");
  }));

test("예측이 끝난 뒤 뒤로가기로 대기 화면에 갇히지 않는다", async () =>
  withPage(async (page, base) => {
    await mock(page, { signedOut: true });
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    await page.goBack();
    await page.waitForFunction(() => location.hash !== "#waiting");
    assert.notEqual(
      await page.evaluate(() => document.body.dataset.page),
      "waiting",
    );
  }));

test("메뉴에서 화면을 고르면 메뉴 창이 닫힌다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    await page.locator("#menu-toggle").click();
    const menu = page.locator("#app-menu");
    assert.equal(await menu.evaluate((el) => el.open), true);
    await menu.getByRole("button", { name: /가방 · 아이템과 보상/ }).click();
    await page.locator('.scene[data-page="rewards"]:not([hidden])').waitFor();
    assert.equal(await menu.evaluate((el) => el.open), false);
  }));

test("외형 변화 기준이 정해지기 전에는 단계별 모습을 미리보기로 안내한다", async () =>
  withPage(async (page, base) => {
    await mock(page);
    await page.goto(new URL(path + "#evolution", base).href);
    const area = page.locator('.scene[data-page="evolution"] .panel-pad');
    await area.locator(".evolution-strip").waitFor();
    const text = (await area.textContent()).replace(/\s+/g, " ");
    assert.match(text, /미리보기/);
    assert.doesNotMatch(text, /공략 진행률에 따라 외형이 변해요/);
  }));

test("받을 보상이 오래돼 다음 페이지에 있어도 가방에 표시한다", async () =>
  withPage(async (page, base) => {
    await mock(page, { manyDraws: true });
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(
      await page
        .locator('#adventure-nav [data-main-target="bag"]')
        .getAttribute("aria-label"),
      "가방, 받을 보상 1개",
    );
  }));

test("슬롯이 다 차면 시작 안 한 추천 카드는 흐리게 막고 지금은 추가로 시작할 수 없다고 알린다", async () =>
  withPage(async (page, base) => {
    await mock(page, { mission: true, full: true, cards: [card()] });
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    await page.locator('#adventure-nav [data-main-target="quests"]').click();
    const locked = page
      .locator(".reco-card")
      .filter({ hasText: "계단으로 올라가기" });
    await locked.waitFor();
    assert.equal(await locked.isDisabled(), true);
    assert.match(await locked.textContent(), /지금은 추가로 시작할 수 없어요/);
    assert.doesNotMatch(await locked.textContent(), /다음 주기/);
    assert.ok(
      Number(await locked.evaluate((el) => getComputedStyle(el).opacity)) < 1,
      "흐리게 보인다",
    );
    const live = page.locator(".reco-card").filter({ hasText: "진행 중" });
    assert.equal(await live.isDisabled(), false, "진행 중 카드는 그대로 연다");
  }));

test("슬롯이 남아 있으면 추천 카드를 그대로 시작할 수 있다", async () =>
  withPage(async (page, base) => {
    await mock(page, { mission: true, cards: [card()] });
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    await page.locator('#adventure-nav [data-main-target="quests"]').click();
    const fresh = page
      .locator(".reco-card")
      .filter({ hasText: "계단으로 올라가기" });
    await fresh.waitFor();
    assert.equal(await fresh.isDisabled(), false);
    assert.doesNotMatch(await fresh.textContent(), /다음 주기/);
  }));

test("전투 화면에서 새로고침해도 슬롯이 찬 상태를 다시 확인해 카드를 막는다", async () =>
  withPage(async (page, base) => {
    await mock(page, { mission: true, full: true, cards: [card()] });
    await page.goto(new URL(path + "#reco", base).href);
    const locked = page
      .locator(".reco-card")
      .filter({ hasText: "계단으로 올라가기" });
    await locked.waitFor();
    assert.equal(await locked.isDisabled(), true);
    assert.match(
      await page.locator("#live-feedback").textContent(),
      /지금은 챌린지를 더 시작할 수 없어요/,
    );
  }));

test("서버가 입력 모델 이름을 붙인 필드로 거절해도 그 입력칸이 있는 단계로 옮기고 한국어로 알린다", async () =>
  withPage(async (page, base) => {
    await mock(page, { signedOut: true, rejectHealth: "decimal" });
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page.locator(".field-error").waitFor();
    assert.equal(
      await page.evaluate(() => document.body.dataset.page),
      "health",
    );
    assert.equal(
      await page
        .getByRole("spinbutton", { name: "체중" })
        .getAttribute("aria-invalid"),
      "true",
    );
    const text = await page.locator(".field-error").textContent();
    assert.doesNotMatch(text, /[A-Za-z]/, "영어 사유를 그대로 보여주지 않는다");
  }));

test("소수 자릿수가 맞지 않는 값은 계정을 만들기 전에 그 칸에서 알려준다", async () =>
  withPage(async (page, base) => {
    const calls = await mock(page, { signedOut: true });
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page, { weight: "70.55", untilHealth: true });
    await page.locator(".field-error").waitFor();
    assert.equal(
      await page.evaluate(() => document.body.dataset.page),
      "health",
    );
    assert.equal(
      await page
        .getByRole("spinbutton", { name: "체중" })
        .getAttribute("aria-invalid"),
      "true",
    );
    assert.match(
      await page.locator(".field-error").textContent(),
      /소수점 아래 한 자리/,
    );
    assert.equal(
      calls.some((c) => c.path === "/auth/signup"),
      false,
    );
  }));

test("로그인하지 않은 채 회원가입 주소로 들어오면 바로 회원가입 화면을 연다", async () =>
  withPage(async (page, base) => {
    await mock(page, { signedOut: true });
    await page.goto(new URL(path + "#signup", base).href);
    await page.locator('.scene[data-page="signup"]:not([hidden])').waitFor();
    assert.equal(
      await page.evaluate(() => document.body.dataset.page),
      "signup",
    );
    assert.equal(new URL(page.url()).hash, "#signup");
  }));

test("키와 출생연도도 저장 형식에 맞지 않으면 그 칸에서 알려준다", async () =>
  withPage(async (page, base) => {
    const calls = await mock(page, { signedOut: true });
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page, { untilHealth: true, height: "170.55" });
    await page.locator(".field-error").waitFor();
    const height = page.getByRole("spinbutton", { name: "키" });
    assert.equal(await height.getAttribute("aria-invalid"), "true");
    assert.match(
      await page.locator(".field-error").textContent(),
      /소수점 아래 한 자리/,
    );
    await height.fill("170.5");
    await page.getByRole("spinbutton", { name: "출생연도" }).fill("1975.5");
    await page.locator('.health button[type="submit"]').click();
    await page.locator(".field-error").waitFor();
    assert.equal(
      await page
        .getByRole("spinbutton", { name: "출생연도" })
        .getAttribute("aria-invalid"),
      "true",
    );
    assert.equal(
      calls.some((c) => c.path === "/auth/signup"),
      false,
    );
  }));

test("건강 기록이 100건을 넘어도 오래된 기록까지 보여준다", async () =>
  withPage(async (page, base) => {
    await mock(page, { manyRecords: true });
    await page.goto(new URL(path + "#progress", base).href);
    await page.locator('[data-growth-tab="health"]').click();
    await page.locator(".live-health-history article").first().waitFor();
    assert.equal(
      await page.locator(".live-health-history article").count(),
      101,
    );
    await page
      .locator(".live-health-history")
      .getByText("체중 99.9 kg", { exact: false })
      .waitFor();
  }));

async function openRecoCard(page, base, state) {
  const calls = await mock(page, state);
  await page.goto(new URL(path + "#reco", base).href);
  await page
    .locator(".reco-card")
    .filter({ hasText: "계단으로 올라가기" })
    .click();
  await page.locator("[data-live-start]").waitFor();
  return calls;
}
const recoPatches = (calls) =>
  calls.filter(
    (c) =>
      c.method === "PATCH" && c.path.startsWith("/challenge-recommendations/"),
  );

test("추천 카드를 '나중에 할게요'로 넘기면 저장하고 전투 화면에서 뺀다", async () =>
  withPage(async (page, base) => {
    const state = { cards: [card()] };
    const calls = await openRecoCard(page, base, state);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "나중에 할게요" }).click();
    await page.getByText("선택을 저장했어요", { exact: false }).waitFor();
    assert.equal(await page.evaluate(() => document.body.dataset.page), "reco");
    assert.deepEqual(
      recoPatches(calls).map((c) => [c.path, c.body]),
      [["/challenge-recommendations/31", { action: "rejected" }]],
    );
    assert.equal(
      await page
        .locator(".reco-card")
        .filter({ hasText: "계단으로 올라가기" })
        .count(),
      0,
    );
  }));

test("연속 거절이면 다시 추천받을 시점을 고르게 한다", async () =>
  withPage(async (page, base) => {
    const state = { cards: [card()], cooldownRequired: true };
    const calls = await openRecoCard(page, base, state);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "나중에 할게요" }).click();
    const choice = page.locator("#live-choice");
    await choice.getByText("언제 다시 추천받을까요?").waitFor();
    await choice.getByRole("button", { name: "30일 후" }).click();
    await page.getByText("선택을 저장했어요", { exact: false }).waitFor();
    assert.deepEqual(
      recoPatches(calls).map((c) => c.body),
      [{ action: "rejected" }, { action: "rejected", cooldown_choice: "30d" }],
    );
  }));

test("'해당 없어요'로 제외한 챌린지는 목록에 모아 두고 다시 켤 수 있다", async () =>
  withPage(async (page, base) => {
    const state = { cards: [card()] };
    const calls = await openRecoCard(page, base, state);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "해당 없어요" }).click();
    const excluded = page.locator(".live-excluded");
    await excluded.getByText("계단으로 올라가기").waitFor();
    assert.match(await excluded.textContent(), /추천에서 제외한 챌린지/);
    await excluded.getByRole("button", { name: "추천 다시 켜기" }).click();
    await page.getByText("다시 추천받을 수 있어요", { exact: false }).waitFor();
    assert.equal(await page.locator(".live-excluded").count(), 0);
    assert.deepEqual(
      recoPatches(calls).map((c) => [c.path, c.body]),
      [
        ["/challenge-recommendations/31", { action: "not_applicable" }],
        ["/challenge-recommendations/31/unsuppress", null],
      ],
    );
  }));

test("재측정하면 위험도 칸에 직전 대비 변화량을 보여준다", async () =>
  withPage(async (page, base) => {
    await mock(page, { dmDelta: -1.26 });
    await page.goto(new URL(path + "#risk", base).href);
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    const delta = page.locator("#dm-risk .live-risk-delta");
    assert.equal((await delta.textContent()).trim(), "직전 대비 -1.3%p");
    assert.equal(await delta.isVisible(), true);
    assert.equal(
      await page.locator("#htn-risk .live-risk-delta").count(),
      0,
      "비교할 직전 예측이 없으면 표시하지 않는다",
    );
    // 휴대폰 너비에서 변화량 때문에 위험도 칸이 화면 밖으로 밀리지 않는다
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      const box = await page.evaluate(() => {
        const dm = document.querySelector("#dm-risk").getBoundingClientRect();
        const htn = document.querySelector("#htn-risk").getBoundingClientRect();
        const delta = document
          .querySelector("#dm-risk .live-risk-delta")
          .getBoundingClientRect();
        const value = document
          .querySelector("#dm-risk strong")
          .getBoundingClientRect();
        return {
          right: htn.right,
          width: innerWidth,
          below: delta.top >= value.bottom - 1,
          inside: delta.right <= dm.right + 0.5,
        };
      });
      assert.ok(
        box.right <= box.width,
        `${width}px: 고혈압 칸이 화면 안에 있다`,
      );
      assert.ok(box.below, `${width}px: 변화량은 숫자 아래 줄에 있다`);
      assert.ok(box.inside, `${width}px: 변화량이 칸 안에 있다`);
      // 휴대폰에서 라벨 뒤에 붙는 ' 위험' 글자가 변화량 뒤에도 붙지 않는다
      assert.equal(
        await delta.evaluate((el) => getComputedStyle(el, "::after").content),
        "none",
        `${width}px: 변화량 뒤에 다른 글자가 붙지 않는다`,
      );
    }
  }));

const predictionPosts = (calls) =>
  calls.filter((c) => c.path === "/predictions" && c.method === "POST");

test("예측이 실패하면 다시 시도할 때 같은 건강기록으로 새로 접수한다", async () =>
  withPage(async (page, base) => {
    const calls = await mock(page, { signedOut: true, failPrediction: true });
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page.getByText("예측에 실패했습니다", { exact: false }).waitFor();
    await page.locator(".waiting [data-live-retry]").click();
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.deepEqual(
      predictionPosts(calls).map((c) => c.body),
      [{ health_record_id: 9 }, { health_record_id: 9 }],
    );
  }));

test("새로고침 뒤 예측이 실패해도 가장 최근 건강기록으로 다시 접수한다", async () =>
  withPage(async (page, base) => {
    const state = { signedOut: true, predicting: true };
    const calls = await mock(page, state);
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page.locator('.scene[data-page="waiting"]:not([hidden])').waitFor();
    Object.assign(state, {
      signedOut: false,
      predicting: false,
      failPrediction: true,
    });
    await page.reload();
    await page.getByText("예측에 실패했습니다", { exact: false }).waitFor();
    await page.locator(".waiting [data-live-retry]").click();
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(predictionPosts(calls).length, 2);
    assert.deepEqual(predictionPosts(calls).at(-1).body, {
      health_record_id: 9,
    });
  }));

test("예측 접수 중 연결이 끊기면 다시 보내지 않고 지도에서 확인하게 한다", async () =>
  withPage(async (page, base) => {
    const state = { signedOut: true, dropPrediction: true };
    const calls = await mock(page, state);
    await page.goto(new URL(path + "#login", base).href);
    await fillSignup(page);
    await page.locator('.health3 button[type="submit"]').click();
    await page
      .getByText("접수됐는지 확인하지 못했어요", { exact: false })
      .waitFor();
    state.dropPrediction = false;
    await page.locator(".waiting [data-live-retry]").click();
    await page.locator("#dm-risk strong").filter({ hasText: "7.5" }).waitFor();
    assert.equal(
      predictionPosts(calls).length,
      1,
      "예측을 두 번 접수하지 않는다",
    );
  }));

test("서비스 주소 /frontend/ 는 v5 화면을 열고 주소의 화면 이름을 이어받는다", async () =>
  withPage(async (page, base) => {
    await mock(page, { signedOut: true });
    await page.goto(new URL("/frontend/#signup", base).href);
    await page.locator('.scene[data-page="signup"]:not([hidden])').waitFor();
    const url = new URL(page.url());
    assert.equal(decodeURIComponent(url.pathname), decodeURIComponent(path));
    assert.equal(url.hash, "#signup");
  }));

test("성장의 조각은 결정 그림으로 보이고 RARE 재료로 받는다", async () =>
  withPage(async (page, base) => {
    const shard = {
      code: "material",
      name: "성장의 조각",
      slot: "material",
      rarity: "RARE",
      asset: "growth-shard.webp",
      duplicate: false,
      materials: 2,
    };
    await mock(page, { draw: true, drawResult: shard, materials: 14 });
    await page.goto(new URL(path + "#rewards", base).href);
    const chip = page.locator(".live-shard-chip");
    await chip.waitFor();
    assert.match(await chip.textContent(), /성장의 조각\s*14/);
    assert.match(
      await chip.locator("img").getAttribute("src"),
      /growth-shard\.webp$/,
    );
    await page.getByRole("button", { name: "카드 뽑기", exact: true }).click();
    await page.getByRole("button", { name: "4번째 카드", exact: true }).click();
    await page
      .getByRole("button", { name: "선택한 카드 열기", exact: true })
      .click();
    const result = page.locator(".draw-result.rare");
    await result.waitFor();
    assert.match(await result.textContent(), /성장의 조각 \+2/);
    assert.match(
      await result.locator("img").getAttribute("src"),
      /growth-shard\.webp$/,
    );
  }));

test("아이템 단계는 2단계에 조각 20개, 3단계에 40개가 필요하다", async () =>
  withPage(async (page, base) => {
    const state = { materials: 14, stage: 1 };
    await mock(page, state);
    await page.goto(new URL(path + "#rewards", base).href);
    const growth = page.locator(".growth-display");
    await growth.waitFor();
    assert.match(await growth.textContent(), /14 \/ 20/);
    assert.match(await growth.textContent(), /다음 단계까지 조각 6개/);
    assert.equal(
      await growth.locator("[data-live-upgrade]").isDisabled(),
      true,
    );
    Object.assign(state, { materials: 40, stage: 2 });
    await page.reload();
    await growth.waitFor();
    assert.match(await growth.textContent(), /40 \/ 40/);
    const upgrade = growth.locator("[data-live-upgrade]");
    assert.equal(await upgrade.isDisabled(), false);
    assert.match(await upgrade.textContent(), /조각 40개로 3단계/);
  }));

test("진행 중인 타이머는 일시정지하고 이어할 수 있다", async () =>
  withPage(async (page, base) => {
    const state = { mission: true };
    const calls = await mock(page, state);
    await page.goto(new URL(path + "#today", base).href);
    await page.getByRole("button", { name: "식후 걷기", exact: false }).click();
    await page.getByText("00:12 / 10분", { exact: false }).waitFor();
    await page.getByRole("button", { name: "일시정지", exact: true }).click();
    await page.getByRole("button", { name: "이어하기", exact: true }).waitFor();
    assert.match(
      await page.locator('[data-timer-display="101"]').textContent(),
      /일시정지/,
    );
    await page.getByRole("button", { name: "이어하기", exact: true }).click();
    await page.getByRole("button", { name: "일시정지", exact: true }).waitFor();
    assert.deepEqual(
      calls
        .filter((c) => /\/timers\/77\/(pause|resume)$/.test(c.path))
        .map((c) => c.path.split("/").pop()),
      ["pause", "resume"],
    );
  }));

test("서버의 성장 단계에 맞는 결정 이름과 외형을 표시하고 재료 그림과 구분한다", async () =>
  withPage(async (page, base) => {
    const state = { materials: 0, stage: 1 };
    await mock(page, state);
    const stages = [
      [1, "작은 별의 결정", "growth-crystal-stage-1.webp", 1],
      [2, "은하의 결정", "growth-crystal-stage-2.webp", 1.08],
      [3, "별빛 왕관", "growth-crystal-stage-3.webp", 1.18],
    ];
    for (const [stage, name, filename, scale] of stages) {
      state.stage = stage;
      if (stage === 1) await page.goto(new URL(path + "#rewards", base).href);
      else await page.reload();
      const growth = page.locator(".growth-display");
      await growth.waitFor();
      assert.equal(await growth.getByRole("img").count(), 1);
      const crystal = growth.getByRole("img", { name: `${name} ${stage}단계`, exact: true });
      const artwork = crystal.locator("img");
      assert.equal(await artwork.count(), 1);
      assert.ok((await artwork.getAttribute("src")).endsWith(filename));
      assert.equal(await artwork.getAttribute("alt"), "");
      await artwork.evaluate((img) => img.decode());
      assert.ok(await artwork.evaluate((img) => img.naturalWidth >= 320));
      assert.equal(await growth.getByRole("heading", { name, exact: true }).count(), 1);
      assert.equal(await growth.getAttribute("data-stage"), String(stage));
      const transform = await crystal.evaluate((el) => {
        const value = getComputedStyle(el).transform;
        return value === "none" ? 1 : new DOMMatrixReadOnly(value).a;
      });
      assert.equal(transform, scale);
      assert.equal(await growth.locator('img[src$="growth-shard.webp"]').count(), 0);
      assert.match(await page.locator(".live-shard-chip img").getAttribute("src"), /growth-shard\.webp$/);
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        const box = await growth.boundingBox();
        assert.ok(box.x >= 0 && box.x + box.width <= width + 1);
      }
    }
  }));

// docs/02_team/design.md 2절. 화면 제목 28px · 섹션 제목 18px · 소제목 15px, 굵기 700, 글꼴 Adventure.
// 예외는 같은 절에 이유와 함께 적은 곳만 둔다.
const HEADING_SIZE = { H1: "28px", H2: "18px", H3: "15px" };
const HEADING_EXCEPTIONS = [".hero-copy", ".signup-copy", ".waiting-copy", ".growth-level", ".reward-tile", ".draw-result", ".room-prop", "#app-menu"];

async function headingReport(page, root = ".scene:not([hidden])") {
  return page.evaluate(
    ([sizes, exceptions, rootSelector]) => {
      const scope = document.querySelector(rootSelector);
      const headings = [...scope.querySelectorAll("h1,h2,h3")].filter((h) => h.getClientRects().length > 0);
      const bad = headings
        .filter((h) => !exceptions.some((selector) => h.closest(selector)))
        .map((h) => {
          const style = getComputedStyle(h);
          return { tag: h.tagName, size: style.fontSize, weight: style.fontWeight, family: style.fontFamily.split(",")[0].trim(), text: h.textContent.trim().slice(0, 16) };
        })
        .filter((h) => h.size !== sizes[h.tag] || h.weight !== "700" || h.family !== "Adventure");
      return { h1: headings.filter((h) => h.tagName === "H1").length, bad };
    },
    [HEADING_SIZE, HEADING_EXCEPTIONS, root],
  );
}

// 고정 시간 대신 화면이 다 그려진 상태를 기다린다. 실제 연결 화면은 불러오는 동안 live-loading 이 붙는다
async function settled(page, id) {
  await page.waitForLoadState("networkidle");
  await page.locator(`.scene[data-page="${id}"]:not([hidden]):not(.live-loading)`).waitFor();
}

test("모든 화면의 제목은 디자인 규칙의 크기·굵기·글꼴을 따르고 화면 제목은 하나다", async () =>
  withPage(async (page, base) => {
    await mock(page, { materials: 0, stage: 1 });
    const problems = [];
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const id of ["risk", "monsters", "reco", "today", "evolution", "health", "health2", "health3", "progress", "rewards"]) {
        await page.goto(new URL(path + "#" + id, base).href);
        await settled(page, id);
        const tab = id === "progress" ? "data-growth-tab" : id === "rewards" ? "data-live-bag" : null;
        const names = tab ? await page.locator(`[${tab}]`).evaluateAll((els, key) => els.map((el) => el.getAttribute(key)), tab) : [null];
        for (const name of names) {
          if (tab) {
            await page.locator(`[${tab}="${name}"]`).click();
            await page.locator(`[${tab}="${name}"][aria-pressed="true"]`).waitFor();
            await settled(page, id);
          }
          const report = await headingReport(page);
          const where = `${width}px ${id}${tab ? ` ${name}` : ""}`;
          if (report.h1 !== 1) problems.push(`${where}: 화면 제목 ${report.h1}개`);
          for (const h of report.bad) problems.push(`${where}: ${h.tag} ${h.size} ${h.weight} ${h.family} "${h.text}"`);
        }
      }
    }
    assert.deepEqual(problems, []);
  }));

test("화면 위에 뜨는 창의 제목도 디자인 규칙을 따른다", async () =>
  withPage(async (page, base) => {
    const problems = [];
    const check = async (where, selector) => {
      for (const h of (await headingReport(page, selector)).bad) problems.push(`${where}: ${h.tag} ${h.size} ${h.weight} ${h.family} "${h.text}"`);
    };
    // 의료 고지
    await mock(page, {});
    await page.goto(new URL(path + "#risk", base).href);
    await settled(page, "risk");
    await page.locator("[data-medical-open]").first().click();
    await page.locator("#medical-dialog[open]").waitFor();
    await check("의료 고지", "#medical-dialog");
    await page.locator("#medical-close").click();
    await page.locator("#medical-dialog:not([open])").waitFor({ state: "attached" });
    // 추천을 넘길 때 뜨는 선택 창
    await openRecoCard(page, base, { cards: [card()], cooldownRequired: true });
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "나중에 할게요" }).click();
    await page.locator("#live-choice[open]").waitFor();
    await check("다시 추천 시점 선택", "#live-choice");
    assert.deepEqual(problems, []);
  }));
