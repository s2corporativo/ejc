import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "OrquestradorPanel.tsx"), "utf-8");

describe("OrquestradorPanel — fluxo de Peças contextual", () => {
  it("mantém caseId ao encaminhar geração, aprovação e protocolo", () => {
    expect(fonte).toContain('to: `/casos/${caseId}?tab=pecas&acao=produzir`');
    expect(fonte).toContain('to: `/casos/${caseId}?tab=pecas`');
    expect(fonte).toContain("Produzir peça neste caso");
    expect(fonte).toContain("Abrir produção jurídica do caso");
  });

  it("não devolve ações de peça para a fila global", () => {
    const bloco = fonte.slice(
      fonte.indexOf('case "gerar_peca"'),
      fonte.indexOf("default:", fonte.indexOf('case "gerar_peca"')),
    );
    expect(bloco).not.toContain('to: "/pecas"');
  });
});
