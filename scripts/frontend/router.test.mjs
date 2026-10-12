import test from "node:test";
import assert from "node:assert/strict";
import {
  parseRoute,
  guardRoute,
  ROUTES,
} from "../../frontend/shared/router.mjs";

test("11화면을 고정된 이름으로 찾고 인증 전에는 원래 목적지를 보존한다", () => {
  assert.equal(Object.keys(ROUTES).length, 11);
  const route = parseRoute("#waiting?prediction_id=501");
  assert.equal(route.id, "waiting");
  assert.equal(route.params.get("prediction_id"), "501");
  assert.deepEqual(guardRoute(route, false), {
    id: "login",
    returnTo: "waiting?prediction_id=501",
  });
  assert.deepEqual(guardRoute(route, true), { id: "waiting", returnTo: null });
  assert.equal(parseRoute("#https://outside.example/token").id, "today");
});
