import { describe, expect, it } from "vitest";
import {
  configWorkspaceDaArea,
  hubSlugDaArea,
  temWorkspaceEspecializado,
} from "./areasWorkspace";
import { abasDoWorkspace } from "./ramoWorkspace";

describe("workspace canônico — integração do fallback", () => {
  it("mantém especialidade canônica sem implementação em workspace próprio e rejeita slug inválido", () => {
    expect(temWorkspaceEspecializado("internacional")).toBe(false);
    expect(hubSlugDaArea("internacional")).toBe("internacional");

    const cfg = configWorkspaceDaArea("internacional");
    expect(cfg?.areaCaso).toBe("internacional");
    expect(cfg?.endpoint).toBe("");
    expect(cfg?.ferramentas).toEqual([]);
    expect(abasDoWorkspace(cfg!).map((aba) => aba.id)).toEqual([
      "visao",
      "casos",
      "referencias",
    ]);

    expect(hubSlugDaArea("area-inexistente")).toBeNull();
    expect(configWorkspaceDaArea("area-inexistente")).toBeUndefined();
  });
});
