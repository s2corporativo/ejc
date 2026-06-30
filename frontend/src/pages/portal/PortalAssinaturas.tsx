import { useEffect, useState } from "react";
import {
  PenLine,
  CheckCircle2,
  ShieldCheck,
  Clock,
  FileText,
  X,
} from "lucide-react";
import api from "../../lib/api";

export default function PortalAssinaturas() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [comprovante, setComprovante] = useState<any>(null);
  const [signing, setSigning] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api
      .get("/signatures/")
      .then((r) => setRows(r.data?.data ?? r.data ?? []))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  const assinar = async (id: string) => {
    if (
      !confirm(
        "Ao confirmar, você declara que LEU e CONCORDA com o documento.\n" +
          "Serão registrados: identificação, data/hora, IP e hash do arquivo.",
      )
    )
      return;
    setSigning(id);
    try {
      const { data } = await api.post(`/signatures/${id}/assinar`);
      setComprovante(data.comprovante);
      load();
    } finally {
      setSigning(null);
    }
  };

  const pendentes = rows.filter((r) => r.status === "pendente");
  const assinados = rows.filter((r) => r.status !== "pendente");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Assinaturas</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {pendentes.length > 0
            ? `${pendentes.length} documento${pendentes.length > 1 ? "s" : ""} aguardando sua assinatura`
            : "Todos os documentos foram assinados"}
        </p>
      </div>

      {/* Comprovante */}
      {comprovante && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-emerald-700">
              Documento assinado com sucesso!
            </p>
            <p className="text-xs text-emerald-600 mt-0.5 font-mono break-all">
              Hash: {comprovante.hash_documento}
            </p>
            <p className="text-xs text-emerald-500 mt-1">
              Registrado em {new Date().toLocaleString("pt-BR")}
            </p>
          </div>
          <button
            onClick={() => setComprovante(null)}
            className="text-emerald-400 hover:text-emerald-600"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Pendentes */}
      {pendentes.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <Clock className="w-4 h-4 text-amber-500" />
            <h2 className="font-semibold text-slate-700">
              Pendentes ({pendentes.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {pendentes.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex items-center justify-between gap-4"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-8 h-8 bg-amber-50 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                    <FileText className="w-4 h-4 text-amber-500" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {s.documento}
                    </p>
                    {s.descricao && (
                      <p className="text-xs text-slate-400 mt-0.5">
                        {s.descricao}
                      </p>
                    )}
                    <p className="text-xs text-slate-300 font-mono mt-0.5">
                      #{s.hash?.slice(0, 16)}…
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => assinar(s.id)}
                  disabled={signing === s.id}
                  className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 flex-shrink-0"
                >
                  <PenLine className="w-3.5 h-3.5" />
                  {signing === s.id ? "Assinando…" : "Assinar"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Assinados */}
      {assinados.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <h2 className="font-semibold text-slate-700">
              Assinados ({assinados.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100">
            {assinados.map((s) => (
              <div
                key={s.id}
                className="px-5 py-4 flex items-center justify-between gap-4"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-8 h-8 bg-emerald-50 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {s.documento}
                    </p>
                    {s.assinado_em && (
                      <p className="text-xs text-slate-400 mt-0.5">
                        Assinado em{" "}
                        {new Date(s.assinado_em).toLocaleString("pt-BR")}
                      </p>
                    )}
                  </div>
                </div>
                <span className="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-1 rounded-full flex-shrink-0">
                  Concluído
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && rows.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <PenLine className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p className="text-slate-400 text-sm">
            Nenhum documento para assinar
          </p>
        </div>
      )}

      <p className="text-xs text-slate-400">
        Assinatura eletrônica nos termos da MP 2.200-2/2001, art. 10, §2º.
        Registramos identificação autenticada, hash SHA-256, IP e data/hora.
      </p>
    </div>
  );
}
