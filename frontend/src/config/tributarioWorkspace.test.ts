import { describe, expect, it } from "vitest";
import { STAFF_ROUTES, canRoleAccessPath } from "./moduleRegistry";
import {
  casoTributarioAtivo,
  filtrarCasosTributarios,
  resumoCarteiraTributaria,
} from "../pages/TributarioWorkspace";
import type { Case } from "../types";

function caso(overrides: Partial<Case>): Case {
  return {
    id: "1",
    titulo: "Caso tributário",
    area: "tributario",
    status: "aberto",
    fase: "diagnostico",
    prioridade: "media",
    client_id: "cliente-1",
    created_at: "2026-09-06T00:00:00Z",
    ...overrides,
  } as Case;
}

describe("workspace tributário", () => {
  it("expõe uma porta própria como SATÉLITE — fora do menu enxuto de 8 domínios", () => {
    const tributario = STAFF_ROUTES.find((route) => route.key === "tributario");

    expect(tributario?.path).toBe("/tributario");
    expect(tributario?.label).toBe("Tributário");
    // Reconstrução do #1550 sobre o desenho do #1680: satélite escondido,
    // alcançável pelo hub /ferramentas e por deep link — não é 9º domínio.
    expect(tributario?.status).toBe("hidden");
    expect(tributario?.showInNav).not.toBe(true);
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

  it("consolida somente os casos tributários canônicos e aceita filtro por cliente", () => {
    const casos = [
      caso({ id: "t1", client_id: "cliente-1" }),
      caso({ id: "t2", client_id: "cliente-2" }),
      caso({ id: "c1", area: "civil", client_id: "cliente-1" }),
    ];

    expect(filtrarCasosTributarios(casos).map((item) => item.id)).toEqual([
      "t1",
      "t2",
    ]);
    expect(
      filtrarCasosTributarios(casos, "cliente-1").map((item) => item.id),
    ).toEqual(["t1"]);
  });

  it("resume ativos, prioridade e risco sem inventar status paralelo", () => {
    const casos = [
      caso({ id: "a", status: "aberto", prioridade: "urgente", risco: "alto" }),
      caso({ id: "b", status: "em_instrucao", prioridade: "alta" }),
      caso({ id: "c", status: "encerrado", risco_nivel: "alto" }),
      caso({ id: "d", status: "arquivado" }),
    ];

    expect(casoTributarioAtivo(casos[0])).toBe(true);
    expect(casoTributarioAtivo(casos[2])).toBe(false);
    expect(resumoCarteiraTributaria(casos)).toEqual({
      total: 4,
      ativos: 2,
      altaPrioridade: 2,
      altoRisco: 2,
    });
  });
});
