import http from "node:http";
import https from "node:https";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".json": "application/json; charset=utf-8",
};

/** 개발 시에만 사용하는 동일 출처 API 프록시와 HTML 정적 서버다. */
export function createDevelopmentServer({
  frontendRoot = fileURLToPath(new URL("../../frontend/", import.meta.url)),
  apiOrigin = "http://127.0.0.1:8000",
} = {}) {
  const root = path.resolve(frontendRoot);
  const backend = new URL(apiOrigin);
  if (
    !["http:", "https:"].includes(backend.protocol) ||
    backend.username ||
    backend.password ||
    backend.pathname !== "/"
  )
    throw new Error("백엔드 주소는 http 또는 https의 기본 주소여야 합니다.");
  return http.createServer(async (request, response) => {
    const url = new URL(request.url, "http://localhost");
    if (url.pathname.startsWith("/api/")) {
      const transport = backend.protocol === "https:" ? https : http;
      const upstream = transport.request(
        new URL(request.url, backend),
        {
          method: request.method,
          headers: { ...request.headers, host: backend.host },
        },
        (reply) => {
          response.writeHead(reply.statusCode || 502, reply.headers);
          reply.pipe(response);
        },
      );
      upstream.on("error", () => {
        if (!response.headersSent)
          response.writeHead(502, {
            "Content-Type": "application/json; charset=utf-8",
          });
        response.end(
          JSON.stringify({
            success: false,
            error: {
              code: "INTERNAL_ERROR",
              message: "백엔드에 연결하지 못했어요. 잠시 후 다시 확인해주세요.",
            },
          }),
        );
      });
      request.on("aborted", () => upstream.destroy());
      response.on("close", () => {
        if (!response.writableEnded) upstream.destroy();
      });
      request.pipe(upstream);
      return;
    }
    if (!["GET", "HEAD"].includes(request.method)) {
      response.writeHead(405);
      response.end();
      return;
    }
    let pathname;
    try {
      pathname = decodeURIComponent(url.pathname);
    } catch {
      response.writeHead(400);
      response.end();
      return;
    }
    if (pathname.startsWith("/frontend/"))
      pathname = pathname.slice("/frontend".length);
    const parts = pathname.split("/");
    const filename = path.resolve(root, `.${pathname}`);
    if (
      parts.some((part) => part.startsWith(".") || part === "node_modules") ||
      !(filename === root || filename.startsWith(root + path.sep))
    ) {
      response.writeHead(404);
      response.end();
      return;
    }
    try {
      let file = filename;
      let details = await stat(file);
      if (details.isDirectory()) {
        file = path.join(file, "index.html");
        details = await stat(file);
      }
      if (!details.isFile()) throw new Error("파일을 찾지 못했습니다.");
      response.writeHead(200, {
        "Content-Type": TYPES[path.extname(file)] || "application/octet-stream",
        "Content-Length": details.size,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      });
      if (request.method === "HEAD") response.end();
      else
        createReadStream(file)
          .on("error", () => response.destroy())
          .pipe(response);
    } catch {
      response.writeHead(404);
      response.end("파일을 찾지 못했습니다.");
    }
  });
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const port = Number(process.env.DANGO_FRONTEND_PORT || 5173);
  const host = process.env.DANGO_FRONTEND_HOST || "127.0.0.1";
  const server = createDevelopmentServer({
    apiOrigin: process.env.DANGO_API_ORIGIN || "http://127.0.0.1:8000",
  });
  server.on("error", () => {
    console.error(
      "개발 서버를 열지 못했습니다. 포트와 실행 환경을 확인해주세요.",
    );
    process.exitCode = 1;
  });
  server.listen(port, host, () =>
    console.log(`당고킬러 화면: http://${host}:${server.address().port}/`),
  );
}
