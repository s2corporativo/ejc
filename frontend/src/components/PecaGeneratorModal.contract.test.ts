import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const DIR = dirname(fileURLToPath(import.meta.url));
const fonte = readFileSync(join(DIR, "PecaGeneratorModal.tsx"), "utf-8");

describe("PecaGeneratorModal — contrato da auditoria E2E", () => {
  it("usa /pecas/meta como fonte única e falha fechado sem catálogo local", () => {
    expect(fonte).toContain('.get<PecasMeta>("/pecas/meta")');
    expect(fonte).toContain("Catálogo jurídico indisponível");
    expect(fonte).toContain("catalogoIndisponivel");

    // Regressão V2-6.6: listas locais parciais não podem reaparecer.
    expect(fonte).not.toContain("TIPOS_FALLBACK");
    expect(fonte).not.toContain("AREAS_FALLBACK");
    expect(fonte).not.toContain("NIVEIS_FALLBACK");
  });

  it("não bloqueia o modo guiado usando campos exclusivos do modo livre", () => {
    // A validação correta ocorre em gerar(), após montar effectiveFatos e
    // effectivePedidos de respostasGuiadas. O footer só deve bloquear quando o
    // catálogo canônico estiver indisponível.
    expect(fonte).toContain("const effectiveFatos = isGuiado");
    expect(fonte).toContain("const effectivePedidos = isGuiado");
    expect(fonte).toContain("disabled={catalogoIndisponivel}");
    expect(fonte).not.toContain(
      "disabled={fatos.length < 50 || pedidos.length < 10}",
    );
  });

  it("rejeita payload parcial do catálogo em vez de degradar silenciosamente", () => {
    expect(fonte).toContain("data.tipos.length === 0");
    expect(fonte).toContain("data.areas.length === 0");
    expect(fonte).toContain("data.niveis_complexidade.length === 0");
    expect(fonte).toContain('setTipos([])');
    expect(fonte).toContain('setAreas([])');
    expect(fonte).toContain('setNiveis([])');
  });
});