import { useEffect, useMemo, useState } from "react";
import {
  CalendarPlus,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clipboard,
  FileSearch,
  FileUp,
  MessageSquarePlus,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import Markdown from "./Markdown";
import { AIFactualityLegend, HumanValidationStatus } from "./UI";
import { toast } from "./Toast";
import api from "../lib/api";
import {
  acoesContextuais as buscarAcoesContextuais,
  executarSkill,
  executarSkillDocumento,
  type ContextualAction,
  type SkillExecuteResponse,
} from "../services/ai";
import type { Case } from "../types";

type NextAction = {
  name: string;
  display_name: string;
  description?: string | null;
};

// SkillResult substituído pelo contrato canônico SkillExecuteResponse
// (services/ai.ts — espelha SkillExecuteResponse do backend).
type SkillResult = SkillExecuteResponse;

type AgendaDraft = {
  open: boolean;
  titulo: string;
  tipo: "compromisso" | "reuniao" | "audiencia" | "diligencia";
  data_evento: string;
};

const SURFACE_LABEL: Record<string, string> = {
  resumo: "visão do caso",
  processos: "processo",
  timeline: "andamentos",
  mensagens: "comunicação",
  documentos: "documentos",
  provas: "provas",
  contratos: "contratos",
  procuracoes: "procurações",
  prazos: "prazos",
  audiencias: "audiências",
  financeiro: "financeiro",
  custos: "custos",
  liquidez: "acordo",
  teses: "teses",
  "teses-sugeridas": "teses sugeridas",
  jurisprudencia: "jurisprudência",
  precedentes: "precedentes",
  risco: "risco",
  score: "score jurídico",
  memoria: "memória",
  dossie: "dossiê",
  iaDefensiva: "estratégia defensiva",
  ferramentas: "ferramentas",
};

function dataAmanha() {
  const data = new Date();
  data.setDate(data.getDate() + 1);
  const ano = data.getFullYear();
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  const dia = String(data.getDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
}

function detalheErro(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return fallback;
}

export default function ContextualAIAssistant({
  caso,
  surface,
}: {
  caso: Case;
  surface: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [actions, setActions] = useState<ContextualAction[]>([]);
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [autoClassify, setAutoClassify] = useState(true);
  const [loadingActions, setLoadingActions] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SkillResult | null>(null);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [feedback, setFeedback] = useState<"util" | "nao_util" | null>(null);
  const [agenda, setAgenda] = useState<AgendaDraft>({
    open: false,
    titulo: "Revisar resultado da IA",
    tipo: "compromisso",
    data_evento: dataAmanha(),
  });

  const surfaceName = SURFACE_LABEL[surface] || "caso";
  const selectedAction = actions.find((item) => item.name === selected);

  useEffect(() => {
    let ativo = true;
    setLoadingActions(true);
    buscarAcoesContextuais({
      case_id: caso.id,
      surface,
      area: caso.area,
      phase: caso.fase,
    })
      .then((resposta) => {
        if (!ativo) return;
        const itens: ContextualAction[] = resposta.actions || [];
        setActions(itens);
        setSelected((atual) =>
          itens.some((item) => item.name === atual)
            ? atual
            : itens[0]?.name || "",
        );
      })
      .catch(() => {
        if (ativo) setActions([]);
      })
      .finally(() => {
        if (ativo) setLoadingActions(false);
      });
    return () => {
      ativo = false;
    };
  }, [caso.area, caso.fase, caso.id, surface]);

  useEffect(() => {
    setResult(null);
    setReviewConfirmed(false);
    setFeedback(null);
  }, [surface]);

  const podeExecutar = Boolean(
    file ? autoClassify || selected : selected && query.trim().length >= 5,
  );

  const executar = async () => {
    if (!podeExecutar) {
      toast.error("Descreva o objetivo ou anexe um documento.");
      return;
    }
    setRunning(true);
    setResult(null);
    setReviewConfirmed(false);
    setFeedback(null);
    try {
      let data: SkillResult;
      if (file) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("skill_name", autoClassify ? "auto" : selected);
        fd.append("case_id", caso.id);
        fd.append("surface", surface);
        fd.append("area", caso.area || "");
        fd.append("phase", caso.fase || "");
        fd.append("usar_rag", "true");
        if (query.trim()) fd.append("instrucoes", query.trim());
        data = await executarSkillDocumento(fd);
      } else {
        data = await executarSkill({
          skill_name: selected,
          query: query.trim(),
          case_id: caso.id,
          usar_rag: true,
          surface,
          area: caso.area,
          phase: caso.fase,
        });
      }
      setResult(data);
    } catch (error: any) {
      toast.error(detalheErro(error, "Não foi possível executar a análise."));
    } finally {
      setRunning(false);
    }
  };

  const copiar = async () => {
    if (!result?.conteudo) return;
    await navigator.clipboard.writeText(result.conteudo);
    toast.success("Resultado copiado.");
  };

  const registrarStatusAplicado = async () => {
    if (!result?.ai_log_id) return;
    try {
      await api.patch(`/ai/logs/${result.ai_log_id}/hitl`, {
        status: "aplicado",
        override_citacoes: false,
      });
    } catch (error: any) {
      if (error?.response?.status === 409) {
        toast.error(
          "O conteúdo foi aplicado, mas as citações ainda precisam ser validadas no histórico de IA.",
        );
      }
    }
  };

  const salvarNota = async () => {
    if (!result || !reviewConfirmed) {
      toast.error("Confirme a revisão humana antes de aplicar o resultado.");
      return;
    }
    if (!window.confirm("Salvar este resultado revisado como nota no caso?")) {
      return;
    }
    try {
      await api.post(`/cases/${caso.id}/movimentos`, {
        tipo: "nota",
        descricao: `[IA revisada — ${result.skill}]\n\n${result.conteudo}`,
      });
      await registrarStatusAplicado();
      toast.success("Resultado salvo no histórico do caso.");
    } catch (error: any) {
      toast.error(detalheErro(error, "Não foi possível salvar a nota."));
    }
  };

  const criarEvento = async () => {
    if (!result || !reviewConfirmed) {
      toast.error("Confirme a revisão humana antes de criar o evento.");
      return;
    }
    if (!agenda.titulo.trim() || !agenda.data_evento) {
      toast.error("Informe título e data do evento.");
      return;
    }
    if (!window.confirm("Criar este evento na agenda vinculada ao caso?")) {
      return;
    }
    try {
      await api.post("/agenda-eventos/", {
        titulo: agenda.titulo.trim(),
        tipo: agenda.tipo,
        data_evento: agenda.data_evento,
        case_id: caso.id,
        descricao: `Originado da análise ${result.skill}. Log de IA: ${result.ai_log_id || "não informado"}.`,
      });
      setAgenda((atual) => ({ ...atual, open: false }));
      await registrarStatusAplicado();
      toast.success("Evento criado na agenda.");
    } catch (error: any) {
      toast.error(detalheErro(error, "Não foi possível criar o evento."));
    }
  };

  const avaliar = async (valor: "util" | "nao_util") => {
    if (!result?.ai_log_id) return;
    try {
      await api.post(`/ai/logs/${result.ai_log_id}/feedback`, {
        feedback: valor,
      });
      setFeedback(valor);
      toast.success("Feedback registrado.");
    } catch {
      toast.error("Não foi possível registrar o feedback.");
    }
  };

  const prepararProxima = (acao: NextAction) => {
    setSelected(acao.name);
    setFile(null);
    setAutoClassify(false);
    setQuery(
      `Use o resultado revisado abaixo como insumo para ${acao.display_name}. Preserve as incertezas e não invente dados.\n\n${result?.conteudo || ""}`,
    );
    setResult(null);
    setReviewConfirmed(false);
    toast.success("Próxima ação preparada; confira o texto antes de executar.");
  };

  const metadadosAuditoria = useMemo(() => {
    if (!result?.auditoria) return [];
    const audit = result.auditoria;
    return [
      audit.surface ? `módulo: ${audit.surface}` : null,
      audit.input_type ? `entrada: ${audit.input_type}` : null,
      audit.rag_habilitado ? "RAG do cliente habilitado" : "sem RAG",
      result.ai_log_id ? `log: ${result.ai_log_id.slice(0, 8)}` : null,
    ].filter(Boolean) as string[];
  }, [result]);

  return (
    <section className="rounded-xl border border-ai-200 bg-ai-50/60 shadow-sm">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="rounded-lg bg-ai-600 p-2 text-white">
            <Sparkles size={16} />
          </span>
          <span className="min-w-0">
            <strong className="block text-sm text-slate-900">
              Ações com IA para {surfaceName}
            </strong>
            <span className="block truncate text-xs text-slate-500">
              {loadingActions
                ? "Selecionando ações adequadas…"
                : actions.length
                  ? actions
                      .slice(0, 3)
                      .map((item) => item.display_name)
                      .join(" · ")
                  : "Nenhuma ação contextual disponível"}
            </span>
          </span>
        </span>
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>

      {expanded && (
        <div className="space-y-4 border-t border-ai-100 p-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Ações recomendadas
            </p>
            <div className="flex flex-wrap gap-2">
              {actions.map((action) => (
                <button
                  type="button"
                  key={action.name}
                  onClick={() => {
                    setSelected(action.name);
                    setAutoClassify(false);
                    setResult(null);
                  }}
                  title={action.reason}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                    selected === action.name
                      ? "border-ai-600 bg-ai-600 text-white"
                      : "border-slate-200 bg-white text-slate-700 hover:border-ai-300"
                  }`}
                >
                  {action.display_name}
                </button>
              ))}
            </div>
            {selectedAction?.reason && (
              <p className="mt-2 text-xs text-slate-500">
                Sugestão: {selectedAction.reason}. O usuário mantém a decisão
                final.
              </p>
            )}
          </div>

          <div className="grid gap-3 lg:grid-cols-[1fr_280px]">
            <textarea
              className="input min-h-28 w-full resize-y"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Descreva o que precisa analisar em ${surfaceName}, o objetivo e as dúvidas. Não é necessário repetir dados já vinculados ao caso.`}
            />
            <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white p-3 text-center hover:border-ai-400">
              <FileUp size={20} className="text-ai-600" />
              <span className="mt-1 text-xs font-medium text-slate-700">
                {file ? file.name : "Anexar documento"}
              </span>
              <span className="mt-1 text-[11px] text-slate-400">
                PDF, DOCX, imagem ou TXT · até 25 MB
              </span>
              <input
                type="file"
                className="hidden"
                accept=".pdf,.docx,.png,.jpg,.jpeg,.tiff,.webp,.txt"
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setAutoClassify(true);
                  setResult(null);
                }}
              />
            </label>
          </div>

          {file && (
            <label className="flex items-center gap-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={autoClassify}
                onChange={(event) => setAutoClassify(event.target.checked)}
              />
              Detectar localmente o tipo do documento e escolher a ação inicial
            </label>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={executar}
              disabled={!podeExecutar || running}
              className="btn-primary"
            >
              <FileSearch size={15} />
              {running ? "Analisando…" : "Executar análise"}
            </button>
            {file && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setFile(null)}
              >
                Remover arquivo
              </button>
            )}
            <span className="text-[11px] text-slate-500">
              Rascunho interno · revisão humana obrigatória
            </span>
          </div>

          {result && (
            <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-ai-700">
                    {result.skill}
                  </span>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold text-slate-900">
                      Resultado auditável
                    </h3>
                    <HumanValidationStatus
                      value={reviewConfirmed ? "validado" : "nao revisado"}
                    />
                  </div>
                </div>
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={copiar}
                    title="Copiar"
                  >
                    <Clipboard size={16} />
                  </button>
                  <button
                    type="button"
                    className={`icon-btn ${feedback === "util" ? "bg-success-50 text-success-700" : ""}`}
                    onClick={() => avaliar("util")}
                    title="Útil"
                  >
                    <ThumbsUp size={16} />
                  </button>
                  <button
                    type="button"
                    className={`icon-btn ${feedback === "nao_util" ? "bg-danger-50 text-danger-700" : ""}`}
                    onClick={() => avaliar("nao_util")}
                    title="Não útil"
                  >
                    <ThumbsDown size={16} />
                  </button>
                </div>
              </div>

              {result.classificacao && (
                <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
                  <strong>Documento identificado:</strong>{" "}
                  {result.classificacao.tipo.replace(/_/g, " ")} · confiança{" "}
                  {Math.round(result.classificacao.confianca * 100)}%
                  {result.classificacao.sinais?.length ? (
                    <span>
                      {" "}
                      · sinais: {result.classificacao.sinais.join(", ")}
                    </span>
                  ) : null}
                </div>
              )}

              <AIFactualityLegend />

              <div className="prose prose-sm max-w-none text-slate-700">
                <Markdown source={result.conteudo} />
              </div>

              <div className="flex flex-wrap gap-1.5">
                {metadadosAuditoria.map((item) => (
                  <span
                    key={item}
                    className="rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-600"
                  >
                    {item}
                  </span>
                ))}
              </div>

              <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={reviewConfirmed}
                  onChange={(event) => setReviewConfirmed(event.target.checked)}
                />
                <span>
                  Revisei fatos, documentos, valores, prazos, pedidos e
                  citações. Confirmo que a aplicação continua sob
                  responsabilidade profissional humana.
                </span>
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={salvarNota}
                  disabled={!reviewConfirmed}
                >
                  <MessageSquarePlus size={15} /> Salvar como nota
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={!reviewConfirmed}
                  onClick={() =>
                    setAgenda((atual) => ({
                      ...atual,
                      open: !atual.open,
                      titulo: `Revisar: ${result.skill}`,
                    }))
                  }
                >
                  <CalendarPlus size={15} /> Criar evento
                </button>
              </div>

              {agenda.open && (
                <div className="grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-[1fr_150px_150px_auto]">
                  <input
                    className="input"
                    value={agenda.titulo}
                    onChange={(event) =>
                      setAgenda((atual) => ({
                        ...atual,
                        titulo: event.target.value,
                      }))
                    }
                    placeholder="Título do evento"
                  />
                  <select
                    className="input"
                    value={agenda.tipo}
                    onChange={(event) =>
                      setAgenda((atual) => ({
                        ...atual,
                        tipo: event.target.value as AgendaDraft["tipo"],
                      }))
                    }
                  >
                    <option value="compromisso">Compromisso</option>
                    <option value="reuniao">Reunião</option>
                    <option value="audiencia">Audiência</option>
                    <option value="diligencia">Diligência</option>
                  </select>
                  <input
                    type="date"
                    className="input"
                    value={agenda.data_evento}
                    onChange={(event) =>
                      setAgenda((atual) => ({
                        ...atual,
                        data_evento: event.target.value,
                      }))
                    }
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={criarEvento}
                  >
                    <CheckCircle2 size={15} /> Confirmar
                  </button>
                </div>
              )}

              {!!result.proximas_acoes?.length && (
                <div>
                  <p className="mb-2 text-xs font-semibold text-slate-600">
                    Próximos passos sugeridos — nada será executado
                    automaticamente
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {result.proximas_acoes.map((acao) => (
                      <button
                        type="button"
                        key={acao.name}
                        className="rounded-full border border-ai-200 bg-ai-50 px-3 py-1.5 text-xs font-medium text-ai-800 hover:bg-ai-100"
                        onClick={() => prepararProxima(acao)}
                      >
                        {acao.display_name} →
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
