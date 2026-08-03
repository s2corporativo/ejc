// Extração canônica da mensagem de erro devolvida pela API.
//
// Antes desta consolidação o mesmo helper existia copiado em 15 arquivos, sob
// três nomes (`detalheErro`, `apiDetail`, `msgErro`) e com coberturas
// diferentes — 7 das cópias tipavam o erro como `any`. Esta versão cobre a
// união dos formatos que o backend realmente devolve em `response.data.detail`:
//
//   - string simples          → HTTPException(detail="mensagem")
//   - objeto com `mensagem`   → HTTPException(detail={"mensagem": ...})
//   - lista (422 do Pydantic) → [{"loc": [...], "msg": "..."}, ...]
//
// Qualquer outro formato cai no `fallback` informado pela tela.
export function detalheErro(erro: unknown, fallback: string): string {
  const detail = (erro as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;

  if (typeof detail === "string") return detail.trim() ? detail : fallback;

  if (Array.isArray(detail)) {
    const mensagens = detail
      .map((item) => {
        if (typeof item === "string") return item;
        const msg = (item as { msg?: unknown })?.msg;
        return typeof msg === "string" ? msg : "";
      })
      .filter(Boolean);
    return mensagens.length ? mensagens.join("; ") : fallback;
  }

  if (detail && typeof detail === "object") {
    const { mensagem, message } = detail as {
      mensagem?: unknown;
      message?: unknown;
    };
    if (typeof mensagem === "string" && mensagem) return mensagem;
    if (typeof message === "string" && message) return message;
  }

  return fallback;
}

/**
 * `response.data` cru. Para quem precisa de sinalização fora do `detail` —
 * `must_change_password` e `precisa_configurar_2fa` no fluxo de sessão.
 */
export function dadosErro(erro: unknown): Record<string, unknown> | undefined {
  const data = (erro as { response?: { data?: unknown } })?.response?.data;
  return data && typeof data === "object"
    ? (data as Record<string, unknown>)
    : undefined;
}

/**
 * `response.data.detail` cru, sem formatar. Só para quem precisa inspecionar a
 * forma do payload (lista de pendências, chave própria); para exibir mensagem,
 * use `detalheErro`.
 */
export function detalheBruto(erro: unknown): unknown {
  return (erro as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
}

/** Código HTTP da resposta que gerou o erro, quando o erro veio do axios. */
export function statusErro(erro: unknown): number | undefined {
  const status = (erro as { response?: { status?: unknown } })?.response
    ?.status;
  return typeof status === "number" ? status : undefined;
}

/** `error.message` com acesso seguro — para erros nativos (fetch/SSE/Error). */
export function mensagemErro(erro: unknown, fallback: string): string {
  const mensagem = (erro as { message?: unknown })?.message;
  return typeof mensagem === "string" && mensagem ? mensagem : fallback;
}

/**
 * Aborto/cancelamento — `AbortController.abort()`, cancelamento do axios e
 * timeout. Não é falha da operação: a tela deve sair em silêncio, sem toast.
 */
export function foiAbortado(erro: unknown): boolean {
  const { name, code } = (erro ?? {}) as { name?: unknown; code?: unknown };
  return (
    name === "AbortError" ||
    name === "CanceledError" ||
    name === "TimeoutError" ||
    code === "ERR_CANCELED"
  );
}
