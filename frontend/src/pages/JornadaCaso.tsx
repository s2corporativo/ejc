import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  BarChart3,
  CalendarClock,
  CheckSquare,
  ChevronDown,
  FileText,
  Filter,
  FolderOpen,
  Gavel,
  Send,
  Sparkles,
  Target,
  Users,
  type LucideIcon,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { useAuth } from "../stores/auth";
import CaseBreadcrumb from "../components/CaseBreadcrumb";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  cn,
} from "../components/UI";

// ─── Contrato da API (GET /casos/{case_id}/jornada) ───────────────────────
// DECISÃO: tipos declarados localmente porque a jornada é consumida apenas
// por esta página (mesmo padrão de tipos locais usado em Kanban.tsx).
type JornadaEtapaChave =
  | "cliente"
  | "triagem"
  | "documentos"
  | "inteligencia"
  | "estrategia"
  | "producao"
  | "revisao"
  | "protocolo"
  | "gestao";

type JornadaEtapaStatus = "pendente" | "em_andamento" | "concluida";

interface JornadaEtapa {
  chave: JornadaEtapaChave;
  titulo: string;
  status: JornadaEtapaStatus;
  resumo: string;
  pendencias: string[];
  link_modulo: string;
}

interface JornadaCasoResp {
  case_id: string;
  titulo: string;
  fase: string | null;
  numero_processo: string | null;
  cliente_id: string | null;
  etapas: JornadaEtapa[];
}

// pendente=cinza, em_andamento=âmbar, concluida=verde (tons do Badge de UI.tsx)
const STATUS_META: Record<
  JornadaEtapaStatus,
  { label: string; tone: "slate" | "amber" | "green"; circle: string }
> = {
  pendente: {
    label: "Pendente",
    tone: "slate",
    circle: "bg-slate-100 text-slate-500 ring-slate-200",
  },
  em_andamento: {
    label: "Em andamento",
    tone: "amber",
    circle: "bg-warn-50 text-warn-700 ring-warn-200",
  },
  concluida: {
    label: "Concluída",
    tone: "green",
    circle: "bg-success-50 text-success-700 ring-success-200",
  },
};

const ETAPA_ICON: Record<JornadaEtapaChave, LucideIcon> = {
  cliente: Users,
  triagem: Filter,
  documentos: FolderOpen,
  inteligencia: Sparkles,
  estrategia: Target,
  producao: FileText,
  revisao: CheckSquare,
  protocolo: Send,
  gestao: BarChart3,
};

// Verbo de ação por etapa (substitui o botão genérico "Abrir módulo"): diz ao
// advogado O QUE FAZER — o destino continua sendo resolvido por rotaModulo().
const ETAPA_ACAO: Record<JornadaEtapaChave, string> = {
  cliente: "Confirmar dados",
  triagem: "Fazer triagem",
  documentos: "Enviar documentos",
  inteligencia: "Gerar dossiê",
  estrategia: "Definir estratégia",
  producao: "Redigir peça",
  revisao: "Revisar minuta",
  protocolo: "Registrar protocolo",
  gestao: "Acompanhar processo",
};

// ─── Fases (agrupamento humano das 9 etapas técnicas) ─────────────────────
// DECISÃO: as 5 fases são só uma CAMADA DE APRESENTAÇÃO — as etapas técnicas
// e suas rotas permanecem intactas; cada etapa é mapeada para a fase dona.
type FaseChave =
  | "entrada"
  | "analise"
  | "producao"
  | "protocolo"
  | "acompanhamento";

const FASE_DE_ETAPA: Record<JornadaEtapaChave, FaseChave> = {
  cliente: "entrada",
  triagem: "entrada",
  documentos: "entrada",
  inteligencia: "analise",
  estrategia: "analise",
  producao: "producao",
  revisao: "producao",
  protocolo: "protocolo",
  gestao: "acompanhamento",
};

const FASES: {
  chave: FaseChave;
  titulo: string;
  descricao: string;
  icon: LucideIcon;
}[] = [
  {
    chave: "entrada",
    titulo: "Entrada",
    descricao: "Cliente, triagem e documentos",
    icon: Users,
  },
  {
    chave: "analise",
    titulo: "Análise",
    descricao: "Inteligência e estratégia",
    icon: Sparkles,
  },
  {
    chave: "producao",
    titulo: "Produção",
    descricao: "Redação e revisão da peça",
    icon: FileText,
  },
  {
    chave: "protocolo",
    titulo: "Protocolo",
    descricao: "Registro do processo",
    icon: Send,
  },
  {
    chave: "acompanhamento",
    titulo: "Acompanhamento",
    descricao: "Movimentos, prazos e encerramento",
    icon: BarChart3,
  },
];

// DECISÃO: mapa chave→rota resolvido no frontend (rotas reais do
// moduleRegistry); link_modulo do backend é usado apenas como fallback.
// GAP fechado (Modo Caso): Documentos, Peças e Prazos agora leem `?caso=`
// da URL (e o caso ativo do contexto) e filtram a listagem por ele.
function rotaModulo(etapa: JornadaEtapa, jornada: JornadaCasoResp): string {
  switch (etapa.chave) {
    case "cliente":
      return jornada.cliente_id
        ? `/clientes/${jornada.cliente_id}`
        : etapa.link_modulo || "/clientes";
    case "triagem":
      // Etapa 2: Entrevista Inteligente — relato livre + painel de confiança IA
      return `/casos/${jornada.case_id}/entrevista`;
    case "protocolo":
      return `/casos/${jornada.case_id}`;
    case "documentos":
      return `/documentos?caso=${jornada.case_id}`;
    case "inteligencia":
    case "estrategia":
      // Não existe tela dedicada de dossiê estratégico: a Sala de Guerra
      // (/casos/:caseId/sala-de-guerra) é o módulo de estratégia por caso.
      return `/casos/${jornada.case_id}/sala-de-guerra`;
    case "producao":
    case "revisao":
      return `/pecas?caso=${jornada.case_id}`;
    case "gestao":
      return `/prazos?caso=${jornada.case_id}`;
    default:
      return etapa.link_modulo || `/casos/${jornada.case_id}`;
  }
}

// Status agregado de uma fase a partir das etapas que ela contém.
function statusDaFase(etapas: JornadaEtapa[]): JornadaEtapaStatus {
  if (etapas.length === 0) return "pendente";
  if (etapas.every((e) => e.status === "concluida")) return "concluida";
  if (etapas.some((e) => e.status !== "pendente")) return "em_andamento";
  return "pendente";
}

// Botão que leva ao módulo da etapa com o VERBO de ação certo (mesmo destino
// de antes; só muda rótulo/ícone). `primary` destaca a próxima ação do foco.
function AcaoEtapa({
  etapa,
  jornada,
  primary,
  className,
}: {
  etapa: JornadaEtapa;
  jornada: JornadaCasoResp;
  primary?: boolean;
  className?: string;
}) {
  const Icon = ETAPA_ICON[etapa.chave] ?? FileText;
  return (
    <Link
      to={rotaModulo(etapa, jornada)}
      className={cn("w-full shrink-0 sm:w-auto", className)}
    >
      <Button
        variant={primary ? "primary" : "secondary"}
        size="sm"
        className="w-full sm:w-auto"
        icon={<Icon className="h-3.5 w-3.5" />}
      >
        {ETAPA_ACAO[etapa.chave] ?? "Abrir etapa"}
      </Button>
    </Link>
  );
}

// Lista de pendências impeditivas (âmbar) — reusa o padrão visual do EJC.
function Pendencias({ itens }: { itens: string[] }) {
  if (itens.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1">
      {itens.map((pendencia, i) => (
        <li
          key={i}
          className="flex items-start gap-1.5 text-xs text-warn-700"
        >
          <span
            className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-warn-400"
            aria-hidden="true"
          />
          {pendencia}
        </li>
      ))}
    </ul>
  );
}

export default function JornadaCaso() {
  const { id } = useParams<{ id: string }>();
  const user = useAuth((s) => s.user);
  const [jornada, setJornada] = useState<JornadaCasoResp | null>(null);
  const [erro, setErro] = useState(false);
  const [loading, setLoading] = useState(true);
  // Jornada completa recolhida por padrão: a tela abre no "o que fazer agora".
  const [completaAberta, setCompletaAberta] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    setLoading(true);
    setErro(false);
    api
      .get<JornadaCasoResp>(`/casos/${id}/jornada`)
      .then((r) => setJornada(r.data))
      .catch(() => {
        setErro(true);
        toast.error("Falha ao carregar a jornada do caso");
      })
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(load, [load]);

  if (loading && !jornada) return <Spinner />;

  if (erro && !jornada) {
    return (
      <EmptyState
        title="Falha ao carregar a jornada"
        message="Não foi possível carregar a jornada do caso. Verifique sua conexão e tente novamente."
        action={
          <Button variant="primary" onClick={load}>
            Tentar novamente
          </Button>
        }
      />
    );
  }

  if (!jornada) return null;

  const total = jornada.etapas.length;
  const concluidas = jornada.etapas.filter(
    (e) => e.status === "concluida",
  ).length;
  const pct = total > 0 ? Math.round((concluidas / total) * 100) : 0;

  // Etapa atual = primeira que ainda não foi concluída (ordem canônica do
  // backend). Se todas concluídas, a jornada terminou.
  const idxAtual = jornada.etapas.findIndex((e) => e.status !== "concluida");
  const jornadaConcluida = idxAtual === -1;
  const etapaAtual = jornadaConcluida ? null : jornada.etapas[idxAtual];
  const faseAtualChave = etapaAtual ? FASE_DE_ETAPA[etapaAtual.chave] : null;
  const faseAtual = FASES.find((f) => f.chave === faseAtualChave) ?? null;

  return (
    <div>
      <CaseBreadcrumb
        caseId={jornada.case_id}
        titulo={jornada.titulo}
        tela="Jornada"
      />
      <PageHeader
        eyebrow={jornada.fase ? `Fase: ${jornada.fase}` : undefined}
        title={`Jornada — ${jornada.titulo}`}
        subtitle={[
          jornada.numero_processo
            ? `Processo ${jornada.numero_processo}`
            : "Sem número de processo",
          `${pct}% concluído · ${concluidas} de ${total} etapas`,
        ].join(" · ")}
        actions={
          <Link to={`/casos/${jornada.case_id}`}>
            <Button variant="secondary" icon={<Gavel className="h-4 w-4" />}>
              Abrir caso
            </Button>
          </Link>
        }
      />

      {/* ── FOCO AGORA: o que fazer neste momento ─────────────────────── */}
      <Card className="border-l-4 border-l-slate-900 p-5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {jornadaConcluida ? "Jornada" : "Foco agora"}
          </span>
          {faseAtual && (
            <Badge tone="blue">
              {faseAtual.titulo}
            </Badge>
          )}
        </div>

        {jornadaConcluida || !etapaAtual ? (
          <div className="mt-2">
            <h2 className="text-base font-semibold text-slate-950">
              Todas as etapas concluídas
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              A jornada deste caso está completa. Continue o acompanhamento
              pelos prazos e movimentos.
            </p>
          </div>
        ) : (
          <div className="mt-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-slate-950">
                {etapaAtual.titulo}
              </h2>
              <Badge tone={STATUS_META[etapaAtual.status].tone}>
                {STATUS_META[etapaAtual.status].label}
              </Badge>
            </div>
            {etapaAtual.resumo && (
              <p className="mt-1 text-sm text-slate-500">{etapaAtual.resumo}</p>
            )}

            {/* Pendência impeditiva */}
            {etapaAtual.pendencias.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold text-warn-700">
                  Pendência que trava esta etapa
                </p>
                <Pendencias itens={etapaAtual.pendencias} />
              </div>
            )}

            {/* Responsável · Prazo */}
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                Responsável:{" "}
                <span className="font-medium text-slate-700">
                  {user?.full_name ?? "—"}
                </span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CalendarClock className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                Prazo:{" "}
                <span className="font-medium text-slate-700">
                  {jornada.numero_processo ? "Ver em Prazos" : "Sem prazo definido"}
                </span>
              </span>
            </div>

            {/* Próxima ação recomendada */}
            <div className="mt-4">
              <p className="mb-1.5 text-xs font-semibold text-slate-500">
                Próxima ação
              </p>
              <AcaoEtapa etapa={etapaAtual} jornada={jornada} primary />
            </div>
          </div>
        )}

        {/* Percentual concluído */}
        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between text-xs text-slate-500">
            <span>Progresso da jornada</span>
            <span className="font-medium text-slate-700">
              {pct}% · {concluidas}/{total}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-slate-900 transition-all"
              style={{ width: `${pct}%` }}
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Percentual concluído da jornada"
            />
          </div>
        </div>
      </Card>

      {/* ── Ver jornada completa (recolhida por padrão) ────────────────── */}
      <div className="mt-4">
        <button
          type="button"
          onClick={() => setCompletaAberta((v) => !v)}
          aria-expanded={completaAberta}
          aria-controls="jornada-completa"
          className="inline-flex items-center gap-1.5 rounded-lg px-1 py-1 text-sm font-medium text-slate-600 hover:text-slate-900 focus:outline-none focus-visible:ring-2"
        >
          <ChevronDown
            className={cn(
              "h-4 w-4 transition-transform",
              completaAberta && "rotate-180",
            )}
            aria-hidden="true"
          />
          {completaAberta ? "Ocultar jornada completa" : "Ver jornada completa"}
        </button>

        {completaAberta && (
          <div id="jornada-completa" className="mt-3 space-y-4">
            {FASES.map((fase) => {
              const etapasFase = jornada.etapas.filter(
                (e) => FASE_DE_ETAPA[e.chave] === fase.chave,
              );
              if (etapasFase.length === 0) return null;
              const stFase = statusDaFase(etapasFase);
              const metaFase = STATUS_META[stFase];
              const feitas = etapasFase.filter(
                (e) => e.status === "concluida",
              ).length;
              const FaseIcon = fase.icon;
              const ehFaseAtual = fase.chave === faseAtualChave;
              return (
                <Card
                  key={fase.chave}
                  className={cn(
                    "p-4",
                    ehFaseAtual && "ring-2 ring-slate-900/10",
                  )}
                >
                  {/* Cabeçalho da fase */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2">
                      <FaseIcon className="h-4 w-4 shrink-0 text-slate-400" />
                      <h3 className="text-sm font-semibold text-slate-950">
                        {fase.titulo}
                      </h3>
                      <Badge tone={metaFase.tone}>{metaFase.label}</Badge>
                      {ehFaseAtual && <Badge tone="blue">Fase atual</Badge>}
                    </div>
                    <span className="text-xs text-slate-500">
                      {feitas}/{etapasFase.length} etapas · {fase.descricao}
                    </span>
                  </div>

                  {/* Etapas técnicas da fase */}
                  <ul className="mt-3 space-y-3">
                    {etapasFase.map((etapa) => {
                      const meta =
                        STATUS_META[etapa.status] ?? STATUS_META.pendente;
                      const Icon = ETAPA_ICON[etapa.chave] ?? FileText;
                      const ehEtapaAtual =
                        etapaAtual?.chave === etapa.chave;
                      return (
                        <li
                          key={etapa.chave}
                          className={cn(
                            "flex flex-wrap items-start justify-between gap-3 rounded-lg p-2",
                            ehEtapaAtual && "bg-slate-50",
                          )}
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <Icon className="h-4 w-4 shrink-0 text-slate-400" />
                              <span className="text-sm font-medium text-slate-950">
                                {etapa.titulo}
                              </span>
                              <Badge tone={meta.tone}>{meta.label}</Badge>
                            </div>
                            {etapa.resumo && (
                              <p className="mt-1 text-sm text-slate-500">
                                {etapa.resumo}
                              </p>
                            )}
                            <Pendencias itens={etapa.pendencias} />
                          </div>
                          <AcaoEtapa etapa={etapa} jornada={jornada} />
                        </li>
                      );
                    })}
                  </ul>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
