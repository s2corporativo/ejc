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
