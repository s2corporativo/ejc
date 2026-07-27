// RBAC das suspensões: criar e remover exigem require_roles no backend
// (superadmin/admin/sócio). A Central esconde os controles de quem tomaria 403 —
// se o backend afrouxar ou apertar esses papéis, este teste falha antes de a UI
// ficar dessincronizada (botão visível que dá erro, ou recurso escondido de quem
// tem direito).
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ROLES_SUSPENSAO } from "./acoesLegadas";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "../../../..");

describe("RBAC das suspensões na Central", () => {
  it("os papéis da UI são exatamente os do require_roles do backend", () => {
    const router = join(RAIZ, "backend/app/routers/suspensoes.py");
    if (!existsSync(router)) return; // frontend isolado: nada a comparar
    const fonte = readFileSync(router, "utf-8");
    const grupos = [...fonte.matchAll(/require_roles\(\[([^\]]+)\]\)/g)].map(
      (m) =>
        [...m[1].matchAll(/"([a-z_]+)"/g)]
          .map((r) => r[1])
          .sort()
          .join(","),
    );
    // As rotas protegidas (criar e remover) usam o MESMO conjunto de papéis.
    expect(grupos.length).toBeGreaterThan(0);
    expect(new Set(grupos).size).toBe(1);
    expect(grupos[0]).toBe([...ROLES_SUSPENSAO].sort().join(","));
  });

  it("simular não é protegida por papel (é cálculo de leitura)", () => {
    const router = join(RAIZ, "backend/app/routers/suspensoes.py");
    if (!existsSync(router)) return;
    const fonte = readFileSync(router, "utf-8");
    const simular = fonte.slice(fonte.indexOf('@router.post("/simular")'));
    const assinatura = simular.slice(0, simular.indexOf("):"));
    expect(assinatura).toContain("get_current_user");
    expect(assinatura).not.toContain("require_roles");
  });
});
