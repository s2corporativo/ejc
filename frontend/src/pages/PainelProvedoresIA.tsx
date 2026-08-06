import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Clock3,
  Coins,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  XCircle,
  Zap,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner, fmtMoney } from "../components/UI";
import { toast } from "../components/Toast";
import { detalheErro } from "../utils/erro";

type ProviderRow = {
  provider: string;
  modelo_configurado?: string | null;
  elegivel: boolean;
  ordem_prioridade?: number | null;
  status: string;
  tentativas: number;
  sucessos: number;
  falhas: number;
  taxa_sucesso_pct?: number | null;
  fallbacks_concluidos: number;
  latencia_media_ms?: number | null;
  tokens_input: number;
  tokens_output: number;
  custo_brl: number;
  custo_medio_sucesso_brl?: number | null;
  ultimo_uso?: string | null;
};

type ProviderEvent = {
  id: string;
  provider: string;
  model?: string | null;
  task_type: string;
  status: string;
  duration_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  estimated_cost_brl: number;
  fallback_triggered: boolean;
  fallback_reason?: string | null;
  error_type?: string | null;
  http_status?: number | null;
  created_at?: string | null;
};

type DashboardData = {
  periodo_dias: number;
  atualizado_em: string;
  historico_disponivel: boolean;
  resumo: {
    tentativas: number;
    sucessos: number;
    falhas: number;
    taxa_sucesso_pct?: number | null;
    fallbacks_concluidos: number;
    latencia_media_ms?: number | null;
    tokens_input: number;
    tokens_output: number;
    custo_brl: number;
  };
  configuracao: {
    ia_habilitada: boolean;
    externos_permitidos: boolean;
    prioridade: string[];
  };
  provedores: ProviderRow[];
  comparacao: { melhor_equilibrio?: string | null; criterio: string };
  por_tarefa: Array<{
    task_type: string;
    provider: string;
    tentativas: number;
    sucessos: number;
    taxa_sucesso_pct?: number | null;
    latencia_media_ms?: number | null;
    custo_brl: number;
  }>;
  eventos_recentes: ProviderEvent[];
  privacidade: string;
  observacao: string;
};

// Custos de tokens usam 4 casas; ausente vira R$ 0,00 (painel soma custos).
const brl = (valor?: number | null) => fmtMoney(valor ?? 0, 4);

const inteiro = (valor?: number | null) => (valor ?? 0).toLocaleString("pt-BR");

const dataHora = (valor?: string | null) =>
  valor ? new Date(valor).toLocaleString("pt-BR") : "—";

const nomeProvider = (provider: string) =>
  ({
    anthropic: "Anthropic",
    maritaca: "Maritaca",
    groq: "Groq",
    ollama: "Ollama",
  })[provider] || provider;

function StatusBadge({ status }: { status: string }) {
  const classes: Record<string, string> = {
    operacional: "bg-success-50 text-success-700 ring-success-200",
    atencao: "bg-warn-50 text-warn-800 ring-warn-200",
    indisponivel: "bg-danger-50 text-danger-700 ring-danger-200",
    configurado_sem_uso: "bg-primary-50 text-primary-700 ring-primary-200",
    desabilitado: "bg-slate-100 text-slate-500 ring-slate-200",
  };
  const labels: Record<string, string> = {
    operacional: "Operacional",
    atencao: "Atenção",
    indisponivel: "Indisponível",
    configurado_sem_uso: "Configurado, sem uso",
    desabilitado: "Desabilitado",
  };
  return (
    <span
      className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ring-1 ${classes[status] || classes.desabilitado}`}
    >
      {labels[status] || status}
    </span>
  );
}

function Kpi({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: typeof Activity;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            {label}
          </p>
          <p className="mt-1 text-2xl font-serif text-navy dark:text-white">
            {value}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
            {hint}
          </p>
        </div>
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary-50 text-primary-700 dark:bg-white/10 dark:text-primary-200">
          <Icon className="h-5 w-5" />
        </span>
      </div>
    </div>
  );
}

export default function PainelProvedoresIA() {
  const navigate = useNavigate();
  const [dias, setDias] = useState(30);
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const carregar = useCallback(
    async (silencioso = false) => {
      if (silencioso) setRefreshing(true);
      else setLoading(true);
      try {
        const response = await api.get("/ia-governanca/provedores", {
          params: { dias, limite: 50 },
        });
        setData(response.data);
      } catch (error: unknown) {
        toast.error(
          detalheErro(
            error,
            "Não foi possível carregar as métricas dos provedores.",
          ),
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [dias],
  );

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void carregar(true), 30_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, carregar]);

  const falhasRecentes = useMemo(
    () =>
      data?.eventos_recentes.filter((evento) => evento.status !== "sucesso") ||
      [],
    [data],
  );

  if (loading && !data) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }

  const resumo = data?.resumo;

  return (
    <div className="space-y-5 pb-10">
      <PageHeader
        eyebrow="Governança da IA"
        title="Inteligência dos Provedores"
        subtitle="Operação, desempenho, custo, consumo e fallback de Anthropic, Maritaca, Groq e Ollama"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button
              className="btn-secondary"
              onClick={() => navigate("/ia-governanca")}
            >
              <ArrowLeft className="h-4 w-4" /> Voltar
            </button>
            <select
              className="input w-auto"
              value={dias}
              onChange={(event) => setDias(Number(event.target.value))}
              aria-label="Período das métricas"
            >
              <option value={7}>7 dias</option>
              <option value={30}>30 dias</option>
              <option value={90}>90 dias</option>
              <option value={365}>365 dias</option>
            </select>
            <button
              className="btn-secondary"
              onClick={() => void carregar(true)}
              disabled={refreshing}
            >
              <RefreshCw
                className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
              />
              Atualizar
            </button>
          </div>
        }
      />

      {!data?.historico_disponivel && (
        <div className="card border-l-4 border-l-warn-500 p-4">
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-warn-600" />
            <div>
              <h3 className="font-semibold text-ink">
                Histórico ainda indisponível
              </h3>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                A migration 111 precisa ser aplicada. A operação da IA continua
                ativa, mas as novas métricas ainda não podem ser consultadas.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Taxa de sucesso"
          value={
            resumo?.taxa_sucesso_pct != null
              ? `${resumo.taxa_sucesso_pct}%`
              : "—"
          }
          hint={`${inteiro(resumo?.sucessos)} sucessos em ${inteiro(resumo?.tentativas)} tentativas`}
          icon={CheckCircle2}
        />
        <Kpi
          label="Latência média"
          value={
            resumo?.latencia_media_ms != null
              ? `${inteiro(resumo.latencia_media_ms)} ms`
              : "—"
          }
          hint="Somente chamadas concluídas"
          icon={Clock3}
        />
        <Kpi
          label="Fallbacks concluídos"
          value={inteiro(resumo?.fallbacks_concluidos)}
          hint={`${inteiro(resumo?.falhas)} falhas técnicas no período`}
          icon={Zap}
        />
        <Kpi
          label="Custo estimado"
          value={brl(resumo?.custo_brl)}
          hint={`${inteiro(resumo?.tokens_input)} tokens de entrada · ${inteiro(resumo?.tokens_output)} de saída`}
          icon={Coins}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4 dark:border-white/10">
            <div>
              <h2 className="font-semibold text-ink">
                Comparativo por provedor
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-300">
                Métricas reais das tentativas feitas pelo gateway único.
              </p>
            </div>
            {data?.comparacao?.melhor_equilibrio && (
              <span className="inline-flex items-center gap-1 rounded-full bg-success-50 px-3 py-1 text-xs font-medium text-success-700 ring-1 ring-success-200">
                <Sparkles className="h-3.5 w-3.5" /> Melhor equilíbrio:{" "}
                {nomeProvider(data.comparacao.melhor_equilibrio)}
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400 dark:bg-white/[0.03]">
                <tr>
                  <th className="px-4 py-3">Provedor / modelo</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Sucesso</th>
                  <th className="px-4 py-3 text-right">Latência</th>
                  <th className="px-4 py-3 text-right">Chamadas</th>
                  <th className="px-4 py-3 text-right">Fallbacks</th>
                  <th className="px-4 py-3 text-right">Tokens</th>
                  <th className="px-4 py-3 text-right">Custo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/10">
                {data?.provedores.map((provider) => (
                  <tr key={provider.provider}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary-50 text-primary-700 dark:bg-white/10 dark:text-primary-200">
                          <Bot className="h-4 w-4" />
                        </span>
                        <div>
                          <div className="font-medium text-navy dark:text-white">
                            {nomeProvider(provider.provider)}
                            {provider.ordem_prioridade && (
                              <span className="ml-2 text-xs font-normal text-slate-400">
                                #{provider.ordem_prioridade} na prioridade
                              </span>
                            )}
                          </div>
                          <div className="max-w-64 truncate text-xs text-slate-400">
                            {provider.modelo_configurado ||
                              "Modelo não informado"}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={provider.status} />
                    </td>
                    <td className="px-4 py-3 text-right font-medium">
                      {provider.taxa_sucesso_pct != null
                        ? `${provider.taxa_sucesso_pct}%`
                        : "—"}
                      <div className="text-xs font-normal text-slate-400">
                        {provider.sucessos}/{provider.tentativas}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {provider.latencia_media_ms != null
                        ? `${inteiro(provider.latencia_media_ms)} ms`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {inteiro(provider.tentativas)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {inteiro(provider.fallbacks_concluidos)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {inteiro(provider.tokens_input + provider.tokens_output)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {brl(provider.custo_brl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <div className="card p-4">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary-600" />
              <h2 className="font-semibold text-ink">Operação atual</h2>
            </div>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">IA habilitada</dt>
                <dd className="font-medium">
                  {data?.configuracao.ia_habilitada ? "Sim" : "Não"}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Provedores externos</dt>
                <dd className="font-medium">
                  {data?.configuracao.externos_permitidos
                    ? "Permitidos"
                    : "Bloqueados"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Ordem de prioridade</dt>
                <dd className="mt-2 flex flex-wrap gap-1">
                  {data?.configuracao.prioridade.map((provider, index) => (
                    <span
                      key={provider}
                      className="rounded-full bg-slate-100 px-2 py-1 text-xs dark:bg-white/10"
                    >
                      {index + 1}. {nomeProvider(provider)}
                    </span>
                  ))}
                </dd>
              </div>
            </dl>
          </div>

          <div className="card p-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-success-600" />
              <h2 className="font-semibold text-ink">Privacidade</h2>
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {data?.privacidade}
            </p>
          </div>

          <label className="card flex cursor-pointer items-center justify-between gap-3 p-4">
            <div>
              <div className="font-medium text-ink">Atualização automática</div>
              <div className="text-xs text-slate-500">
                Recarrega a cada 30 segundos
              </div>
            </div>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
              className="h-4 w-4"
            />
          </label>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="border-b border-slate-100 p-4 dark:border-white/10">
            <h2 className="font-semibold text-ink">
              Desempenho por tipo de tarefa
            </h2>
            <p className="text-sm text-slate-500">
              Top 60 combinações no período.
            </p>
          </div>
          <div className="max-h-[420px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-400 dark:bg-slate-900">
                <tr>
                  <th className="px-4 py-3">Tarefa</th>
                  <th className="px-4 py-3">Provedor</th>
                  <th className="px-4 py-3 text-right">Sucesso</th>
                  <th className="px-4 py-3 text-right">Latência</th>
                  <th className="px-4 py-3 text-right">Custo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/10">
                {data?.por_tarefa.map((item) => (
                  <tr key={`${item.task_type}-${item.provider}`}>
                    <td className="px-4 py-3">{item.task_type}</td>
                    <td className="px-4 py-3">{nomeProvider(item.provider)}</td>
                    <td className="px-4 py-3 text-right">
                      {item.taxa_sucesso_pct != null
                        ? `${item.taxa_sucesso_pct}%`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {item.latencia_media_ms != null
                        ? `${inteiro(item.latencia_media_ms)} ms`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {brl(item.custo_brl)}
                    </td>
                  </tr>
                ))}
                {!data?.por_tarefa.length && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-slate-400"
                    >
                      Sem dados no período.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 p-4 dark:border-white/10">
            <div>
              <h2 className="font-semibold text-ink">
                Falhas e motivos de fallback
              </h2>
              <p className="text-sm text-slate-500">
                Somente classes de erro seguras, sem conteúdo da requisição.
              </p>
            </div>
            <span className="rounded-full bg-danger-50 px-2 py-1 text-xs font-medium text-danger-700">
              {falhasRecentes.length} recentes
            </span>
          </div>
          <div className="max-h-[420px] overflow-auto divide-y divide-slate-100 dark:divide-white/10">
            {falhasRecentes.map((evento) => (
              <div key={evento.id} className="p-4">
                <div className="flex items-start gap-3">
                  {evento.status === "bloqueado_lgpd" ? (
                    <ShieldCheck className="mt-0.5 h-5 w-5 text-warn-600" />
                  ) : (
                    <XCircle className="mt-0.5 h-5 w-5 text-danger-600" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-medium text-ink">
                        {nomeProvider(evento.provider)} · {evento.task_type}
                      </div>
                      <time className="text-xs text-slate-400">
                        {dataHora(evento.created_at)}
                      </time>
                    </div>
                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                      {evento.fallback_reason ||
                        evento.error_type ||
                        "Falha técnica sem detalhe"}
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      {inteiro(evento.duration_ms)} ms
                      {evento.http_status
                        ? ` · HTTP ${evento.http_status}`
                        : ""}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {!falhasRecentes.length && (
              <div className="p-8 text-center text-sm text-slate-400">
                Nenhuma falha registrada no período selecionado.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card p-4 text-xs text-slate-500 dark:text-slate-300">
        <strong>Critério comparativo:</strong> {data?.comparacao.criterio}.{" "}
        {data?.observacao}
        <span className="ml-2">
          Atualizado em {dataHora(data?.atualizado_em)}.
        </span>
      </div>
    </div>
  );
}
