// Contrato de segurança do estimador OAB/MG.
// Sem fonte oficial vigente e verificável, a UI deve bloquear o cálculo e o
// backend não pode ser substituído por referências genéricas de mercado.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(
  join(SRC_DIR, "components/EstimadorHonorarios.tsx"),
  "utf-8",
);

describe("governança da tabela OAB/MG", () => {
  it("valida a disponibilidade antes de liberar a estimativa", () => {
    expect(source).toContain('api.get("/honorarios-oab/tabela"');
    expect(source).toContain(
      'disabled={loading || tabelaStatus !== "disponivel"}',
    );
    expect(source).toContain('role="alert"');
  });

  it("não apresenta valores genéricos de mercado como alternativa", () => {
    expect(source).not.toMatch(/refer[êe]ncia gen[ée]rica de mercado/i);
    expect(source).toContain("A estimativa permanece bloqueada.");
  });
});
