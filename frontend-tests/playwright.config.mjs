import { defineConfig } from "@playwright/test";

const PORT = process.env.CV_E2E_PORT || "8123";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.mjs/,
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "list" : [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, headless: true },
  webServer: {
    command: "node e2e/serve.mjs",
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
