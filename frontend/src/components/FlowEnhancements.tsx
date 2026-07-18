import { useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import api from "../lib/api";
import CaseCommandDock from "./CaseCommandDock";

const CREATED_CASE_KEY = "ejc_created_case_journey";
const CREATED_CASE_TTL_MS = 60_000;
const CONTEXTUAL_CREATE_ENDPOINTS = new Set([
  "/deadlines/",
  "/deadlines",
  "/tasks/",
  "/tasks",
  "/agenda-eventos/",
  "/agenda-eventos",
]);

interface CreatedCaseMarker {
  id: string;
  at: number;
}

function normalizarEndpoint(url?: string): string {
  if (!url) return "";
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.pathname.replace(/^\/api/, "");
  } catch {
    return url.split("?")[0] || "";
  }
}

export function caseIdSeguro(value: string | null | undefined): string | null {
  const id = String(value || "").trim();
  if (!id || id.length > 64 || !/^[a-zA-Z0-9-]+$/.test(id)) return null;
  return id;
}

export function caseIdCriadoDaResposta(
  response: Pick<AxiosResponse, "config" | "data">,
): string | null {
  const metodo = String(response.config?.method || "get").toLowerCase();
  const endpoint = normalizarEndpoint(response.config?.url);
  if (metodo !== "post" || !["/cases", "/cases/"].includes(endpoint)) {
    return null;
  }
  const data = response.data as { id?: unknown } | null;
  return caseIdSeguro(typeof data?.id === "string" ? data.id : null);
}

export function casoContextualDaUrl(search: string): string | null {
  return caseIdSeguro(new URLSearchParams(search).get("caso"));
}

export function deveInjetarCaso(
  config: Pick<InternalAxiosRequestConfig, "method" | "url" | "data">,
  search: string,
): string | null {
  const metodo = String(config.method || "get").toLowerCase();
  if (metodo !== "post") return null;
  if (!CONTEXTUAL_CREATE_ENDPOINTS.has(normalizarEndpoint(config.url))) return null;
  if (
    !config.data ||
    typeof config.data !== "object" ||
    Array.isArray(config.data) ||
    (typeof FormData !== "undefined" && config.data instanceof FormData) ||
    "case_id" in config.data
  ) {
    return null;
  }
  return casoContextualDaUrl(search);
}

function lerMarcador(): CreatedCaseMarker | null {
  try {
    const raw = sessionStorage.getItem(CREATED_CASE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CreatedCaseMarker>;
    const id = caseIdSeguro(typeof parsed.id === "string" ? parsed.id : null);
    const at = Number(parsed.at);
    if (!id || !Number.isFinite(at) || Date.now() - at > CREATED_CASE_TTL_MS) {
      sessionStorage.removeItem(CREATED_CASE_KEY);
      return null;
    }
    return { id, at };
  } catch {
    sessionStorage.removeItem(CREATED_CASE_KEY);
    return null;
  }
}

function salvarMarcador(id: string) {
  sessionStorage.setItem(
    CREATED_CASE_KEY,
    JSON.stringify({ id, at: Date.now() } satisfies CreatedCaseMarker),
  );
}

/**
 * Extensões transversais de baixo acoplamento:
 * - guarda o caso recém-criado e continua para a Jornada quando o fluxo legado
 *   voltar à lista;
 * - injeta `case_id` em prazo/tarefa/evento criados a partir de `?caso=`;
 * - mostra a central simples do caso na rota exata `/casos/:id`.
 *
 * Nenhuma autorização é decidida aqui: todos os endpoints continuam validando
 * RBAC e ownership no backend.
 */
export default function FlowEnhancements() {
  const location = useLocation();
  const navigate = useNavigate();
  const searchRef = useRef(location.search);

  useEffect(() => {
    searchRef.current = location.search;
  }, [location.search]);

  useEffect(() => {
    const requestInterceptor = api.interceptors.request.use((config) => {
      const caseId = deveInjetarCaso(config, searchRef.current);
      if (caseId) {
        config.data = {
          ...(config.data as Record<string, unknown>),
          case_id: caseId,
        };
      }
      return config;
    });

    const responseInterceptor = api.interceptors.response.use((response) => {
      const caseId = caseIdCriadoDaResposta(response);
      if (caseId) salvarMarcador(caseId);
      return response;
    });

    return () => {
      api.interceptors.request.eject(requestInterceptor);
      api.interceptors.response.eject(responseInterceptor);
    };
  }, []);

  useEffect(() => {
    const marker = lerMarcador();
    if (!marker) return;

    if (location.pathname === "/casos") {
      sessionStorage.removeItem(CREATED_CASE_KEY);
      navigate(`/casos/${marker.id}/jornada`, { replace: true });
      return;
    }

    if (location.pathname.startsWith(`/casos/${marker.id}`)) {
      sessionStorage.removeItem(CREATED_CASE_KEY);
    }
  }, [location.pathname, navigate]);

  const caseId = useMemo(() => {
    const match = location.pathname.match(/^\/casos\/([a-zA-Z0-9-]+)$/);
    return caseIdSeguro(match?.[1]);
  }, [location.pathname]);

  return caseId ? <CaseCommandDock caseId={caseId} /> : null;
}
