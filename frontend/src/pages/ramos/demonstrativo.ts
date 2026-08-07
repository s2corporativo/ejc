// ── Conversão do resultado de uma calculadora em linhas de Demonstrativo ─────
// A Onda 2 reestruturou as respostas: o conteúdo passou a viver dentro de
// objetos e arrays (`marcos[]`, `componentes[]`, `fase_1{}`, `verbas{}`…).
// Achatar em pares label/valor é o que impede a peça de sair vazia — o filtro
// antigo descartava tudo que não fosse escalar de primeiro nível.
import { METADADOS_REGRA } from "../../components/RodapeRegra";

/** Chaves que nunca viram linha: vão para o rodapé da peça. */
const CHAVES_RODAPE = [
  "aviso",
  "aviso_homologacao",
  "homologada",
  "base",
  "observacao",
  "descricao",
  ...METADADOS_REGRA,
];

export type LinhaDemonstrativo = { label: string; valor: string };

function rotular(chave: string): string {
  return chave.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatarValor(v: unknown): string {
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

/**
 * Rótulo de um item de array: usa o campo mais identificador do item
 * (evento/marco/parcela/nome/…); sem ele, cai na numeração. Devolve também a
 * chave consumida, que não vira linha própria (seria redundante com o rótulo).
 */
function rotuloItem(
  item: unknown,
  indice: number,
): { rotulo: string; chaveUsada?: string } {
  if (item && typeof item === "object" && !Array.isArray(item)) {
    const obj = item as Record<string, unknown>;
    for (const chave of [
      "evento",
      "marco",
      "parcela",
      "item",
      "titulo",
      "nome",
      "rotulo",
      "label",
      "descricao",
      "requisito",
      "fase",
      "tipo",
    ]) {
      const v = obj[chave];
      if (typeof v === "string" && v.trim()) {
        return { rotulo: v.trim(), chaveUsada: chave };
      }
    }
  }
  return { rotulo: `${indice + 1}` };
}

/**
 * Achata o resultado em linhas legíveis, com label hierárquico
 * ("Marcos › Plano de recuperação"), preservando a ordem original das chaves.
 */
export function linhasDoResultado(
  data: unknown,
  prefixo = "",
  raiz = true,
  ignorar?: string,
): LinhaDemonstrativo[] {
  if (data === null || data === undefined) return [];
  const compor = (parte: string) => (prefixo ? `${prefixo} › ${parte}` : parte);

  if (Array.isArray(data)) {
    return data.flatMap((item, i) => {
      if (item !== null && typeof item === "object") {
        const { rotulo, chaveUsada } = rotuloItem(item, i);
        return linhasDoResultado(item, compor(rotulo), false, chaveUsada);
      }
      return [{ label: compor(`${i + 1}`), valor: formatarValor(item) }];
    });
  }

  if (typeof data === "object") {
    return Object.entries(data as Record<string, unknown>).flatMap(([k, v]) => {
      // Metadados/avisos só entram no rodapé da peça.
      if (raiz && CHAVES_RODAPE.includes(k)) return [];
      // Chave já usada como rótulo do item — não repetir como linha.
      if (k === ignorar) return [];
      if (v === null || v === undefined) return [];
      if (typeof v === "object") {
        return linhasDoResultado(v, compor(rotular(k)), false);
      }
      return [{ label: compor(rotular(k)), valor: formatarValor(v) }];
    });
  }

  return prefixo ? [{ label: prefixo, valor: formatarValor(data) }] : [];
}

/**
 * Rodapé da peça: fundamentação (fontes, vigência e versão da regra) mais os
 * avisos/observações que a resposta ainda traga. É o que torna o demonstrativo
 * defensável — sem isso a peça salva perde a base normativa mostrada na tela.
 */
export function rodapeDoResultado(data: any): string {
  if (!data || typeof data !== "object") return "";
  const linhas: string[] = [];
  const fontes = Array.isArray(data.fontes)
    ? data.fontes
    : data.fonte
      ? [data.fonte]
      : [];
  const textos = fontes
    .map((f: unknown) => {
      if (typeof f === "string") return f;
      if (f && typeof f === "object") {
        const o = f as Record<string, unknown>;
        for (const v of [o.titulo, o.nome, o.fonte]) {
          if (typeof v === "string" && v) return v;
        }
      }
      return "";
    })
    .filter(Boolean);
  if (textos.length) linhas.push(`Fontes: ${textos.join(" · ")}`);

  const vigencia = data.vigencia_regra ?? data.vigencia_tabela;
  if (vigencia) linhas.push(`Vigência: ${vigencia}`);
  if (data.versao_regra) linhas.push(`Versão da regra: ${data.versao_regra}`);
  if (data.base) linhas.push(`Base: ${data.base}`);
  for (const chave of ["observacao", "descricao", "aviso"]) {
    if (data[chave]) linhas.push(String(data[chave]));
  }
  return linhas.join("\n");
}

export type Proveniencia = {
  fontes: string[];
  vigencia_regra: string;
  versao_regra: string;
};

/**
 * Extrai a proveniência do cálculo (fontes/vigência/versão da regra) que a
 * calculadora já carimba na resposta — a MESMA leitura que `rodapeDoResultado`
 * faz para o texto do rodapé (fonte/fontes no singular ou plural, objeto ou
 * string, vigencia_regra/vigencia_tabela), aqui como campos ESTRUTURADOS.
 *
 * Backend (`POST /pecas/demonstrativo`, Issue #702) passou a exigir
 * `fontes`/`vigencia_regra`/`versao_regra` no corpo da requisição — sem isto,
 * toda chamada do único chamador real (`RamoBase.tsx`) recebia 422 mesmo com
 * a ferramenta homologada e a flag geral ligada (achado do review Codex).
 *
 * `null` quando a resposta não carrega proveniência suficiente — o chamador
 * deve bloquear o envio nesse caso, não tentar mandar campos vazios (o
 * backend já rejeita string/lista em branco).
 */
export function provenienciaDoResultado(data: unknown): Proveniencia | null {
  if (!data || typeof data !== "object") return null;
  const obj = data as Record<string, unknown>;

  const fontesBrutas = Array.isArray(obj.fontes)
    ? obj.fontes
    : obj.fonte
      ? [obj.fonte]
      : [];
  const fontes = fontesBrutas
    .map((f: unknown) => {
      if (typeof f === "string") return f.trim();
      if (f && typeof f === "object") {
        const o = f as Record<string, unknown>;
        for (const v of [o.titulo, o.nome, o.fonte]) {
          if (typeof v === "string" && v.trim()) return v.trim();
        }
      }
      return "";
    })
    .filter((f: string) => f.length > 0);

  const vigenciaBruta = obj.vigencia_regra ?? obj.vigencia_tabela;
  const vigencia_regra =
    typeof vigenciaBruta === "string" ? vigenciaBruta.trim() : "";
  const versao_regra =
    typeof obj.versao_regra === "string" ? obj.versao_regra.trim() : "";

  if (!fontes.length || !vigencia_regra || !versao_regra) return null;
  return { fontes, vigencia_regra, versao_regra };
}
