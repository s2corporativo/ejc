import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = dirname(fileURLToPath(import.meta.url));
const areas = readFileSync(join(SRC, "areas.ts"), "utf-8");
const ramosHub = readFileSync(join(SRC, "../pages/RamosHub.tsx"), "utf-8");
const raioX = readFileSync(join(SRC, "../pages/RaioXProcesso.tsx"), "utf-8");

describe("FE-08 — taxonomia de áreas compartilhada", () => {
  it("mantém GET /areas e fallback no hook canônico", () => {
    expect(areas).toContain('.get("/areas")');
    expect(areas).toContain("AREAS_FALLBACK");
    expect(areas).toContain("let cache: AreaDireito[] | null = null");
  });

  it("remove os fetches duplicados dos consumidores", () => {
    expect(ramosHub).toContain('import { useAreas } from "../lib/areas"');
    expect(raioX).toContain('import { useAreas } from "../lib/areas"');
    expect(ramosHub).not.toContain('api.get("/areas")');
    expect(raioX).not.toContain('api.get("/areas")');
    expect(ramosHub).toContain("mesclarAreas(areasRemotas)");
    expect(raioX).toContain("const areas = areasRemotas");
  });
});
