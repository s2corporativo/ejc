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

// Detector: `api.<metodo>` seguido de um genérico OPCIONAL e do literal do
// caminho. Regex não serve para o genérico — ele tem delimitador BALANCEADO e
// pode conter parênteses e literais de string:
//
//     api.get<Resposta<(Item | null)[]>>("/v1/itens")
//     api.get<Resposta<Record<"campo", Item>>>(`/api/v1/itens`)
//
// `<[^>]*>` para no primeiro `>`; `<[^()"\'`]*>` tropeça no parêntese e na
// aspa. Qualquer classe de caracteres erra num desses casos, e um detector com
// buraco é pior que detector nenhum: passa a falsa garantia. Daí o scanner.
const METODOS = "get|post|put|patch|delete|request|head|options";
const INICIO_CHAMADA = new RegExp(`\\bapi\\s*\\.\\s*(${METODOS})\\b`, "g");
const PREFIXOS_PROIBIDOS = ["/api/v1/", "/api/", "/v1/"] as const;

/** Avança sobre espaços a partir de `i`. */
function pularEspacos(texto: string, i: number): number {
  while (i < texto.length && /\s/.test(texto[i])) i += 1;
  return i;
}

/**
 * Fim de um genérico `<...>` iniciado em `i`, contando aninhamento e pulando
 * literais de string — ou -1 se não fechar. Aceita `<` e `>` dentro de string
 * sem contá-los como delimitador.
 */
function fimDoGenerico(texto: string, i: number): number {
  let profundidade = 0;
  while (i < texto.length) {
    const c = texto[i];
    if (c === '"' || c === "'" || c === "`") {
      i += 1;
      while (i < texto.length && texto[i] !== c) {
        if (texto[i] === "\\") i += 1; // escape dentro do literal
        i += 1;
      }
    } else if (c === "<") {
      profundidade += 1;
    } else if (c === ">") {
      profundidade -= 1;
      if (profundidade === 0) return i + 1;
    } else if (c === "(" && profundidade === 0) {
      return -1; // chegou na chamada sem genérico aberto
    } else if (c === ";" || c === "\n") {
      if (profundidade === 0) return -1;
    }
    i += 1;
  }
  return -1;
}

type Ocorrencia = { indice: number; metodo: string; prefixo: string };

/** Chamadas ao cliente `api` cujo caminho literal repete o prefixo do baseURL. */
export function chamadasComPrefixo(conteudo: string): Ocorrencia[] {
  const achados: Ocorrencia[] = [];
  INICIO_CHAMADA.lastIndex = 0;
  for (const m of conteudo.matchAll(INICIO_CHAMADA)) {
    let i = pularEspacos(conteudo, (m.index ?? 0) + m[0].length);
    if (conteudo[i] === "<") {
      const fim = fimDoGenerico(conteudo, i);
      if (fim === -1) continue;
      i = pularEspacos(conteudo, fim);
    }
    if (conteudo[i] !== "(") continue;
    i = pularEspacos(conteudo, i + 1);
    const aspa = conteudo[i];
    if (aspa !== '"' && aspa !== "'" && aspa !== "`") continue;
    const literal = conteudo.slice(i + 1, i + 1 + 12);
    const prefixo = PREFIXOS_PROIBIDOS.find((p) => literal.startsWith(p));
    if (prefixo) {
      achados.push({ indice: m.index ?? 0, metodo: m[1], prefixo });
    }
  }
  return achados;
}

function linhaDe(conteudo: string, indice: number): number {
  return conteudo.slice(0, indice).split("\n").length;
}

describe("prefixo das chamadas ao cliente api", () => {
  const arquivos = arquivosFonte(RAIZ).filter((f) => !ISENTOS.has(f));

  it("varreu a raiz certa (o guarda não roda no vazio)", () => {
    // Sentinela estável em vez de contagem: um número mínimo de arquivos
    // reprovaria numa poda legítima da árvore e ainda assim não provaria que a
    // raiz percorrida foi `src/`. Estes dois arquivos são o coração do
    // roteamento e das chamadas — se sumirem, o guarda precisa mesmo ser
    // revisto.
    expect(arquivos).toContain("config/moduleRegistry.tsx");
    expect(arquivos).toContain("lib/stream.ts");
  });

  it("nenhuma chamada ao cliente api repete o prefixo do baseURL", () => {
    const ocorrencias: string[] = [];
    for (const relativo of arquivos) {
      const conteudo = readFileSync(join(RAIZ, relativo), "utf-8");
      for (const o of chamadasComPrefixo(conteudo)) {
        ocorrencias.push(
          `${relativo}:${linhaDe(conteudo, o.indice)}  api.${o.metodo}("${o.prefixo}…)  →  escreva o caminho sem prefixo`,
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
      // Parêntese DENTRO do genérico — quebrava a classe `[^()"\'`]`.
      'api.get<Resposta<(Item | null)[]>>("/v1/itens")',
      // Literal de string dentro do genérico — idem.
      'api.get<Resposta<Record<"campo", Item>>>(`/api/v1/itens`)',
      'api.get<Resposta<Resultado<A, B>>>(\n  "/v1/resultado",\n)',
    ];
    for (const amostra of amostras) {
      expect(chamadasComPrefixo(amostra).length, amostra).toBe(1);
    }
    // E o que é legítimo NÃO dispara.
    for (const ok of [
      'api.get("/despesas")',
      'streamSSE("/api/ia/agente/stream", body)',
      'backendPrefixes: ["/api/diagnostico"]',
      'axios.post("/api/auth/refresh")',
      // Genérico sem prefixo no caminho: legítimo.
      'api.get<Resposta<Record<"campo", Item>>>("/itens")',
    ]) {
      expect(chamadasComPrefixo(ok).length, ok).toBe(0);
    }
  });
});
