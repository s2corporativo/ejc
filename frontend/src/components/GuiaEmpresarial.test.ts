import { describe, expect, it } from "vitest";
import { podeAcessarDpt360 } from "./GuiaEmpresarial";

describe("GuiaEmpresarial — acesso ao DPT360", () => {
  it("permite somente os papéis já autorizados na rota DPT360", () => {
    for (const role of ["superadmin", "admin", "socio", "advogado"]) {
      expect(podeAcessarDpt360(role), role).toBe(true);
    }

    for (const role of [
      "advogado_auxiliar",
      "estagiario",
      "financeiro",
      "secretaria",
      "cliente_externo",
    ]) {
      expect(podeAcessarDpt360(role), role).toBe(false);
    }
  });

  it("não cria acesso quando o papel está ausente", () => {
    expect(podeAcessarDpt360(undefined)).toBe(false);
    expect(podeAcessarDpt360(null)).toBe(false);
  });
});
