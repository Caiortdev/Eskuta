/**
 * E2E happy path — smoke test do fluxo crítico do app.
 *
 * Pré-requisito: sidecar Python rodando em :8765 (com sessão limpa
 * — sem meetings prévias). Em CI, isso é levantado por um job
 * dedicado antes de chamar npx playwright test.
 *
 * Esse arquivo é um SCAFFOLD — adicionamos mais casos conforme
 * tracker em RELEASE-READINESS.md. Por enquanto valida apenas:
 *   1. App carrega
 *   2. Sidecar gate fica verde
 *   3. Sidebar aparece com 3 itens
 *   4. Navega entre páginas via shortcuts
 */

import { expect, test } from "@playwright/test";

test.describe("Eskuta — happy path", () => {
  test("app carrega sem erros + sidebar aparece", async ({ page }) => {
    await page.goto("/");

    // Aguarda sidecar gate fechar (pode mostrar "Aguardando..." inicialmente)
    await expect(page.getByText(/eskuta/i).first()).toBeVisible({
      timeout: 30000,
    });

    // Sidebar tem 3 itens
    await expect(page.getByRole("link", { name: /reuniões/i })).toBeVisible();
    await expect(
      page.getByRole("link", { name: /nova reunião/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /configurações/i }),
    ).toBeVisible();
  });

  test("shortcut Ctrl+, navega pra Settings", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+,");
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByText(/configurações/i).first()).toBeVisible();
  });

  test("shortcut Ctrl+U navega pra Upload", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+u");
    await expect(page).toHaveURL(/\/upload/);
    await expect(page.getByText(/nova reunião/i).first()).toBeVisible();
  });

  test("Settings renderiza 5 providers", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText(/groq/i).first()).toBeVisible();
    await expect(page.getByText(/assemblyai/i).first()).toBeVisible();
    await expect(page.getByText(/anthropic/i).first()).toBeVisible();
    await expect(page.getByText(/openai/i).first()).toBeVisible();
    await expect(page.getByText(/google/i).first()).toBeVisible();
  });
});
