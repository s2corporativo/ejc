import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const CONSUMIDORES = [
  "pages/CadastroManual.tsx",
  "pages/RaioXProcesso.tsx",
  "pages/RamosHub.tsx",
] as const;

describe("consumidores do catálogo canônico de áreas", () => {
  for (const relativo of CONSUMIDORES) {
    it(`${relativo} deriva o fallback de areaCatalog`, () => {
      const fonte = readFileSync(join(SRC, relativo), "utf-8");

      expect(fonte).toContain('from "../lib/areaCatalog"');
      expect(fonte).toContain("AREAS_FALLBACK");
      expect(fonte).not.toMatch(
        /const\s+(?:FALLBACK_AREAS|AREAS)[^=]*=\s*\[/,
      );
    });
  }
});
