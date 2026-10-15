import test from "node:test";
import assert from "node:assert/strict";
import { PredictionReadiness } from "../../frontend/shared/prediction-readiness.mjs";

test("완료 직후의 첫 추천만 1초 간격 두 번 재시도한다", async () => {
  const waits = [];
  const readiness = new PredictionReadiness({
    wait: async (ms) => waits.push(ms),
  });
  readiness.markDone({ prediction_id: 501, status: "done" });
  let calls = 0;
  const result = await readiness.request(async () => {
    if (++calls < 3)
      throw Object.assign(new Error("추천 근거를 준비하고 있어요."), {
        status: 409,
        code: "CHLG_RECOMMENDATION_UNAVAILABLE",
      });
    return { items: [] };
  });
  assert.deepEqual(result, { items: [] });
  assert.equal(calls, 3);
  assert.deepEqual(waits, [1000, 1000]);
});

test("완료 표시가 없거나 오래됐거나 이미 쓴 경우에는 재시도하지 않는다", async () => {
  let time = 0;
  const ready = new PredictionReadiness({
    now: () => time,
    wait: async () => assert.fail("재시도하지 않아야 합니다."),
  });
  const failure = Object.assign(new Error("완료된 예측이 없습니다."), {
    status: 404,
    code: "PRED_NOT_FOUND",
  });
  const request = async () => {
    throw failure;
  };
  ready.markDone({ prediction_id: 1, status: "pending" });
  await assert.rejects(ready.request(request), (error) => error === failure);
  ready.markDone({ prediction_id: 1, status: "done" });
  time = 5001;
  await assert.rejects(ready.request(request), (error) => error === failure);
  time = 0;
  ready.markDone({ prediction_id: 1, status: "done" });
  await ready.request(async () => ({ items: [] }));
  await assert.rejects(ready.request(request), (error) => error === failure);
});

test("완료 직후에도 다른 오류는 재시도하지 않고 마지막 서버 오류를 전달한다", async () => {
  const ready = new PredictionReadiness({ wait: async () => {} });
  for (const failure of [
    Object.assign(new Error("연결 실패"), { status: 0, code: "NETWORK" }),
    Object.assign(new Error("다른 충돌"), {
      status: 409,
      code: "CHLG_LIMIT_EXCEEDED",
    }),
  ]) {
    ready.markDone({ prediction_id: 1, status: "done" });
    let calls = 0;
    await assert.rejects(
      ready.request(async () => {
        ++calls;
        throw failure;
      }),
      (error) => error === failure,
    );
    assert.equal(calls, 1);
  }
  ready.markDone({ prediction_id: 1, status: "done" });
  let calls = 0;
  const final = Object.assign(new Error("선택 가능한 챌린지가 없습니다."), {
    status: 409,
    code: "CHLG_RECOMMENDATION_UNAVAILABLE",
  });
  await assert.rejects(
    ready.request(async () => {
      ++calls;
      throw final;
    }),
    (error) => error === final,
  );
  assert.equal(calls, 3);
});

test("계정 변경이나 화면 이탈 후에는 예약된 재시도를 보내지 않는다", async () => {
  for (const cause of ["auth", "route"]) {
    const controller = new AbortController();
    let calls = 0;
    const ready = new PredictionReadiness({
      wait: async () => {
        if (cause === "auth") ready.clear();
        else controller.abort();
      },
    });
    ready.markDone({ prediction_id: 1, status: "done" });
    await assert.rejects(
      ready.request(
        async () => {
          ++calls;
          throw Object.assign(new Error("갱신 대기"), {
            status: 404,
            code: "PRED_NOT_FOUND",
          });
        },
        { signal: controller.signal },
      ),
      { name: "AbortError" },
    );
    assert.equal(calls, 1);
  }
});

test("추천 후보 소진이 확인되면 예측 완료 직후에도 재시도하지 않는다", async () => {
  let calls = 0;
  const ready = new PredictionReadiness({ wait: async () => {} });
  ready.markDone({ status: "done", prediction_id: 501 });
  await assert.rejects(
    ready.request(async () => {
      calls++;
      throw {
        status: 409,
        code: "CHLG_RECOMMENDATION_UNAVAILABLE",
        details: { reason: "no_additional_candidates" },
      };
    }),
  );
  assert.equal(calls, 1);
});
