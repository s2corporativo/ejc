import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  Clock3,
  FileText,
  Gavel,
  LockKeyhole,
  RefreshCw,
  Route,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import CaseBreadcrumb from "../components/CaseBreadcrumb";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  cn,
  fmtDate,
} from "../components/UI";

type JornadaStatus = "concluida" | "em_andamento" | "pendente" | "bloqueada";

type AcaoOrquestrador = {
  acao: string;
  metodo: string;
  endpoint: string;
  payload_esperado?: Record<string, unknown>;
  executavel_via_orquestrador: boolean;
};

type PendenciaOrquestrador = {
  tipo: string;
  detalhe: string;
  endpoint?: string;
  itens?: Array<Record<string, unknown>>;
};

type JornadaItem = {
  etapa: string;
  rotulo: string;
  status: JornadaStatus;
};

type EventoOrquestrador = {
  versao: number;
  origem: string;
  estado?: string | null;
  resumo?: string | null;
  congelado: boolean;
  criado_em?: string | null;
};

type VisaoOrquestrador = {
  case_id: string;
  estado: string;
  estado_rotulo: string;
  estados: string[];
  proximo_passo: {
    estado: string;
    estado_rotulo: string;
    passo_recomendado: string;
    acoes_disponiveis: AcaoOrquestrador[];
    pendencias_bloqueantes: PendenciaOrquestrador[];
  };
  jornada: JornadaItem[];
  linha_do_tempo: EventoOrquestrador[];
};

type CasoResumo = {
  id: string;
  titulo?: string | null;
  numero_processo?: string | null;
  numero_interno?: string | null;
  fase?: string | null;
};

const STATUS_META: Record<
  JornadaStatus,
  {
    label: string;
    icon: typeof Circle;
    badge: "green" | "amber" | "slate" | "red";
    circle: string;
    line: string;
  }
> = {
  concluida: {
    label: "Concluída",
    icon: CheckCircle2,
    badge: "green",
    circle: "bg-success-100 text-success-700 ring-success-200",
    line: "bg-success-300",
  },
  em_andamento: {
    label: "Em andamento",
    icon: Clock3,
    badge: "amber",
    circle: "bg-warn-100 text-warn-700 ring-warn-200",
    line: "bg-warn-300",
  },
  bloqueada: {
    label: "Requer validação",
    icon: LockKeyhole,
    badge: "red",
    circle: "bg-danger-100 text-danger-700 ring-danger-200",
    line: "bg-danger-200",
  },
  pendente: {
    label: "Pendente",
    icon: Circle,
    badge: "slate",
    circle: "bg-slate-100 text-slate-500 ring-slate-200",
    line: "bg-slate-200",
  },
};

const ESTADO_DESTINO: Record<string, (caseId: string) => string> = {
  entrada: (id) => `/documentos?caso=${id}`,
  compreensao: (id) => `/casos/${id}?tab=resumo`,
  classificacao: (id) => `/casos/${id}/sala-de-guerra`,
  validacao_processual: (id) => `/casos/${id}/sala-de-guerra`,
  estrategia: (id) => `/casos/${id}/sala-de-guerra`,
  contratacao: (id) => `/casos/${id}?tab=contratos`,
  producao: (id) => `/pecas?caso=${id}`,
  revisao: (id) => `/pecas?caso=${id}`,
  protocolo: (id) => `/pecas?caso=${id}`,
  acompanhamento: (id) => `/atividades?caso=${id}`,
};

function destinoDaProximaAcao(estado: string, caseId: string): string {
  return (ESTADO_DESTINO[estado] ?? ((id: string) => `/casos/${id}`))(caseId);
}

function rotuloOrigem(origem: string): string {
  const mapa: Record<string, string> = {
    triagem: "Triagem",
    intake: "Leitura inicial",
    raio_x: "Raio-X",
    manual: "Registro manual",
    motor_peca: "Validação processual",
    matriz_teses: "Matriz de teses",
    orquestrador: "Jornada do caso",
  };
  return mapa[origem] ?? origem.replaceAll("_", " ");
}

export default function JornadaCaso() {
  const { id } = useParams<{ id: string }>();
  const [visao, setVisao] = useState<VisaoOrquestrador | null>(null);
  const [caso, setCaso] = useState<CasoResumo | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);
  const [jornadaAberta, setJornadaAberta] = useState(false);
  const [historicoAberto, setHistoricoAberto] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setErro(false);
    try {
      const [orquestrador, casoResp] = await Promise.all([
        api.get<VisaoOrquestrador>(`/cases/${id}/orquestrador`),
        api.get<CasoResumo>(`/cases/${id}`),
      ]);
      setVisao(orquestrador.data);
      setCaso(casoResp.data);
    } catch {
      setErro(true);
      toast.error("Falha ao carregar a jornada operacional do caso");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const progresso = useMemo(() => {
    const total = visao?.jornada.length ?? 0;
    const concluidas =
      visao?.jornada.filter((item) => item.status === "concluida").length ?? 0;
    return {
      total,
      concluidas,
      percentual: total > 0 ? Math.round((concluidas / total) * 100) : 0,
    };
  }, [visao]);

  const etapaAtual = useMemo(
    () =>
      visao?.jornada.find(
        (item) => item.status === "em_andamento" || item.status === "bloqueada",
      ) ?? null,
    [visao],
  );

  if (loading && !visao) return <Spinner />;

  if (erro && !visao) {
    return (
      <EmptyState
        icon={Route}
        title="Falha ao carregar a jornada"
        message="Não foi possível calcular o estado do caso a partir dos documentos, análises, teses, honorários, peças e prazos registrados."
        action={
          <Button variant="primary" onClick={load} icon={<RefreshCw className="h-4 w-4" />}>
            Tentar novamente
          </Button>
        }
      />
    );
  }

  if (!visao || !id) return null;

  const titulo = caso?.titulo || "Caso";
  const referencia = caso?.numero_processo || caso?.numero_interno || "Sem número processual";
  const destino = destinoDaProximaAcao(visao.estado, id);
  const pendencias = visao.proximo_passo.pendencias_bloqueantes ?? [];
  const historico = [...(visao.linha_do_tempo ?? [])].reverse();

  return (
    <div className="space-y-6">
      <CaseBreadcrumb caseId={id} titulo={titulo} tela="Jornada" />

      <PageHeader
        eyebrow={caso?.fase ? `Fase cadastrada: ${caso.fase}` : "Fluxo jurídico do caso"}
        title={`Jornada — ${titulo}`}
        subtitle={`${referencia} · ${progresso.percentual}% concluído · estado calculado pelos artefatos reais do caso`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={load} icon={<RefreshCw className="h-4 w-4" />}>
              Atualizar
            </Button>
            <Link to={`/casos/${id}`}>
              <Button variant="secondary" icon={<Gavel className="h-4 w-4" />}>
                Abrir caso
              </Button>
            </Link>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.4fr]">
        <Card className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Onde o caso está
              </p>
              <h2 className="mt-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
                {visao.estado_rotulo}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                {etapaAtual?.rotulo || "Todas as etapas previstas foram concluídas."}
              </p>
            </div>
            <span className="rounded-2xl bg-primary-50 p-3 text-primary-700 ring-1 ring-inset ring-primary-100 dark:bg-primary-500/10 dark:text-primary-200">
              <Route className="h-6 w-6" />
            </span>
          </div>

          <div className="mt-5">
            <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
              <span>{progresso.concluidas} de {progresso.total} etapas concluídas</span>
              <span className="font-semibold tabular-nums">{progresso.percentual}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10">
              <div
                className="h-full rounded-full bg-success-500 transition-all"
                style={{ width: `${progresso.percentual}%` }}
              />
            </div>
          </div>
        </Card>

        <Card className="border-primary-100 bg-gradient-to-br from-primary-50/80 via-white to-white p-5 dark:border-primary-500/20 dark:from-primary-500/10 dark:via-transparent dark:to-transparent">
          <div className="flex items-start gap-4">
            <span className="rounded-2xl bg-primary-600 p-3 text-white shadow-sm">
              <Sparkles className="h-6 w-6" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary-700 dark:text-primary-200">
                  Próxima ação recomendada
                </p>
                {pendencias.length > 0 && (
                  <Badge tone="amber">{pendencias.length} pendência(s)</Badge>
                )}
              </div>
              <h2 className="mt-2 text-lg font-semibold text-slate-900 dark:text-slate-100">
                {visao.proximo_passo.passo_recomendado}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                A recomendação é determinística e usa somente documentos, análises aprovadas,
                teses, contratação, peças e prazos efetivamente registrados.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link to={destino}>
                  <Button variant="primary" icon={<ArrowRight className="h-4 w-4" />}>
                    Continuar jornada
                  </Button>
                </Link>
                <Link to={`/documentos?caso=${id}`}>
                  <Button variant="secondary" icon={<FileText className="h-4 w-4" />}>
                    Ver documentos
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {pendencias.length > 0 && (
        <Card className="border-warn-200 p-5 dark:border-warn-500/25">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warn-600" />
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold text-slate-900 dark:text-slate-100">
                O que impede o avanço
              </h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">
                Aprovações jurídicas, confirmação de prazo e atos externos continuam obrigatoriamente humanos.
              </p>
              <div className="mt-4 space-y-2">
                {pendencias.map((pendencia, index) => (
                  <div
                    key={`${pendencia.tipo}-${index}`}
                    className="rounded-xl bg-warn-50 px-4 py-3 text-sm text-warn-900 ring-1 ring-inset ring-warn-200/70 dark:bg-warn-500/10 dark:text-warn-100"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="amber">{pendencia.tipo.replaceAll("_", " ")}</Badge>
                      <span>{pendencia.detalhe}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      <Card className="overflow-hidden">
        <button
          type="button"
          onClick={() => setJornadaAberta((aberta) => !aberta)}
          className="flex w-full items-center justify-between gap-4 p-5 text-left hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.03]"
          aria-expanded={jornadaAberta}
        >
          <div>
            <h2 className="font-semibold text-slate-900 dark:text-slate-100">
              Jornada completa
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">
              Sequência única derivada pelo Orquestrador Jurídico.
            </p>
          </div>
          {jornadaAberta ? (
            <ChevronUp className="h-5 w-5 text-slate-400" />
          ) : (
            <ChevronDown className="h-5 w-5 text-slate-400" />
          )}
        </button>

        {jornadaAberta && (
          <div className="border-t border-slate-100 p-5 dark:border-white/10">
            <ol className="space-y-0">
              {visao.jornada.map((item, index) => {
                const meta = STATUS_META[item.status];
                const Icon = meta.icon;
                const ultimo = index === visao.jornada.length - 1;
                return (
                  <li key={item.etapa} className="relative flex gap-4 pb-5 last:pb-0">
                    {!ultimo && (
                      <span
                        className={cn(
                          "absolute left-[17px] top-9 h-[calc(100%-1.25rem)] w-0.5",
                          meta.line,
                        )}
                      />
                    )}
                    <span
                      className={cn(
                        "relative z-10 grid h-9 w-9 shrink-0 place-items-center rounded-full ring-1 ring-inset",
                        meta.circle,
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1 pt-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                          {item.rotulo}
                        </span>
                        <Badge tone={meta.badge}>{meta.label}</Badge>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </Card>

      {historico.length > 0 && (
        <Card className="overflow-hidden">
          <button
            type="button"
            onClick={() => setHistoricoAberto((aberto) => !aberto)}
            className="flex w-full items-center justify-between gap-4 p-5 text-left hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.03]"
            aria-expanded={historicoAberto}
          >
            <div>
              <h2 className="font-semibold text-slate-900 dark:text-slate-100">
                Histórico de análises e transições
              </h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">
                {historico.length} registro(s) rastreável(is) no caso.
              </p>
            </div>
            {historicoAberto ? (
              <ChevronUp className="h-5 w-5 text-slate-400" />
            ) : (
              <ChevronDown className="h-5 w-5 text-slate-400" />
            )}
          </button>

          {historicoAberto && (
            <div className="divide-y divide-slate-100 border-t border-slate-100 dark:divide-white/10 dark:border-white/10">
              {historico.map((evento) => (
                <div key={`${evento.versao}-${evento.origem}`} className="flex gap-3 px-5 py-4">
                  <span className="mt-0.5 rounded-xl bg-slate-100 p-2 text-slate-500 dark:bg-white/10 dark:text-slate-300">
                    {evento.congelado ? (
                      <ShieldCheck className="h-4 w-4" />
                    ) : (
                      <Clock3 className="h-4 w-4" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-semibold text-slate-800 dark:text-slate-100">
                        {rotuloOrigem(evento.origem)}
                      </span>
                      {evento.estado && <Badge tone="slate">{evento.estado.replaceAll("_", " ")}</Badge>}
                      {evento.congelado && <Badge tone="green">Aprovado pelo advogado</Badge>}
                    </div>
                    {evento.resumo && (
                      <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">
                        {evento.resumo}
                      </p>
                    )}
                    {evento.criado_em && (
                      <p className="mt-1 text-xs text-slate-400">{fmtDate(evento.criado_em)}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
