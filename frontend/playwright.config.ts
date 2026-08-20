import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

process.env.MARKFORGE_E2E_DATA =
  process.env.MARKFORGE_E2E_DATA ??
  join(tmpdir(), `markforge-e2e-${Date.now()}`);

const e2eData = process.env.MARKFORGE_E2E_DATA;
const backendPython =
  process.platform === "win32"
    ? join(".venv", "Scripts", "python.exe")
    : join(".venv", "bin", "python");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  timeout: 60_000,
  globalSetup: "./playwright.global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: `${backendPython} -m uvicorn app.main:app --host 127.0.0.1 --port 3001`,
      cwd: "../backend",
      url: "http://127.0.0.1:3001/api/health",
      timeout: 60_000,
      env: {
        MARKFORGE_JOB_MODE: "sync",
        MARKFORGE_STORAGE_DIR: `${e2eData}${process.platform === "win32" ? "\\" : "/"}storage`,
        MARKFORGE_DATABASE_PATH: `${e2eData}${process.platform === "win32" ? "\\" : "/"}markforge.db`,
        MARKFORGE_UPLOAD_DIR: `${e2eData}${process.platform === "win32" ? "\\" : "/"}uploads`,
        MARKFORGE_OUTPUT_DIR: `${e2eData}${process.platform === "win32" ? "\\" : "/"}outputs`,
        MARKFORGE_TEMP_DIR: `${e2eData}${process.platform === "win32" ? "\\" : "/"}temp`,
      },
    },
    {
      command: "npm run dev",
      cwd: ".",
      url: "http://127.0.0.1:3000",
      timeout: 120_000,
      env: {
        API_PROXY_TARGET: "http://127.0.0.1:3001",
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
