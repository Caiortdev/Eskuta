import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UpdateChecker } from "./UpdateChecker";

describe("UpdateChecker", () => {
  it("não renderiza nada em ambiente não-Tauri (sem __TAURI_INTERNALS__)", () => {
    const { container } = render(<UpdateChecker />);
    // Sem Tauri env, fica idle e nada visível
    expect(container.firstChild).toBeNull();
  });

  it("não mostra UI quando estado é idle", () => {
    render(<UpdateChecker />);
    // Não tem role="dialog" pra update
    expect(
      screen.queryByRole("dialog", { name: /atualiza/i }),
    ).not.toBeInTheDocument();
  });
});
