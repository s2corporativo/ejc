import { useState } from "react";
import { Link } from "react-router";
import {
  Sparkles,
  AlertTriangle,
  Scale,
  BookOpen,
  Target,
  Wallet,
  LayoutGrid,
  ChevronDown,
  ChevronUp,
  Wrench,
} from "lucide-react";
import api from "../lib/api";
import { caminhoAbaCaso } from "../lib/caseContext";
import { configWorkspaceDaArea } from "../pages/ramos/areasWorkspace";
import { toast } from "./Toast";
import Markdown from "./Markdown";
import ErrorBoundary from "./ErrorBoundary";
import { fmtTaxaSucesso } from "../utils/formato";
import { mensagemErroIA, ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { MENSAGEM_IA_NAO_ATIVADA, useIaStatus } from "../lib/iaStatus";
import {
  AISurface,
  Alert,
  Badge,
  Button,
  Skeleton,
  Table,
  THead,
  TR,
  TH,
  TD,
  Textarea,
  fmtMoney,
} from "./UI";

/**
 * IntakeAnalise — painel "Análise Completa (IA)" do intake de casos.
 *
 * Dispara POST /intake/casos/{case_id}/analise-completa e renderiza o RASCUNHO
 * retornado: área provável, teses do banco (nunca inventadas), estratégia
 * recomendada, honorários de referência OAB/MG e módulos sugeridos.
 * Tudo em superfície ai-* (rascunho sujeito a revisão humana obrigatória).
 */

interface TeseSugerida {
  id: string | number;
  titulo: string;
  taxa_sucesso: number | null;
  area_juridica?: string | null;
  tribunal?: string | null;
  vezes_usada?: number | null;
  fonte?: string | null;
}

interface EstrategiaInfo {
  recomendada: string | null;
  justificativa?: string | null;
  riscos?: string[];
  fontes_rag_usadas?: number | null;
  modelo?: string | null;
  ai_log_id?: string | null;
}

interface HonorarioItem {
  item_codigo?: string | null;
  descricao?: string | null;
  valor_minimo?: number | null;
  percentual?: number | null;
  unidade?: string | null;
  fonte?: string | null;
  observacoes?: string | null;
}

interface HonorariosInfo {
  origem?: string | null;
  itens?: HonorarioItem[];
}

// `ferramentas` pode vir como lista de strings OU de objetos {nome, endpoint}
// (AreaModuloMapping.ferramentas no backend — ver models/redesign.py). Nunca
// renderizar o objeto direto: era a causa do crash "Objects are not valid as
// a React child (found: object with keys {nome, endpoint})".
type FerramentaSugerida =
  string | { nome?: string | null; endpoint?: string | null };

interface ModuloSugerido {
  module_key: string;
  ordem?: number | null;
  ferramentas?: FerramentaSugerida[];
}

interface AnaliseCompleta {
  status: string;
  aviso: string;
  case_id: string;
  area?: { valor?: string | null; origem?: string | null } | null;
  teses?: TeseSugerida[] | null;
  teses_aviso?: string | null;
  estrategia?: EstrategiaInfo | null;
  honorarios?: HonorariosInfo | null;
  honorarios_aviso?: string | null;
  modulos_sugeridos?: ModuloSugerido[] | null;
  pii_removida?: boolean;
  ai_log_ids?: string[];
  /** Contrato novo do backend: false quando nenhum provedor de IA responde. */
  ia_disponivel?: boolean;
  mensagem?: string | null;
}

/** Rótulo seguro de uma ferramenta sugerida (string ou objeto {nome}). */
function rotuloFerramenta(f: FerramentaSugerida): string {
  if (typeof f === "string") return f;
  if (f && typeof f === "object" && typeof f.nome === "string") return f.nome;
  return "";
}

const ABA_POR_MODULO_CORE: Record<string, string> = {
  casos: "resumo",
  prazos: "prazos",
  documentos: "documentos",
  pecas: "pecas",
  checklists: "checklists",
};

/**
 * Resolve apenas destinos confirmados no frontend atual.
 * - módulos Core abrem a aba canônica do MESMO caso;
 * - ramos/<slug> abre o workspace especializado com o case_id preservado;
 * - chaves sem destino canônico comprovado (ex.: workflow) ficam informativas.
 */
export function rotaModuloSugerido(
  moduleKey: string,
  caseId: string,
): string | null {
  const key = moduleKey.trim().replace(/^\/+/, "");
  const aba = ABA_POR_MODULO_CORE[key];
  if (aba) return caminhoAbaCaso(caseId, aba);

  if (key.startsWith("ramos/")) {
    const slug = key.slice("ramos/".length).trim();
    if (
      !slug ||
      !/^[a-z0-9_-]+$/.test(slug) ||
      !configWorkspaceDaArea(slug)
    ) {
      return null;
    }
    const params = new URLSearchParams({
      case_id: caseId,
      tab: "ferramentas",
    });
    return `/areas-de-atuacao/${encodeURIComponent(slug)}?${params.toString()}`;
  }
  return null;
}

const ORIGEM_AREA_LABEL: Record<string, string> = {
  classificacao_ia: "classificada pela IA",
  area_do_caso: "área cadastrada no caso",
  informada: "informada na análise",
};

const ESTRATEGIA_LABEL: Record<string, string> = {
  defesa_administrativa: "Defesa administrativa",
  acao_judicial: "Ação judicial",
  acordo: "Acordo",
  arquivamento_prescricao: "Arquivamento / prescrição",
  outra: "Outra",
};

// taxa_sucesso vem do banco como fração 0–1 (vezes_venceu/vezes_usada)
function CardTitulo({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <h4 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
      {icon}
      {children}
    </h4>
  );
}

// Boundary local: qualquer payload inesperado vira mensagem amigável em
// português em vez de derrubar a tela do caso com erro React cru.
export default function IntakeAnalise({ caseId }: { caseId: string }) {
  return (
    <ErrorBoundary
      fallback={
        <div className="card border border-warn-200 bg-warn-50 p-4 text-sm text-warn-800">
          Não foi possível exibir a Análise Completa (IA) deste caso. Tente
          novamente em instantes; se o problema continuar, procure o
          administrador do sistema.
        </div>
      }
    >
      <IntakeAnaliseInner caseId={caseId} />
    </ErrorBoundary>
  );
}

function IntakeAnaliseInner({ caseId }: { caseId: string }) {
  const [dados, setDados] = useState<AnaliseCompleta | null>(null);
  const [loading, setLoading] = useState(false);
  const [texto, setTexto] = useState("");
  const [mostrarTexto, setMostrarTexto] = useState(false);
  const { disponivel: iaDisponivel } = useIaStatus();

  const gerar = async () => {
    setLoading(true);
    try {
      const body = texto.trim() ? { texto: texto.trim() } : {};
      const { data } = await api.post<AnaliseCompleta>(
        `/intake/casos/${caseId}/analise-completa`,
        body,
      );
      setDados(data);
    } catch (e) {
      toast.error(
        mensagemErroIA(e, "Falha ao gerar a análise completa do caso."),
      );
    } finally {
      setLoading(false);
    }
  };

  const estrategia = dados?.estrategia;
  // Payload degradado: IA indisponível ou envelope vazio → estado amigável.
  const iaIndisponivelNaResposta =
    !!dados &&
    (dados.ia_disponivel === false ||
      (!dados.area?.valor && !dados.estrategia && !dados.teses?.length));

  return (
    <AISurface
      title="Análise Completa (IA)"
      subtitle="Área provável, teses do banco, estratégia, honorários OAB/MG e módulos — rascunho sujeito a revisão humana."
      actions={
        <span title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}>
          <Button
            variant="ai"
            size="sm"
            onClick={gerar}
            disabled={loading || !iaDisponivel}
            icon={<Sparkles className="h-4 w-4" />}
          >
            {!iaDisponivel
              ? "IA não ativada"
              : loading
                ? "Analisando..."
                : dados
                  ? "Refazer análise"
                  : "Gerar análise completa"}
          </Button>
        </span>
      }
    >
      {/* Texto adicional opcional (enviado no body do POST) */}
      {!dados && !loading && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setMostrarTexto(!mostrarTexto)}
            className="flex items-center gap-1 text-sm text-ai-600 hover:text-ai-800"
          >
            {mostrarTexto ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            {mostrarTexto
              ? "Ocultar texto adicional"
              : "Adicionar texto de documento (opcional)"}
          </button>
          {mostrarTexto && (
            <Textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={4}
              placeholder="Cole aqui o texto de petição, contrato ou documento para enriquecer a análise..."
            />
          )}
          <p className="text-xs text-slate-400">
            A análise usa somente dados do caso e do banco do escritório — nada
            é inventado.
          </p>
        </div>
      )}

      {/* Loading — skeletons */}
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-12" />
          <Skeleton className="h-24" />
          <Skeleton className="h-32" />
          <Skeleton className="h-24" />
        </div>
      )}

      {/* IA indisponível na resposta: estado amigável, nunca exceção React. */}
      {dados && !loading && iaIndisponivelNaResposta && (
        <Alert variant="warning" title="Inteligência artificial não ativada">
          {dados.mensagem || MENSAGEM_IA_NAO_ATIVADA}
        </Alert>
      )}

      {dados && !loading && !iaIndisponivelNaResposta && (
        <div className="space-y-4">
          {/* Banner: rascunho sujeito a revisão humana */}
          <Alert
            variant="warning"
            title="Rascunho — revisão humana obrigatória"
          >
            {dados.aviso}
          </Alert>

          {/* Área provável */}
          <div className="card p-4">
            <CardTitulo icon={<Scale className="h-4 w-4 text-ai-500" />}>
              Área provável
            </CardTitulo>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold capitalize text-slate-800">
                {(dados.area?.valor || "não identificada").replace(/_/g, " ")}
              </span>
              {dados.area?.origem && (
                <Badge
                  tone={
                    dados.area.origem === "classificacao_ia"
                      ? "purple"
                      : "slate"
                  }
                >
                  {ORIGEM_AREA_LABEL[dados.area.origem] ||
                    dados.area.origem.replace(/_/g, " ")}
                </Badge>
              )}
              {dados.pii_removida && (
                <Badge tone="green">PII removida (LGPD)</Badge>
              )}
            </div>
          </div>

          {/* Teses do banco */}
          <div className="card p-4">
            <CardTitulo icon={<BookOpen className="h-4 w-4 text-ai-500" />}>
              Teses pertinentes
            </CardTitulo>
            {(dados.teses ?? []).length === 0 ? (
              <Alert variant="info">
                {dados.teses_aviso ||
                  "Nenhuma tese cadastrada no banco para esta área."}
              </Alert>
            ) : (
              <Table>
                <THead>
                  <TR zebra={false}>
                    <TH>Tese</TH>
                    <TH>Taxa de sucesso</TH>
                    <TH>Tribunal</TH>
                    <TH>Vezes usada</TH>
                  </TR>
                </THead>
                <tbody>
                  {(dados.teses ?? []).map((t) => (
                    <TR key={t.id}>
                      <TD className="font-medium text-slate-800">{t.titulo}</TD>
                      <TD className="font-mono">
                        {fmtTaxaSucesso(t.taxa_sucesso)}
                      </TD>
                      <TD>{t.tribunal || "—"}</TD>
                      <TD className="font-mono">{t.vezes_usada ?? "—"}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            )}
            <p className="mt-2 text-caption text-slate-400">
              Fonte: banco de teses do escritório.
            </p>
          </div>

          {/* Estratégia recomendada */}
          <div className="card p-4">
            <CardTitulo icon={<Target className="h-4 w-4 text-ai-500" />}>
              Estratégia recomendada
            </CardTitulo>
            {estrategia?.recomendada ? (
              <div className="space-y-3">
                <Badge tone="purple" className="px-3 py-1 text-sm">
                  {ESTRATEGIA_LABEL[estrategia.recomendada] ||
                    estrategia.recomendada.replace(/_/g, " ")}
                </Badge>
                {estrategia.justificativa && (
                  <Markdown
                    source={estrategia.justificativa}
                    className="text-sm leading-relaxed text-slate-700"
                  />
                )}
                {estrategia.riscos && estrategia.riscos.length > 0 && (
                  <div className="rounded-xl border border-warn-200 bg-warn-50 p-3">
                    <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-warn-800">
                      <AlertTriangle className="h-3.5 w-3.5" /> Riscos
                    </p>
                    <ul className="space-y-1">
                      {estrategia.riscos.map((r, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 text-sm text-warn-700"
                        >
                          <span className="mt-0.5 text-warn-500">•</span>
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-caption text-slate-400">
                  {estrategia.modelo ? `Modelo: ${estrategia.modelo}` : ""}
                  {typeof estrategia.fontes_rag_usadas === "number"
                    ? ` · ${estrategia.fontes_rag_usadas} fonte(s) da base de conhecimento (RAG)`
                    : ""}
                </p>
              </div>
            ) : (
              <Alert variant="info">
                {estrategia?.justificativa ||
                  "Estratégia indisponível para este caso."}
              </Alert>
            )}
          </div>

          {/* Honorários de referência OAB/MG */}
          <div className="card p-4">
            <CardTitulo icon={<Wallet className="h-4 w-4 text-ai-500" />}>
              Honorários de referência (OAB/MG)
            </CardTitulo>
            {dados.honorarios?.itens && dados.honorarios.itens.length > 0 ? (
              <div className="space-y-2">
                {dados.honorarios.itens.map((h, i) => (
                  <div key={h.item_codigo || i} className="card p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-slate-800">
                        {h.item_codigo ? `${h.item_codigo} — ` : ""}
                        {h.descricao || "Item da tabela"}
                      </span>
                      <span className="font-mono font-semibold text-slate-900">
                        {h.valor_minimo != null ? fmtMoney(h.valor_minimo) : ""}
                        {h.valor_minimo != null && h.percentual != null
                          ? " · "
                          : ""}
                        {h.percentual != null ? `${h.percentual}%` : ""}
                        {h.valor_minimo == null && h.percentual == null
                          ? "—"
                          : ""}
                      </span>
                    </div>
                    <p className="mt-1 text-caption text-slate-400">
                      {[h.unidade, h.fonte, h.observacoes]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                ))}
                {/* Aviso SEMPRE visível quando há itens */}
                <p className="flex items-start gap-1.5 rounded-lg bg-warn-50 px-3 py-2 text-sm font-semibold text-warn-800">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  {dados.honorarios_aviso}
                </p>
              </div>
            ) : (
              <Alert variant="info" title="Tabela indisponível">
                {dados.honorarios_aviso}
              </Alert>
            )}
          </div>

          {/* Módulos sugeridos */}
          <div className="card p-4">
            <CardTitulo icon={<LayoutGrid className="h-4 w-4 text-ai-500" />}>
              Módulos sugeridos
            </CardTitulo>
            {(dados.modulos_sugeridos ?? []).length === 0 ? (
              <p className="text-sm text-slate-400">
                Nenhum módulo mapeado para esta área.
              </p>
            ) : (
              <div className="space-y-2">
                {(dados.modulos_sugeridos ?? []).map((m) => {
                  const destino = rotaModuloSugerido(m.module_key, caseId);
                  const conteudo = (
                    <>
                      <Badge tone="purple">{m.module_key}</Badge>
                      {(m.ferramentas || [])
                        .map(rotuloFerramenta)
                        .filter(Boolean)
                        .map((nome, i) => (
                          <span
                            key={`${nome}-${i}`}
                            className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-caption text-ai-800 ring-1 ring-inset ring-ai-200"
                          >
                            <Wrench className="h-3 w-3" />
                            {nome}
                          </span>
                        ))}
                      {destino && (
                        <span className="ml-auto text-xs font-semibold text-ai-700">
                          Abrir →
                        </span>
                      )}
                    </>
                  );
                  return destino ? (
                    <Link
                      key={m.module_key}
                      to={destino}
                      className="flex flex-wrap items-center gap-2 rounded-lg border border-ai-200 bg-ai-50 px-3 py-2 transition hover:border-ai-300 hover:bg-ai-100/70"
                    >
                      {conteudo}
                    </Link>
                  ) : (
                    <div
                      key={m.module_key}
                      className="flex flex-wrap items-center gap-2 rounded-lg border border-ai-200 bg-ai-50 px-3 py-2"
                    >
                      {conteudo}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </AISurface>
  );
}
