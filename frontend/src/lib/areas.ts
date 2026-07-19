import { useEffect, useState } from "react";
import api from "./api";

/**
 * Taxonomia canônica de áreas do direito.
 *
 * Fonte oficial em runtime: GET /areas (tabela `areas` do backend, router
 * app/routers/areas.py). O fallback estático abaixo espelha o enum CaseArea
 * completo (app/models/case.py — 25 áreas) e só é usado se a chamada falhar.
 */
export type AreaDireito = { slug: string; nome: string; ordem?: number };

export const AREAS_FALLBACK: AreaDireito[] = [
  { slug: "civil", nome: "Cível" },
  { slug: "trabalhista", nome: "Trabalhista" },
  { slug: "consumidor", nome: "Consumidor" },
  { slug: "familia", nome: "Família" },
  { slug: "ambiental", nome: "Ambiental" },
  { slug: "criminal", nome: "Criminal" },
  { slug: "previdenciario", nome: "Previdenciário" },
  { slug: "empresarial", nome: "Empresarial" },
  { slug: "tributario", nome: "Tributário" },
  { slug: "administrativo", nome: "Administrativo" },
  { slug: "bancario", nome: "Bancário" },
  { slug: "imobiliario", nome: "Imobiliário" },
  { slug: "sucessoes", nome: "Sucessões" },
  { slug: "constitucional", nome: "Constitucional" },
  { slug: "digital_lgpd", nome: "Digital e LGPD" },
  { slug: "transito", nome: "Trânsito" },
  { slug: "saude", nome: "Saúde" },
  { slug: "medico", nome: "Médico" },
  { slug: "agrario", nome: "Agrário" },
  { slug: "agronegocio", nome: "Agronegócio" },
  { slug: "eleitoral", nome: "Eleitoral" },
  { slug: "internacional", nome: "Internacional" },
  { slug: "contratual", nome: "Contratual" },
  { slug: "societario", nome: "Societário" },
  { slug: "licitacoes", nome: "Licitações" },
];

const LABELS: Record<string, string> = Object.fromEntries(
  AREAS_FALLBACK.map((a) => [a.slug, a.nome]),
);

/** Rótulo PT-BR de um slug de área; devolve o próprio slug se desconhecido. */
export function areaLabel(slug?: string | null): string {
  if (!slug) return "";
  return LABELS[slug] ?? slug;
}

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
