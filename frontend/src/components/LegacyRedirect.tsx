import { Navigate, useLocation } from "react-router";

/**
 * FLX-029 — mescla a URL de origem com o destino de um redirect legado,
 * PRESERVANDO a query string e o hash do usuário. O destino declarado em
 * LEGACY_REDIRECTS pode embutir params próprios (ex.: /atividades?tipo=prazo);
 * em conflito, o param do destino vence e os demais params da URL antiga são
 * mantidos (ex.: /prazos?caso=c1 → /atividades?tipo=prazo&caso=c1).
 * Função pura — testável sem router.
 */
export function mesclarDestinoLegado(
  to: string,
  searchOrigem: string,
  hashOrigem: string,
): string {
  const posHash = to.indexOf("#");
  const hashDestino = posHash >= 0 ? to.slice(posHash) : "";
  const semHash = posHash >= 0 ? to.slice(0, posHash) : to;
  const posQuery = semHash.indexOf("?");
  const pathname = posQuery >= 0 ? semHash.slice(0, posQuery) : semHash;
  const params = new URLSearchParams(
    posQuery >= 0 ? semHash.slice(posQuery + 1) : "",
  );
  // Chaves já embutidas no destino têm precedência sobre as da URL antiga.
  const chavesDestino = new Set(Array.from(params.keys()));
  new URLSearchParams(searchOrigem).forEach((valor, chave) => {
    if (!chavesDestino.has(chave)) params.append(chave, valor);
  });
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}${hashDestino || hashOrigem}`;
}

/**
 * Redirect de rota legada que não descarta a query/hash de quem chegou com
 * uma URL salva (filtros, caso ativo etc.). Usado pelos LEGACY_REDIRECTS
 * estáticos no App.tsx.
 */
export default function LegacyRedirect({ to }: { to: string }) {
  const location = useLocation();
  return (
    <Navigate
      to={mesclarDestinoLegado(to, location.search, location.hash)}
      replace
    />
  );
}
