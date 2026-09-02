import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "Pecas.tsx"), "utf-8");

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

  it("mantém inteligência separada do texto da peça", () => {
    expect(fonte).toContain("Inteligência jurídica");
    expect(fonte).toContain("Validação, fontes e crítica ficam concentradas aqui");
    expect(fonte).toContain('<Markdown source={view.conteudo}');
  });
});
