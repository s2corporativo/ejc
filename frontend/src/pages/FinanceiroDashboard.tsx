import { useState, useEffect, useCallback } from "react";
import {
  DollarSign,
  TrendingDown,
  Wallet,
  AlertCircle,
  CheckCircle,
  RefreshCw,
  Download,
  FileText,
  PiggyBank,
  ChevronRight,
  Clock3,
  Receipt,
  BarChart3,
  ShieldCheck,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { Empty, Spinner } from "../components/UI";

function fmtR$(v: number | undefined | null) {
  if (v == null) return "R$ 0,00";
  return Number(v).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
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

type FinanceDestino = "honorarios" | "despesas" | "nfse" | "contratos";

type FinanceAction = { tab?: FinanceDestino; status?: string };

interface AtencaoItem {
  codigo: string;
  prioridade: "alta" | "media" | "baixa";
  titulo: string;
  qtd: number;
  valor: number | null;
  acao?: FinanceAction;
}

interface FechamentoItem {
  codigo: string;
  severidade: "bloqueio" | "revisao";
  titulo: string;
  qtd: number;
  valor: number | null;
  acao?: FinanceAction;
}

interface FechamentoData {
  competencia: string;
  modo: "pre_fechamento_read_only";
  status: "pronto" | "revisao" | "bloqueado";
  score_integridade: number;
  pode_fechar_persistente: boolean;
  bloqueios: FechamentoItem[];
  revisoes: FechamentoItem[];
  total_bloqueios: number;
  total_revisoes: number;
  dependencia_estrutural?: string;
  recomendacao?: string;
  aviso?: string;
}

function StatCard({
  label,
  value,
  icon: Icon,
  tone = "slate",
  sub,
  onClick,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  tone?: "green" | "red" | "yellow" | "blue" | "slate";
  sub?: string;
  onClick?: () => void;
}) {
  const tones: Record<string, string> = {
    green: "bg-success-50 text-success-600",
    red: "bg-danger-50 text-danger-600",
    yellow: "bg-warn-50 text-warn-600",
    blue: "bg-primary-50 text-primary-600",
    slate: "bg-slate-100 text-slate-600",
  };
  const content = (
    <>
      <div className={`rounded-lg p-2.5 ${tones[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {label}
        </p>
        <p className="mt-0.5 text-lg font-bold text-slate-800">{value}</p>
        {sub && <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>}
      </div>
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="card flex w-full items-center gap-3 p-4 text-left transition-shadow hover:shadow-md hover:ring-1 hover:ring-primary-200"
      >
        {content}
      </button>
    );
  }
  return <div className="card flex items-center gap-3 p-4">{content}</div>;
}

function competenciaAtual() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export default function FinanceiroDashboard({
  competencia = competenciaAtual(),
  onDrillDown,
  onNavigate,
}: {
  competencia?: string;
  onDrillDown?: (tab: "honorarios" | "despesas", status?: string) => void;
  onNavigate?: (tab: FinanceDestino) => void;
}) {
  const [d, setD] = useState<any>(null);
  const [atencao, setAtencao] = useState<AtencaoItem[]>([]);
  const [fechamento, setFechamento] = useState<FechamentoData | null>(null);
  const [relatorio, setRelatorio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const consolidado = await api.get("/financeiro/consolidado", {
        params: { competencia },
      });
      setD(consolidado.data);

      const [fila, preFechamento] = await Promise.allSettled([
        api.get("/financeiro/atencao"),
        api.get("/financeiro/fechamento-inteligente", {
          params: { competencia },
        }),
      ]);

      setAtencao(
        fila.status === "fulfilled" && Array.isArray(fila.value.data?.itens)
          ? fila.value.data.itens
          : [],
      );
      setFechamento(
        preFechamento.status === "fulfilled" ? preFechamento.value.data : null,
      );
    } catch (e: any) {
      setD(null);
      setFechamento(null);
      setErro(
        e?.response?.data?.detail ||
          "Não foi possível carregar o consolidado financeiro.",
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
      const r = await api.get("/relatorio/mensal", {
        params: { mes: competencia },
      });
      setRelatorio(r.data);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Falha ao carregar relatório");
    }
  };

  const exportarCSV = async () => {
    try {
      const resp = await api.get("/despesas/export/csv", {
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
        e?.response?.data?.detail || "Não foi possível exportar o CSV",
      );
    }
  };

  const navegarAcao = (acao?: FinanceAction) => {
    const tab = acao?.tab;
    if (!tab) return;
    if ((tab === "honorarios" || tab === "despesas") && onDrillDown) {
      onDrillDown(tab, acao?.status);
      return;
    }
    onNavigate?.(tab);
  };

  if (loading) return <Spinner />;
  if (erro) {
    return (
      <div className="rounded-xl border border-danger-200 bg-danger-50 p-4 text-sm text-danger-700">
        {erro}
        <button onClick={load} className="ml-3 underline">
          Tentar novamente
        </button>
      </div>
    );
  }

  const rec = d?.receitas ?? {};
  const desp = d?.despesas ?? {};
  const caixa = Number(d?.caixa_periodo ?? 0);
  const totalDespesas = Number(desp.fixo ?? 0) + Number(desp.variavel ?? 0);
  const fechamentoItens = [
    ...(fechamento?.bloqueios ?? []),
    ...(fechamento?.revisoes ?? []),
  ];
  const fechamentoTone =
    fechamento?.status === "bloqueado"
      ? "border-danger-200 bg-danger-50/40"
      : fechamento?.status === "revisao"
        ? "border-warn-200 bg-warn-50/40"
        : "border-success-200 bg-success-50/40";
  const fechamentoLabel =
    fechamento?.status === "bloqueado"
      ? "Bloqueado"
      : fechamento?.status === "revisao"
        ? "Revisão necessária"
        : "Pronto para revisão final";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button onClick={carregarRelatorio} className="btn-secondary">
          <FileText className="h-4 w-4" /> Relatório
        </button>
        <button onClick={exportarCSV} className="btn-secondary">
          <Download className="h-4 w-4" /> CSV
        </button>
        <button
          onClick={load}
          className="btn-secondary p-2"
          aria-label="Atualizar"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Caixa do período"
          value={fmtR$(caixa)}
          icon={PiggyBank}
          tone={caixa >= 0 ? "green" : "red"}
          sub={`Margem ${d?.margem_pct ?? 0}%`}
        />
        <StatCard
          label="A receber"
          value={fmtR$(Number(rec.a_receber ?? 0) + Number(rec.atrasado ?? 0))}
          icon={DollarSign}
          tone="yellow"
          sub={`Atrasado: ${fmtR$(rec.atrasado)}`}
          onClick={
            onDrillDown
              ? () => onDrillDown("honorarios", "pendente")
              : undefined
          }
        />
        <StatCard
          label="A pagar"
          value={fmtR$(desp.a_pagar)}
          icon={TrendingDown}
          tone="red"
          sub={`Pago: ${fmtR$(desp.pagas)}`}
          onClick={
            onDrillDown ? () => onDrillDown("despesas", "pendente") : undefined
          }
        />
        <StatCard
          label="Recebido no mês"
          value={fmtR$(rec.recebido_mes)}
          icon={Wallet}
          tone="blue"
        />
      </div>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="font-semibold text-slate-800">
              Precisa da sua atenção
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Somente itens que exigem decisão ou conferência financeira.
            </p>
          </div>
          <Clock3 className="h-5 w-5 text-slate-300" />
        </div>
        {atencao.length === 0 ? (
          <div className="p-5">
            <div className="flex items-center gap-2 text-sm text-success-700">
              <CheckCircle className="h-4 w-4" /> Nenhuma pendência financeira
              prioritária.
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {atencao.map((item) => {
              const tone =
                item.prioridade === "alta"
                  ? "text-danger-600 bg-danger-50"
                  : item.prioridade === "media"
                    ? "text-warn-700 bg-warn-50"
                    : "text-slate-500 bg-slate-100";
              return (
                <button
                  key={item.codigo}
                  type="button"
                  onClick={() => navegarAcao(item.acao)}
                  className="flex w-full items-center gap-3 px-5 py-3.5 text-left hover:bg-slate-50"
                >
                  <div className={`rounded-lg p-2 ${tone}`}>
                    <AlertCircle className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800">
                      {item.titulo}
                    </p>
                    <p className="text-xs text-slate-400">
                      {item.qtd} item(ns)
                      {item.valor != null ? ` · ${fmtR$(item.valor)}` : ""}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-slate-300" />
                </button>
              );
            })}
          </div>
        )}
      </section>

      {fechamento && (
        <section className={`card overflow-hidden border ${fechamentoTone}`}>
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100/70 px-5 py-4">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-white p-2 shadow-sm">
                <ShieldCheck className="h-5 w-5 text-primary-600" />
              </div>
              <div>
                <h2 className="font-semibold text-slate-800">
                  Pré-fechamento inteligente
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  Gate gerencial da competência {fechamento.competencia}. Não
                  congela lançamentos.
                </p>
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {fechamentoLabel}
              </div>
              <div className="mt-0.5 text-2xl font-bold text-slate-800">
                {fechamento.score_integridade}/100
              </div>
            </div>
          </div>

          {fechamentoItens.length === 0 ? (
            <div className="px-5 py-4">
              <div className="flex items-center gap-2 text-sm font-medium text-success-700">
                <CheckCircle className="h-4 w-4" /> Nenhum bloqueio ou item de
                revisão detectado.
              </div>
              <p className="mt-1 text-xs text-slate-500">
                A competência está pronta para conferência humana final. O
                fechamento imutável será habilitado somente após a migration
                linear própria.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100/80">
              {fechamentoItens.map((item) => (
                <button
                  key={item.codigo}
                  type="button"
                  onClick={() => navegarAcao(item.acao)}
                  className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-white/60"
                >
                  <AlertCircle
                    className={`h-4 w-4 ${
                      item.severidade === "bloqueio"
                        ? "text-danger-600"
                        : "text-warn-600"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800">
                      {item.titulo}
                    </p>
                    <p className="text-xs text-slate-500">
                      {item.severidade === "bloqueio"
                        ? "Impede fechamento"
                        : "Exige conferência"}
                      {` · ${item.qtd} item(ns)`}
                      {item.valor != null ? ` · ${fmtR$(item.valor)}` : ""}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-slate-300" />
                </button>
              ))}
            </div>
          )}

          <div className="border-t border-slate-100/70 px-5 py-3 text-[11px] leading-relaxed text-slate-500">
            {fechamento.dependencia_estrutural}
          </div>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-semibold text-slate-800">
              <Wallet className="h-4 w-4 text-primary-500" /> Recebimentos
            </h2>
            <button
              type="button"
              onClick={() => onNavigate?.("honorarios")}
              className="text-xs font-medium text-primary-600 hover:underline"
            >
              Abrir
            </button>
          </div>
          <div className="space-y-3 text-sm">
            {[
              ["Recebido no mês", rec.recebido_mes, "text-success-600"],
              ["A receber", rec.a_receber, "text-warn-600"],
              ["Em atraso", rec.atrasado, "text-danger-600"],
              ["Previsto", rec.previsto?.total, "text-slate-700"],
            ].map(([label, value, cls]: any) => (
              <div
                key={label}
                className="flex justify-between border-b border-slate-50 pb-2 last:border-0"
              >
                <span className="text-slate-500">{label}</span>
                <span className={`font-semibold ${cls}`}>{fmtR$(value)}</span>
              </div>
            ))}
          </div>
          {Number(rec.percentuais_sem_valor ?? 0) > 0 && (
            <div className="mt-4 rounded-lg bg-warn-50 px-3 py-2 text-xs text-warn-700">
              {rec.percentuais_sem_valor} honorário(s) percentual(is) ainda sem
              valor monetário apurado.
            </div>
          )}
        </section>

        <section className="card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-semibold text-slate-800">
              <Receipt className="h-4 w-4 text-danger-500" /> Despesas
            </h2>
            <button
              type="button"
              onClick={() => onNavigate?.("despesas")}
              className="text-xs font-medium text-primary-600 hover:underline"
            >
              Abrir
            </button>
          </div>
          <div className="space-y-3 text-sm">
            {[
              ["A pagar", desp.a_pagar, "text-danger-600"],
              ["Pagas", desp.pagas, "text-success-600"],
              ["Fixas", desp.fixo, "text-slate-700"],
              ["Variáveis / extras", desp.variavel, "text-slate-700"],
            ].map(([label, value, cls]: any) => (
              <div
                key={label}
                className="flex justify-between border-b border-slate-50 pb-2 last:border-0"
              >
                <span className="text-slate-500">{label}</span>
                <span className={`font-semibold ${cls}`}>{fmtR$(value)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="card p-5">
        <h2 className="mb-4 flex items-center gap-2 font-semibold text-slate-800">
          <BarChart3 className="h-4 w-4 text-slate-400" /> Despesas por
          categoria
        </h2>
        {!desp.por_categoria?.length ? (
          <Empty message="Sem despesas no mês" />
        ) : (
          <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
            {desp.por_categoria.map(({ categoria, total }: any) => {
              const pct =
                totalDespesas > 0 ? (Number(total) / totalDespesas) * 100 : 0;
              return (
                <div key={categoria}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-slate-600">
                      {CATEGORIA_LABEL[categoria] ?? categoria}
                    </span>
                    <span className="font-medium text-slate-700">
                      {fmtR$(total)}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-100">
                    <div
                      className="h-1.5 rounded-full bg-slate-400"
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {relatorio && (
        <section className="card p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="font-semibold text-slate-800">
                Relatório gerencial — {relatorio.mes_label}
              </h2>
              <p className="mt-0.5 text-xs text-slate-400">
                Caixa por pagamentos efetivos e saldo residual. Não substitui a
                contabilidade.
              </p>
            </div>
            <button
              onClick={() => setRelatorio(null)}
              className="text-xs text-slate-400 hover:text-slate-700"
            >
              Fechar
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="rounded-xl bg-success-50 p-3">
              <p className="text-[11px] uppercase tracking-wide text-success-700">
                Recebido
              </p>
              <p className="mt-1 font-bold text-success-800">
                {fmtR$(relatorio.financeiro?.recebido_mes)}
              </p>
            </div>
            <div className="rounded-xl bg-danger-50 p-3">
              <p className="text-[11px] uppercase tracking-wide text-danger-700">
                Despesas pagas
              </p>
              <p className="mt-1 font-bold text-danger-800">
                {fmtR$(relatorio.financeiro?.despesas_pagas)}
              </p>
            </div>
            <div className="rounded-xl bg-slate-100 p-3">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">
                Resultado
              </p>
              <p className="mt-1 font-bold text-slate-800">
                {fmtR$(relatorio.financeiro?.resultado_mes)}
              </p>
            </div>
            <div className="rounded-xl bg-warn-50 p-3">
              <p className="text-[11px] uppercase tracking-wide text-warn-700">
                Em atraso
              </p>
              <p className="mt-1 font-bold text-warn-800">
                {fmtR$(relatorio.financeiro?.atrasado)}
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-lg border border-slate-100 p-3">
              <span className="text-slate-500">Novos casos no mês</span>
              <strong className="float-right text-slate-800">
                {relatorio.casos?.novos_mes ?? 0}
              </strong>
            </div>
            <div className="rounded-lg border border-slate-100 p-3">
              <span className="text-slate-500">Casos encerrados</span>
              <strong className="float-right text-slate-800">
                {relatorio.casos?.encerrados_mes ?? 0}
              </strong>
            </div>
            <div className="rounded-lg border border-slate-100 p-3">
              <span className="text-slate-500">Prazos vencidos</span>
              <strong className="float-right text-danger-600">
                {relatorio.prazos?.vencidos_abertos ?? 0}
              </strong>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
