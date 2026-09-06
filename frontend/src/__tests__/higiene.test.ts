/**
 * Guardas de higiene do frontend — impedem a volta do que a limpeza da
 * Issue #1543 removeu: asset em `public/` que ninguém referencia e export
 * de `src/lib/` que ninguém consome. Verificação nativa (sem knip), para
 * não reintroduzir peso de ferramenta só para medir peso.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND = process.cwd();
const SRC = join(FRONTEND, "src");
const PUBLIC = join(FRONTEND, "public");

function arquivos(dir: string, filtro?: RegExp): string[] {
  const saida: string[] = [];
  for (const entrada of readdirSync(dir)) {
    if (entrada === "node_modules") continue;
    const caminho = join(dir, entrada);
    if (statSync(caminho).isDirectory()) saida.push(...arquivos(caminho, filtro));
    else if (!filtro || filtro.test(entrada)) saida.push(caminho);
  }
  return saida;
}

const FONTES = [
  ...arquivos(SRC, /\.(tsx?|css)$/),
  ...arquivos(PUBLIC),
  join(FRONTEND, "index.html"),
];

/** Asset carregado pelo próprio navegador a partir do HTML/manifest. */
const ENTRYPOINTS_DO_NAVEGADOR = new Set(["manifest.json", "sw.js", "sw-register.js"]);

describe("higiene do frontend", () => {
  it("todo asset de public/ é referenciado", () => {
    const conteudo = new Map(
      FONTES.map((f) => [f, readFileSync(f, "utf8")] as const),
    );
    const orfaos: string[] = [];

    for (const asset of arquivos(PUBLIC)) {
      const nome = asset.split("/").pop() as string;
      if (ENTRYPOINTS_DO_NAVEGADOR.has(nome)) continue;
      const referenciado = [...conteudo].some(
        ([arquivo, texto]) => arquivo !== asset && texto.includes(nome),
      );
      if (!referenciado) orfaos.push(relative(FRONTEND, asset));
    }

    expect(
      orfaos,
      `Asset em public/ sem nenhuma referência (peso morto no build):\n  ${orfaos.join("\n  ")}`,
    ).toEqual([]);
  });

  it("todo export de src/lib é consumido", () => {
    const fontesTs = arquivos(SRC, /\.tsx?$/);
    const conteudo = new Map(
      fontesTs.map((f) => [f, readFileSync(f, "utf8")] as const),
    );
    const orfaos: string[] = [];

    for (const arquivo of fontesTs) {
      if (!arquivo.startsWith(join(SRC, "lib"))) continue;
      if (/\.(test|spec)\.tsx?$/.test(arquivo)) continue;
      const proprio = conteudo.get(arquivo) as string;
      const exports = [
        ...proprio.matchAll(
          /^export\s+(?:async\s+)?(?:const|function|class)\s+(\w+)/gm,
        ),
      ].map((m) => m[1]);

      for (const nome of exports) {
        const alvo = new RegExp(`\\b${nome}\\b`);
        const usado = [...conteudo].some(
          ([outro, texto]) => outro !== arquivo && alvo.test(texto),
        );
        if (!usado) orfaos.push(`${relative(FRONTEND, arquivo)}: ${nome}`);
      }
    }

    expect(
      orfaos,
      `Export de src/lib sem nenhum consumidor (código morto):\n  ${orfaos.join("\n  ")}`,
    ).toEqual([]);
  });
});
