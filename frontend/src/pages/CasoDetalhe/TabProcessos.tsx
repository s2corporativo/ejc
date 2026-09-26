import React, { useState } from "react";
import { Link } from "react-router";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { mensagemErroHttp } from "../../lib/iaErro";
import { useCarregar } from "../../lib/useCarregar";
import { toast } from "../../components/Toast";
import {
  StatusBadge,
  Modal,
  Empty,
  ErrorState,
  fmtMoney,
} from "../../components/UI";
import { ConsultaProfundaTJMG } from "../../components/Infosimples";

type ProvenienciaProcesso = {
  id: string;
  field_name: string;
  source_type: string;
  source_ref?: string | null;
  captured_at?: string | null;
  confidence?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
};

export default function TabProcessos({ caseId }: { caseId: string }) {
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [arquivo, setArquivo] = useState<"ativos" | "arquivados" | "todos">(
    "ativos",
  );
  const [arqPid, setArqPid] = useState<string | null>(null);
  const [arqMotivo, setArqMotivo] = useState("");
  const [arqSaving, setArqSaving] = useState(false);
  const [provenienciaPid, setProvenienciaPid] = useState<string | null>(null);
  const [provenienciaLoading, setProvenienciaLoading] = useState(false);
  const [proveniencia, setProveniencia] = useState<Record<string, ProvenienciaProcesso[]>>({});
  const vazio = {
    tipo: "judicial",
    numero_cnj: "",
    instancia: "",
    tribunal: "",
    comarca: "",
    vara: "",
    fase: "",
    data_ajuizamento: "",
    valor_causa: "",
  };
  const [form, setForm] = useState<any>(vazio);
  const TIPOS: Record<string, string> = {
    judicial: "Judicial",
    recurso: "Recurso",
    cautelar: "Cautelar",
    execucao: "Execução",
    administrativo: "Administrativo",
    extrajudicial: "Extrajudicial",
  };
  const TIPO_COR: Record<string, string> = {
    judicial: "bg-primary-100 text-primary-700",
    recurso: "bg-ai-100 text-ai-700",
    cautelar: "bg-warn-100 text-warn-700",
    execucao: "bg-danger-100 text-danger-700",
    administrativo: "bg-cyan-100 text-cyan-700",
    extrajudicial: "bg-slate-100 text-slate-600",
  };
  const carga = useCarregar<any[]>(
    () =>
      api
        .get(`/cases/${caseId}/processes`, { params: { arquivo } })
        .then((r) => asList(r.data)),
    [caseId, arquivo],
    { fallbackErro: "Não foi possível carregar os processos do caso." },
  );
  const procs = carga.dados ?? [];
  const carregar = carga.recarregar;

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`/cases/${caseId}/processes`, {
        ...form,
        valor_causa: form.valor_causa ? Number(form.valor_causa) : null,
      });
      setForm(vazio);
      setShowForm(false);
      carregar();
    } catch (err) {
      toast.error(mensagemErroHttp(err, "Falha ao criar processo"));
    } finally {
      setSaving(false);
    }
  };
  const remover = async (pid: string) => {
    if (!confirm("Remover este processo?")) return;
    try {
      await api.delete(`/processes/${pid}`);
      carregar();
    } catch (err) {
      toast.error(mensagemErroHttp(err, "Falha ao remover"));
    }
  };
  const arquivar = (pid: string) => {
    setArqMotivo("");
    setArqPid(pid);
  };
  const confirmarArquivamento = async () => {
    if (!arqPid) return;
    setArqSaving(true);
    try {
      await api.post(`/processes/${arqPid}/arquivar`, {
        motivo: arqMotivo.trim() || undefined,
      });
      toast.success("Processo arquivado.");
      setArqPid(null);
      setArqMotivo("");
      carregar();
    } catch (err) {
      toast.error(mensagemErroHttp(err, "Falha ao arquivar"));
    } finally {
      setArqSaving(false);
    }
  };
  const desarquivar = async (pid: string) => {
    try {
      await api.post(`/processes/${pid}/desarquivar`);
      toast.success("Processo desarquivado.");
      carregar();
    } catch (err) {
      toast.error(mensagemErroHttp(err, "Falha ao desarquivar"));
    }
  };

  const alternarProveniencia = async (pid: string) => {
    if (provenienciaPid === pid) {
      setProvenienciaPid(null);
      return;
    }
    setProvenienciaPid(pid);
    if (proveniencia[pid]) return;
    setProvenienciaLoading(true);
    try {
      const { data } = await api.get(`/processes/${pid}/proveniencia`);
      setProveniencia((atual) => ({
        ...atual,
        [pid]: Array.isArray(data?.data) ? data.data : [],
      }));
    } catch (err) {
      toast.error(mensagemErroHttp(err, "Falha ao carregar a origem dos dados"));
      setProvenienciaPid(null);
    } finally {
      setProvenienciaLoading(false);
    }
  };

  const dataJudHref = (numeroCnj: string) => {
    const params = new URLSearchParams({ numero: numeroCnj, caso: caseId });
    return `/datajud?${params.toString()}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="font-semibold">Processos do caso</h2>
          <p className="text-xs text-gray-400">
            Um caso pode ter múltiplos processos (principal, recurso, cautelar,
            execução) — inclusive em tribunais distintos.
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <div className="flex rounded-lg overflow-hidden bg-slate-900/[0.05] dark:bg-white/[0.07]">
            {[
              ["ativos", "Ativos"],
              ["arquivados", "Arquivados"],
              ["todos", "Todos"],
            ].map(([k, label]) => (
              <button
                key={k}
                onClick={() => setArquivo(k as typeof arquivo)}
                className={`px-3 py-1.5 text-xs font-medium ${arquivo === k ? "bg-navy text-white" : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <ConsultaProfundaTJMG caseId={caseId} />
          <button
            onClick={() => setShowForm(!showForm)}
            className="btn-primary text-sm"
          >
            + Processo
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={salvar} className="card p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <label className="label">Tipo</label>
              <select
                value={form.tipo}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, tipo: e.target.value }))
                }
                className="input w-full"
              >
                {Object.entries(TIPOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Nº CNJ</label>
              <input
                value={form.numero_cnj}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, numero_cnj: e.target.value }))
                }
                className="input w-full"
                placeholder="0000000-00.0000.0.00.0000"
              />
            </div>
            <div>
              <label className="label">Instância</label>
              <input
                value={form.instancia}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, instancia: e.target.value }))
                }
                className="input w-full"
                placeholder="1ª / 2ª / STJ"
              />
            </div>
            <div>
              <label className="label">Fase</label>
              <input
                value={form.fase}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, fase: e.target.value }))
                }
                className="input w-full"
                placeholder="Conhecimento / Recursal"
              />
            </div>
            <div>
              <label className="label">Data de ajuizamento</label>
              <input
                type="date"
                value={form.data_ajuizamento}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, data_ajuizamento: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Tribunal</label>
              <input
                value={form.tribunal}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, tribunal: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Comarca</label>
              <input
                value={form.comarca}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, comarca: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Vara</label>
              <input
                value={form.vara}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, vara: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Valor da causa</label>
              <input
                type="number"
                step="0.01"
                value={form.valor_causa}
                onChange={(e) =>
                  setForm((f: any) => ({ ...f, valor_causa: e.target.value }))
                }
                className="input w-full"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="btn-primary text-sm"
            >
              {saving ? "Salvando…" : "Salvar"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="btn-secondary text-sm"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className="space-y-2">
        {procs.map((p) => (
          <div key={p.id} className="card p-4">
            <div className="flex justify-between items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-full ${TIPO_COR[p.tipo] || "bg-slate-100 text-slate-600"}`}
                  >
                    {TIPOS[p.tipo] || p.tipo}
                  </span>
                  <span className="font-medium text-sm">
                    {p.numero_cnj || "(sem número)"}
                  </span>
                  <StatusBadge value={p.status || "ativo"} />
                  {p.instancia && (
                    <span className="text-xs text-gray-500">
                      · {p.instancia} instância
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600">
                  {[p.tribunal, p.comarca, p.vara]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                  {p.fase ? ` · fase: ${p.fase}` : ""}
                  {p.data_ajuizamento ? ` · ajuizado em: ${p.data_ajuizamento}` : ""}
                </p>
                {p.valor_causa != null && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    Valor da causa: {fmtMoney(p.valor_causa)}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                  {p.numero_cnj && (
                    <Link
                      to={dataJudHref(p.numero_cnj)}
                      className="inline-flex text-xs font-medium text-primary-700 hover:underline"
                    >
                      Consultar no DataJud e sincronizar com este caso
                    </Link>
                  )}
                  <button
                    type="button"
                    onClick={() => void alternarProveniencia(p.id)}
                    className="text-xs font-medium text-slate-600 hover:text-primary-700 hover:underline"
                  >
                    {provenienciaPid === p.id ? "Ocultar origem dos dados" : "Ver origem dos dados"}
                  </button>
                </div>
                {provenienciaPid === p.id && (
                  <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                    {provenienciaLoading && !proveniencia[p.id] ? (
                      <p className="text-xs text-slate-500">Carregando proveniência…</p>
                    ) : (proveniencia[p.id] ?? []).length === 0 ? (
                      <p className="text-xs text-slate-500">
                        Sem registros de proveniência para este processo.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {(proveniencia[p.id] ?? []).map((item) => (
                          <div key={item.id} className="text-xs text-slate-600">
                            <strong className="text-slate-800">
                              {item.field_name.replace(/_/g, " ")}
                            </strong>
                            {" · "}
                            {item.source_type.replace(/_/g, " ")}
                            {item.confidence ? ` · ${item.confidence}` : ""}
                            {item.confirmed_at ? " · confirmado" : ""}
                            {item.captured_at
                              ? ` · ${new Date(item.captured_at).toLocaleString("pt-BR")}`
                              : ""}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {p.status === "arquivado" ? (
                  <button
                    onClick={() => desarquivar(p.id)}
                    className="text-primary-600 hover:text-primary-800 text-xs"
                  >
                    Desarquivar
                  </button>
                ) : (
                  <button
                    onClick={() => arquivar(p.id)}
                    className="text-slate-500 hover:text-slate-800 text-xs"
                  >
                    Arquivar
                  </button>
                )}
                <button
                  onClick={() => remover(p.id)}
                  className="text-red-400 hover:text-red-600 text-xs"
                >
                  Remover
                </button>
              </div>
            </div>
          </div>
        ))}
        {carga.estado === "falhou" && (
          <ErrorState
            title="Não foi possível carregar os processos"
            message={carga.erro ?? undefined}
            onRetry={carga.recarregar}
          />
        )}
        {carga.estado === "vazio" && !showForm && (
          <Empty message="Nenhum processo cadastrado neste caso ainda." />
        )}
      </div>

      <Modal
        open={arqPid !== null}
        onClose={() => setArqPid(null)}
        title="Arquivar processo"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Informe o motivo do arquivamento (opcional). O processo pode ser
            desarquivado depois.
          </p>
          <textarea
            className="input min-h-[90px]"
            value={arqMotivo}
            onChange={(e) => setArqMotivo(e.target.value)}
            placeholder="Motivo do arquivamento (opcional)"
          />
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setArqPid(null)}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={arqSaving}
              onClick={confirmarArquivamento}
            >
              {arqSaving ? "Arquivando..." : "Arquivar"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
