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

describe("Peças — contrato da interface operacional simplificada", () => {
  it("mantém os seis estados internos agrupados em quatro fases visuais", () => {
    expect(fonte).toContain('statuses: ["rascunho", "em_revisao"]');
    expect(fonte).toContain('statuses: ["corrigida"]');
    expect(fonte).toContain('statuses: ["aprovada", "final"]');
    expect(fonte).toContain('statuses: ["protocolada"]');
    expect(fonte).toContain('label: "Em elaboração"');
    expect(fonte).toContain('label: "Revisadas"');
    expect(fonte).toContain('label: "Aprovadas"');
    expect(fonte).toContain('label: "Protocoladas"');
  });

  it("usa ações jurídicas explícitas em vez de movimentação genérica de status", () => {
    expect(fonte).toContain("Revisar peça");
    expect(fonte).toContain("Aprovar e assinar");
    expect(fonte).toContain("Finalizar");
    expect(fonte).toContain("Protocolar");
    expect(fonte).toContain("/conferir-e-assinar");
    expect(fonte).not.toContain("avancarStatus");
  });

  it("concentra ferramentas secundárias em Mais e preserva capacidades existentes", () => {
    expect(fonte).toContain("function MaisAcoes");
    expect(fonte).toContain('label="PDF"');
    expect(fonte).toContain('label="DOCX"');
    expect(fonte).toContain("Documento único / Visual Law");
    expect(fonte).toContain("Jurisprudência e citações");
    expect(fonte).toContain("Crítica da peça");
  });

  it("mantém inteligência separada do texto e suporta edição controlada", () => {
    expect(fonte).toContain("Workspace Jurídico");
    expect(fonte).toContain("Inteligência jurídica");
    expect(fonte).toContain("Fontes, validação e crítica ficam separados do texto");
    expect(fonte).toContain('<Markdown source={view.conteudo}');
    expect(fonte).toContain("Salvar nova versão");
  });
});
