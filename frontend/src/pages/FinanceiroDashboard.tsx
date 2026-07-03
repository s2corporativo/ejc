import { useState, useEffect, useCallback } from "react";
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Wallet,
  Award,
  Scale,
  AlertCircle,
  CheckCircle,
  BarChart3,
  RefreshCw,
  Calendar,
  Download,
  FileText,
  PiggyBank,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

function fmtR$(v: number | undefined | null) {
  if (v == null) return "R$ 0,00";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

const CATEGORIA_LABEL: Record<string, string> = {
  infraestrutura: "Infraestrutura",
  tecnologia: "Tecnologia",
  pessoal: "Pessoal / Pró-labore",
  oab: "OAB / Anuidade",
  marketing: "Marketing",
  operacao: "Operação",
  fiscal: "Fiscal / Contab.",
  investimento: "Investimento",
  outro: "Outros",
};

function StatCard({
  label,
  value,
  icon: Icon,
  color = "blue",
  sub,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color?: "blue" | "green" | "red" | "yellow" | "purple" | "slate" | "bronze";
  sub?: string;
}) {
  const colors: Record<string, string> = {
    blue: "bg-primary-50 text-primary-600",
    green: "bg-success-50 text-success-600",
    red: "bg-danger-50 text-danger-600",
    yellow: "bg-warn-50 text-warn-600",
    purple: "bg-ai-50 text-ai-600",
    slate: "bg-slate-100 text-slate-600",
    bronze: "bg-orange-50 text-orange-600",
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-3">
      <div className={`p-2.5 rounded-lg ${colors[color]}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] text-slate-500 uppercase tracking-wide font-medium">
          {label}
        </p>
        <p className="text-lg font-bold text-slate-800 mt-0.5">{value}</p>
        {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

export default function FinanceiroDashboard() {
  const [d, setD] = useState<any>(null);
  const [relatorio, setRelatorio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [competencia, setCompetencia] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(
        `/v1/financeiro/consolidado?competencia=${competencia}`,
      );
      setD(r.data);
    } finally {
      setLoading(false);
    }
  }, [competencia]);

  useEffect(() => {
    load();
  }, [load]);

  const carregarRelatorio = async () => {
    try {
      const r = await api.get(`/v1/relatorio/mensal?mes=${competencia}`);
      setRelatorio(r.data);
    } catch {}
  };

  const exportarCSV = async () => {
    const token = localStorage.getItem("ejc_access");
    const resp = await fetch(
      `/api/v1/despesas/export/csv?competencia=${competencia}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `despesas-${competencia}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const rec = d?.receitas ?? {};
  const desp = d?.despesas ?? {};
  const caixa = d?.caixa_periodo ?? 0;
  const totalGeralDesp = (desp.fixo ?? 0) + (desp.variavel ?? 0);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <PageHeader
        title="Financeiro"
        subtitle="Controle integrado do escritório"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-2 border border-slate-200 rounded-lg px-3 py-1.5">
              <Calendar className="w-4 h-4 text-slate-400" />
              <input
                type="month"
                className="text-sm text-slate-700 outline-none bg-transparent"
                value={competencia}
                onChange={(e) => setCompetencia(e.target.value)}
              />
            </div>
            <button
              onClick={carregarRelatorio}
              className="btn-secondary"
            >
              <FileText className="w-4 h-4" /> Relatório
            </button>
            <button
              onClick={exportarCSV}
              className="btn-secondary"
            >
              <Download className="w-4 h-4" /> CSV
            </button>
            <button
              onClick={load}
              className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-500"
              aria-label="Atualizar"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        }
      />

      {loading ? (
        <div className="text-center py-16 text-slate-400">Carregando...</div>
      ) : (
        <>
          {/* Cards principais — Caixa / Receber / Pagar / Resultado */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Caixa do período"
              value={fmtR$(caixa)}
              icon={PiggyBank}
              color={caixa >= 0 ? "green" : "red"}
              sub={`Margem ${d?.margem_pct ?? 0}%`}
            />
            <StatCard
              label="A Receber"
              value={fmtR$((rec.a_receber ?? 0) + (rec.atrasado ?? 0))}
              icon={DollarSign}
              color="yellow"
              sub={`Atrasado: ${fmtR$(rec.atrasado)}`}
            />
            <StatCard
              label="A Pagar"
              value={fmtR$(desp.a_pagar)}
              icon={TrendingDown}
              color="red"
              sub={`Pagas: ${fmtR$(desp.pagas)}`}
            />
            <StatCard
              label="Resultado do mês"
              value={fmtR$(caixa)}
              icon={caixa >= 0 ? CheckCircle : AlertCircle}
              color={caixa >= 0 ? "green" : "red"}
            />
          </div>

          {/* Receitas classificadas */}
          <div>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Receitas (recebidas no mês)
            </h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Honorários Contratuais"
                value={fmtR$(rec.contratual)}
                icon={Wallet}
                color="blue"
                sub="Pro labore / partido"
              />
              <StatCard
                label="Êxito (Ad Exitum)"
                value={fmtR$(rec.exito)}
                icon={Award}
                color="bronze"
                sub="50% titular / 50% escritório"
              />
              <StatCard
                label="Sucumbência"
                value={fmtR$(rec.sucumbencia)}
                icon={Scale}
                color="purple"
                sub="Parte vencida"
              />
              <StatCard
                label="Custas / Despesas"
                value={fmtR$(rec.custas)}
                icon={TrendingUp}
                color="slate"
                sub="Reembolsáveis"
              />
            </div>
          </div>

          {/* Receitas previstas (a receber) */}
          {rec.previsto && rec.previsto.total > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Receitas previstas (a receber)
              </h2>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                  label="Contratual prevista"
                  value={fmtR$(rec.previsto.contratual)}
                  icon={Wallet}
                  color="blue"
                />
                <StatCard
                  label="Êxito previsto"
                  value={fmtR$(rec.previsto.exito)}
                  icon={Award}
                  color="bronze"
                />
                <StatCard
                  label="Sucumbência prevista"
                  value={fmtR$(rec.previsto.sucumbencia)}
                  icon={Scale}
                  color="purple"
                />
                <StatCard
                  label="Custas previstas"
                  value={fmtR$(rec.previsto.custas)}
                  icon={TrendingUp}
                  color="slate"
                />
              </div>
            </div>
          )}

          {/* Duas colunas: receita detalhe + despesas */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Honorários (status) */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="font-semibold text-slate-800 mb-4 flex items-center gap-2">
                <Wallet className="w-4 h-4 text-primary-500" /> Honorários —
                situação
              </h2>
              <div className="space-y-3">
                {[
                  {
                    label: "Recebido no mês",
                    value: rec.recebido_mes,
                    color: "text-success-600",
                  },
                  {
                    label: "A receber (pendente)",
                    value: rec.a_receber,
                    color: "text-warn-600",
                  },
                  {
                    label: "Atrasado",
                    value: rec.atrasado,
                    color: "text-danger-600",
                  },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    className="flex justify-between items-center py-2 border-b border-slate-50 last:border-0"
                  >
                    <span className="text-sm text-slate-600">{label}</span>
                    <span className={`text-sm font-semibold ${color}`}>
                      {fmtR$(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Despesas por categoria + fixo/variável */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="font-semibold text-slate-800 mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-danger-500" /> Despesas por
                categoria
              </h2>
              {!desp.por_categoria?.length ? (
                <p className="text-sm text-slate-400 text-center py-6">
                  Sem despesas no mês
                </p>
              ) : (
                <div className="space-y-2.5">
                  {desp.por_categoria.map(({ categoria, total }: any) => {
                    const pct =
                      totalGeralDesp > 0 ? (total / totalGeralDesp) * 100 : 0;
                    return (
                      <div key={categoria}>
                        <div className="flex justify-between text-xs mb-0.5">
                          <span className="text-slate-600">
                            {CATEGORIA_LABEL[categoria] ?? categoria}
                          </span>
                          <span className="font-medium text-slate-700">
                            {fmtR$(total)}
                          </span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full">
                          <div
                            className="h-1.5 bg-danger-400 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Custos fixos</span>
                  <span className="font-medium text-slate-700">
                    {fmtR$(desp.fixo)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Custos variáveis</span>
                  <span className="font-medium text-slate-700">
                    {fmtR$(desp.variavel)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Relatório gerencial */}
          {relatorio && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-slate-800 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-ai-500" /> Relatório
                  Gerencial — {relatorio.mes_label}
                </h2>
                <button
                  onClick={() => setRelatorio(null)}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Fechar
                </button>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { l: "Casos ativos", v: relatorio.casos?.ativos },
                  { l: "Novos no mês", v: relatorio.casos?.novos_mes },
                  { l: "Encerrados", v: relatorio.casos?.encerrados_mes },
                  {
                    l: "Prazos vencidos",
                    v: relatorio.prazos?.vencidos_abertos,
                  },
                ].map(({ l, v }) => (
                  <div
                    key={l}
                    className="bg-slate-50 rounded-lg p-3 text-center"
                  >
                    <p className="text-xs text-slate-500">{l}</p>
                    <p className="text-lg font-bold text-slate-800 mt-0.5">
                      {v ?? 0}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Saldo destaque */}
          <div
            className={`rounded-xl border p-5 flex items-center justify-between ${caixa >= 0 ? "bg-success-50 border-success-200" : "bg-danger-50 border-danger-200"}`}
          >
            <div>
              <p
                className={`text-sm font-medium ${caixa >= 0 ? "text-success-700" : "text-danger-700"}`}
              >
                {caixa >= 0
                  ? "Resultado positivo no período"
                  : "Resultado negativo no período"}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                Recebido {fmtR$(rec.recebido_mes)} − Despesas pagas{" "}
                {fmtR$(desp.pagas)}
              </p>
            </div>
            <p
              className={`text-2xl font-bold ${caixa >= 0 ? "text-success-700" : "text-danger-700"}`}
            >
              {fmtR$(caixa)}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
