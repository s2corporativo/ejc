import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = dirname(fileURLToPath(import.meta.url));
const read = (relative: string) => readFileSync(join(SRC, relative), "utf-8");

describe("FE-11 — operações AI canônicas", () => {
  it("expõe as operações legadas na fachada services/ai.ts", () => {
    const service = read("ai.ts");
    for (const fn of [
      "sugerirHonorarios",
      "analisarCaso",
      "analisarContrato",
      "registrarAplicacaoHITL",
      "registrarFeedbackIA",
    ]) {
      expect(service).toContain(`export async function ${fn}`);
    }
  });

  it("remove endpoints raw dos três consumidores migrados", () => {
    for (const file of [
      "../pages/CasoDetalhe/TabResumo.tsx",
      "../pages/CasoDetalhe/TabFerramentas.tsx",
      "../components/ContextualAIAssistant.tsx",
    ]) {
      const source = read(file);
      expect(source).not.toMatch(
        /api\.(get|post|patch|put|delete)\([^\n]*\/ai\//,
      );
    }
  });
});
