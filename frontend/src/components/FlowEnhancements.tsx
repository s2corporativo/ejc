import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { FileUp, X } from "lucide-react";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import api from "../lib/api";
import { toast } from "./Toast";
import { Button, Modal } from "./UI";

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

function detalheErro(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return "Não foi possível anexar o documento ao caso.";
}

/**
 * Extensões de fluxo aplicadas em um único ponto do app:
 * - guarda o caso recém-criado e continua para a Jornada quando o fluxo legado
 *   voltar à lista;
 * - injeta `case_id` em prazo/tarefa/evento criados a partir de `?caso=`;
 * - oferece upload contextual na tela exata do caso.
 *
 * Nenhuma autorização é decidida aqui: todos os endpoints continuam validando
 * RBAC e ownership no backend.
 */
export default function FlowEnhancements() {
  const location = useLocation();
  const navigate = useNavigate();
  const searchRef = useRef(location.search);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState("outro");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    searchRef.current = location.search;
  }, [location.search]);

  useEffect(() => {
    const requestInterceptor = api.interceptors.request.use((config) => {
      const caseId = deveInjetarCaso(config, searchRef.current);
      if (caseId) {
        config.data = { ...(config.data as Record<string, unknown>), case_id: caseId };
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

  useEffect(() => {
    if (!caseId) setUploadOpen(false);
  }, [caseId]);

  const fecharUpload = () => {
    if (enviando) return;
    setUploadOpen(false);
    setArquivo(null);
    setTitulo("");
    setTipo("outro");
  };

  const enviarDocumento = async () => {
    if (!caseId || !arquivo) {
      toast.error("Selecione um documento para anexar ao caso.");
      return;
    }
    setEnviando(true);
    try {
      const body = new FormData();
      body.append("file", arquivo);
      body.append("titulo", titulo.trim() || arquivo.name);
      body.append("tipo", tipo);
      body.append("case_id", caseId);
      await api.post("/documents/upload", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Documento anexado ao caso.");
      fecharUpload();
    } catch (error) {
      toast.error(detalheErro(error));
    } finally {
      setEnviando(false);
    }
  };

  if (!caseId) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setUploadOpen(true)}
        className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-xl bg-primary-700 px-4 py-3 text-sm font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-primary-800 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
        aria-label="Anexar documento ao caso atual"
      >
        <FileUp className="h-4 w-4" />
        Anexar ao caso
      </button>

      <Modal
        open={uploadOpen}
        onClose={fecharUpload}
        title="Anexar documento ao caso"
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Arquivo
            </label>
            <input
              type="file"
              accept=".pdf,.docx,.jpg,.jpeg,.png,.xlsx,.xml"
              className="input w-full"
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null;
                setArquivo(next);
                if (next && !titulo) setTitulo(next.name);
              }}
            />
            <p className="mt-1 text-xs text-slate-500">
              Formatos aceitos: PDF, DOCX, JPG, PNG, XLSX e XML.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Título
            </label>
            <input
              className="input w-full"
              value={titulo}
              maxLength={255}
              onChange={(event) => setTitulo(event.target.value)}
              placeholder="Identificação do documento"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Tipo
            </label>
            <select
              className="input w-full"
              value={tipo}
              onChange={(event) => setTipo(event.target.value)}
            >
              <option value="outro">Outro</option>
              <option value="peticao">Petição</option>
              <option value="decisao">Decisão</option>
              <option value="contrato">Contrato</option>
              <option value="procuracao">Procuração</option>
              <option value="documento_pessoal">Documento pessoal</option>
              <option value="comprovante">Comprovante</option>
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="secondary"
              onClick={fecharUpload}
              disabled={enviando}
              icon={<X className="h-4 w-4" />}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={() => void enviarDocumento()}
              disabled={!arquivo || enviando}
              loading={enviando}
              icon={<FileUp className="h-4 w-4" />}
            >
              Anexar documento
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
