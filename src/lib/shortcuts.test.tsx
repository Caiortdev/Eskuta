import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useShortcuts, type Shortcut } from "./shortcuts";

function TestComponent({ shortcuts }: { shortcuts: Shortcut[] }) {
  useShortcuts(shortcuts);
  return null;
}

function dispatchKey(
  key: string,
  opts: {
    ctrl?: boolean;
    shift?: boolean;
    alt?: boolean;
    target?: EventTarget;
  } = {},
) {
  const event = new KeyboardEvent("keydown", {
    key,
    ctrlKey: opts.ctrl,
    shiftKey: opts.shift,
    altKey: opts.alt,
    bubbles: true,
    cancelable: true,
  });
  if (opts.target) {
    Object.defineProperty(event, "target", { value: opts.target });
  }
  window.dispatchEvent(event);
  return event;
}

describe("useShortcuts", () => {
  it("dispara handler quando match simples (sem modificador)", () => {
    const handler = vi.fn();
    render(
      <TestComponent
        shortcuts={[{ key: "a", description: "test", handler }]}
      />,
    );
    dispatchKey("a");
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("dispara handler com Ctrl (mod=true)", () => {
    const handler = vi.fn();
    render(
      <TestComponent
        shortcuts={[{ key: "u", mod: true, description: "upload", handler }]}
      />,
    );
    dispatchKey("u", { ctrl: true });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("NÃO dispara se mod=true e sem Ctrl", () => {
    const handler = vi.fn();
    render(
      <TestComponent
        shortcuts={[{ key: "u", mod: true, description: "x", handler }]}
      />,
    );
    dispatchKey("u");
    expect(handler).not.toHaveBeenCalled();
  });

  it("NÃO dispara se mod=false e com Ctrl", () => {
    const handler = vi.fn();
    render(
      <TestComponent shortcuts={[{ key: "u", description: "x", handler }]} />,
    );
    dispatchKey("u", { ctrl: true });
    expect(handler).not.toHaveBeenCalled();
  });

  it("dispara com Shift+Alt combinado", () => {
    const handler = vi.fn();
    render(
      <TestComponent
        shortcuts={[
          { key: "k", shift: true, alt: true, description: "x", handler },
        ]}
      />,
    );
    dispatchKey("k", { shift: true, alt: true });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("NÃO dispara em input editável", () => {
    const handler = vi.fn();
    render(
      <TestComponent shortcuts={[{ key: "u", description: "x", handler }]} />,
    );
    const input = document.createElement("input");
    document.body.appendChild(input);
    dispatchKey("u", { target: input });
    expect(handler).not.toHaveBeenCalled();
    document.body.removeChild(input);
  });

  it("NÃO dispara em textarea", () => {
    const handler = vi.fn();
    render(
      <TestComponent shortcuts={[{ key: "u", description: "x", handler }]} />,
    );
    const ta = document.createElement("textarea");
    document.body.appendChild(ta);
    dispatchKey("u", { target: ta });
    expect(handler).not.toHaveBeenCalled();
    document.body.removeChild(ta);
  });

  it("para no primeiro match (não chama 2º handler)", () => {
    const h1 = vi.fn();
    const h2 = vi.fn();
    render(
      <TestComponent
        shortcuts={[
          { key: "a", description: "1", handler: h1 },
          { key: "a", description: "2", handler: h2 },
        ]}
      />,
    );
    dispatchKey("a");
    expect(h1).toHaveBeenCalledTimes(1);
    expect(h2).not.toHaveBeenCalled();
  });

  it("case-insensitive na key", () => {
    const handler = vi.fn();
    render(
      <TestComponent shortcuts={[{ key: "U", description: "x", handler }]} />,
    );
    dispatchKey("u");
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("cleanup remove o listener ao desmontar", () => {
    const handler = vi.fn();
    const { unmount } = render(
      <TestComponent shortcuts={[{ key: "a", description: "x", handler }]} />,
    );
    unmount();
    dispatchKey("a");
    expect(handler).not.toHaveBeenCalled();
  });
});
