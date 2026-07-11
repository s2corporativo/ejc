import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowUpRight,
  BarChart3,
  CheckSquare,
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

// DECISÃO: mapa chave→rota resolvido no frontend (rotas reais do
// moduleRegistry); link_modulo do backend é usado apenas como fallback.
// GAPs conhecidos: /documentos (GestaoDocumental) e /pecas (Pecas) não leem
// query param de caso — navegamos sem filtro para não sujar a URL.
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
      return "/documentos";
    case "inteligencia":
    case "estrategia":
      // Não existe tela dedicada de dossiê estratégico: a Sala de Guerra
      // (/casos/:caseId/sala-de-guerra) é o módulo de estratégia por caso.
      return `/casos/${jornada.case_id}/sala-de-guerra`;
    case "producao":
    case "revisao":
      return "/pecas";
    case "gestao":
      return "/prazos";
    default:
      return etapa.link_modulo || `/casos/${jornada.case_id}`;
  }
}

export default function JornadaCaso() {
  const { id } = useParams<{ id: string }>();
  const [jornada, setJornada] = useState<JornadaCasoResp | null>(null);
  const [erro, setErro] = useState(false);
  const [loading, setLoading] = useState(true);

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

  const concluidas = jornada.etapas.filter(
    (e) => e.status === "concluida",
  ).length;

  return (
    <div>
      <PageHeader
        eyebrow={jornada.fase ? `Fase: ${jornada.fase}` : undefined}
        title={`Jornada — ${jornada.titulo}`}
        subtitle={[
          jornada.numero_processo
            ? `Processo ${jornada.numero_processo}`
            : "Sem número de processo",
          `${concluidas} de ${jornada.etapas.length} etapas concluídas`,
        ].join(" · ")}
        actions={
          <Link to={`/casos/${jornada.case_id}`}>
            <Button variant="secondary" icon={<Gavel className="h-4 w-4" />}>
              Abrir caso
            </Button>
          </Link>
        }
      />

      {/* Stepper VERTICAL: linha contínua à esquerda ligando as 9 etapas */}
      <ol className="relative ml-1 space-y-4 border-l border-slate-200 pl-8">
        {jornada.etapas.map((etapa, index) => {
          const meta = STATUS_META[etapa.status] ?? STATUS_META.pendente;
          const Icon = ETAPA_ICON[etapa.chave] ?? FileText;
          return (
            <li key={etapa.chave} className="relative">
              {/* Círculo numerado sobre a linha do stepper */}
              <span
                className={cn(
                  "absolute -left-[3.25rem] top-4 flex h-9 w-9 items-center justify-center rounded-full text-xs font-semibold ring-2",
                  meta.circle,
                )}
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <Card className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 shrink-0 text-slate-400" />
                      <h2 className="text-sm font-semibold text-slate-950">
                        {etapa.titulo}
                      </h2>
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                    </div>
                    {etapa.resumo && (
                      <p className="mt-1.5 text-sm text-slate-500">
                        {etapa.resumo}
                      </p>
                    )}
                    {etapa.pendencias.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {etapa.pendencias.map((pendencia, i) => (
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
                    )}
                  </div>
                  <Link to={rotaModulo(etapa, jornada)} className="shrink-0">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<ArrowUpRight className="h-3.5 w-3.5" />}
                    >
                      Abrir módulo
                    </Button>
                  </Link>
                </div>
              </Card>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
