import { useEffect, useState, useCallback } from "react";
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

const fmtMoney = (v?: number | null) =>
  (Number.isFinite(v) ? (v as number) : 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });

const fmtPct = (v?: number | null) =>
  Number.isFinite(v) ? `${((v as number) * 100).toFixed(1)}%` : "—";

interface Socio {
  id: string;
  user_id: string;
  participacao_percentual: number;
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
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-emerald-50 text-emerald-700",
  rejected: "bg-red-50 text-red-600",
  paid: "bg-blue-50 text-blue-700",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  approved: "Aprovado",
  rejected: "Rejeitado",
  paid: "Pago",
};

export default function Sociedade() {
  const [socios, setSocios] = useState<Socio[]>([]);
  const [totalPart, setTotalPart] = useState(0);
  const [distrib, setDistrib] = useState<Distribuicao[]>([]);
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [tab, setTab] = useState<"socios" | "distribuicao" | "saques">(
    "socios",
  );
  const [showFormSocio, setShowFormSocio] = useState(false);
  const [showFormDist, setShowFormDist] = useState(false);
  const [showFormSaque, setShowFormSaque] = useState(false);
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
        api.get("/v1/partner-withdrawals?page_size=50"),
      ]);
      if (s.status === "fulfilled") {
        setSocios(s.value.data?.socios ?? []);
        setTotalPart(s.value.data?.total_participacao ?? 0);
      } else setErro("Acesso restrito a sócios.");
      if (d.status === "fulfilled")
        setDistrib(d.value.data?.data ?? d.value.data ?? []);
      if (u.status === "fulfilled")
        setUsers(
          u.value.data?.data ?? u.value.data?.items ?? u.value.data ?? [],
        );
      if (w.status === "fulfilled") setWithdrawals(w.value.data?.data ?? []);
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
      alert("Selecione o sócio e percentual válido.");
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
      alert(err.response?.data?.detail || "Falha ao cadastrar sócio");
    }
  };

  const addDist = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = parseFloat(novaDist.valor_total);
    if (!(v > 0) || !novaDist.mes_referencia) {
      alert("Informe mês e valor.");
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
      alert(err.response?.data?.detail || "Falha ao registrar distribuição");
    }
  };

  const addSaque = async (e: React.FormEvent) => {
    e.preventDefault();
    const gross = parseFloat(novoSaque.gross_value);
    if (!(gross > 0)) {
      alert("Informe o valor bruto.");
      return;
    }
    try {
      await api.post("/v1/partner-withdrawals", {
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
      alert(err.response?.data?.detail || "Falha ao registrar saque");
    }
  };

  const approveWithdrawal = async (
    id: string,
    action: "approve" | "reject",
  ) => {
    try {
      await api.patch(`/v1/partner-withdrawals/${id}/${action}`);
      load();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Falha");
    }
  };

  // KPIs
  const totalDistrib = distrib.reduce((a, d) => a + (d.valor_total ?? 0), 0);
  const totalSaquesPagos = withdrawals
    .filter((w) => w.status === "paid")
    .reduce((a, w) => a + (w.net_value ?? 0), 0);
  const totalSaquesPendentes = withdrawals
    .filter((w) => w.status === "pending")
    .reduce((a, w) => a + (w.gross_value ?? 0), 0);

  if (loading)
    return (
      <div className="flex justify-center items-center py-20 text-slate-400 text-sm">
        Carregando...
      </div>
    );
  if (erro)
    return (
      <div className="p-6 max-w-xl mx-auto text-center">
        <Building2 className="w-12 h-12 mx-auto mb-3 text-slate-300" />
        <p className="text-slate-500">{erro}</p>
      </div>
    );

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">
            Gestão Societária
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Sócios, participação e distribuição de lucros
          </p>
        </div>
        <button
          onClick={load}
          className="p-2 border border-slate-200 rounded-lg hover:bg-slate-50"
        >
          <RefreshCw
            className={`w-4 h-4 text-slate-400 ${loading ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
          <div className="p-2.5 bg-blue-50 rounded-lg">
            <Users className="w-5 h-5 text-blue-600" />
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
        <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
          <div className="p-2.5 bg-emerald-50 rounded-lg">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
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
        <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
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
        <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
          <div className="p-2.5 bg-amber-50 rounded-lg">
            <Clock className="w-5 h-5 text-amber-600" />
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

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {(["socios", "distribuicao", "saques"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-blue-600 text-blue-600"
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

      {/* Tab: Sócios */}
      {tab === "socios" && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
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
                      ? "text-red-600 font-semibold"
                      : "text-slate-600 font-semibold"
                  }
                >
                  {fmtPct(totalPart)}
                </span>
              </p>
            </div>
            <button
              onClick={() => setShowFormSocio((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100 rounded-lg"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
                >
                  Salvar
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            {socios.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">
                Nenhum sócio cadastrado.
              </p>
            ) : (
              socios.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center gap-4 p-3 rounded-lg border border-slate-100 hover:bg-slate-50"
                >
                  <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center flex-shrink-0">
                    <Users className="w-5 h-5 text-blue-500" />
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
                    <p className="text-xs text-slate-400">Participação</p>
                    <p className="text-lg font-bold text-blue-600">
                      {fmtPct(s.participacao_percentual)}
                    </p>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${s.ativo ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-400"}`}
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

      {/* Tab: Distribuição */}
      {tab === "distribuicao" && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">
              Distribuição de Lucros
            </h2>
            <button
              onClick={() => setShowFormDist((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700"
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
                  className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="border border-slate-200 rounded-lg px-3 py-2 text-sm w-44"
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
                  className="px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 rounded-lg"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700"
                >
                  Salvar
                </button>
              </div>
            </form>
          )}

          <div className="space-y-3">
            {distrib.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">
                Nenhuma distribuição registrada.
              </p>
            ) : (
              distrib.map((d, i) => {
                const quota = socios
                  .filter((s) => s.ativo)
                  .map((s) => ({
                    nome: nomeUser(s.user_id),
                    valor: d.valor_total * s.participacao_percentual,
                    pct: s.participacao_percentual,
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
                      <p className="text-lg font-bold text-emerald-600">
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

      {/* Tab: Saques */}
      {tab === "saques" && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-800">Saques de Sócios</h2>
            <button
              onClick={() => setShowFormSaque((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
                  className="px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100 rounded-lg"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
                >
                  Solicitar
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            {withdrawals.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">
                Nenhum saque registrado.
              </p>
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
                  {w.status === "pending" && (
                    <div className="flex gap-1.5">
                      <button
                        onClick={() => approveWithdrawal(w.id, "approve")}
                        className="p-1.5 bg-emerald-50 text-emerald-600 rounded-lg hover:bg-emerald-100"
                        title="Aprovar"
                      >
                        <CheckCircle className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => approveWithdrawal(w.id, "reject")}
                        className="p-1.5 bg-red-50 text-red-500 rounded-lg hover:bg-red-100"
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
