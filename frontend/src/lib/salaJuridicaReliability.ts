import api from "./api";
import { toast } from "../components/Toast";

export const DOCUMENT_SESSION_READY_EVENT =
  "ejc:sala-juridica-document-session-created";

const INSTALL_KEY = Symbol.for("ejc.sala-juridica.reliability-installed");
const WORKSPACE_CACHE_PREFIX = "ejc:sala-juridica:workspace:";

type RequestFn = (...args: any[]) => Promise<any>;
type PatchableApi = typeof api & { [INSTALL_KEY]?: boolean };

function workspaceSessionId(url: unknown): string | null {
  if (typeof url !== "string") return null;
  const match = url.match(/^\/sala-juridica\/([^/]+)$/);
  return match?.[1] ?? null;
}

function workspaceCacheKey(sessionId: string) {
  return `${WORKSPACE_CACHE_PREFIX}${sessionId}`;
}

function cacheWorkspace(sessionId: string, value: string) {
  try {
    sessionStorage.setItem(workspaceCacheKey(sessionId), value);
  } catch {
    // O editor continua funcionando mesmo quando o armazenamento do navegador
    // estiver indisponível (modo privado restritivo, quota, política do device).
  }
}

function cachedWorkspace(sessionId: string): string | null {
  try {
    return sessionStorage.getItem(workspaceCacheKey(sessionId));
  } catch {
    return null;
  }
}

function clearCachedWorkspace(sessionId: string) {
  try {
    sessionStorage.removeItem(workspaceCacheKey(sessionId));
  } catch {
    // Sem ação: o próximo salvamento bem-sucedido continuará sendo a fonte oficial.
  }
}

function delay(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

/**
 * Camada de confiabilidade exclusiva da Sala Jurídica.
 *
 * - conserva localmente o texto do workspace quando o PATCH falha;
 * - reaplica o rascunho local na leitura da sessão, evitando apagar notas;
 * - tenta novamente listagens paginadas antes de declarar falha;
 * - impede que “Carregar mais” altere o limite antes de uma prevalidação de rede;
 * - anuncia a criação de sessão documental para oferecer anexação por gesto real.
 */
export function installSalaJuridicaReliabilityPatches() {
  if (typeof window === "undefined" || typeof document === "undefined") return;

  const patchableApi = api as PatchableApi;
  if (patchableApi[INSTALL_KEY]) return;
  patchableApi[INSTALL_KEY] = true;

  const originalGet = api.get.bind(api) as RequestFn;
  const originalPatch = api.patch.bind(api) as RequestFn;
  const originalPost = api.post.bind(api) as RequestFn;

  (api as unknown as { patch: RequestFn }).patch = async (...args: any[]) => {
    const [url, payload] = args;
    const sessionId = workspaceSessionId(url);
    const workspaceText =
      sessionId && typeof payload?.workspace_texto === "string"
        ? payload.workspace_texto
        : null;

    try {
      const response = await originalPatch(...args);
      if (sessionId && workspaceText !== null) clearCachedWorkspace(sessionId);
      return response;
    } catch (error) {
      if (sessionId && workspaceText !== null) {
        cacheWorkspace(sessionId, workspaceText);
      }
      throw error;
    }
  };

  (api as unknown as { get: RequestFn }).get = async (...args: any[]) => {
    const [url, config] = args;
    const isPaginatedSalaList =
      url === "/sala-juridica" && Number(config?.params?.limit ?? 0) > 50;
    const attempts = isPaginatedSalaList ? 3 : 1;

    let lastError: unknown;
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        const response = await originalGet(...args);
        const sessionId = workspaceSessionId(url);
        const pending = sessionId ? cachedWorkspace(sessionId) : null;
        if (sessionId && pending !== null && response?.data) {
          return {
            ...response,
            data: { ...response.data, workspace_texto: pending },
          };
        }
        return response;
      } catch (error) {
        lastError = error;
        if (attempt < attempts) await delay(250 * attempt);
      }
    }
    throw lastError;
  };

  (api as unknown as { post: RequestFn }).post = async (...args: any[]) => {
    const [url, payload] = args;
    const response = await originalPost(...args);
    if (
      url === "/sala-juridica" &&
      typeof payload?.titulo === "string" &&
      payload.titulo.startsWith("Raio-X documental")
    ) {
      window.dispatchEvent(
        new CustomEvent(DOCUMENT_SESSION_READY_EVENT, {
          detail: { sessionId: response?.data?.id ?? null },
        }),
      );
    }
    return response;
  };

  const bypass = new WeakSet<HTMLButtonElement>();
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      const root = button?.closest("[data-sala-juridica-root]");
      if (
        !button ||
        !root ||
        bypass.has(button) ||
        button.textContent?.trim() !== "Carregar mais"
      ) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const searchValue =
        root.querySelector<HTMLInputElement>(
          'input[placeholder="Pesquisar conversas…"]',
        )?.value ?? "";
      const params: Record<string, string | number> = { limit: 1 };
      if (searchValue.trim()) params.q = searchValue.trim().slice(0, 200);

      void originalGet("/sala-juridica", { params })
        .then(() => {
          bypass.add(button);
          button.click();
          window.setTimeout(() => bypass.delete(button), 0);
        })
        .catch(() => {
          toast.error(
            "Não foi possível carregar mais conversas. O limite foi preservado; tente novamente.",
          );
        });
    },
    true,
  );
}
