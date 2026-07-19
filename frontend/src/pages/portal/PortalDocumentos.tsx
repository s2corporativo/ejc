// ── Portal do Cliente: documentos solicitados pelo escritório ──
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle,
  FileText,
  FileUp,
  FolderOpen,
  Paperclip,
  RefreshCw,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { EmptyState, ErrorState, Spinner } from "../../components/UI";

interface ItemSolicitado {
  id: string;
  nome: string;
  descricao?: string | null;
  status: "pendente" | "enviado";
  enviado_em?: string | null;
  filename?: string | null;
}

interface Solicitacao {
  id: string;
  case_id: string;
  caso_titulo: string;
  numero_interno?: string | null;
  mensagem?: string | null;
  created_at: string;
  status: "pendente" | "parcial" | "atendida";
  itens: ItemSolicitado[];
}

interface DocMeu {
  id: string;
  titulo: string;
  filename?: string | null;
  created_at?: string | null;
}

const ST: Record<string, [string, string, string]> = {
  pendente: ["Pendente", "text-warn-600", "bg-warn-50"],
  parcial: ["Parcialmente atendida", "text-primary-600", "bg-primary-50"],
  atendida: ["Atendida", "text-success-600", "bg-success-50"],
};

function fmtDate(d?: string | null) {
  if (!d) return "";
  return new Date(d).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export default function PortalDocumentos() {
  const [rows, setRows] = useState<Solicitacao[]>([]);
  const [meusDocs, setMeusDocs] = useState<DocMeu[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingItemRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [sol, docs] = await Promise.allSettled([
        api.get("/portal/solicitacoes-documentos"),
        api.get("/portal/documentos"),
      ]);
      if (sol.status === "fulfilled")
        setRows(asList<Solicitacao>(sol.value.data));
      else throw sol.reason;
      if (docs.status === "fulfilled")
        setMeusDocs(asList<DocMeu>(docs.value.data));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pickFile = (itemId: string) => {
    pendingItemRef.current = itemId;
    inputRef.current?.click();
  };

  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const itemId = pendingItemRef.current;
    e.target.value = "";
    pendingItemRef.current = null;
    if (!file || !itemId) return;

    setUploadingId(itemId);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.post(
        `/portal/solicitacoes-documentos/itens/${itemId}/upload`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      toast.success("Documento enviado com sucesso.");
      await load();
    } catch (err: any) {
      toast.error(
        err.response?.data?.detail ||
          "Não foi possível enviar o documento. Tente novamente.",
      );
    } finally {
      setUploadingId(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">
          Documentos solicitados
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Documentos que o escritório solicitou para os seus processos
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={onFileChosen}
      />

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar os documentos solicitados."
          onRetry={load}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Nenhum documento pendente"
          message="Você está em dia — quando o escritório solicitar um documento para os seus processos, ele aparecerá aqui."
        />
      ) : (
        rows.map((s) => {
          const [label, cor, bgcor] = ST[s.status] ?? [
            s.status,
            "text-slate-500",
            "bg-slate-50",
          ];
          return (
            <div key={s.id} className="card overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">
                      {s.caso_titulo}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {s.numero_interno ? `${s.numero_interno} · ` : ""}
                      Solicitado em {fmtDate(s.created_at)}
                    </p>
                  </div>
                  <span
                    className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${cor} ${bgcor}`}
                  >
                    {label}
                  </span>
                </div>
                {s.mensagem && (
                  <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                    {s.mensagem}
                  </p>
                )}
              </div>

              <div className="divide-y divide-slate-100">
                {s.itens.map((it) => (
                  <div
                    key={it.id}
                    className="px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800">
                        {it.nome}
                      </p>
                      {it.descricao && (
                        <p className="text-xs text-slate-400 mt-0.5">
                          {it.descricao}
                        </p>
                      )}
                      {it.status === "enviado" && (
                        <>
                          <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                            <Paperclip className="w-3 h-3 flex-shrink-0" />
                            <span className="truncate">{it.filename}</span>
                            {it.enviado_em && (
                              <span className="text-slate-400 flex-shrink-0">
                                · enviado em {fmtDate(it.enviado_em)}
                              </span>
                            )}
                          </p>
                          <p className="text-[11px] text-slate-400 mt-1">
                            Precisa substituir este arquivo? Avise o escritório
                            pelas{" "}
                            <Link
                              to="/portal/mensagens"
                              className="text-primary-600 hover:underline"
                            >
                              Mensagens
                            </Link>
                            .
                          </p>
                        </>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {it.status === "enviado" ? (
                        <span
                          className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full text-success-600 bg-success-50"
                          title="O arquivo foi recebido e o advogado responsável já foi avisado."
                        >
                          <CheckCircle className="w-3.5 h-3.5" /> Recebido pelo
                          escritório
                        </span>
                      ) : (
                        <button
                          onClick={() => pickFile(it.id)}
                          disabled={uploadingId !== null}
                          className="btn-primary inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm disabled:opacity-60"
                        >
                          {uploadingId === it.id ? (
                            <>
                              <RefreshCw className="w-4 h-4 animate-spin" />
                              Enviando...
                            </>
                          ) : (
                            <>
                              <FileUp className="w-4 h-4" /> Enviar documento
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}

      {/* Documentos do cliente já arquivados no escritório (GED) — inclui os
          enviados pelo portal, confirmando o recebimento/arquivamento. */}
      {!loading && !error && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-slate-400" />
            <h2 className="font-semibold text-slate-700">
              Meus documentos no escritório
            </h2>
          </div>
          {meusDocs.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-400">
              Nenhum documento arquivado ainda. Os documentos que você enviar
              (ou que o escritório liberar) aparecerão aqui.
            </p>
          ) : (
            <div className="divide-y divide-slate-100">
              {meusDocs.map((d) => (
                <div
                  key={d.id}
                  className="px-5 py-3 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0 flex items-center gap-3">
                    <FileText className="w-4 h-4 text-slate-300 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">
                        {d.titulo}
                      </p>
                      {d.filename && (
                        <p className="text-xs text-slate-400 truncate">
                          {d.filename}
                        </p>
                      )}
                    </div>
                  </div>
                  {d.created_at && (
                    <span className="text-xs text-slate-400 flex-shrink-0">
                      Arquivado em {fmtDate(d.created_at)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
