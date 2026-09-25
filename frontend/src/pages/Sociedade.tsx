import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router";
import { toast } from "../components/Toast";
import {
  Building2,
  Plus,
  TrendingUp,
  Users,
  RefreshCw,
  CheckCircle,
  Clock,
  XCircle,
  Receipt,
} from "lucide-react";
import api from "../lib/api";
import ExtratoSocio from "../components/ExtratoSocio";
import { Empty, Spinner } from "../components/UI";
import { asList } from "../lib/list";

const fmtMoney = (v?: number | null) =>
  (Number.isFinite(v) ? (v as number) : 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });

const fmtPct = (v?: number | null) =>
  Number.isFinite(v) ? `${((v as number) * 100).toFixed(1)}%` : "—";

export type SocietyTab = "socios" | "distribuicao" | "saques";

export function isSocietyTab(value: string | null): value is SocietyTab {
  return ["socios", "distribuicao", "saques"].includes(value ?? "");
}

interface Socio {
  id: string;
  user_id: string;
  participacao_percentual: number;
  resultado_percentual?: number | null;
  regime: string;
  pro_labore?: number;
  ativo: boolean;
  data_entrada?: string;
  oab_numero?: string;
  oab_uf?: string;
}

interface Distribuicao {
  id: string;
  mes_referencia: string;
  valor_total: number;
  created_at: string;
  observacoes?: string;
}

interface Withdrawal {
  id: string;
  partner_id: string;
  gross_value: number;
  net_value: number;
  case_expenses: number;
  partner_share: number;
  description?: string;
  period_reference?: string;
  status: string;
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  pendente: "bg-warn-50 text-warn-700",
  aprovado: "bg-success-50 text-success-700",
  rejeitado: "bg-danger-50 text-danger-600",
  pago: "bg-primary-50 text-primary-700",
};
const STATUS_LABEL: Record<string, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
  pago: "Pago",
};

export default function Sociedade() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("sub");
  const tab: SocietyTab = isSocietyTab(rawTab) ? rawTab : "socios";
  const setTab = (next: SocietyTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("sub", next);
    setSearchParams(params, { replace: true });
  };

  const [socios, setSocios] = useState<Socio[]>([]);
  const [totalPart, setTotalPart] = useState(0);
  const [distrib, setDistrib] = useState<Distribuicao[]>([]);
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [showFormSocio, setShowFormSocio] = useState(false);
  const [showFormDist, setShowFormDist] = useState(false);
  const [showFormSaque, setShowFormSaque] = useState(false);
  const [savingSaque, setSavingSaque] = useState(false);
  const [novoSocio, setNovoSocio] = useState({
    user_id: "",
    pct: "",
    data_entrada: "",
  });
  const [novaDist, setNovaDist] = useState({
    mes_referencia: "",
    valor_total: "",
  });
  const [novoSaque, setNovoSaque] = useState({
    gross_value: "",
    case_expenses: "0",
    description: "",
    period_reference: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, d, u, w] = await Promise.allSettled([
        api.get("/sociedade/socios"),
        api.get("/sociedade/distribuicao"),
        api.get("/users/?page_size=50"),
        api.get("/partner-withdrawals?page_size=50"),
      ]);
      if (s.status === "fulfilled") {
        setSocios(s.value.data?.socios ?? []);
        setTotalPart(s.value.data?.total_participacao ?? 0);
      } else setErro("Acesso restrito a sócios.");
      if (d.status === "fulfilled")
        setDistrib(asList<Distribuicao>(d.value.data));
      if (u.status === "fulfilled") setUsers(asList(u.value.data));
      if (w.status === "fulfilled")
        setWithdrawals(asList<Withdrawal>(w.value.data));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const nomeUser = (id: string) =>
    users.find((u) => u.id === id)?.full_name || id?.slice(0, 8) || "—";

  const addSocio = async (e: React.FormEvent) => {
    e.preventDefault();
    const pct = parseFloat(novoSocio.pct);
    if (!novoSocio.user_id || !(pct > 0 && pct <= 100)) {
      toast.error("Selecione o sócio e percentual válido.");
      return;
    }
    try {
      await api.post("/sociedade/socios", {
        user_id: novoSocio.user_id,
        participacao_percentual: pct / 100,
        data_entrada:
          novoSocio.data_entrada || new Date().toISOString().slice(0, 10),
      });
      setNovoSocio({ user_id: "", pct: "", data_entrada: "" });
      setShowFormSocio(false);
      load();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao cadastrar sócio");
    }
  };

  const addDist = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = parseFloat(novaDist.valor_total);
    if (!(v > 0) || !novaDist.mes_referencia) {
      toast.error("Informe mês e valor.");
      return;
    }
    try {
      await api.post("/sociedade/distribuicao", {
        mes_referencia: novaDist.mes_referencia,
        valor_total: v,
      });
      setNovaDist({ mes_referencia: "", valor_total: "" });
      setShowFormDist(false);
      load();
    } catch (err: any) {
      toast.error(
        err.response?.data?.detail || "Falha ao registrar distribuição",
      );
    }
  };

  const addSaque = async (e: React.FormEvent) => {
    e.preventDefault();
    const gross = parseFloat(novoSaque.gross_value);
    if (!(gross > 0)) {
      toast.error("Informe o valor bruto.");
      return;
    }
    if (savingSaque) return;
    setSavingSaque(true);
    try {
      await api.post("/partner-withdrawals", {
        gross_value: gross,
        case_expenses: parseFloat(novoSaque.case_expenses) || 0,
        description: novoSaque.description || undefined,
        period_reference: novoSaque.period_reference || undefined,
      });
      setNovoSaque({
        gross_value: "",
        case_expenses: "0",
        description: "",
        period_reference: "",
      });
      setShowFormSaque(false);
      load();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao registrar saque");
    } finally {
      setSavingSaque(false);
    }
  };

  const approveWithdrawal = async (
    id: string,
    action: "approve" | "reject",
  ) => {
    try {
      await api.patch(`/partner-withdrawals/${id}/${action}`);
      load();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha");
    }
  };

  const totalDistrib = distrib.reduce((a, d) => a + (d.valor_total ?? 0), 0);
  const totalSaquesPagos = withdrawals
    .filter((w) => w.status === "pago")
    .reduce((a, w) => a + (w.net_value ?? 0), 0);
  const totalSaquesPendentes = withdrawals
    .filter((w) => w.status === "pendente")
    .reduce((a, w) => a + (w.gross_value ?? 0), 0);

  if (loading) return <Spinner />;
  if (erro)
    return (
      <div className="p-6 max-w-xl mx-auto text-center">
        <Building2 className="w-12 h-12 mx-auto mb-3 text-slate-300" />
        <p className="text-slate-500">{erro}</p>
      </div>
    );

  return (
    <div className="space-y-6">
      {/* Cabeçalho fica no FinanceiroWorkspace; aqui apenas as ações da aba. */}
      <div className="flex items-center justify-end">
        <button
          onClick={load}
          className="btn-secondary p-2"
          aria-label="Atualizar"
        >
          <RefreshCw
            className={`w-4 h-4 text-slate-400 ${loading ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-primary-50 rounded-lg">
            <Users className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              Sócios ativos
            </p>
            <p className="text-xl font-bold text-slate-800">
              {socios.filter((s) => s.ativo).length}
            </p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-success-50 rounded-lg">
            <TrendingUp className="w-5 h-5 text-success-600" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              Distribuído total
            </p>
            <p className="text-xl font-bold text-slate-800">
              {fmtMoney(totalDistrib)}
            </p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-slate-100 rounded-lg">
            <Receipt className="w-5 h-5 text-slate-500" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              Saques pagos
            </p>
            <p className="text-xl font-bold text-slate-800">
              {fmtMoney(totalSaquesPagos)}
            </p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="p-2.5 bg-warn-50 rounded-lg">
            <Clock className="w-5 h-5 text-warn-600" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              Saques pendentes
            </p>
            <p className="text-xl font-bold text-slate-800">
              {fmtMoney(totalSaquesPendentes)}
            </p>
          </div>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {(["socios", "distribuicao", "saques"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-primary-600 text-primary-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t === "socios"
              ? "Sócios"
              : t === "distribuicao"
                ? "Distribuição de Lucros"
                : "Saques"}
          </button>
        ))}
      </div>

      {tab === "socios" && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold text-slate-800">
                Quadro Societário
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Participação total:{" "}
                <span
                  className={
                    totalPart > 1.0001
                      ? "text-danger-600 font-semibold"
                      : "text-slate-600 font-semibold"
                  }
                >
                  {fmtPct(totalPart)}
                </span>
              </p>
            </div>
            <button
              onClick={() => setShowFormSocio((v) => !v)}
              className="btn-primary text-sm px-3 py-1.5"
            >
              <Plus className="w-4 h-4" /> Novo sócio
            </button>
          </div>

          {showFormSocio && (
            <form
              onSubmit={addSocio}
              className="mb-4 p-4 bg-slate-50 rounded-lg grid grid-cols-3 gap-3"
            >
              <div className="col-span-3 sm:col-span-1">
                <label className="block text-xs text-slate-500 mb-1">
                  Usuário
                </label>
                <select
                  className="input"
                  value={novoSocio.user_id}
                  onChange={(e) =>
                    setNovoSocio({ ...novoSocio, user_id: e.target.value })
                  }
                >
                  <option value="">Selecione…</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Participação (%)
                </label>
                <input
                  type="number"
                  min="0.01"
                  max="100"
                  step="0.01"
                  className="input"
                  value={novoSocio.pct}
                  onChange={(e) =>
                    setNovoSocio({ ...novoSocio, pct: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Data de entrada
                </label>
                <input
                  type="date"
                  className="input"
                  value={novoSocio.data_entrada}
                  onChange={(e) =>
                    setNovoSocio({ ...novoSocio, data_entrada: e.target.value })
                  }
                />
              </div>
              <div className="col-span-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowFormSocio(false)}
                  className="btn-ghost text-sm px-3 py-1.5"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="btn-primary text-sm px-4 py-1.5"
                >
                  Salvar
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            {socios.length === 0 ? (
              <Empty message="Nenhum sócio cadastrado." />
            ) : (
              socios.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center gap-4 p-3 rounded-lg border border-slate-100 hover:bg-slate-50"
                >
                  <div className="w-10 h-10 bg-primary-50 rounded-full flex items-center justify-center flex-shrink-0">
                    <Users className="w-5 h-5 text-primary-500" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-slate-800">
                      {nomeUser(s.user_id)}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Regime: {s.regime} · Desde:{" "}
                      {s.data_entrada?.slice(0, 10) ?? "—"}
                      {s.oab_numero && ` · OAB ${s.oab_numero}/${s.oab_uf}`}
                    </p>
                  </div>
                  {s.pro_labore && (
                    <div className="text-right">
                      <p className="text-xs text-slate-400">Pró-labore</p>
                      <p className="text-sm font-medium text-slate-700">
                        {fmtMoney(s.pro_labore)}
                      </p>
                    </div>
                  )}
                  <div className="text-right w-20">
                    <p className="text-xs text-slate-400">Capital</p>
                    <p className="text-lg font-bold text-primary-600">
                      {fmtPct(s.participacao_percentual)}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      Resultado {fmtPct(s.resultado_percentual ?? s.participacao_percentual)}
                    </p>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${s.ativo ? "bg-success-50 text-success-700" : "bg-slate-100 text-slate-400"}`}
                  >
                    {s.ativo ? "Ativo" : "Inativo"}
                  </span>
                  <ExtratoSocio
                    userId={s.user_id}
                    nome={nomeUser(s.user_id)}
                    isSocio
                  />
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {tab === "distribuicao" && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">
              Distribuição de Lucros
            </h2>
            <button
              onClick={() => setShowFormDist((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700"
            >
              <Plus className="w-4 h-4" /> Registrar distribuição
            </button>
          </div>

          {showFormDist && (
            <form
              onSubmit={addDist}
              className="mb-4 p-4 bg-slate-50 rounded-lg flex gap-3 flex-wrap"
            >
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Mês de referência
                </label>
                <input
                  type="month"
                  className="input w-auto"
                  value={novaDist.mes_referencia}
                  onChange={(e) =>
                    setNovaDist({ ...novaDist, mes_referencia: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Valor total (R$)
                </label>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  placeholder="0,00"
                  className="input w-44"
                  value={novaDist.valor_total}
                  onChange={(e) =>
                    setNovaDist({ ...novaDist, valor_total: e.target.value })
                  }
                />
              </div>
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowFormDist(false)}
                  className="btn-ghost text-sm px-3 py-2"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700"
                >
                  Salvar
                </button>
              </div>
            </form>
          )}

          <div className="space-y-3">
            {distrib.length === 0 ? (
              <Empty message="Nenhuma distribuição registrada." />
            ) : (
              distrib.map((d) => {
                const quota = socios
                  .filter((s) => s.ativo)
                  .map((s) => ({
                    nome: nomeUser(s.user_id),
                    valor: d.valor_total * (s.resultado_percentual ?? s.participacao_percentual),
                    pct: s.resultado_percentual ?? s.participacao_percentual,
                  }));
                return (
                  <div
                    key={d.id}
                    className="border border-slate-100 rounded-xl p-4"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="font-semibold text-slate-800">
                          {d.mes_referencia}
                        </p>
                        <p className="text-xs text-slate-400">
                          {new Date(d.created_at).toLocaleDateString("pt-BR")}
                        </p>
                      </div>
                      <p className="text-lg font-bold text-success-600">
                        {fmtMoney(d.valor_total)}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {quota.map((q) => (
                        <div
                          key={q.nome}
                          className="bg-slate-50 rounded-lg p-2.5"
                        >
                          <p className="text-xs text-slate-500">{q.nome}</p>
                          <p className="text-sm font-semibold text-slate-800">
                            {fmtMoney(q.valor)}
                          </p>
                          <p className="text-[10px] text-slate-400">
                            {fmtPct(q.pct)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {tab === "saques" && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">Saques de Sócios</h2>
            <button
              onClick={() => setShowFormSaque((v) => !v)}
              className="btn-primary text-sm px-3 py-1.5"
            >
              <Plus className="w-4 h-4" /> Solicitar saque
            </button>
          </div>

          {showFormSaque && (
            <form
              onSubmit={addSaque}
              className="mb-4 p-4 bg-slate-50 rounded-lg grid grid-cols-2 gap-3"
            >
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Valor bruto (R$)
                </label>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  placeholder="0,00"
                  className="input"
                  value={novoSaque.gross_value}
                  onChange={(e) =>
                    setNovoSaque({ ...novoSaque, gross_value: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Despesas do caso (R$)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0,00"
                  className="input"
                  value={novoSaque.case_expenses}
                  onChange={(e) =>
                    setNovoSaque({
                      ...novoSaque,
                      case_expenses: e.target.value,
                    })
                  }
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Período de referência
                </label>
                <input
                  type="month"
                  className="input"
                  value={novoSaque.period_reference}
                  onChange={(e) =>
                    setNovoSaque({
                      ...novoSaque,
                      period_reference: e.target.value,
                    })
                  }
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Descrição
                </label>
                <input
                  type="text"
                  placeholder="Honorários Proc. X"
                  className="input"
                  value={novoSaque.description}
                  onChange={(e) =>
                    setNovoSaque({ ...novoSaque, description: e.target.value })
                  }
                />
              </div>
              <div className="col-span-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowFormSaque(false)}
                  className="btn-ghost text-sm px-3 py-1.5"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={savingSaque}
                  className="btn-primary text-sm px-4 py-1.5"
                >
                  {savingSaque ? "Solicitando…" : "Solicitar"}
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            {withdrawals.length === 0 ? (
              <Empty message="Nenhum saque registrado." />
            ) : (
              withdrawals.map((w) => (
                <div
                  key={w.id}
                  className="flex items-center gap-4 p-3 rounded-lg border border-slate-100 hover:bg-slate-50"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="text-sm font-semibold text-slate-800">
                        {nomeUser(w.partner_id)}
                      </p>
                      <ExtratoSocio
                        userId={w.partner_id}
                        nome={nomeUser(w.partner_id)}
                        isSocio
                      />
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[w.status] ?? "bg-slate-100 text-slate-500"}`}
                      >
                        {STATUS_LABEL[w.status] ?? w.status}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">
                      {w.period_reference ?? "—"} · {w.description ?? ""}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-slate-800">
                      {fmtMoney(w.net_value ?? w.gross_value)}
                    </p>
                    {w.case_expenses > 0 && (
                      <p className="text-[10px] text-slate-400">
                        Despesas: {fmtMoney(w.case_expenses)}
                      </p>
                    )}
                  </div>
                  {w.status === "pendente" && (
                    <div className="flex gap-1.5">
                      <button
                        onClick={() => approveWithdrawal(w.id, "approve")}
                        className="p-1.5 bg-success-50 text-success-600 rounded-lg hover:bg-success-100"
                        title="Aprovar"
                      >
                        <CheckCircle className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => approveWithdrawal(w.id, "reject")}
                        className="p-1.5 bg-danger-50 text-danger-500 rounded-lg hover:bg-danger-100"
                        title="Rejeitar"
                      >
                        <XCircle className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                  <p className="text-[10px] text-slate-400 flex-shrink-0">
                    {new Date(w.created_at).toLocaleDateString("pt-BR")}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
