import { useCallback, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Gavel,
  ListChecks,
  MapPin,
  Scale,
  ShieldAlert,
  Siren,
  Sparkles,
  Timer,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import CaseBreadcrumb from "../components/CaseBreadcrumb";
import { useCaseContext } from "../stores/caseContext";
import {
  AIFactualityLegend,
  AISurface,
  Badge,
  Button,
  Card,
  ConfidenceBadge,
  EmptyState,
  FieldLabel,
  IANotice,
  PageHeader,
  Textarea,
  cn,
  fmtMoney,
} from "../components/UI";

// ─── Contrato da API (POST /triagem/entrevista) ────────────────────────────
// DECISÃO: tipos locais — a entrevista é consumida apenas por esta página
// (mesmo padrão de tipos locais de JornadaCaso.tsx / Kanban.tsx).
interface ItemConfianca {
  valor: string | number | boolean | null;
  confianca: number | null;
  justificativa?: string | null;
  faixa?: string | null;
}

interface EntrevistaAnalise {
  area_direito: ItemConfianca;
  competencia: ItemConfianca;
  possivel_acao: ItemConfianca;
  urgencia: ItemConfianca;
  tutela_liminar: ItemConfianca;
  prescricao: {
    dentro_prazo: boolean | null;
    alerta: string | null;
    confianca: number | null;
  };
  valor_causa: ItemConfianca;
  pedidos_possiveis: string[];
  riscos: string[];
  // V2-4.2 / decisão D4 do plano-mestre (2026-08-24): a API ainda devolve
  // este campo (percentual GERADO POR IA, não estatística), mas deixou de
  // ser renderizado -- risco OAB art. 34, XXIX (vedação a captação/
  // mercantilização inadequada da expectativa do cliente) + fragilidade
  // estatística (poucos casos para calibrar). Tipado aqui só para não
  // quebrar o parse da resposta; NÃO reintroduzir a exibição sem decisão
  // nova do titular.
  chance_exito: {
    percentual: number | null;
    justificativa: string | null;
    confianca: number | null;
  };
}

interface EntrevistaResp {
  status: string;
  aviso: string;
  case_id: string | null;
  analise: EntrevistaAnalise;
  parse_ok: boolean;
  // Ponte Entrevista→Ficha: true quando o painel virou rascunho da Ficha de
  // Triagem do caso (só campos vazios; ficha confirmada nunca é tocada).
  ficha_atualizada?: boolean;
  pii_removida: boolean;
  modelo: string;
  ai_log_id: string;
}

const MIN_RELATO = 40;

// ─── Painel lateral: linha de item com badge de confiança ──────────────────
function PainelItem({
  icon: Icon,
  label,
  confianca,
  children,
}: {
  icon: typeof Scale;
  label: string;
  confianca: number | null;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-slate-100 py-3 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
          <Icon className="h-3.5 w-3.5 text-slate-400" />
          {label}
        </span>
        <ConfidenceBadge value={confianca} />
      </div>
      <div className="mt-1.5 text-sm text-slate-900">{children}</div>
    </div>
  );
}

function SimNao({ valor }: { valor: ItemConfianca["valor"] }) {
  if (valor === true) return <Badge tone="red">Sim</Badge>;
  if (valor === false) return <Badge tone="green">Não</Badge>;
  return <span className="text-slate-400">Não avaliado</span>;
}

function TextoOuPendente({ valor }: { valor: ItemConfianca["valor"] }) {
  return valor != null && valor !== "" ? (
    <span className="capitalize">{String(valor)}</span>
  ) : (
    <span className="text-slate-400">Não identificado</span>
  );
}

export default function EntrevistaInteligente() {
  const { id } = useParams<{ id: string }>();
  // Modo Caso: título para o breadcrumb (o CaseContextBar já ativou o caso).
  const casoAtivo = useCaseContext((state) => state.caso);
  const [relato, setRelato] = useState("");
  const [loading, setLoading] = useState(false);
  const [aplicando, setAplicando] = useState(false);
  const [resultado, setResultado] = useState<EntrevistaResp | null>(null);
  // Debounce de submissão: ignora cliques repetidos enquanto a análise roda
  const emVoo = useRef(false);

  const analisar = useCallback(() => {
    if (emVoo.current) return;
    if (relato.trim().length < MIN_RELATO) {
      toast.error(
        `Descreva o ocorrido com pelo menos ${MIN_RELATO} caracteres`,
      );
      return;
    }
    emVoo.current = true;
    setLoading(true);
    api
      .post<EntrevistaResp>("/triagem/entrevista", {
        relato: relato.trim(),
        case_id: id ?? null,
      })
      .then((r) => {
        setResultado(r.data);
        if (!r.data.parse_ok) {
          toast.error(
            "A IA não retornou análise estruturada completa — revise os itens com cautela",
          );
        } else if (r.data.ficha_atualizada) {
          toast.success(
            "Ficha de Triagem pré-preenchida com o painel (rascunho — revise antes de gerar a peça)",
          );
        }
      })
      .catch((e) => {
        const detail = e?.response?.data?.detail;
        toast.error(
          typeof detail === "string" ? detail : "Falha ao analisar o relato",
        );
      })
      .finally(() => {
        emVoo.current = false;
        setLoading(false);
      });
  }, [relato, id]);

  // "Aplicar ao caso": só o que o PATCH /cases/{id} já aceita (valor_causa).
  // Área do direito é exibida como sugestão — não existe campo no CaseUpdate.
  const valorCausaSugerido =
    typeof resultado?.analise.valor_causa.valor === "number"
      ? resultado.analise.valor_causa.valor
      : null;

  const aplicarAoCaso = useCallback(() => {
    if (!id || valorCausaSugerido == null) return;
    setAplicando(true);
    api
      .patch(`/cases/${id}`, { valor_causa: valorCausaSugerido })
      .then(() =>
        toast.success(
          `Valor da causa ${fmtMoney(valorCausaSugerido)} aplicado ao caso`,
        ),
      )
      .catch(() => toast.error("Falha ao aplicar o valor da causa ao caso"))
      .finally(() => setAplicando(false));
  }, [id, valorCausaSugerido]);

  const a = resultado?.analise;

  return (
    <div>
      {id && (
        <CaseBreadcrumb
          caseId={id}
          titulo={casoAtivo?.id === id ? casoAtivo.titulo : undefined}
          tela="Entrevista"
        />
      )}
      <PageHeader
        eyebrow="Jornada do Caso — Etapa 2"
        title="Entrevista Inteligente"
        subtitle="Conte o ocorrido em texto livre e receba a triagem preliminar da IA com nível de confiança por item."
        actions={
          id && (
            <Link to={`/casos/${id}/jornada`}>
              <Button
                variant="secondary"
                icon={<ArrowLeft className="h-4 w-4" />}
              >
                Voltar à jornada
              </Button>
            </Link>
          )
        }
      />

      {/* Próximo passo concreto: o painel já virou rascunho da ficha — leve o
          advogado direto para a revisão em vez de deixá-lo procurar. */}
      {resultado?.ficha_atualizada && id && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          <Sparkles className="h-4 w-4 shrink-0" />
          <span>
            Este painel foi copiado para a <strong>Ficha de Triagem</strong> do
            caso como rascunho (apenas campos vazios).
          </span>
          <Link
            to={`/pecas?caso=${id}`}
            className="font-semibold underline underline-offset-2"
          >
            Revisar a ficha →
          </Link>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        {/* Relato em texto livre */}
        <Card className="p-5">
          <FieldLabel required>Conte o ocorrido</FieldLabel>
          <Textarea
            value={relato}
            onChange={(e) => setRelato(e.target.value)}
            rows={14}
            maxLength={15000}
            placeholder="Descreva o ocorrido com suas palavras: o que aconteceu, quando, quem está envolvido, valores, documentos disponíveis e o que o cliente espera…"
            className="min-h-72"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-slate-400">
              {relato.trim().length} caracteres
              {relato.trim().length < MIN_RELATO && ` (mínimo ${MIN_RELATO})`}
            </span>
            <Button
              onClick={analisar}
              disabled={loading || relato.trim().length < MIN_RELATO}
              icon={
                <Sparkles
                  className={cn("h-4 w-4", loading && "animate-pulse")}
                />
              }
            >
              {loading ? "Analisando…" : resultado ? "Reanalisar" : "Analisar"}
            </Button>
          </div>
          <div className="mt-4">
            <IANotice>
              Estimativa preliminar gerada por IA — não é parecer jurídico.
              Revisão do advogado responsável é obrigatória (OAB Prov.
              205/2021).
            </IANotice>
          </div>
        </Card>

        {/* Painel lateral de confiança */}
        <AISurface
          title="Painel de triagem"
          subtitle={
            resultado
              ? `Modelo ${resultado.modelo} — rascunho sujeito a revisão humana.`
              : "Os itens aparecem aqui após a análise."
          }
          actions={
            id &&
            valorCausaSugerido != null && (
              <Button
                variant="secondary"
                size="sm"
                onClick={aplicarAoCaso}
                disabled={aplicando}
                icon={<ClipboardCheck className="h-3.5 w-3.5" />}
              >
                {aplicando ? "Aplicando…" : "Aplicar ao caso"}
              </Button>
            )
          }
        >
          {!a ? (
            <EmptyState
              icon={Sparkles}
              title="Nenhuma análise ainda"
              message="Descreva o ocorrido ao lado e clique em Analisar para ver área do direito, urgência, prescrição, valor da causa e chance de êxito."
            />
          ) : (
            <div className={cn(loading && "opacity-50 transition-opacity")}>
              <AIFactualityLegend className="mb-4" />
              <PainelItem
                icon={Scale}
                label="Área do Direito"
                confianca={a.area_direito.confianca}
              >
                <TextoOuPendente valor={a.area_direito.valor} />
              </PainelItem>

              <PainelItem
                icon={MapPin}
                label="Competência"
                confianca={a.competencia.confianca}
              >
                <TextoOuPendente valor={a.competencia.valor} />
              </PainelItem>

              <PainelItem
                icon={Gavel}
                label="Possível ação"
                confianca={a.possivel_acao.confianca}
              >
                <TextoOuPendente valor={a.possivel_acao.valor} />
              </PainelItem>

              <PainelItem
                icon={Siren}
                label="Urgência"
                confianca={a.urgencia.confianca}
              >
                <SimNao valor={a.urgencia.valor} />
                {a.urgencia.justificativa && (
                  <p className="mt-1 text-xs text-slate-500">
                    {a.urgencia.justificativa}
                  </p>
                )}
              </PainelItem>

              <PainelItem
                icon={ShieldAlert}
                label="Tutela / liminar possível?"
                confianca={a.tutela_liminar.confianca}
              >
                <SimNao valor={a.tutela_liminar.valor} />
                {a.tutela_liminar.justificativa && (
                  <p className="mt-1 text-xs text-slate-500">
                    {a.tutela_liminar.justificativa}
                  </p>
                )}
              </PainelItem>

              <PainelItem
                icon={Timer}
                label="Prescrição"
                confianca={a.prescricao.confianca}
              >
                {a.prescricao.dentro_prazo === true && (
                  <Badge tone="green">Dentro do prazo</Badge>
                )}
                {a.prescricao.dentro_prazo === false && (
                  <Badge tone="red">Risco de prescrição</Badge>
                )}
                {a.prescricao.dentro_prazo == null && (
                  <span className="text-slate-400">Não avaliado</span>
                )}
                {a.prescricao.alerta && (
                  <p className="mt-1 text-xs text-warn-700">
                    {a.prescricao.alerta}
                  </p>
                )}
              </PainelItem>

              <PainelItem
                icon={Wallet}
                label="Valor aproximado da causa"
                confianca={a.valor_causa.confianca}
              >
                {valorCausaSugerido != null ? (
                  <span className="font-semibold">
                    {fmtMoney(valorCausaSugerido)}
                  </span>
                ) : (
                  <span className="text-slate-400">Não estimado</span>
                )}
                {a.valor_causa.faixa && (
                  <p className="mt-1 text-xs text-slate-500">
                    Faixa: {a.valor_causa.faixa}
                  </p>
                )}
              </PainelItem>

              <PainelItem
                icon={ListChecks}
                label="Pedidos possíveis"
                confianca={null}
              >
                {a.pedidos_possiveis.length > 0 ? (
                  <ul className="space-y-1">
                    {a.pedidos_possiveis.map((p, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-sm">
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success-600" />
                        {p}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-slate-400">Nenhum identificado</span>
                )}
              </PainelItem>

              <PainelItem icon={ShieldAlert} label="Riscos" confianca={null}>
                {a.riscos.length > 0 ? (
                  <ul className="space-y-1">
                    {a.riscos.map((r, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-1.5 text-sm text-warn-700"
                      >
                        <span
                          className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn-400"
                          aria-hidden="true"
                        />
                        {r}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-slate-400">Nenhum identificado</span>
                )}
              </PainelItem>
            </div>
          )}
        </AISurface>
      </div>
    </div>
  );
}
