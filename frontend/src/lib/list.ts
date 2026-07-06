// ── Desempacotamento de listas de API ────────────────────
// Endpoints do EJC devolvem ora um array cru, ora um envelope { items: [] }
// (paginado) ou { data: [] } (portal). Este util normaliza os três formatos
// em `T[]`, com guarda de Array.isArray para nunca quebrar a renderização
// (uma resposta inesperada vira lista vazia, não tela branca).
export function asList<T = unknown>(resp: unknown): T[] {
  if (Array.isArray(resp)) return resp as T[];
  if (resp && typeof resp === "object") {
    const obj = resp as Record<string, unknown>;
    if (Array.isArray(obj.items)) return obj.items as T[];
    if (Array.isArray(obj.data)) return obj.data as T[];
  }
  return [];
}
