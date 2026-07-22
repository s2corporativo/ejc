import api from "./api";

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

    const visualLaw = url.match(/^\/sala-de-guerra-v3\/visual-law\/([^/?#]+)$/);
    if (visualLaw) {
      config.url = `/cases/${encodeURIComponent(decodeURIComponent(visualLaw[1]))}/sala-de-guerra/visual-law`;
      return config;
    }

    if (url === "/sala-de-guerra-v3/war-room/simular") {
      const route = window.location.pathname.match(
        /^\/casos\/([^/]+)\/sala-de-guerra\/?$/,
      );
      if (route) {
        config.url = `/cases/${encodeURIComponent(decodeURIComponent(route[1]))}/sala-de-guerra/simular-contestacao`;
      }
    }

    return config;
  });
}
