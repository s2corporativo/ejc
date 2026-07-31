import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(
  join(SRC_DIR, "pages/CasoDetalhe/TabRisco.tsx"),
  "utf-8",
);

describe("governança do índice de risco", () => {
  it("não apresenta triagem incompleta com semântica verde", () => {
    const bloco = source.match(/incompleto:\s*\{([\s\S]*?)\},\s*baixo:/)?.[1];

    expect(bloco).toBeDefined();
    expect(bloco).toContain("text-gray");
    expect(bloco).not.toContain("green");
  });

  it("explica que ausência documental impede avaliação conclusiva", () => {
    expect(source).toContain("Triagem incompleta");
    expect(source).toContain('role="status"');
    expect(source).toContain(
      "Não há documentos anexados suficientes para uma avaliação",
    );
    expect(source).toContain(
      "antes de usar este índice em uma decisão jurídica",
    );
  });
});
