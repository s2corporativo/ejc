// ── Portal do Cliente: documentos solicitados pelo escritório ──
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle,
  FileText,
  FileUp,
  Paperclip,
  RefreshCw,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";

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
  const [loading, setLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingItemRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/portal/solicitacoes-documentos");
      setRows(asList<Solicitacao>(r.data));
    } catch {
      setRows([]);
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
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center text-slate-400 text-sm">
          Carregando...
        </div>
      ) : rows.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
          <FileText className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">
            Nenhum documento solicitado no momento.
          </p>
        </div>
      ) : (
        rows.map((s) => {
          const [label, cor, bgcor] = ST[s.status] ?? [
            s.status,
            "text-slate-500",
            "bg-slate-50",
          ];
          return (
            <div
              key={s.id}
              className="bg-white rounded-xl border border-slate-200 overflow-hidden"
            >
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
                        <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                          <Paperclip className="w-3 h-3 flex-shrink-0" />
                          <span className="truncate">{it.filename}</span>
                          {it.enviado_em && (
                            <span className="text-slate-400 flex-shrink-0">
                              · {fmtDate(it.enviado_em)}
                            </span>
                          )}
                        </p>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {it.status === "enviado" ? (
                        <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full text-success-600 bg-success-50">
                          <CheckCircle className="w-3.5 h-3.5" /> Enviado
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
    </div>
  );
}
