import axios from "axios";

/** Formas públicas do detail HTTP. Nunca devolve um objeto para renderização. */
export function detailMessage(
  detail: unknown,
  fallback: string,
  { empty = true, objectFallback = false } = {},
): string {
  if (typeof detail === "string") return empty || detail ? detail : fallback;
  if (Array.isArray(detail)) {
    if (objectFallback) return JSON.stringify(detail).slice(0, 200);
    const message = detail
      .map((item) => (typeof item === "string" ? item : item?.msg || ""))
      .filter((item): item is string => typeof item === "string" && !!item)
      .join("; ");
    return empty || message ? message : fallback;
  }
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    for (const key of ["mensagem", "message", "detail"]) {
      if (typeof obj[key] === "string") {
        const message = obj[key] as string;
        return empty || message ? message : fallback;
      }
    }
    if (objectFallback) return JSON.stringify(detail).slice(0, 200);
  }
  return fallback;
}

export function apiDetailMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return detailMessage(detail, fallback);
}

/** Dock/documentos rejeitavam string vazia, mas aceitavam mensagem vazia no objeto. */
export function apiDetailNonemptyMessage(
  error: unknown,
  fallback: string,
): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string" && !detail
    ? fallback
    : detailMessage(detail, fallback);
}

/** Compatibilidade com telas que exibiam objetos de erro de peças/timeline. */
export function legacyDetailMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string" && !detail
    ? fallback
    : detailMessage(detail, fallback, { objectFallback: true });
}

export function caseCreationError(error: unknown, fallback: string): string {
  const response = (
    error as { response?: { status?: number; data?: { detail?: unknown } } }
  )?.response;
  const detail = response?.data?.detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => {
        const loc = Array.isArray(item?.loc) ? item.loc : [];
        const field = loc.length
          ? String(loc[loc.length - 1]).replace(/_/g, " ")
          : null;
        const message = String(item?.msg ?? item);
        return field ? `${field}: ${message}` : message;
      })
      .join("; ");
  }
  if (typeof detail === "string" && detail) return detail;
  if (response?.status === 422 || response?.status === 400)
    return "Algum campo está em formato inválido ou ausente. Revise os campos destacados e tente novamente.";
  return detailMessage(detail, fallback, { empty: false });
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    const responseFallback =
      typeof error.message === "string" && error.message.trim()
        ? error.message
        : fallback;
    return detailMessage(
      typeof detail === "string" && !detail.trim() ? undefined : detail,
      responseFallback,
      { empty: !Array.isArray(detail) },
    );
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}
