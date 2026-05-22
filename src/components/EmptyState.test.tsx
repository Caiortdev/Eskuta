import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renderiza o título obrigatório", () => {
    render(<EmptyState title="Nada por aqui" />);
    expect(screen.getByText(/nada por aqui/i)).toBeInTheDocument();
  });

  it("renderiza description quando fornecido", () => {
    render(<EmptyState title="Vazio" description="Faça upload do seu áudio" />);
    expect(screen.getByText(/faça upload/i)).toBeInTheDocument();
  });

  it("não renderiza description quando omitido", () => {
    const { container } = render(<EmptyState title="X" />);
    // Apenas 1 elemento textual (o título)
    expect(container.querySelectorAll("p").length).toBe(0);
  });

  it("renderiza action node quando fornecido", () => {
    render(
      <EmptyState
        title="X"
        action={<button type="button">Clica aqui</button>}
      />,
    );
    expect(
      screen.getByRole("button", { name: /clica aqui/i }),
    ).toBeInTheDocument();
  });
});
