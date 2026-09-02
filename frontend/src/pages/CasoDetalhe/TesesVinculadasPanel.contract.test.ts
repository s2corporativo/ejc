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
    expect(fonte).toContain("Esta tela não oferece ação de vínculo");
    expect(fonte).not.toContain("api.post(");
    expect(fonte).not.toContain("api.patch(");
  });

  it("expõe contrargumento e exige conferência de vigência e fonte oficial", () => {
    expect(fonte).toContain("Contrargumento previsível cadastrado");
    expect(fonte).toContain("confira vigência, inteiro teor e");
    expect(fonte).toContain("fonte oficial");
    expect(fonte).toContain("a decisão jurídica continua humana");
  });

  it("mantém inteiro teor visível e diferencia teses não ativas", () => {
    expect(fonte).toContain('const ativa = tese.status === "ativa"');
    expect(fonte).toContain("Tese não ativa");
    expect(fonte).not.toContain("line-clamp-4");
    expect(fonte).toContain("Jurisprudência cadastrada");
  });

  it("formata histórico pelas duas convenções canônicas", () => {
    expect(fonte).toContain('import { fmtTaxaSucesso } from "../../utils/formato"');
    expect(fonte).toContain("fmtTaxaSucesso(tese.taxa_sucesso)");
    expect(fonte).not.toContain("tese.taxa_sucesso * 100");
  });

  it("descarta respostas antigas quando o caso muda", () => {
    expect(fonte).toContain("requestSeqRef");
    expect(fonte).toContain("requestSeq !== requestSeqRef.current");
    expect(fonte).toContain("requestSeqRef.current += 1");
  });

  it("trata loading, erro, retry e estado vazio sem prometer vínculo inexistente", () => {
    expect(fonte).toContain("Carregando teses do caso");
    expect(fonte).toContain("Não foi possível carregar as teses vinculadas");
    expect(fonte).toContain("Tentar novamente");
    expect(fonte).toContain("Nenhuma tese está vinculada a este caso");
    expect(fonte).toContain("Consulte o Banco de Teses para localizar conteúdo institucional");
  });
});
