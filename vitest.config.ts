/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "node:path";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    css: false,
    // e2e/ é Playwright (não vitest). Excluímos do testMatch pra evitar
    // import error de "@playwright/test" que não é dep do vitest.
    exclude: ["node_modules/**", "dist/**", "e2e/**"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/vitest.d.ts",
        "src/components/ui/**", // Shadcn components (cópia do upstream)
        "src/types/**", // Pure type declarations (no runtime code)
        "src/**/*.test.{ts,tsx}",
        "e2e/**", // Playwright E2E tests, não vitest
      ],
      reporter: ["text", "html"],
      thresholds: {
        lines: 70,
        functions: 70,
        branches: 70,
        statements: 70,
      },
    },
  },
});
