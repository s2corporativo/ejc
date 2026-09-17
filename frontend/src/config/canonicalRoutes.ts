import { STAFF_ROUTES } from "./moduleRegistry";

/**
 * Rotas canônicas do EJC — DERIVADAS do moduleRegistry (auditoria §2.6 #6).
 *
 * Antes este mapa duplicava os paths do registry à mão e a paridade era
 * garantida por teste. Agora os valores são lookup direto em STAFF_ROUTES:
 * mudar um path no registry atualiza os consumidores daqui automaticamente.
 *
 * Os redirects legados (`LEGACY_CANONICAL_REDIRECTS`) têm definição única no
 * moduleRegistry e são re-exportados aqui por compatibilidade — o fluxo de
 * import é unidirecional (canonicalRoutes → moduleRegistry), sem ciclos.
 */
export {
  LEGACY_CANONICAL_REDIRECTS,
  type LegacyCanonicalRedirect,
} from "./moduleRegistry";

function rotaCanonica(key: string): string {
  const modulo = STAFF_ROUTES.find((route) => route.key === key);
  if (!modulo) {
    throw new Error(`moduleRegistry sem módulo canônico: ${key}`);
  }
  return modulo.path;
}

export const CANONICAL_ROUTES = {
  dashboard: rotaCanonica("dashboard"),
  clientes: rotaCanonica("clientes"),
  casos: rotaCanonica("casos"),
  atividades: rotaCanonica("atividades"),
  documentos: rotaCanonica("documentos"),
  pecas: rotaCanonica("pecas"),
  inteligencia: rotaCanonica("inteligencia"),
  // Chave semântica: o módulo "ramos" é a Área de Atuação canônica
  // (rota /areas-de-atuacao desde a unificação de nomenclatura).
  areasAtuacao: rotaCanonica("ramos"),
  financeiro: rotaCanonica("financeiro"),
  configuracoes: rotaCanonica("configuracoes"),
} as const;
