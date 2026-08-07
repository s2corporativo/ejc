// @vitest-environment node
// Prefixo canônico das chamadas ao cliente `api` (Onda 2 da refatoração).
//
// `lib/api.ts` usa `baseURL: "/api/v1"`. Dentro do cliente `api`, o caminho se
// escreve SEM prefixo (`/casos`, não `/api/casos` nem `/v1/casos`).
//
// O interceptor de request apara `/api/v1/`, `/api/` e `/v1/` — mas ele mesmo
// se declara "compatibilidade transitória". Enquanto 27 call sites dependiam
// dessa poda, remover o shim quebraria as 27 de uma vez; e a auditoria de
// julho/2026 leu o sintoma pelo lado errado, vendo `/api/v1/v1/despesas`
// responder 200 e concluindo que o backend tinha prefixo duplicado.
//
// ESCOPO do guarda: só o que passa pelo cliente `api`. Quem fala com o backend
// por outro caminho — `streamSSE` (fetch cru), `refreshAccessToken` (axios cru)
// e os `backendPrefixes` do moduleRegistry (metadado, não chamada) — precisa
// do path REAL e continua legítimo com `/api/…`.
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath, não `.pathname`: a URL preserva escapes (%20, %C3%A1) e o
// readdirSync receberia um caminho inexistente se o checkout ficasse numa
// pasta com espaço ou acento — o guarda morreria de erro, não de achado.
const RAIZ = fileURLToPath(new URL("..", import.meta.url)); // src/
// O interceptor PRECISA continuar reconhecendo as formas antigas para não
// quebrar chamada legada — é o único arquivo isento.
const ISENTOS = new Set(["lib/api.ts", "lib/api.prefixo.test.ts"]);

function arquivosFonte(dir: string, prefixo = ""): string[] {
  const saida: string[] = [];
  for (const entrada of readdirSync(dir)) {
    const caminho = join(dir, entrada);
    const relativo = prefixo ? `${prefixo}/${entrada}` : entrada;
    if (statSync(caminho).isDirectory()) {
      saida.push(...arquivosFonte(caminho, relativo));
    } else if (/\.tsx?$/.test(entrada)) {
      saida.push(relativo);
    }
  }
  return saida;
}

// `api.get("/api/v1/x")`, `api.post<T>(\n  `/v1/x`…)` etc.
//
// O genérico aceita ANINHAMENTO (`api.get<Resposta<Item[]>>(…)`): `<[^>]*>`
// pararia no primeiro `>` e deixaria a chamada passar batido — um buraco no
// guarda, e este teste existe justamente para não ter buraco. `[^()"\'`]*`
// consome o corpo do genérico inteiro sem atravessar o parêntese de abertura
// nem o literal do caminho, que são os delimitadores reais aqui.
const CHAMADA_COM_PREFIXO =
  /\bapi\s*\.\s*(get|post|put|patch|delete|request|head|options)\s*(?:<[^()"'`]*>)?\s*\(\s*(["'`])\/(api\/v1|api|v1)\//g;

function linhaDe(conteudo: string, indice: number): number {
  return conteudo.slice(0, indice).split("\n").length;
}

describe("prefixo das chamadas ao cliente api", () => {
  const arquivos = arquivosFonte(RAIZ).filter((f) => !ISENTOS.has(f));

  it("varre um conjunto de arquivos não trivial", () => {
    // Guarda contra o próprio teste passar por vacuidade (raiz errada, glob
    // quebrado) e dar falsa sensação de cobertura.
    expect(arquivos.length).toBeGreaterThan(100);
  });

  it("nenhuma chamada ao cliente api repete o prefixo do baseURL", () => {
    const ocorrencias: string[] = [];
    for (const relativo of arquivos) {
      const conteudo = readFileSync(join(RAIZ, relativo), "utf-8");
      for (const m of conteudo.matchAll(CHAMADA_COM_PREFIXO)) {
        ocorrencias.push(
          `${relativo}:${linhaDe(conteudo, m.index ?? 0)}  api.${m[1]}("/${m[3]}/…)  →  escreva o caminho sem prefixo`,
        );
      }
    }
    expect(ocorrencias).toEqual([]);
  });

  it("o padrão proibido é de fato detectado (o guarda não é vácuo)", () => {
    const amostras = [
      'api.get("/v1/despesas")',
      "api.post(`/api/v1/casos/${id}`)",
      'await api.patch(\n  "/api/clients/1",\n  {},\n)',
      'api.get<Sessao[]>("/v1/sala-juridica")',
      // Genérico ANINHADO — o buraco que `<[^>]*>` deixava passar.
      'api.get<Resposta<Item[]>>("/v1/itens")',
      'api.get<Resposta<Map<string, Item[]>>>("/api/v1/itens")',
    ];
    for (const amostra of amostras) {
      CHAMADA_COM_PREFIXO.lastIndex = 0;
      expect(CHAMADA_COM_PREFIXO.test(amostra), amostra).toBe(true);
    }
    // E o que é legítimo NÃO dispara.
    for (const ok of [
      'api.get("/despesas")',
      'streamSSE("/api/ia/agente/stream", body)',
      'backendPrefixes: ["/api/diagnostico"]',
      'axios.post("/api/auth/refresh")',
    ]) {
      CHAMADA_COM_PREFIXO.lastIndex = 0;
      expect(CHAMADA_COM_PREFIXO.test(ok), ok).toBe(false);
    }
  });
});
