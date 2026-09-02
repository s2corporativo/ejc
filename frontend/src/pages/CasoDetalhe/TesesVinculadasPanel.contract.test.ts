import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "TesesVinculadasPanel.tsx"), "utf-8");
const aba = readFileSync(join(DIR, "TabPecas.tsx"), "utf-8");

describe("Peças — Banco de Teses canônico no contexto do caso", () => {
  it("usa somente a rota canônica de teses já vinculadas ao caso", () => {
    expect(fonte).toContain("`/teses/casos/${caseId}`");
    expect(fonte).not.toContain("teses_juridicas");
    expect(fonte).not.toContain("/workspace/teses");
    expect(aba).toContain("<TesesVinculadasPanel caseId={caseId} />");
  });

  it("não injeta automaticamente tese na peça nem cria vínculo", () => {
    expect(fonte).toContain("não injeta automaticamente estas teses na peça");
    expect(fonte).toContain("o EJC não cria vínculo automático");
    expect(fonte).not.toContain("api.post(");
    expect(fonte).not.toContain("api.patch(");
  });

  it("expõe contrargumento e exige conferência de vigência e fonte oficial", () => {
    expect(fonte).toContain("Contrargumento previsível cadastrado");
    expect(fonte).toContain("confira vigência, inteiro teor e");
    expect(fonte).toContain("fonte oficial");
    expect(fonte).toContain("a decisão jurídica continua humana");
  });

  it("trata loading, erro, retry e estado vazio", () => {
    expect(fonte).toContain("Carregando teses do caso");
    expect(fonte).toContain("Não foi possível carregar as teses vinculadas");
    expect(fonte).toContain("Tentar novamente");
    expect(fonte).toContain("Nenhuma tese está vinculada a este caso");
  });
});
