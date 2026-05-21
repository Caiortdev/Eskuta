import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("concatena classes simples", () => {
    expect(cn("a", "b", "c")).toBe("a b c");
  });

  it("ignora valores falsy", () => {
    expect(cn("a", false, null, undefined, 0, "b")).toBe("a b");
  });

  it("aplica condicionais via clsx", () => {
    expect(cn("base", { active: true, disabled: false })).toBe("base active");
  });

  it("resolve conflitos do Tailwind via twMerge", () => {
    // bg-red-500 deve ser sobrescrito por bg-blue-500
    expect(cn("bg-red-500", "bg-blue-500")).toBe("bg-blue-500");
    // p-2 sobrescrito por p-4
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("preserva classes não-conflitantes", () => {
    expect(cn("flex", "items-center", "gap-2")).toContain("flex");
    expect(cn("flex", "items-center", "gap-2")).toContain("items-center");
    expect(cn("flex", "items-center", "gap-2")).toContain("gap-2");
  });

  it("aceita arrays aninhados", () => {
    expect(cn(["a", "b"], "c")).toBe("a b c");
  });
});
