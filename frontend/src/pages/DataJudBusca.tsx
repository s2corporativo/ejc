import { useState } from "react";
import { useSearchParams } from "react-router";
import {
  Search,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Clock,
  FileText,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader, fmtMoney, fmtDate } from "../components/UI";

interface Movimento {
  data: string;
  descricao: string;
  complemento?: string;
}

interface ProcessoDataJud {
  numero: string;
  tribunal?: string;
  orgao_julgador?: string;
  classe?: string;
  assunto?: string;
  data_distribuicao?: string;
  valor_causa?: number;
  situacao?: string;
  movimentos?: Movimento[];
  partes?: { tipo: string; nome: string }[];
}

function formatCNJ(raw: string) {
  const d = raw.replace(/\D/g, "");
  if (d.length !== 20) return raw;
  return `${d.slice(0, 7)}-${d.slice(7, 9)}.${d.slice(9, 13)}.${d.slice(13, 14)}.${d.slice(14, 16)}.${d.slice(16)}`;
}

export default function DataJudBusca() {
  const [searchParams] = useSearchParams();
  // Deep-link de Caso → Processos: o número chega preenchido, sem inventar
  // endpoint nem disparar consulta externa automaticamente. `caso` habilita a
  // sincronização apenas após o advogado conferir o resultado.
  const numeroInicial = searchParams.get("numero")?.trim() || "";
  const caseIdContexto = searchParams.get("caso")?.trim() || null;
  const [numero, setNumero] = useState(numeroInicial);
  const [loading, setLoading] = useState(false);
  const [processo, setProcesso] = useState<ProcessoDataJud | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  async function buscar() {
    if (!numero.trim()) return;
    setLoading(true);
    setErro(null);
    setProcesso(null);
    setSyncMsg(null);
    try {
      const cnj = formatCNJ(numero.trim());
      const res = await api.get(`/datajud/process/${encodeURIComponent(cnj)}`);
      setProcesso(res.data);
    } catch (e: any) {
      const msg =
        e.response?.data?.detail ?? "Processo não encontrado no DataJud";
      setErro(typeof msg === "string" ? msg : "Processo não encontrado no DataJud");
    } finally {
      setLoading(false);
    }
  }

  async function sincronizar(caseId: string) {
    setSyncingId(caseId);
    setSyncMsg(null);
    try {
      const res = await api.post(`/datajud/cases/${caseId}/sync`);
      setSyncMsg(`Sincronizado: ${res.data.synced} movimentos atualizados`);
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setSyncMsg(
        `Erro: ${typeof detail === "string" ? detail : "Falha na sincronização"}`,
      );
    } finally {
      setSyncingId(null);
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <PageHeader
        title="Consulta DataJud"
        subtitle="Busca de processos pelo número CNJ — API pública do Conselho Nacional de Justiça"
      />

      {caseIdContexto && (
        <div className="rounded-xl border border-primary-100 bg-primary-50 p-3 text-sm text-primary-800">
          Consulta aberta a partir de um Caso. Confira o processo antes de
          sincronizar movimentações com o cadastro interno.
        </div>
      )}

      <div className="card p-5">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          Número do processo (CNJ)
        </label>
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="0000000-00.0000.0.00.0000 ou 20 dígitos"
            className="input flex-1 px-4 py-2.5"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && buscar()}
          />
          <button
            onClick={buscar}
            disabled={loading || !numero.trim()}
            className="btn-primary"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Buscar
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          Ex: 1234567-89.2023.8.26.0000 · Os dados vêm do DataJud CNJ em tempo
          real
        </p>
      </div>

      {erro && (
        <div className="bg-danger-50 border border-danger-200 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-danger-500 flex-shrink-0" />
          <p className="text-sm text-danger-700">{erro}</p>
        </div>
      )}

      {processo && (
        <div className="space-y-4">
          <div className="card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
              <div>
                <h2 className="font-semibold text-slate-800 text-lg">
                  {processo.numero}
                </h2>
                {processo.tribunal && (
                  <p className="text-sm text-slate-500 mt-0.5">
                    {processo.tribunal}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {processo.situacao && (
                  <span className="px-3 py-1 bg-primary-50 text-primary-700 rounded-full text-xs font-medium">
                    {processo.situacao}
                  </span>
                )}
                {caseIdContexto && (
                  <button
                    type="button"
                    className="btn-secondary text-xs"
                    disabled={syncingId === caseIdContexto}
                    onClick={() => void sincronizar(caseIdContexto)}
                  >
                    <RefreshCw
                      className={`w-3.5 h-3.5 ${
                        syncingId === caseIdContexto ? "animate-spin" : ""
                      }`}
                    />
                    {syncingId === caseIdContexto
                      ? "Sincronizando…"
                      : "Sincronizar com este caso"}
                  </button>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
              {[
                { label: "Classe", value: processo.classe },
                { label: "Assunto", value: processo.assunto },
                { label: "Órgão julgador", value: processo.orgao_julgador },
                {
                  label: "Distribuição",
                  value: fmtDate(processo.data_distribuicao),
                },
                {
                  label: "Valor da causa",
                  value: fmtMoney(processo.valor_causa),
                },
              ].map(
                ({ label, value }) =>
                  value && (
                    <div key={label}>
                      <p className="text-xs text-slate-400 uppercase tracking-wide">
                        {label}
                      </p>
                      <p className="text-slate-800 font-medium mt-0.5">
                        {value}
                      </p>
                    </div>
                  ),
              )}
            </div>
          </div>

          {processo.partes && processo.partes.length > 0 && (
            <div className="card p-5">
              <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
                <FileText className="w-4 h-4 text-slate-400" />
                Partes do processo
              </h3>
              <div className="space-y-2">
                {processo.partes.map((p, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 py-1.5 border-b border-slate-50 last:border-0"
                  >
                    <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded capitalize flex-shrink-0">
                      {p.tipo}
                    </span>
                    <span className="text-sm text-slate-800">{p.nome}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {processo.movimentos && processo.movimentos.length > 0 && (
            <div className="card p-5">
              <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
                <Clock className="w-4 h-4 text-slate-400" />
                Movimentações ({processo.movimentos.length})
              </h3>
              <div className="space-y-0 max-h-80 overflow-y-auto">
                {processo.movimentos.slice(0, 30).map((m, i) => (
                  <div
                    key={i}
                    className="flex gap-4 py-2.5 border-b border-slate-50 last:border-0"
                  >
                    <span className="text-xs text-slate-400 flex-shrink-0 w-24 pt-0.5">
                      {fmtDate(m.data)}
                    </span>
                    <div>
                      <p className="text-sm text-slate-800">{m.descricao}</p>
                      {m.complemento && (
                        <p className="text-xs text-slate-400 mt-0.5">
                          {m.complemento}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {syncMsg && (
            <div className="bg-success-50 border border-success-200 rounded-xl p-4 flex items-center gap-3">
              <CheckCircle className="w-4 h-4 text-success-600" />
              <p className="text-sm text-success-700">{syncMsg}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
