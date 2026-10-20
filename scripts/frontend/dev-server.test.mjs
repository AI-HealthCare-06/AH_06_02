import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { createDevelopmentServer } from "./dev-server.mjs";

test("HTML 개발 서버는 파일과 모듈을 제공하고 인증 헤더·쿠키를 API로 전달한다", async () => {
  const backend = http.createServer((request, response) => {
    assert.equal(request.url, "/api/v1/auth/refresh");
    assert.equal(request.headers.cookie, "refresh_token=test-only");
    response.writeHead(200, {
      "Content-Type": "application/json",
      "Set-Cookie": "refresh_token=renewed; HttpOnly; Path=/",
    });
    response.end(
      JSON.stringify({
        success: true,
        data: { access_token: "new-test-token" },
      }),
    );
  });
  backend.listen(0, "127.0.0.1");
  await once(backend, "listening");
  const server = createDevelopmentServer({
    frontendRoot: fileURLToPath(new URL("../../frontend/", import.meta.url)),
    apiOrigin: `http://127.0.0.1:${backend.address().port}`,
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const page = await fetch(`${base}/`);
    assert.equal(page.status, 200);
    assert.ok((await page.text()).includes("당고킬러-모험시안_v5.html"));
    const module = await fetch(`${base}/frontend/shared/auth.mjs`);
    assert.match(module.headers.get("content-type"), /javascript/);
    const secret = await fetch(`${base}/.env`);
    assert.equal(secret.status, 404);
    const outside = await fetch(`${base}/%2e%2e%2fAGENTS.md`);
    assert.equal(outside.status, 404);
    const reply = await fetch(`${base}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { Cookie: "refresh_token=test-only" },
    });
    assert.equal(reply.status, 200);
    assert.match(reply.headers.get("set-cookie"), /HttpOnly/);
    assert.equal((await reply.json()).data.access_token, "new-test-token");
  } finally {
    server.closeAllConnections();
    backend.closeAllConnections();
    await Promise.all([
      new Promise((resolve) => server.close(resolve)),
      new Promise((resolve) => backend.close(resolve)),
    ]);
  }
});
