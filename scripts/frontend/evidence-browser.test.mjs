import test from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./browser-harness.mjs";

async function fixture(
  page,
  { failure = false, custom = false, enabled = true } = {},
) {
  page.setDefaultTimeout(6000);
  const writes = [];
  let completed = false;
  await page.clock.install({ time: new Date("2026-10-15T04:00:00Z") });
  await page.addInitScript(
    ({ custom, enabled }) => {
      window.dangoConfig = { evidencePhotosEnabled: enabled };
      if (custom)
        window.dangoEvidence = {
          uploadPhoto: (_file, context) => {
            window.photoContext = {
              userChallengeId: context?.userChallengeId,
              occurrenceId: context?.occurrenceId,
            };
            return new Promise((resolve) => {
              window.finishPhoto = () =>
                resolve({ evidence_url: "private:late" });
            });
          },
        };
    },
    { custom, enabled },
  );
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data = { items: [], total: 0 };
    if (path.endsWith("/auth/refresh"))
      data = { access_token: "test-photo-token" };
    else if (path.endsWith("/users/me"))
      data = { id: 3, nickname: "사진 검증" };
    else if (path.endsWith("/monsters/me")) data = { items: [] };
    else if (path.endsWith("/evidence/photos")) {
      writes.push({
        path,
        body: request.postData(),
        headers: request.headers(),
      });
      if (failure)
        return route.fulfill({
          status: 422,
          json: {
            success: false,
            error: {
              code: "VALIDATION_ERROR",
              message: "사진 형식을 확인해주세요.",
            },
          },
        });
      data = {
        evidence_url: "private:photo-1",
        uploaded_at: "2026-10-15T13:00:00",
      };
    } else if (path.endsWith("/logs")) {
      writes.push({ path, body: request.postDataJSON() });
      completed = true;
      data = { reward_eligible: true, xp_granted: 10, level_up: false };
    } else if (path.endsWith("/user-challenges"))
      data = {
        items: [
          {
            user_challenge_id: 21,
            title: "식품 라벨 확인",
            verification_type: "photo",
            daily_target_count: 1,
            start_date: "2026-10-15",
            end_date: "2026-11-11",
            today_date: "2026-10-15",
            target_monster: { monster_id: 1, code: "viscera", name: "비세라" },
            today_occurrences: [
              {
                occurrence_id: 101,
                status: completed ? "completed" : "planned",
                sequence_no: 1,
              },
            ],
          },
        ],
        total: 1,
      };
    await route.fulfill({ json: { success: true, data } });
  });
  return writes;
}

async function submitPhoto(page, dUrl) {
  await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#today`);
  await page
    .locator('[data-photo="101"]')
    .setInputFiles({
      name: "수행.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from([255, 216, 255]),
    });
  await page.locator('[data-upload="101"]').click();
  await page.locator('[data-dialog-choice="confirm"]').click();
}

test("사진 업로드 성공 후에만 같은 미션의 수행 기록을 한 번 보낸다", async () => {
  await withPage(async (page, dUrl) => {
    const writes = await fixture(page);
    await submitPhoto(page, dUrl);
    await page.getByText("수행을 인정받았어요. 10 XP를 얻었어요.").waitFor();
    assert.equal(writes.length, 2);
    assert.equal(writes[0].path, "/api/v1/evidence/photos");
    assert.match(writes[0].body, /name="user_challenge_id"\r\n\r\n21/);
    assert.equal(writes[0].headers.authorization, "Bearer test-photo-token");
    assert.equal(writes[1].path, "/api/v1/user-challenges/21/logs");
    assert.equal(writes[1].body.verification_method, "photo");
    assert.equal(writes[1].body.evidence_url, "private:photo-1");
  });
});

test("사진 업로드 실패 시 수행 기록과 보상을 요청하지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    const writes = await fixture(page, { failure: true });
    await submitPhoto(page, dUrl);
    await page.getByText("사진 형식을 확인해주세요.").waitFor();
    assert.equal(writes.length, 1);
    assert.equal(await page.locator('[data-upload="101"]').isEnabled(), true);
  });
});

for (const change of ["account", "page"])
  test(`사진 업로드 중 ${change === "account" ? "계정" : "화면"} 변경 후 도착한 결과로 수행 기록을 만들지 않는다`, async () => {
    await withPage(async (page, dUrl) => {
      const writes = await fixture(page, { custom: true });
      await submitPhoto(page, dUrl);
      await page.waitForFunction(
        () => typeof window.finishPhoto === "function",
      );
      assert.deepEqual(await page.evaluate(() => window.photoContext), {
        userChallengeId: 21,
        occurrenceId: 101,
      });
      await page.evaluate((change) => {
        if (change === "account")
          window.dispatchEvent(new Event("dango:auth-changed"));
        else location.hash = "#monsters";
      }, change);
      if (change === "page")
        await page.locator(".monster-list").waitFor({ state: "attached" });
      else await page.locator('[data-photo="101"]').waitFor();
      await page.evaluate(() => window.finishPhoto());
      // 두 렌더링 주기 후에도 뒤늦은 쓰기가 없는지 확인한다.
      await page.evaluate(
        () =>
          new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve)),
          ),
      );
      assert.equal(writes.length, 0);
    });
  });

test("업로드 API가 준비되기 전에는 기본 비활성 상태로 사진 요청을 보내지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    const writes = await fixture(page, { enabled: false });
    await page.goto(`${dUrl.replace("/frontend/d/", "/frontend/")}#today`);
    await page
      .getByText(
        "지금은 사진 인증을 사용할 수 없어요. 잠시 후 다시 확인해주세요.",
      )
      .waitFor();
    assert.equal(await page.locator("[data-upload]").count(), 0);
    assert.equal(writes.length, 0);
  });
});
