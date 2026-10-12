import test from "node:test";
import assert from "node:assert/strict";
import { scoreView } from "../../frontend/d/model.mjs";

test("공략 점수는 100을 넘어도 그대로 표시하고 게이지만 채운다", () => {
  assert.deepEqual(scoreView(135), { text: "135 / 100", fill: 100 });
  assert.deepEqual(scoreView(null), { text: "— / 100", fill: 0 });
});

test("KST 자정 경계와 종료일을 날짜 기준으로 처리한다", async () => {
  const { kstDate, cycleView } = await import("../../frontend/d/model.mjs");
  assert.equal(kstDate(new Date("2026-10-11T15:01:00Z")), "2026-10-12");
  assert.equal(
    cycleView(
      { start_date: "2026-10-01", end_date: "2026-10-28" },
      "2026-10-12",
    ).day,
    12,
  );
  assert.equal(
    cycleView(
      { start_date: "2026-10-01", end_date: "2026-10-28" },
      "2026-10-29",
    ).ended,
    true,
  );
});

test("목표 전 타이머는 완료할 수 없고 일시정지 시간은 수행 시간에 넣지 않는다", async () => {
  const { ActivityTimer } = await import("../../frontend/d/model.mjs");
  let now = 0;
  const timer = new ActivityTimer(() => now);
  timer.start();
  now = 599000;
  assert.equal(timer.ready(10), false);
  timer.pause();
  now += 300000;
  assert.equal(timer.minutes, 9.9);
  timer.start();
  now += 1000;
  assert.equal(timer.ready(10), true);
  assert.equal(timer.minutes, 10);
});
