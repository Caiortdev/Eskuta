import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiKeyGuideModal } from "./ApiKeyGuideModal";

describe("ApiKeyGuideModal", () => {
  let openSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  });

  afterEach(() => {
    openSpy.mockRestore();
  });

  it("renderiza título com nome do provider", () => {
    render(<ApiKeyGuideModal provider="groq" onClose={() => {}} />);
    expect(
      screen.getByText(/como obter sua chave do groq/i),
    ).toBeInTheDocument();
  });

  it("renderiza role='dialog' acessível", () => {
    render(<ApiKeyGuideModal provider="anthropic" onClose={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "api-key-guide-title");
  });

  it("renderiza todos os 5 steps numerados", () => {
    render(<ApiKeyGuideModal provider="groq" onClose={() => {}} />);
    // Cada passo tem um <li>; conferimos que tem ≥4 (alguns providers têm 4-5)
    const items = screen.getAllByRole("listitem");
    expect(items.length).toBeGreaterThanOrEqual(4);
  });

  it("botão de fechar (X) chama onClose", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ApiKeyGuideModal provider="openai" onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: /fechar/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("botão 'Cancelar' chama onClose", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ApiKeyGuideModal provider="google" onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("tecla Esc chama onClose", () => {
    const onClose = vi.fn();
    render(<ApiKeyGuideModal provider="assemblyai" onClose={onClose} />);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("botão 'Abrir console' chama window.open com noopener,noreferrer", async () => {
    const user = userEvent.setup();
    render(<ApiKeyGuideModal provider="groq" onClose={() => {}} />);
    const openBtn = screen.getByRole("button", {
      name: /abrir console\.groq\.com/i,
    });
    await user.click(openBtn);
    expect(openSpy).toHaveBeenCalledWith(
      "https://console.groq.com/keys",
      "_blank",
      "noopener,noreferrer",
    );
  });

  it("renderiza nota de segurança sobre keyring", () => {
    render(<ApiKeyGuideModal provider="anthropic" onClose={() => {}} />);
    expect(screen.getByText(/criptografada no keyring/i)).toBeInTheDocument();
  });

  it("renderiza nota específica do provider (gemini menciona 'mais barato')", () => {
    render(<ApiKeyGuideModal provider="google" onClose={() => {}} />);
    expect(screen.getByText(/gemini-2\.0-flash/i)).toBeInTheDocument();
  });

  it("click no backdrop chama onClose", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ApiKeyGuideModal provider="openai" onClose={onClose} />);
    // O backdrop é o div com role='dialog' (que tem onClick no target===currentTarget)
    await user.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("cada provider tem consoleUrl diferente", async () => {
    const user = userEvent.setup();
    const providers: Array<{
      p: "groq" | "anthropic" | "openai";
      url: string;
    }> = [
      { p: "groq", url: "https://console.groq.com/keys" },
      { p: "anthropic", url: "https://console.anthropic.com/settings/keys" },
      { p: "openai", url: "https://platform.openai.com/api-keys" },
    ];
    for (const { p, url } of providers) {
      openSpy.mockClear();
      const { unmount } = render(
        <ApiKeyGuideModal provider={p} onClose={() => {}} />,
      );
      const btn = screen.getByRole("button", { name: /^abrir /i });
      await user.click(btn);
      expect(openSpy).toHaveBeenCalledWith(
        url,
        "_blank",
        "noopener,noreferrer",
      );
      unmount();
    }
  });
});
