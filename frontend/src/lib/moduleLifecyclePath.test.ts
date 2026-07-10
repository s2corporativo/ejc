import { describe, expect, it } from "vitest";
import { matchModuleByPath } from "./moduleLifecycle";

describe("module lifecycle route matching", () => {
  it("resolve rota dinâmica de detalhe de caso", () => {
    expect(matchModuleByPath("/casos/caso-123")?.path).toBe("/casos/:id");
  });

  it("não associa rota inexistente a outro módulo", () => {
    expect(matchModuleByPath("/rota-que-nao-existe")).toBeNull();
  });
});
