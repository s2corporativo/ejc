// Integridade dos módulos lazy: todo `lazy(() => import("…"))` do registry e do
// App precisa apontar para um arquivo que EXISTE no disco.
//
// Por que este teste: um import quebrado por remoção de página órfã não aparece
// no `tsc --noEmit` de forma óbvia nem em teste de rota — só estoura no build
// (ou, pior, em runtime ao navegar). Depois da consolidação das superfícies de
// Conhecimento (Biblioteca, KnowledgeHub, Memória Institucional e Wiki viraram
// a aba `/inteligencia?tab=conhecimento`), esta trava evita que uma faxina
// futura deixe o registry apontando para um arquivo apagado.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");

/** Extensões que o Vite resolve para um specifier sem extensão. */
const EXTENSOES = [".tsx", ".ts", ".jsx", ".js"];

function resolveModulo(arquivoOrigem: string, specifier: string): boolean {
  const base = resolve(dirname(arquivoOrigem), specifier);
  if (EXTENSOES.some((ext) => existsSync(base + ext))) return true;
  // Diretório com index.*
  return EXTENSOES.some((ext) => existsSync(join(base, `index${ext}`)));
}

function lazyImports(arquivo: string): string[] {
  const fonte = readFileSync(arquivo, "utf-8");
  return [...fonte.matchAll(/lazy\(\s*\(\)\s*=>\s*import\("([^"]+)"\)/g)].map(
    (m) => m[1],
  );
}

const ARQUIVOS = [
  join(SRC_DIR, "config/moduleRegistry.tsx"),
  join(SRC_DIR, "App.tsx"),
];

describe("integridade dos módulos lazy", () => {
  for (const arquivo of ARQUIVOS) {
    it(`todo lazy import de ${arquivo.replace(SRC_DIR, "src")} aponta para arquivo existente`, () => {
      const specifiers = lazyImports(arquivo);
      // Guarda contra regex que pare de casar após refactor de formatação.
      expect(specifiers.length).toBeGreaterThan(0);
      const quebrados = specifiers.filter((s) => !resolveModulo(arquivo, s));
      expect(quebrados).toEqual([]);
    });
  }
});
