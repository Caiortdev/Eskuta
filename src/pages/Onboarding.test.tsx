import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { OnboardingPage } from "./Onboarding";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/onboarding"]}>
      <Routes>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/settings" element={<p>settings landed</p>} />
        <Route path="/" element={<p>home landed</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OnboardingPage", () => {
  it("renderiza heading de boas-vindas", () => {
    renderPage();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /bem-vindo ao eskuta/i,
    );
  });

  it("explica STT e LLM", () => {
    renderPage();
    expect(screen.getByText(/STT/)).toBeInTheDocument();
    expect(screen.getByText(/LLM/)).toBeInTheDocument();
  });

  it("menciona keyring do sistema", () => {
    renderPage();
    expect(screen.getByText(/keyring/i)).toBeInTheDocument();
  });

  it("botão 'Configurar agora' navega pra /settings", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /configurar agora/i }));
    expect(screen.getByText(/settings landed/i)).toBeInTheDocument();
  });

  it("botão 'Pular' navega pra /", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /pular/i }));
    expect(screen.getByText(/home landed/i)).toBeInTheDocument();
  });
});
