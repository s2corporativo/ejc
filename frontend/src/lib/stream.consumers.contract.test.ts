import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = dirname(fileURLToPath(import.meta.url));

const read = (relative: string) => readFileSync(join(SRC, relative), "utf-8");

describe("FE-07 — consumidores reais do streaming HTTP", () => {
  it("mantém AgenteIA no parser SSE canônico", () => {
    const source = read("../pages/AgenteIA.tsx");
    expect(source).toContain('from "../lib/stream"');
    expect(source).toContain("streamSSE(");
  });

  it("mantém o caminho raw-fetch de geração de peça", () => {
    const source = read("../components/PecaGeneratorModal.tsx");
    expect(source).toContain('from "../lib/stream"');
    expect(source).toContain("authFetch(");
  });

  it("preserva streaming incremental nos módulos de extratos e bancário", () => {
    const extratos = read("../components/AnaliseExtratos.tsx");
    const bancario = read("../components/BancarioForense.tsx");
    expect(extratos).toContain('from "../lib/stream"');
    expect(bancario).toContain('from "../lib/stream"');
    expect(extratos).toMatch(/authFetch\(|streamSSE\(/);
    expect(bancario).toMatch(/authFetch\(|streamSSE\(/);
  });
});
