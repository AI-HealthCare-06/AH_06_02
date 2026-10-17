import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { withPage } from "./browser-harness.mjs";

const prototypePath = `/frontend/docs/prototype/${encodeURIComponent("당고킬러-모험시안_v5.html")}`;
const prototypeUrl = (dUrl) => new URL(prototypePath, dUrl).href;

test("v5는 모든 화면에서 팀 검토용 시안임을 알리고 실행 오류가 없다", async () => {
  await withPage(async (page, dUrl) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    page.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
    await page.emulateMedia({reducedMotion:"reduce"});
    await page.goto(`${prototypeUrl(dUrl)}#login`);
    await page.getByText("팀 검토용 v5 · API 미연결 · 예시 데이터").waitFor({ timeout: 5000 });
    const banner = await page.locator(".prototype-status").boundingBox();
    const content = await page.locator("#screen").boundingBox();
    assert.ok(banner.y + banner.height <= content.y + 1, "시안 안내는 화면 내용 위에 배치합니다.");
    for (const name of ["signup", "health", "health2", "health3", "waiting", "risk", "monsters", "reco", "today", "progress", "evolution", "evolution-complete", "rewards"]) {
      await page.goto(`${prototypeUrl(dUrl)}#${name}`);
      await page.locator(`.scene[data-page="${name}"]`).waitFor({ state: "visible" });
      assert.equal(await page.locator(".prototype-status").isVisible(), true);
      if (name === "risk" && process.env.DANGO_PREVIEW_ARTIFACT_DIR) {
        await mkdir(process.env.DANGO_PREVIEW_ARTIFACT_DIR, {recursive:true});
        await page.screenshot({path:path.join(process.env.DANGO_PREVIEW_ARTIFACT_DIR,"v5-map.png")});
      }
    }
    assert.deepEqual(errors, []);
  });
});

test("진단 또는 복약 중인 질환에는 확률을 표시하지 않는다", async () => {
  await withPage(async (page, dUrl) => {
    await page.goto(`${prototypeUrl(dUrl)}#health`);
    await page.getByLabel("당뇨 진단",{exact:true}).selectOption("yes");
    await page.getByLabel("고혈압약 복용",{exact:true}).selectOption("yes");
    await page.goto(`${prototypeUrl(dUrl)}#risk`);
    assert.equal(await page.locator("#dm-risk strong").innerText(),"진단 관리 중");
    assert.equal(await page.locator("#htn-risk strong").innerText(),"진단 관리 중");
    assert.equal(await page.locator(".risk-tile strong small").count(),0);
  });
});

test("가입부터 공략 수행·보상·꾸미기까지 연결하고 중단해도 기록을 보존한다", async () => {
  await withPage(async (page, dUrl) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`${prototypeUrl(dUrl)}#login`);
    await page.locator('.login [data-route="signup"]').click();
    await page.locator("#nickname").fill("검토 모험가");
    await page.locator('.signup button[type="submit"]').click();
    await page.getByRole("button", { name: "♂ 남성", exact: true }).click();
    await page.getByLabel("출생연도", {exact: true}).fill("1980");
    await page.getByLabel("키", {exact: true}).fill("170");
    await page.getByLabel("체중", {exact: true}).fill("80");
    await page.getByLabel("허리둘레", {exact: true}).fill("90");
    await page.locator('.health button[type="submit"]').click();
    await page.getByLabel("음주 빈도", {exact: true}).selectOption("1");
    assert.equal(await page.getByLabel("1회 음주량", {exact: true}).isVisible(), false);
    await page.locator('.health2 button[type="submit"]').click();
    assert.equal(await page.getByLabel("총콜레스테롤", {exact: true}).count(), 0);
    await page.locator('.health3 button[type="submit"]').click();
    await page.getByRole("button", {name: "예시 결과 보기", exact: true}).click();
    assert.equal(await page.locator('[data-village-key="cotinine"]').isDisabled(), true);
    assert.equal(await page.locator('[data-village-key="spike"]').isDisabled(), true);
    await page.locator('[data-village-key="viscera"]').click();
    await page.locator('.reco-card[data-title="식후 걷기"]').click();
    await page.getByRole("button", {name: "이 챌린지 시작하기 →", exact: true}).click();
    await page.locator('.today .slot:not([hidden]) .verify').first().click();
    await page.locator('[data-growth-action="draw"]').click();
    for (const index of [0, 1, 2]) await page.locator(`[data-pick-card="${index}"]`).click();
    await page.locator('[data-reward-action="open"]').click();
    assert.equal(await page.locator(".draw-result").count(), 3);
    await page.locator('[data-reward-view="inventory"]').click();
    await page.getByRole("heading", {name: "성장 아이템",exact: true}).waitFor();
    assert.doesNotMatch(await page.locator("#reward-panel").innerText(), /undefined/);
    await page.locator('[data-reward-view="decorate"]').click();
    await page.locator('[data-decorate-view="room"]').click();
    await page.locator('[data-room-preview="room-star-bed"]').click();
    await page.getByText("별빛 침대 · 미리보기",{exact: true}).waitFor();
    if (process.env.DANGO_PREVIEW_ARTIFACT_DIR) {
      await mkdir(process.env.DANGO_PREVIEW_ARTIFACT_DIR, {recursive:true});
      await page.screenshot({path:path.join(process.env.DANGO_PREVIEW_ARTIFACT_DIR,"v5-room.png")});
    }
    await page.locator('[data-room-cancel]').click();
    await page.locator('#adventure-nav [data-main-target="home"]').click();
    assert.equal(await page.locator('[data-village-key="alde"]').isDisabled(), true);
    await page.locator('[data-village-key="viscera"]').click();
    await page.locator('.reco-card[data-title="식후 걷기"]').click();
    page.once("dialog", (dialog) => dialog.accept());
    await page.locator('[data-stop-pending]').click();
    await page.locator('#adventure-nav [data-main-target="records"]').click();
    assert.match(await page.locator(".growth-numbers").innerText(), /10/);
    assert.match(await page.locator(".growth-level").innerText(), /18 \/ 120 XP/);
    assert.deepEqual(errors, []);
  });
});

test("모든 화면은 320px에서 가로로 넘치지 않고 축소 모션에서 영상이 정지한다", async () => {
  await withPage(async (page, dUrl) => {
    await page.setViewportSize({width:320,height:740});
    await page.emulateMedia({reducedMotion:"reduce"});
    await page.goto(`${prototypeUrl(dUrl)}#login`);
    for (const name of ["login","signup","health","health2","health3","waiting","risk","monsters","reco","today","progress","evolution","evolution-complete","rewards"]) {
      await page.goto(`${prototypeUrl(dUrl)}#${name}`);
      await page.locator(`.scene[data-page="${name}"]`).waitFor({state:"visible"});
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow,false,`${name} 화면의 가로 넘침을 확인합니다`);
      assert.equal(await page.evaluate(() => [...document.querySelectorAll("video")].every(video=>video.paused)),true);
    }
  });
});
