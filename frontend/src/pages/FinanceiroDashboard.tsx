import { useCallback, useEffect, useState, type ElementType } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  FileText,
  PiggyBank,
  RefreshCw,
  TrendingDown,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { Modal, Spinner } from "../components/UI";
import { toast } from "../components/Toast";

function fmtR$(value: number | undefined | null) {
  return Number(value ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

function competenciaLabel(competencia: string) {
  const [ano, mes] = competencia.split("-");
  return `${mes}/${ano}`;
}

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

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
  tone,
  onClick,
}: {
  label: string;
  value: string;
  detail?: string;
  icon: ElementType;
  tone: "green" | "blue" | "amber" | "red";
  onClick?: () => void;
}) {
  const toneClasses = {
    green:
      "bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300",
    blue: "bg-blue-50 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300",
    amber:
      "bg-amber-50 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300",
    red: "bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300",
  };

  const body = (
    <>
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${toneClasses[tone]}`}
      >
        <Icon className="h-4.5 w-4.5" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {label}
        </p>
        <p className="mt-1 truncate text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
          {value}
        </p>
        {detail && (
          <p className="mt-1 truncate text-[11px] text-slate-400 dark:text-slate-500">
            {detail}
          </p>
        )}
      </div>
    </>
  );

  const className =
    "flex min-h-[104px] w-full items-start gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 text-left shadow-sm transition hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70 dark:hover:border-slate-700";

  return onClick ? (
    <button type="button" onClick={onClick} className={className}>
      {body}
    </button>
  ) : (
    <div className={className}>{body}</div>
  );
}

function FlowRow({
  label,
  value,
  max,
  kind,
}: {
  label: string;
  value: number;
  max: number;
  kind: "in" | "out";
}) {
  const width = Math.max(value > 0 ? 7 : 0, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-4 text-sm">
        <span className="text-slate-500 dark:text-slate-400">{label}</span>
        <span className="font-semibold text-slate-800 dark:text-slate-100">
          {fmtR$(value)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={`h-full rounded-full ${
            kind === "in" ? "bg-emerald-500" : "bg-slate-400 dark:bg-slate-500"
          }`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
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
  const [data, setData] = useState<any>(null);
  const [atencao, setAtencao] = useState<AtencaoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [relatorioAberto, setRelatorioAberto] = useState(false);
  const [relatorioLoading, setRelatorioLoading] = useState(false);
  const [relatorio, setRelatorio] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErro(null);

    const [consolidado, fila] = await Promise.allSettled([
      api.get("/financeiro/consolidado", { params: { competencia } }),
      api.get("/financeiro/atencao"),
    ]);

    if (consolidado.status === "rejected") {
      const e: any = consolidado.reason;
      setData(null);
      setAtencao([]);
      setErro(
        e?.response?.data?.detail || "Não foi possível carregar o financeiro.",
      );
      setLoading(false);
      return;
    }

    setData(consolidado.value.data);
    setAtencao(
      fila.status === "fulfilled" && Array.isArray(fila.value.data?.itens)
        ? fila.value.data.itens
        : [],
    );
    setLoading(false);
  }, [competencia]);

  useEffect(() => {
    load();
  }, [load]);

  const abrirRelatorio = async () => {
    setRelatorioAberto(true);
    setRelatorioLoading(true);
    try {
      const r = await api.get("/relatorio/mensal", {
        params: { mes: competencia },
      });
      setRelatorio(r.data);
    } catch (e: any) {
      setRelatorioAberto(false);
      toast.error(
        e?.response?.data?.detail || "Falha ao carregar o relatório.",
      );
    } finally {
      setRelatorioLoading(false);
    }
  };

  const navegarAcao = (acao?: FinanceAction) => {
    if (!acao?.tab) return;
    if ((acao.tab === "honorarios" || acao.tab === "despesas") && onDrillDown) {
      onDrillDown(acao.tab, acao.status);
      return;
    }
    onNavigate?.(acao.tab);
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  if (erro) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
        {erro}
        <button
          type="button"
          onClick={load}
          className="ml-3 font-medium underline"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  const rec = data?.receitas ?? {};
  const desp = data?.despesas ?? {};
  const fluxo = data?.fluxo_caixa ?? {};

  const caixa = Number(data?.caixa_periodo ?? 0);
  const recebido = Number(rec.recebido_mes ?? 0);
  const aReceber = Number(rec.a_receber ?? 0) + Number(rec.atrasado ?? 0);
  const aPagar = Number(desp.a_pagar ?? 0);
  const saidas = Number(desp.saidas_caixa_mes ?? 0);
  const atrasado = Number(rec.atrasado ?? 0);
  const despesasLancadas = Number(desp.fixo ?? 0) + Number(desp.variavel ?? 0);
  const honorariosFuturos =
    Number(rec.previsto?.exito ?? 0) + Number(rec.previsto?.sucumbencia ?? 0);
  const maxFluxo = Math.max(recebido, saidas, 1);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-slate-400 dark:text-slate-500">
          {competenciaLabel(competencia)}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={abrirRelatorio}
            className="btn-secondary text-sm"
          >
            <FileText className="h-4 w-4" />
            Relatório
          </button>
          <button
            type="button"
            onClick={load}
            className="btn-secondary p-2"
            aria-label="Atualizar financeiro"
            title="Atualizar"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard
          label="A receber"
          value={fmtR$(aReceber)}
          detail={
            atrasado > 0
              ? `${fmtR$(atrasado)} em atraso`
              : "Sem atraso relevante"
          }
          icon={CircleDollarSign}
          tone="amber"
          onClick={
            onDrillDown
              ? () => onDrillDown("honorarios", "pendente")
              : undefined
          }
        />
        <StatCard
          label="Recebido no mês"
          value={fmtR$(recebido)}
          detail="Entradas efetivas no mês"
          icon={Wallet}
          tone="blue"
          onClick={
            onDrillDown ? () => onDrillDown("honorarios", "pago") : undefined
          }
        />
        <StatCard
          label="A pagar"
          value={fmtR$(aPagar)}
          detail={`${fmtR$(saidas)} pagos no mês`}
          icon={TrendingDown}
          tone="red"
          onClick={
            onDrillDown ? () => onDrillDown("despesas", "pendente") : undefined
          }
        />
        <StatCard
          label="Saldo"
          value={fmtR$(caixa)}
          detail={`Margem ${Number(data?.margem_pct ?? 0).toLocaleString("pt-BR")}%`}
          icon={PiggyBank}
          tone={caixa >= 0 ? "green" : "red"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
        <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">
                Fluxo do mês
              </h2>
              <p className="mt-0.5 text-xs text-slate-400">
                Somente entradas e saídas efetivamente baixadas.
              </p>
            </div>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                caixa >= 0
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300"
                  : "bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300"
              }`}
            >
              {caixa >= 0 ? "Positivo" : "Negativo"}
            </span>
          </div>

          <div className="space-y-4">
            <FlowRow
              label="Entradas"
              value={Number(fluxo.entradas ?? recebido)}
              max={maxFluxo}
              kind="in"
            />
            <FlowRow
              label="Saídas"
              value={Number(fluxo.saidas ?? saidas)}
              max={maxFluxo}
              kind="out"
            />
          </div>

          <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
            <span className="text-sm text-slate-500 dark:text-slate-400">
              Saldo
            </span>
            <span
              className={`text-lg font-semibold ${
                caixa >= 0
                  ? "text-emerald-700 dark:text-emerald-300"
                  : "text-rose-700 dark:text-rose-300"
              }`}
            >
              {fmtR$(caixa)}
            </span>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            Resumo rápido
          </h2>
          <div className="mt-4 divide-y divide-slate-100 dark:divide-slate-800">
            <div className="flex items-center justify-between gap-3 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                Em atraso
              </span>
              <strong className="text-sm text-rose-700 dark:text-rose-300">
                {fmtR$(atrasado)}
              </strong>
            </div>
            <div className="flex items-center justify-between gap-3 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                Honorários futuros
              </span>
              <strong className="text-sm text-slate-800 dark:text-slate-100">
                {fmtR$(honorariosFuturos)}
              </strong>
            </div>
            <div className="flex items-center justify-between gap-3 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                Despesas lançadas
              </span>
              <strong className="text-sm text-slate-800 dark:text-slate-100">
                {fmtR$(despesasLancadas)}
              </strong>
            </div>
          </div>
        </section>
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">
              Precisa da sua atenção
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Só o que exige ação.
            </p>
          </div>
          <AlertCircle className="h-5 w-5 text-slate-300 dark:text-slate-600" />
        </div>

        {atencao.length === 0 ? (
          <div className="flex items-center gap-2 px-5 py-5 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4" />
            Nenhuma pendência financeira prioritária.
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {atencao.slice(0, 6).map((item) => (
              <button
                key={item.codigo}
                type="button"
                onClick={() => navegarAcao(item.acao)}
                className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition hover:bg-slate-50 dark:hover:bg-white/[0.04]"
              >
                <span
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                    item.prioridade === "alta"
                      ? "bg-rose-500"
                      : item.prioridade === "media"
                        ? "bg-amber-500"
                        : "bg-slate-300 dark:bg-slate-600"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-700 dark:text-slate-200">
                    {item.titulo}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {item.qtd} {item.qtd === 1 ? "item" : "itens"}
                    {item.valor != null ? ` · ${fmtR$(item.valor)}` : ""}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-300 dark:text-slate-600" />
              </button>
            ))}
          </div>
        )}
      </section>

      <p className="px-1 text-[11px] text-slate-400 dark:text-slate-600">
        Visão gerencial. Caixa considera apenas pagamentos e baixas efetivos.
      </p>

      <Modal
        open={relatorioAberto}
        onClose={() => setRelatorioAberto(false)}
        title={
          relatorio?.mes_label
            ? `Relatório · ${relatorio.mes_label}`
            : "Relatório mensal"
        }
      >
        {relatorioLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : relatorio ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              {[
                ["Recebido", relatorio.financeiro?.recebido_mes],
                ["Resultado", relatorio.financeiro?.resultado_mes],
                ["A receber", relatorio.financeiro?.pendente],
                ["A pagar", relatorio.financeiro?.despesas_pendentes],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-xl border border-slate-100 p-3 dark:border-slate-800"
                >
                  <p className="text-xs text-slate-400">{label}</p>
                  <p className="mt-1 font-semibold text-slate-900 dark:text-white">
                    {fmtR$(Number(value ?? 0))}
                  </p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-3 border-t border-slate-100 pt-4 text-center dark:border-slate-800">
              <div>
                <p className="text-lg font-semibold text-slate-900 dark:text-white">
                  {Number(relatorio.casos?.ativos ?? 0)}
                </p>
                <p className="text-xs text-slate-400">Casos ativos</p>
              </div>
              <div>
                <p className="text-lg font-semibold text-slate-900 dark:text-white">
                  {Number(relatorio.casos?.novos_mes ?? 0)}
                </p>
                <p className="text-xs text-slate-400">Novos</p>
              </div>
              <div>
                <p className="text-lg font-semibold text-slate-900 dark:text-white">
                  {Number(relatorio.prazos?.vencidos_abertos ?? 0)}
                </p>
                <p className="text-xs text-slate-400">Prazos vencidos</p>
              </div>
            </div>
            <p className="text-[11px] leading-relaxed text-slate-400">
              {relatorio.aviso}
            </p>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
