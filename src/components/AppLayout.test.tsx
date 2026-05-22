import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppLayout } from "./AppLayout";

function renderWithRouter(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<p data-testid="outlet">home page</p>} />
          <Route path="/upload" element={<p data-testid="outlet">upload</p>} />
          <Route
            path="/settings"
            element={<p data-testid="outlet">settings</p>}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AppLayout", () => {
  it("renderiza o título do app na sidebar", () => {
    renderWithRouter();
    expect(
      screen.getByRole("heading", { name: /eskuta/i, level: 1 }),
    ).toBeInTheDocument();
  });

  it("renderiza os 3 links de navegação", () => {
    renderWithRouter();
    expect(screen.getByText(/^reuniões$/i)).toBeInTheDocument();
    expect(screen.getByText(/^nova reunião$/i)).toBeInTheDocument();
    expect(screen.getByText(/^configurações$/i)).toBeInTheDocument();
  });

  it("renderiza o Outlet (rota filha)", () => {
    renderWithRouter("/");
    expect(screen.getByTestId("outlet")).toHaveTextContent("home page");
  });

  it("muda o Outlet quando navega entre rotas", () => {
    renderWithRouter("/settings");
    expect(screen.getByTestId("outlet")).toHaveTextContent("settings");
  });

  it("link ativo recebe classes diferentes do inativo", () => {
    const { container } = renderWithRouter("/");
    const links = container.querySelectorAll("a");
    // Pelo menos um link tem classe de "ativo" (primary)
    const activeLinks = Array.from(links).filter((a) =>
      a.className.includes("text-primary"),
    );
    expect(activeLinks.length).toBeGreaterThanOrEqual(1);
  });
});
