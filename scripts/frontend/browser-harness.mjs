import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(
  new URL("../../frontend/package.json", import.meta.url),
);
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = require(
    path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, "playwright"),
  ));
}
const repo = fileURLToPath(new URL("../../", import.meta.url));
// macOS·리눅스에는 python 없이 python3 만 있는 경우가 많다. 다른 실행 파일은 PYTHON 으로 지정한다
const python =
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

export async function withPage(run) {
  const server = spawn(
    python,
    [
      "-u",
      "-m",
      "http.server",
      "0",
      "--bind",
      "127.0.0.1",
      "--directory",
      repo,
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  let browser;
  try {
    const port = await new Promise((resolve, reject) => {
      let output = "";
      server.stdout.on("data", (chunk) => {
        output += chunk;
        const match = output.match(/port (\d+)/);
        if (match) resolve(match[1]);
      });
      server.on("error", reject);
      server.on("exit", () =>
        reject(new Error("테스트 서버를 시작하지 못했습니다.")),
      );
    });
    browser = await chromium.launch({
      headless: true,
      ...(process.env.D_BROWSER_EXECUTABLE
        ? {
            executablePath: process.env.D_BROWSER_EXECUTABLE,
            args: ["--no-sandbox", "--disable-dev-shm-usage"],
          }
        : {}),
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    await run(page, `http://127.0.0.1:${port}/frontend/`);
  } finally {
    await browser?.close();
    // 실행 파일을 못 찾아 시작조차 못 한 서버는 exit 를 보내지 않아 기다리면 테스트가 끝나지 않는다
    if (
      server.pid !== undefined &&
      server.exitCode === null &&
      server.signalCode === null
    ) {
      server.kill();
      await once(server, "exit").catch(() => {});
    }
  }
}
