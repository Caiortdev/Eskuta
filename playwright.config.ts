/**
 * Playwright config — E2E happy path tests pro frontend do Eskuta.
 *
 * IMPORTANTE: Esses testes rodam contra o app rodando em dev (vite dev
 * server + sidecar Python sidecar mockado). Não substituem os unit tests
 * (vitest) — cobrem fluxos completos cross-componente.
 *
 * Rodar local:
 *   1. Em um terminal: cd src-python; venv/Scripts/activate; python -m uvicorn app.main:app --port 8765
 *   2. Em outro: npm run dev
 *   3. Em outro: npx playwright test
 *
 * Em CI (release.yml): só roda no PR pra main pra evitar carga.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // sidecar é singleton, não pode rodar em paralelo
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: "http://localhost:1420",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Tauri webview usa Chromium, então só testamos isso
  webServer: {
    command: "npm run dev",
    url: "http://localhost:1420",
    reuseExistingServer: !process.env.CI,
    timeout: 60 * 1000,
  },
});
