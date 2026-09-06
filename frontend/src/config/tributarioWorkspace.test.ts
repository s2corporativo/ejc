import { describe, expect, it } from "vitest";
import { STAFF_ROUTES, canRoleAccessPath } from "./moduleRegistry";

describe("workspace tributário", () => {
  it("expõe uma porta própria sem criar outro módulo essencial", () => {
    const tributario = STAFF_ROUTES.find((route) => route.key === "tributario");

    expect(tributario?.path).toBe("/tributario");
    expect(tributario?.label).toBe("Tributário");
    expect(tributario?.showInNav).toBe(true);
    expect(tributario?.essential).toBe(false);
    expect(tributario?.backendPrefixes).toContain("/api/tributario/fiscal");
  });

  it("preserva o RBAC da equipe jurídica", () => {
    for (const role of [
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "advogado_auxiliar",
      "estagiario",
    ]) {
      expect(canRoleAccessPath(role, "/tributario"), role).toBe(true);
    }

    for (const role of ["financeiro", "secretaria", "cliente_externo"]) {
      expect(canRoleAccessPath(role, "/tributario"), role).toBe(false);
    }
  });
});
