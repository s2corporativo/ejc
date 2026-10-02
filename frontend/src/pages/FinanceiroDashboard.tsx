import { useCallback, useEffect, useState, type ElementType } from "react";
import { useNavigate } from "react-router";
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
  ShieldCheck,
  Upload,
  Landmark,
  BarChart3,
  Download,
} from "lucide-react";
import api from "../lib/api";
import {
  currentFinanceCompetence,
  financeCompetenceLabel,
  formatCurrency,
} from "../lib/financeiro";
import { Modal, Spinner } from "../components/UI";
import { toast } from "../components/Toast";
import { apiErrorMessage } from "../lib/apiError";
import type {
  DistributionAvailability,
  FinanceAction as FinanceActionBase,
  FinanceApproval,
  FinanceClosing,
  FinanceConsolidated,
  FinanceExceptionItem,
  FinanceExceptionsResponse,
  MonthlyReport,
  PreClosingResponse,
  ReconciliationResponse,
  ReconciliationSuggestion,
  RentabilidadeResponse,
} from "../types/financeiro";

const formatBRL = formatCurrency;
const competenciaLabel = financeCompetenceLabel;

type FinanceDestino =
  | "visao"
  | "honorarios"
  | "despesas"
  | "comissoes"
  | "nfse"
  | "contratos"
  | "recorrentes"
  | "societaria"
  | "estimador";
type FinanceAction = Omit<FinanceActionBase, "tab"> & { tab?: FinanceDestino };

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
          {formatBRL(value)}
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

export default function FinanceiroDashboard({
  competencia = currentFinanceCompetence(),
  onDrillDown,
  onNavigate,
}: {
  competencia?: string;
  onDrillDown?: (
    tab: "honorarios" | "despesas" | "comissoes",
    status?: string,
    focus?: string,
  ) => void;
  onNavigate?: (tab: FinanceDestino) => void;
}) {
  const navigate = useNavigate();
  const [data, setData] = useState<FinanceConsolidated | null>(null);
  const [atencao, setAtencao] = useState<AtencaoItem[]>([]);
  const [rentabilidade, setRentabilidade] =
    useState<RentabilidadeResponse | null>(null);
  const [excecoes, setExcecoes] = useState<FinanceExceptionsResponse>({
    competencia,
    itens: [],
    total: 0,
  });
  const [fechamento, setFechamento] = useState<FinanceClosing | null>(null);
  const [preFechamento, setPreFechamento] = useState<PreClosingResponse | null>(
    null,
  );
  const [preparandoFechamento, setPreparandoFechamento] = useState(false);
  const [distribuicao, setDistribuicao] =
    useState<DistributionAvailability | null>(null);
  const [aprovacoes, setAprovacoes] = useState<FinanceApproval[]>([]);
  const [governancaAberta, setGovernancaAberta] = useState(false);
  const [fechando, setFechando] = useState(false);
  const [limite, setLimite] = useState("10000");
  const [salvandoPolitica, setSalvandoPolitica] = useState(false);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [importandoBanco, setImportandoBanco] = useState(false);
  const [conciliacao, setConciliacao] = useState<ReconciliationResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [relatorioAberto, setRelatorioAberto] = useState(false);
  const [relatorioLoading, setRelatorioLoading] = useState(false);
  const [relatorio, setRelatorio] = useState<MonthlyReport | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErro(null);

    const [
      consolidado,
      fila,
      rent,
      exc,
      fechamentoResp,
      distribuicaoResp,
      politicaResp,
      aprovacoesResp,
    ] = await Promise.allSettled([
      api.get("/financeiro/consolidado", { params: { competencia } }),
      api.get("/financeiro/atencao"),
      api.get("/financeiro/rentabilidade", { params: { competencia } }),
      api.get("/financeiro/excecoes", { params: { competencia } }),
      api.get(`/financeiro/fechamentos/${competencia}`),
      api.get("/financeiro/distribuicao-disponivel", {
        params: { competencia },
      }),
      api.get("/financeiro/politica"),
      api.get("/financeiro/aprovacoes", { params: { status: "pendente" } }),
    ]);

    if (consolidado.status === "rejected") {
      const e: unknown = consolidado.reason;
      setData(null);
      setAtencao([]);
      setRentabilidade(null);
      setExcecoes({ competencia, itens: [], total: 0 });
      setErro(apiErrorMessage(e, "Não foi possível carregar o financeiro."));
      setLoading(false);
      return;
    }

    setData(consolidado.value.data);
    setAtencao(
      fila.status === "fulfilled" && Array.isArray(fila.value.data?.itens)
        ? fila.value.data.itens
        : [],
    );
    setRentabilidade(rent.status === "fulfilled" ? rent.value.data : null);
    setExcecoes(
      exc.status === "fulfilled"
        ? exc.value.data
        : { competencia, itens: [], total: 0 },
    );
    setFechamento(
      fechamentoResp.status === "fulfilled" ? fechamentoResp.value.data : null,
    );
    setDistribuicao(
      distribuicaoResp.status === "fulfilled"
        ? distribuicaoResp.value.data
        : null,
    );
    if (politicaResp.status === "fulfilled") {
      setLimite(
        String(politicaResp.value.data?.double_approval_threshold ?? 10000),
      );
    }
    setAprovacoes(
      aprovacoesResp.status === "fulfilled" &&
        Array.isArray(aprovacoesResp.value.data)
        ? aprovacoesResp.value.data
        : [],
    );
    setLoading(false);
  }, [competencia]);

  useEffect(() => {
    setPreFechamento(null);
    load();
  }, [load]);

  const baixarPacoteMensal = async () => {
    try {
      const response = await api.get(
        `/relatorio/mensal/${competencia}/pacote`,
        {
          responseType: "blob",
        },
      );
      const url = URL.createObjectURL(response.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `financeiro-${competencia}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Pacote financeiro mensal gerado.");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao gerar o pacote financeiro."));
    }
  };

  const abrirRelatorio = async () => {
    setRelatorioAberto(true);
    setRelatorioLoading(true);
    try {
      const r = await api.get("/relatorio/mensal", {
        params: { mes: competencia },
      });
      setRelatorio(r.data);
    } catch (e: unknown) {
      setRelatorioAberto(false);
      toast.error(apiErrorMessage(e, "Falha ao carregar o relatório."));
    } finally {
      setRelatorioLoading(false);
    }
  };

  const navegarAcao = (acao?: FinanceActionBase) => {
    const tab = acao?.tab as FinanceDestino | undefined;
    if (!tab) return;
    if (
      (tab === "honorarios" || tab === "despesas" || tab === "comissoes") &&
      onDrillDown
    ) {
      onDrillDown(tab, acao?.status, acao?.focus);
      return;
    }
    onNavigate?.(tab);
  };

  const prepararFechamento = async () => {
    if (preparandoFechamento) return;
    setPreparandoFechamento(true);
    try {
      const { data } = await api.get("/financeiro/fechamento-inteligente", {
        params: { competencia },
      });
      setPreFechamento(data);
      if (data?.total_bloqueios > 0) {
        toast.error(
          `Fechamento preparado com ${data.total_bloqueios} bloqueio(s) a corrigir.`,
        );
      } else {
        toast.success("Checklist preparado. A competência pode ser fechada.");
      }
    } catch (e: unknown) {
      toast.error(
        apiErrorMessage(e, "Não foi possível preparar o fechamento."),
      );
    } finally {
      setPreparandoFechamento(false);
    }
  };

  const fecharMes = async () => {
    if (fechando || fechamento?.id) return;
    if (!preFechamento) {
      toast.error("Prepare o fechamento antes de bloquear a competência.");
      return;
    }
    if (!preFechamento?.pode_fechar_persistente) {
      toast.error("Corrija os bloqueios do checklist antes de fechar o mês.");
      return;
    }
    setFechando(true);
    try {
      const { data } = await api.post("/financeiro/fechamentos", {
        competencia,
      });
      const baseline = data?.snapshot?.reference_baseline;
      toast.success(
        baseline?.is_baseline
          ? `Competência ${competencia} fechada. Snapshot financeiro de referência criado.`
          : `Competência ${competencia} fechada e protegida.`,
      );
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Não foi possível fechar a competência."));
    } finally {
      setFechando(false);
    }
  };

  const salvarPolitica = async () => {
    const valor = Number(limite);
    if (!Number.isFinite(valor) || valor < 0) {
      toast.error("Informe uma alçada válida.");
      return;
    }
    setSalvandoPolitica(true);
    try {
      const { data } = await api.patch("/financeiro/politica", {
        double_approval_threshold: valor,
      });
      toast.success("Alçada financeira atualizada.");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao atualizar alçada."));
    } finally {
      setSalvandoPolitica(false);
    }
  };

  const aprovarSolicitacao = async (id: string) => {
    try {
      await api.post(`/financeiro/aprovacoes/${id}/aprovar`);
      toast.success("Segunda aprovação concedida.");
      await load();
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao aprovar pagamento."));
    }
  };

  const importarExtrato = async () => {
    if (!bankFile || importandoBanco) return;
    setImportandoBanco(true);
    try {
      const fd = new FormData();
      fd.append("file", bankFile);
      const { data } = await api.post("/bank-analysis/upload", fd);
      const analysisId = data?.analise?.id;
      if (!analysisId) throw new Error("Análise bancária sem identificador");
      const recon = await api.get(`/financeiro/conciliacao/${analysisId}`);
      setConciliacao(recon.data);
      toast.success("Extrato importado. Sugestões de conciliação geradas.");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha ao importar o extrato."));
    } finally {
      setImportandoBanco(false);
    }
  };

  const confirmarConciliacao = async (item: ReconciliationSuggestion) => {
    try {
      await api.post("/financeiro/conciliacao/confirmar", {
        bank_transaction_id: item.bank_transaction_id,
        target_type: item.target_type,
        target_id: item.target_id,
      });
      const analysisId = conciliacao?.analise?.id;
      if (analysisId) {
        const { data } = await api.get(`/financeiro/conciliacao/${analysisId}`);
        setConciliacao(data);
      }
      toast.success("Movimento conciliado.");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, "Falha na conciliação."));
    }
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
        <div className="flex flex-wrap items-center gap-2">
          {Number(excecoes?.total ?? 0) > 0 && (
            <button
              type="button"
              onClick={() => setGovernancaAberta(true)}
              className="btn-secondary text-sm"
            >
              <AlertCircle className="h-4 w-4 text-amber-500" />
              {excecoes.total} exceção(ões)
            </button>
          )}
          <button
            type="button"
            onClick={() => setGovernancaAberta(true)}
            className="btn-secondary text-sm"
          >
            <ShieldCheck className="h-4 w-4" />
            Governança
          </button>
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
          value={formatBRL(aReceber)}
          detail={
            atrasado > 0
              ? `${formatBRL(atrasado)} em atraso`
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
          value={formatBRL(recebido)}
          detail="Entradas efetivas no mês"
          icon={Wallet}
          tone="blue"
          onClick={
            onDrillDown ? () => onDrillDown("honorarios", "pago") : undefined
          }
        />
        <StatCard
          label="A pagar"
          value={formatBRL(aPagar)}
          detail={`${formatBRL(saidas)} pagos no mês`}
          icon={TrendingDown}
          tone="red"
          onClick={
            onDrillDown ? () => onDrillDown("despesas", "pendente") : undefined
          }
        />
        <StatCard
          label="Saldo"
          value={formatBRL(caixa)}
          detail={`Margem ${Number(data?.margem_pct ?? 0).toLocaleString("pt-BR")}%`}
          icon={PiggyBank}
          tone={caixa >= 0 ? "green" : "red"}
        />
      </div>

      <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-white">
              <BarChart3 className="h-4 w-4 text-primary-500" />
              Rentabilidade do escritório
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Recebido − despesas dos casos − comissões − despesas gerais.
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400">Resultado líquido</p>
            <p
              className={`text-xl font-semibold ${
                Number(rentabilidade?.resumo?.resultado_escritorio ?? 0) >= 0
                  ? "text-emerald-700 dark:text-emerald-300"
                  : "text-rose-700 dark:text-rose-300"
              }`}
            >
              {formatBRL(
                Number(rentabilidade?.resumo?.resultado_escritorio ?? 0),
              )}
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {(rentabilidade?.casos ?? [])
            .slice(0, 3)
            .map((item: RentabilidadeResponse["casos"][number]) => (
              <div
                key={item.case_id}
                className="rounded-xl border border-slate-100 p-3 dark:border-slate-800"
              >
                <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                  {item.numero_interno || item.caso}
                </p>
                <p className="truncate text-xs text-slate-400">
                  {item.cliente}
                </p>
                <p className="mt-2 text-sm font-semibold">
                  {formatBRL(Number(item.resultado || 0))}
                </p>
              </div>
            ))}
          {(rentabilidade?.casos ?? []).length === 0 && (
            <p className="text-sm text-slate-400">
              Sem movimentação por caso nesta competência.
            </p>
          )}
        </div>
      </section>

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
              {formatBRL(caixa)}
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
                {formatBRL(atrasado)}
              </strong>
            </div>
            <div className="flex items-center justify-between gap-3 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                Honorários futuros
              </span>
              <strong className="text-sm text-slate-800 dark:text-slate-100">
                {formatBRL(honorariosFuturos)}
              </strong>
            </div>
            <div className="flex items-center justify-between gap-3 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                Despesas lançadas
              </span>
              <strong className="text-sm text-slate-800 dark:text-slate-100">
                {formatBRL(despesasLancadas)}
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
                    {item.valor != null ? ` · ${formatBRL(item.valor)}` : ""}
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
        open={governancaAberta}
        onClose={() => setGovernancaAberta(false)}
        title={`Governança financeira · ${competenciaLabel(competencia)}`}
        wide
      >
        <div className="space-y-5">
          <section>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold">Fechamento da competência</h3>
                <p className="text-xs text-slate-400">
                  Mês fechado preserva o snapshot. Correções continuam possíveis
                  com justificativa e auditoria.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {!fechamento?.id && (
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={preparandoFechamento}
                    onClick={prepararFechamento}
                  >
                    <ShieldCheck className="h-4 w-4" />
                    {preparandoFechamento
                      ? "Preparando..."
                      : preFechamento
                        ? "Atualizar checklist"
                        : "Preparar fechamento"}
                  </button>
                )}
                <button
                  type="button"
                  className={fechamento?.id ? "btn-secondary" : "btn-primary"}
                  disabled={
                    !!fechamento?.id ||
                    fechando ||
                    !preFechamento?.pode_fechar_persistente
                  }
                  onClick={fecharMes}
                >
                  {fechamento?.id
                    ? "Competência fechada"
                    : fechando
                      ? "Fechando..."
                      : "Fechar mês"}
                </button>
              </div>
            </div>
          </section>

          {preFechamento && !fechamento?.id && (
            <section className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="font-semibold">Checklist de fechamento</h3>
                  <p className="mt-1 text-xs text-slate-400">
                    Integridade {preFechamento.score_integridade}% ·{" "}
                    {preFechamento.total_bloqueios} bloqueio(s) ·{" "}
                    {preFechamento.total_revisoes} revisão(ões)
                  </p>
                </div>
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                    preFechamento.pode_fechar_persistente
                      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300"
                      : "bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300"
                  }`}
                >
                  {preFechamento.pode_fechar_persistente
                    ? "Pronto para fechar"
                    : "Correções obrigatórias"}
                </span>
              </div>
              {[
                ...(preFechamento.bloqueios ?? []),
                ...(preFechamento.revisoes ?? []),
              ].map((item: FinanceExceptionItem) => (
                <button
                  key={item.codigo}
                  type="button"
                  className="mt-2 flex w-full items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 text-left text-sm dark:bg-white/[0.04]"
                  onClick={() => navegarAcao(item.acao)}
                >
                  <span>
                    {item.severidade === "bloqueio" ? "Bloqueio" : "Revisar"} ·{" "}
                    {item.titulo}
                  </span>
                  <strong>{item.qtd}</strong>
                </button>
              ))}
              {preFechamento.total_bloqueios === 0 &&
                preFechamento.total_revisoes === 0 && (
                  <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">
                    Recebimentos, despesas e integridade financeira conferidos.
                  </p>
                )}
            </section>
          )}

          <section className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <h3 className="font-semibold">Exceções</h3>
            {(excecoes?.itens ?? []).length === 0 ? (
              <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-300">
                Nenhuma exceção financeira detectada.
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                {(excecoes.itens ?? []).map((item: FinanceExceptionItem) => (
                  <div
                    key={item.codigo}
                    className="rounded-xl bg-slate-50 px-3 py-2 text-sm dark:bg-white/[0.04]"
                  >
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 text-left"
                      onClick={() => navegarAcao(item.acao)}
                    >
                      <span>{item.titulo}</span>
                      <strong>
                        {item.qtd}
                        {item.valor != null
                          ? ` · ${formatBRL(Number(item.valor))}`
                          : ""}
                      </strong>
                    </button>
                    {(item.registros ?? []).length > 0 && (
                      <div className="mt-2 space-y-1 border-t border-slate-200/70 pt-2 dark:border-slate-700">
                        {(item.registros ?? []).slice(0, 5).map((registro) => (
                          <button
                            key={registro.id}
                            type="button"
                            className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-white dark:hover:bg-white/[0.06]"
                            onClick={() => navegarAcao(registro.action)}
                          >
                            <span className="truncate">{registro.label}</span>
                            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <h3 className="font-semibold">Alçada e segunda aprovação</h3>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <label className="min-w-56 flex-1">
                <span className="label">
                  Limite para segunda aprovação (R$)
                </span>
                <input
                  type="number"
                  min="0"
                  step="100"
                  className="input"
                  value={limite}
                  onChange={(e) => setLimite(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn-secondary"
                disabled={salvandoPolitica}
                onClick={salvarPolitica}
              >
                Salvar alçada
              </button>
            </div>
            {aprovacoes.length > 0 && (
              <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
                {aprovacoes.slice(0, 8).map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        {a.entity_type === "office_expense"
                          ? "Despesa"
                          : a.entity_type}
                        {" · "}
                        {formatBRL(Number(a.amount || 0))}
                      </p>
                      <p className="truncate text-xs text-slate-400">
                        Solicitado por {a.solicitado_por_nome || "usuário"}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn-secondary px-3 py-1 text-xs"
                      onClick={() => aprovarSolicitacao(a.id)}
                    >
                      Aprovar
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <h3 className="font-semibold">Conciliação bancária</h3>
            <p className="mt-1 text-xs text-slate-400">
              Importe OFX ou CSV. O sistema sugere correspondências por valor e
              data; a confirmação continua humana.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <label className="input flex min-w-56 flex-1 cursor-pointer items-center gap-2">
                <Upload className="h-4 w-4 text-slate-400" />
                <span className="truncate text-sm">
                  {bankFile?.name || "Selecionar OFX/CSV"}
                </span>
                <input
                  type="file"
                  accept=".ofx,.csv,.txt"
                  className="hidden"
                  onChange={(e) => setBankFile(e.target.files?.[0] || null)}
                />
              </label>
              <button
                type="button"
                className="btn-secondary"
                disabled={!bankFile || importandoBanco}
                onClick={importarExtrato}
              >
                {importandoBanco ? "Importando..." : "Importar e sugerir"}
              </button>
            </div>
            {conciliacao && (
              <div className="mt-3">
                <p className="text-xs text-slate-400">
                  {conciliacao.confirmados} conciliado(s) ·{" "}
                  {conciliacao.pendentes} pendente(s)
                </p>
                <div className="mt-2 max-h-64 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
                  {(conciliacao.sugestoes ?? [])
                    .filter(
                      (item: ReconciliationSuggestion) =>
                        item.status !== "rejeitado",
                    )
                    .slice(0, 20)
                    .map((item: ReconciliationSuggestion) => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between gap-3 py-2"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm">
                            {item.bank_description} ·{" "}
                            {formatBRL(Number(item.bank_value))}
                          </p>
                          <p className="truncate text-xs text-slate-400">
                            Sugestão: {item.label} · confiança{" "}
                            {Math.round(Number(item.confidence || 0) * 100)}%
                          </p>
                        </div>
                        {item.status === "confirmado" ? (
                          <span className="text-xs text-emerald-600">
                            Conciliado
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="btn-secondary px-2.5 py-1 text-xs"
                            onClick={() => confirmarConciliacao(item)}
                          >
                            Confirmar
                          </button>
                        )}
                      </div>
                    ))}
                </div>
              </div>
            )}
          </section>

          <section className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold">Distribuição societária</h3>
                <p className="text-xs text-slate-400">
                  Resultado disponível:{" "}
                  {formatBRL(Number(distribuicao?.disponivel ?? 0))}
                  {distribuicao?.fechado
                    ? " · mês fechado"
                    : " · feche o mês antes de distribuir"}
                </p>
              </div>
              <button
                type="button"
                className="btn-secondary"
                disabled={!distribuicao?.fechado}
                onClick={() =>
                  navigate("/gestao-escritorio/sociedade?sub=distribuicao")
                }
              >
                <Landmark className="h-4 w-4" />
                Ir para Sociedade
              </button>
            </div>
          </section>
        </div>
      </Modal>

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
                    {formatBRL(Number(value ?? 0))}
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
            <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-800">
              <button
                type="button"
                className="btn-secondary"
                onClick={baixarPacoteMensal}
              >
                <Download className="h-4 w-4" />
                Baixar PDF + planilhas + auditoria
              </button>
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
