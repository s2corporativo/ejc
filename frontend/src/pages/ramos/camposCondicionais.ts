// ── Campos condicionais das calculadoras dos ramos ───────────────────────────
// Várias ferramentas têm campos MUTUAMENTE EXCLUDENTES: o backend aceita apenas
// o campo correspondente à opção escolhida (ex.: /transito/ferramentas/prazos-recurso
// devolve 422 se vier a data de outra fase). `mostrarSe` na config diz quando o
// campo existe; estas funções aplicam a regra na renderização e no envio.
import type { FerramentaCampo } from "./ramosConfig";

type Valores = Record<string, any>;

/** Um campo é visível quando não tem condição ou quando ela está satisfeita. */
export function campoVisivel(campo: FerramentaCampo, vals: Valores): boolean {
  const cond = campo.mostrarSe;
  if (!cond) return true;
  return cond.valores.includes(String(vals[cond.campo] ?? ""));
}

/** Campos que devem ser renderizados para os valores atuais do formulário. */
export function camposVisiveis(
  campos: FerramentaCampo[],
  vals: Valores,
): FerramentaCampo[] {
  return campos.filter((c) => campoVisivel(c, vals));
}

/**
 * Parâmetros que podem ir na querystring: só de campos visíveis e preenchidos.
 * Campos escondidos NUNCA viajam — é o que evita o 422 de campo incompatível.
 */
export function paramsVisiveis(
  campos: FerramentaCampo[],
  vals: Valores,
): Valores {
  const out: Valores = {};
  for (const campo of camposVisiveis(campos, vals)) {
    const v = vals[campo.nome];
    if (v !== undefined && v !== null && v !== "") out[campo.nome] = v;
  }
  return out;
}

/**
 * Chaves de campos que deixaram de ser visíveis e ainda têm valor no estado.
 * Usado para limpar o formulário quando o campo condicionante muda.
 */
export function chavesObsoletas(
  campos: FerramentaCampo[],
  vals: Valores,
): string[] {
  return campos
    .filter((c) => !campoVisivel(c, vals) && vals[c.nome] !== undefined)
    .map((c) => c.nome);
}
