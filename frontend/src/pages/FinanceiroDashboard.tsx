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
  Download,
  FileText,
  PiggyBank,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { Empty, Spinner } from "../components/UI";

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
  onClick,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color?: "blue" | "green" | "red" | "yellow" | "purple" | "slate" | "bronze";
  sub?: string;
  onClick?: () => void;
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
  const inner = (
    <>
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
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="card p-4 flex items-center gap-3 text-left w-full cursor-pointer transition-shadow hover:shadow-md hover:ring-1 hover:ring-primary-200"
        title={`Ver detalhes de ${label}`}
      >
        {inner}
      </button>
    );
  }
  return <div className="card p-4 flex items-center gap-3">{inner}</div>;
}

function competenciaAtual() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export default function FinanceiroDashboard({
  competencia = competenciaAtual(),
  onDrillDown,
}: {
  /** Competência (AAAA-MM) — controlada pelo FinanceiroWorkspace. */
  competencia?: string;
  /** Navega para outra aba do workspace (drill-down dos indicadores). */
  onDrillDown?: (tab: "honorarios" | "despesas", status?: string) => void;
}) {
  const [d, setD] = useState<any>(null);
  const [relatorio, setRelatorio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const r = await api.get(
        `/financeiro/consolidado?competencia=${competencia}`,
      );
      setD(r.data);
    } catch (e: any) {
      setD(null);
      setErro(
        e?.response?.data?.detail ||
          "Não foi possível carregar o consolidado financeiro. Os valores abaixo podem estar indisponíveis — tente atualizar.",
      );
    } finally {
      setLoading(false);
    }
  }, [competencia]);

  useEffect(() => {
    load();
  }, [load]);

  const carregarRelatorio = async () => {
    try {
      const r = await api.get(`/relatorio/mensal?mes=${competencia}`);
      setRelatorio(r.data);
    } catch (e: any) {
      setRelatorio(null);
      setErro(
        e?.response?.data?.detail ||
          "Não foi possível carregar o relatório mensal. Tente atualizar.",
      );
    }
  };

  const exportarCSV = async () => {
    try {
      // Reusa o cliente axios (baseURL /api + interceptor de token/refresh).
      const resp = await api.get("/v1/despesas/export/csv", {
        params: { competencia },
        responseType: "blob",
      });
      const url = URL.createObjectURL(resp.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `despesas-${competencia}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível exportar o CSV",
      );
    }
  };

  const rec = d?.receitas ?? {};
  const desp = d?.despesas ?? {};
  const caixa = d?.caixa_periodo ?? 0;
  const totalGeralDesp = (desp.fixo ?? 0) + (desp.variavel ?? 0);

  return (
    <div className="space-y-6">
      {/* Cabeçalho fica no FinanceiroWorkspace (título + competência única);
          aqui apenas as ações específicas da visão consolidada. */}
      <div className="flex items-center justify-end gap-2 flex-wrap">
        <button onClick={carregarRelatorio} className="btn-secondary">
          <FileText className="w-4 h-4" /> Relatório
        </button>
        <button onClick={exportarCSV} className="btn-secondary">
          <Download className="w-4 h-4" /> CSV
        </button>
        <button
          onClick={load}
          className="btn-secondary p-2"
          aria-label="Atualizar"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {loading ? (
        <Spinner />
      ) : erro ? (
        <div className="rounded-xl border border-danger-200 bg-danger-50 p-4 text-sm text-danger-700">
          {erro}
        </div>
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
              onClick={
                onDrillDown
                  ? () => onDrillDown("honorarios", "pendente")
                  : undefined
              }
            />
            <StatCard
              label="A Pagar"
              value={fmtR$(desp.a_pagar)}
              icon={TrendingDown}
              color="red"
              sub={`Pagas: ${fmtR$(desp.pagas)}`}
              onClick={
                onDrillDown
                  ? () => onDrillDown("despesas", "pendente")
                  : undefined
              }
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
              {/* REGRA FIXA: rateio 50/50 hardcoded no backend
                  (backend/app/routers/exito_rateio.py). Não existe endpoint de
                  configuração societária para esse percentual — se um dia
                  existir, carregar daqui em vez do texto fixo. */}
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
            <div className="card p-5">
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
            <div className="card p-5">
              <h2 className="font-semibold text-slate-800 mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-danger-500" /> Despesas por
                categoria
              </h2>
              {!desp.por_categoria?.length ? (
                <Empty message="Sem despesas no mês" />
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
            <div className="card p-5">
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
