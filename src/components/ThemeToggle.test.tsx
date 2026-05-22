import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("renderiza botão acessível com aria-label", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /tema/i })).toBeInTheDocument();
  });

  it("default mostra ícone do tema system", () => {
    render(<ThemeToggle />);
    const btn = screen.getByRole("button", { name: /tema/i });
    // ícone do system é o monitor
    expect(btn.textContent).toContain("🖥");
  });

  it("cicla system → light → dark → system ao clicar", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    const btn = screen.getByRole("button", { name: /tema/i });

    expect(btn).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/automático/i),
    );
    await user.click(btn);
    expect(btn).toHaveAttribute("aria-label", expect.stringMatching(/claro/i));
    await user.click(btn);
    expect(btn).toHaveAttribute("aria-label", expect.stringMatching(/escuro/i));
    await user.click(btn);
    expect(btn).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/automático/i),
    );
  });

  it("compact prop esconde o label de texto", () => {
    render(<ThemeToggle compact />);
    const btn = screen.getByRole("button", { name: /tema/i });
    // Em compact, só o ícone — sem "Auto"/"Claro"/"Escuro"
    expect(btn.textContent?.trim()).not.toMatch(/auto|claro|escuro/i);
  });

  it("não-compact mostra label", () => {
    render(<ThemeToggle />);
    const btn = screen.getByRole("button", { name: /tema/i });
    expect(btn.textContent).toMatch(/auto|claro|escuro/i);
  });
});
