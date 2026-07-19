import { useEffect, useState } from "react";
import api from "./api";
import { AREAS_FALLBACK, type AreaDireito } from "./areaCatalog";

export { AREAS_FALLBACK, areaLabel, type AreaDireito } from "./areaCatalog";

/**
 * Taxonomia canônica de áreas do direito.
 *
 * Fonte oficial em runtime: GET /areas (tabela `areas` do backend, router
 * app/routers/areas.py). O fallback estático abaixo espelha o enum CaseArea
 * completo (app/models/case.py — 25 áreas) e só é usado se a chamada falhar.
 */
// Cache de módulo: a taxonomia não muda durante a sessão; evita refetch por tela.
let cache: AreaDireito[] | null = null;

/** Lista de áreas vinda de GET /areas, com fallback estático completo. */
export function useAreas(): AreaDireito[] {
  const [areas, setAreas] = useState<AreaDireito[]>(cache ?? AREAS_FALLBACK);
  useEffect(() => {
    if (cache) return;
    api
      .get("/areas")
      .then((r) => {
        const lista = (r.data?.areas ?? []) as AreaDireito[];
        if (lista.length > 0) {
          cache = lista;
          setAreas(lista);
        }
      })
      .catch(() => {
        // Mantém o fallback estático; a UI continua funcional offline.
      });
  }, []);
  return areas;
}
