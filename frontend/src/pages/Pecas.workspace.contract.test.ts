import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));

// A decomposição do monólito (auditoria §2.6 #10) moveu blocos da página para
// pecas/ — o contrato da feature continua único: ler a página + o módulo.
const fonte = [
  join(DIR, "Pecas.tsx"),
  ...readdirSync(join(DIR, "pecas"))
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => join(DIR, "pecas", f)),
]
  .map((p) => readFileSync(p, "utf-8"))
  .join("\n")
  // Prettier quebra textos JSX longos em várias linhas — o contrato
  // é sobre a frase existir no módulo, não sobre o layout do fonte.
  .replace(/\s+/g, " ");

describe("Peças — Workspace Jurídico", () => {
  it("permite editar pelo PATCH canônico e não cria endpoint paralelo", () => {
    expect(fonte).toContain("Workspace Jurídico");
    expect(fonte).toContain('api.patch(`/legal-docs/${view.id}`, {');
    expect(fonte).toContain("conteudo: conteudoEdicao");
    expect(fonte).toContain("Salvar nova versão");
    expect(fonte).not.toContain("/workspace/pecas");
  });

  it("bloqueia edição de versão final ou protocolada", () => {
    expect(fonte).toContain('view.status === "final" || view.status === "protocolada"');
    expect(fonte).toContain('view.status !== "final" && view.status !== "protocolada"');
    expect(fonte).toContain("Versão final ou protocolada não pode ser editada");
  });

  it("explicita que nova versão exige nova validação/revisão", () => {
    expect(fonte).toContain("Validação e revisão devem ser refeitas antes da aprovação");
    expect(fonte).toContain("Salve ou cancele a edição antes de revisar");
  });

  it("mantém inteligência separada do texto", () => {
    expect(fonte).toContain("Inteligência jurídica");
    expect(fonte).toContain("Jurisprudência e citações");
    expect(fonte).toContain("Crítica da peça");
    expect(fonte).toContain("A IA não altera a peça sem ação explícita do advogado");
  });

  it("reidrata o detalhe aberto depois da validação jurídica", () => {
    expect(fonte).toContain("if (view?.id === doc.id) {");
    expect(fonte).toContain("await abrirDetalhe(doc.id);");
  });

  it("não oferece aprovação intermediária pelo endpoint legado de revisão", () => {
    expect(fonte).toContain("const devolverParaRevisao = async () => {");
    expect(fonte).toContain("aprovado: false");
    expect(fonte).not.toContain("Salvar revisão");
    expect(fonte).not.toContain("salvarRevisao(true)");
    expect(fonte).toContain("Aprovar e assinar");
  });
});
