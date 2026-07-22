import api from "./api";

function safePathId(value: string): string {
  try {
    return encodeURIComponent(decodeURIComponent(value));
  } catch {
    return encodeURIComponent(value);
  }
}

/** Retorna a rota canônica ou preserva a URL quando não há contexto seguro. */
export function canonicalCaseWarRoomUrl(url: string, pathname: string): string {
  const visualLaw = url.match(/^\/sala-de-guerra-v3\/visual-law\/([^/?#]+)$/);
  if (visualLaw) {
    return `/cases/${safePathId(visualLaw[1])}/sala-de-guerra/visual-law`;
  }

  if (url === "/sala-de-guerra-v3/war-room/simular") {
    const route = pathname.match(/^\/casos\/([^/]+)\/sala-de-guerra\/?$/);
    if (route) {
      return `/cases/${safePathId(route[1])}/sala-de-guerra/simular-contestacao`;
    }
  }

  return url;
}

/**
 * Ponte transitória para consumidores antigos da página SalaDeGuerra.
 *
 * A fachada canônica vive em /cases/{caseId}/sala-de-guerra/*. Enquanto o
 * componente histórico é decomposto, reescrevemos somente as duas operações
 * contextuais. A Sentinela continua global em /sala-de-guerra-v3 por desenho.
 */
export function installCaseWarRoomCanonicalBridge(): void {
  api.interceptors.request.use((config) => {
    const url = String(config.url || "");
    config.url = canonicalCaseWarRoomUrl(url, window.location.pathname);
    return config;
  });
}
