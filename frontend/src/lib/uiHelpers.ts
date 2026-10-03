export function rotulo(v: string): string {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function nomeCliente(c: {
  nome?: string | null;
  razao_social?: string | null;
  cnpj?: string | null;
  cpf?: string | null;
  id: string;
}): string {
  return c.nome || c.razao_social || c.cnpj || c.cpf || c.id;
}

/** Mantém todos os parâmetros de contexto ao trocar uma aba. */
export function paramsDaAba(
  searchParams: URLSearchParams,
  tab: string,
): URLSearchParams {
  const params = new URLSearchParams(searchParams);
  params.set("tab", tab);
  return params;
}
