import { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, RefreshCw, Search, ShieldAlert } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "./Toast";
import { Empty, ErrorState, Spinner } from "./UI";

interface DocumentoPortal {
  id: string;
  titulo: string;
  filename: string;
  client_id: string;
  case_id?: string | null;
  confidencialidade: string;
  publicado_portal: boolean;
  publicado_em?: string | null;
  created_at?: string | null;
}

interface ClienteMini {
  id: string;
  nome?: string | null;
  razao_social?: string | null;
  email?: string | null;
}

const fmtData = (value?: string | null) =>
  value ? new Date(value).toLocaleString("pt-BR") : "—";

export default function PortalCompartilhamentoDocumentos() {
  const [docs, setDocs] = useState<DocumentoPortal[]>([]);
  const [clientes, setClientes] = useState<Record<string, ClienteMini>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<"todos" | "publicados" | "nao_publicados">(
    "todos",
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [docsResp, clientsResp] = await Promise.all([
        api.get("/portal/admin/documentos", { params: { page_size: 200 } }),
        api.get("/clients/", { params: { page_size: 200 } }),
      ]);
      setDocs(asList<DocumentoPortal>(docsResp.data));
      const lista = asList<ClienteMini>(clientsResp.data);
      setClientes(Object.fromEntries(lista.map((cliente) => [cliente.id, cliente])));
    } catch (e: any) {
      setError(true);
      toast.error(
        e?.response?.data?.detail ||
          "Não foi possível carregar o compartilhamento do Portal.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return docs.filter((doc) => {
      if (filtro === "publicados" && !doc.publicado_portal) return false;
      if (filtro === "nao_publicados" && doc.publicado_portal) return false;
      if (!termo) return true;
      const cliente = clientes[doc.client_id];
      const nome = cliente?.nome || cliente?.razao_social || cliente?.email || "";
      return `${doc.titulo} ${doc.filename} ${nome}`.toLowerCase().includes(termo);
    });
  }, [busca, clientes, docs, filtro]);

  const alterar = async (doc: DocumentoPortal) => {
    const publicar = !doc.publicado_portal;
    if (publicar && doc.confidencialidade !== "normal") {
      toast.error(
        "Somente documento classificado como normal pode ser publicado. Reclassifique conscientemente no GED antes de expor ao cliente.",
      );
      return;
    }
    const verbo = publicar ? "publicar" : "revogar";
    if (
      !confirm(
        publicar
          ? "Publicar este documento no Portal do Cliente? Ele ficará visível ao titular vinculado."
          : "Revogar o acesso deste documento no Portal do Cliente?",
      )
    )
      return;

    setBusy(doc.id);
    try {
      const { data } = await api.post(
        `/portal/admin/documentos/${doc.id}/${verbo}`,
      );
      setDocs((atuais) =>
        atuais.map((item) =>
          item.id === doc.id
            ? {
                ...item,
                publicado_portal: Boolean(data.publicado_portal),
                publicado_em: data.publicado_em ?? null,
              }
            : item,
        ),
      );
      toast.success(data.detail || "Compartilhamento atualizado.");
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || "Não foi possível atualizar o compartilhamento.",
      );
    } finally {
      setBusy(null);
    }
  };

  if (loading && docs.length === 0) return <Spinner />;
  if (error && docs.length === 0)
    return (
      <ErrorState
        message="Não foi possível carregar os documentos publicáveis."
        onRetry={() => void load()}
      />
    );

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-primary-100 bg-primary-50/50 p-4 text-sm text-slate-600">
        <div className="flex items-start gap-3">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-primary-600" />
          <div>
            <div className="font-semibold text-slate-800">
              Publicação externa é uma decisão explícita
            </div>
            <p className="mt-1 text-xs leading-5">
              Classificação de confidencialidade e visibilidade no Portal são
              controles independentes. Apenas documentos <b>normais</b> podem ser
              publicados; a ação fica registrada em auditoria e pode ser revogada.
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            className="input pl-9"
            placeholder="Buscar documento ou cliente..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <select
          className="input sm:w-48"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value as typeof filtro)}
        >
          <option value="todos">Todos</option>
          <option value="publicados">Publicados</option>
          <option value="nao_publicados">Não publicados</option>
        </select>
        <button className="btn-secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </button>
      </div>

      {rows.length === 0 ? (
        <Empty
          titulo="Nenhum documento encontrado"
          descricao="Ajuste o filtro ou vincule documentos a clientes antes de publicar."
        />
      ) : (
        <div className="card overflow-x-auto">
          <table className="table w-full text-sm">
            <thead>
              <tr>
                <th className="text-left">Documento</th>
                <th className="text-left">Cliente</th>
                <th className="text-left">Classificação</th>
                <th className="text-left">Portal</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((doc) => {
                const cliente = clientes[doc.client_id];
                const clienteNome =
                  cliente?.nome || cliente?.razao_social || cliente?.email || "Cliente vinculado";
                const elegivel = doc.confidencialidade === "normal";
                return (
                  <tr key={doc.id}>
                    <td>
                      <div className="font-medium text-slate-800">{doc.titulo}</div>
                      <div className="text-[11px] text-slate-400">{doc.filename}</div>
                    </td>
                    <td className="text-slate-600">{clienteNome}</td>
                    <td>
                      <span
                        className={`badge ${elegivel ? "badge-success" : "badge-neutral"}`}
                      >
                        {doc.confidencialidade}
                      </span>
                    </td>
                    <td>
                      {doc.publicado_portal ? (
                        <div>
                          <span className="inline-flex items-center gap-1 text-xs font-semibold text-success-700">
                            <Eye className="h-3.5 w-3.5" /> Publicado
                          </span>
                          <div className="text-[10px] text-slate-400">
                            {fmtData(doc.publicado_em)}
                          </div>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                          <EyeOff className="h-3.5 w-3.5" /> Interno
                        </span>
                      )}
                    </td>
                    <td className="text-right">
                      <button
                        className={doc.publicado_portal ? "btn-secondary text-xs" : "btn-primary text-xs"}
                        disabled={busy === doc.id || (!doc.publicado_portal && !elegivel)}
                        title={!elegivel && !doc.publicado_portal ? "Reclassifique como normal antes de publicar" : undefined}
                        onClick={() => void alterar(doc)}
                      >
                        {doc.publicado_portal ? (
                          <><EyeOff className="h-3.5 w-3.5" /> Revogar</>
                        ) : (
                          <><Eye className="h-3.5 w-3.5" /> Publicar</>
                        )}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
