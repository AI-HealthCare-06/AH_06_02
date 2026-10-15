import test from "node:test";
import assert from "node:assert/strict";
import { createEvidenceUploader } from "../../frontend/shared/evidence.mjs";
import { createApiClient } from "../../frontend/shared/api.mjs";

const photo = () =>
  new File([new Uint8Array([255, 216, 255])], "수행.jpg", {
    type: "image/jpeg",
  });

test("사진과 사용자 미션 ID를 인증된 multipart 요청으로 한 번 전송한다", async () => {
  const calls = [];
  const api = createApiClient({
    getToken: () => "검증용-토큰",
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return new Response(
        JSON.stringify({
          success: true,
          data: { evidence_url: "private:photo-1" },
        }),
      );
    },
  });
  const result = await createEvidenceUploader(api)(photo(), {
    userChallengeId: 21,
  });
  assert.equal(result.evidence_url, "private:photo-1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/evidence/photos");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers.Authorization, "Bearer 검증용-토큰");
  assert.equal(calls[0].options.headers["Content-Type"], undefined);
  assert.equal(calls[0].options.body.get("user_challenge_id"), "21");
  assert.equal(calls[0].options.body.get("photo").name, "수행.jpg");
});

test("미션 ID가 없거나 JPEG·PNG가 아니거나 10 MiB를 넘으면 업로드하지 않는다", async () => {
  let calls = 0;
  const upload = createEvidenceUploader(async () => {
    calls++;
    return { evidence_url: "private:1" };
  });
  for (const userChallengeId of [undefined, 0, -1, 1.5, "21"])
    await assert.rejects(upload(photo(), { userChallengeId }));
  for (const file of [
    null,
    new File(["gif"], "수행.gif", { type: "image/gif" }),
    new File([new Uint8Array(10 * 1024 * 1024 + 1)], "큰사진.png", {
      type: "image/png",
    }),
    new File([], "빈사진.png", { type: "image/png" }),
  ])
    await assert.rejects(upload(file, { userChallengeId: 21 }));
  assert.equal(calls, 0);
});

test("잘못된 업로드 응답을 수행 증빙으로 넘기지 않는다", async () => {
  for (const result of [
    null,
    {},
    { evidence_url: "" },
    { evidence_url: "  " },
    { evidence_url: "a".repeat(256) },
  ])
    await assert.rejects(
      createEvidenceUploader(async () => result)(photo(), {
        userChallengeId: 21,
      }),
    );
});

test("업로드의 401은 재인증 뒤 자동 재전송하지 않는다", async () => {
  let uploads = 0;
  const api = createApiClient({
    getToken: () => "만료-토큰",
    fetchImpl: async (url) => {
      if (url.endsWith("/evidence/photos")) uploads++;
      return new Response(
        JSON.stringify({
          success: false,
          error: {
            code: "AUTH_TOKEN_EXPIRED",
            message: "다시 로그인해주세요.",
          },
        }),
        { status: 401 },
      );
    },
  });
  await assert.rejects(
    createEvidenceUploader(api)(photo(), { userChallengeId: 21 }),
  );
  assert.equal(uploads, 1);
});
