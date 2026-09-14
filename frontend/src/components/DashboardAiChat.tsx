import { useRef, useState } from "react";
import {
  BriefcaseBusiness,
  CheckCircle2,
  FileText,
  Maximize2,
  Paperclip,
  Scale,
  Send,
  Sparkles,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import Markdown from "./Markdown";
import api from "../lib/api";
import { mensagemErroIA } from "../lib/iaErro";
import { useIaStatus } from "../lib/iaStatus";

type ModeKey = "livre" | "caso" | "documentos" | "estrategia" | "peca";

type TrustIndicators = {
  fontes_rastreaveis?: number;
  documentos_utilizados?: number;
  fatos_nao_confirmados?: number;
  citacoes_a_conferir?: number;
  revisao_humana_necessaria?: boolean;
};

type NextAction = {
  acao: string;
  prioridade?: string;
  justificativa?: string;
  confirmada?: boolean;
};

type AiTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  notice?: string;
  alerts?: string[];
  trust?: TrustIndicators;
  nextAction?: NextAction | null;
};

type Attachment = { id: string; nome_original: string };

const MODE_OPTIONS: Array<{ key: ModeKey; label: string }> = [
  { key: "livre", label: "Livre" },
  { key: "caso", label: "Analisar caso" },
  { key: "documentos", label: "Documentos" },
  { key: "estrategia", label: "Estratégia" },
  { key: "peca", label: "Redigir/Revisar peça" },
];

function apiMode(mode: ModeKey, hasAttachments: boolean) {
  if (mode === "caso") return "organizar_fatos";
  if (mode === "documentos") return "analisar_provas";
  if (mode === "estrategia") return "estrategia_da_parte";
  if (mode === "peca")
    return hasAttachments ? "revisar_documento" : "elaborar_documento";
  return hasAttachments ? "organizar_fatos" : "conversa_livre";
}

export default function DashboardAiChat({
  canUseLegal,
}: {
  canUseLegal: boolean;
}) {
  const { disponivel: iaDisponivel, mensagem: iaMensagem } = useIaStatus();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const sessionPromiseRef = useRef<Promise<string> | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<AiTurn[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [mode, setMode] = useState<ModeKey>("livre");
  const [useEjcContext, setUseEjcContext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [confirmingAction, setConfirmingAction] = useState<string | null>(null);
  const [error, setError] = useState("");

  if (!canUseLegal) {
    return (
      <div className="ejc-reference-empty">
        Inteligência Jurídica disponível apenas aos perfis jurídicos
        autorizados.
      </div>
    );
  }

  const ensureSession = async (seed?: string): Promise<string> => {
    if (sessionId) return sessionId;
    if (!sessionPromiseRef.current) {
      const titulo =
        (seed || "Análise rápida do Dashboard").trim().slice(0, 120) ||
        "Análise rápida do Dashboard";
      sessionPromiseRef.current = api
        .post("/sala-juridica", { titulo })
        .then(({ data }) => {
          const id = String(data?.id || "");
          if (!id) throw new Error("Sessão jurídica não criada");
          setSessionId(id);
          return id;
        })
        .finally(() => {
          sessionPromiseRef.current = null;
        });
    }
    return sessionPromiseRef.current;
  };

  const uploadFiles = async (files: FileList | null) => {
    if (!files?.length || uploading || loading) return;
    setUploading(true);
    setError("");
    try {
      const id = await ensureSession(Array.from(files)[0]?.name || undefined);
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      const { data } = await api.post(`/sala-juridica/${id}/anexos`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const novos = Array.isArray(data?.anexados) ? data.anexados : [];
      setAttachments((current) => [
        ...current,
        ...novos.map((item: any) => ({
          id: String(item.id),
          nome_original: String(item.nome_original || "Anexo"),
        })),
      ]);
      if (novos.length) {
        setMode("documentos");
        setQuestion(
          (current) =>
            current ||
            "Leia integralmente os anexos disponíveis, organize o dossiê jurídico e diga o que ainda precisa ser confirmado.",
        );
      }
      const erros = Array.isArray(data?.erros) ? data.erros : [];
      if (erros.length)
        setError(
          "Alguns anexos não puderam ser processados. Confira-os na Sala Jurídica.",
        );
    } catch (err: any) {
      setError(mensagemErroIA(err, "Não foi possível anexar o documento."));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const submit = async () => {
    const text = question.trim();
    if (text.length < 3 || loading || uploading || !iaDisponivel) return;
    const userTurn: AiTurn = {
      id: `${Date.now()}-user`,
      role: "user",
      content: text,
    };
    setTurns((current) => [...current, userTurn]);
    setQuestion("");
    setError("");
    setLoading(true);
    try {
      const id = await ensureSession(text);
      const { data } = await api.post(`/sala-juridica/${id}/mensagens`, {
        conteudo: text,
        modo: apiMode(mode, attachments.length > 0),
        incluir_workspace: true,
        incluir_contexto_ejc: useEjcContext,
        usar_rag: true,
      });
      const msg = data?.mensagem_ia ?? {};
      const rawSources = msg?.fontes ?? [];
      const sources = Array.isArray(rawSources)
        ? rawSources.map((source: any) =>
            String(
              source?.titulo ??
                source?.fonte ??
                source?.categoria ??
                "Fonte consultada",
            ),
          )
        : [];
      const nextActionRaw = data?.proxima_acao_sugerida;
      const nextAction =
        nextActionRaw && typeof nextActionRaw === "object"
          ? {
              acao: String(nextActionRaw.acao || "").trim(),
              prioridade: nextActionRaw.prioridade
                ? String(nextActionRaw.prioridade)
                : undefined,
              justificativa: nextActionRaw.justificativa
                ? String(nextActionRaw.justificativa)
                : undefined,
              confirmada: Boolean(nextActionRaw.confirmada),
            }
          : null;
      setTurns((current) => [
        ...current,
        {
          id: String(msg?.id || `${Date.now()}-assistant`),
          role: "assistant",
          content: String(
            msg?.conteudo || "A IA não retornou conteúdo para esta pergunta.",
          ).trim(),
          sources,
          notice: String(data?.aviso_hitl || "").trim(),
          alerts: Array.isArray(msg?.alertas) ? msg.alertas.map(String) : [],
          trust: data?.indicadores_confianca || undefined,
          nextAction: nextAction?.acao ? nextAction : null,
        },
      ]);
    } catch (err: any) {
      setError(mensagemErroIA(err));
    } finally {
      setLoading(false);
    }
  };

  const confirmNextAction = async (turnId: string, action: string) => {
    setConfirmingAction(turnId);
    setError("");
    try {
      const id = await ensureSession(action);
      await api.post(`/sala-juridica/${id}/proxima-acao/confirmar`, {
        acao: action,
      });
      setTurns((current) =>
        current.map((turn) =>
          turn.id === turnId && turn.nextAction
            ? {
                ...turn,
                nextAction: { ...turn.nextAction, confirmada: true },
              }
            : turn,
        ),
      );
    } catch (err: any) {
      setError(
        mensagemErroIA(err, "Não foi possível confirmar a próxima ação."),
      );
    } finally {
      setConfirmingAction(null);
    }
  };

  const openFull = async () => {
    try {
      const id = await ensureSession(
        question || attachments[0]?.nome_original || undefined,
      );
      navigate(`/sala-juridica?session=${encodeURIComponent(id)}`);
    } catch (err: any) {
      setError(
        mensagemErroIA(err, "Não foi possível abrir a análise completa."),
      );
    }
  };

  const canSubmit =
    question.trim().length >= 3 && iaDisponivel && !loading && !uploading;

  return (
    <>
      <div className="ejc-reference-ai-status">
        <span className={iaDisponivel ? "is-online" : "is-offline"}>
          <i aria-hidden="true" />
          {iaDisponivel ? "IA disponível" : "IA indisponível"}
        </span>
        <small>
          Conversa com memória · anexos · vínculo com caso só no final
        </small>
      </div>

      <div className="ejc-ai-modebar" aria-label="Modo de atuação da IA">
        {MODE_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={mode === option.key ? "is-active" : ""}
            aria-pressed={mode === option.key}
            onClick={() => setMode(option.key)}
          >
            {option.label}
          </button>
        ))}
        <button
          type="button"
          className={`ejc-ai-context-toggle ${useEjcContext ? "is-active" : ""}`}
          aria-pressed={useEjcContext}
          title="Inclui somente dados operacionais da carteira que seu usuário pode acessar"
          onClick={() => setUseEjcContext((current) => !current)}
        >
          <BriefcaseBusiness aria-hidden="true" /> Contexto EJC
        </button>
      </div>

      <div className="ejc-reference-ai-chat" aria-live="polite">
        {turns.length === 0 && !loading ? (
          <div className="ejc-reference-ai-welcome">
            <Sparkles aria-hidden="true" />
            <div>
              <strong>Converse com a Inteligência Jurídica</strong>
              <span>
                Anexe documentos, selecione o modo e deixe o EJC estruturar
                fatos, provas, partes, riscos e estratégia. O Contexto EJC só é
                incluído quando você o ativa.
              </span>
            </div>
          </div>
        ) : (
          turns.map((turn) => (
            <div
              key={turn.id}
              className={`ejc-reference-ai-message is-${turn.role}`}
            >
              <span className="ejc-reference-ai-message__role">
                {turn.role === "user" ? "Você" : "EJC IA"}
              </span>
              {turn.role === "assistant" ? (
                <Markdown source={turn.content} className="markdown" />
              ) : (
                <p>{turn.content}</p>
              )}

              {turn.role === "assistant" && turn.trust && (
                <div
                  className="ejc-ai-trustbar"
                  aria-label="Indicadores de evidência"
                >
                  <span>
                    Fontes rastreáveis: {turn.trust.fontes_rastreaveis ?? 0}
                  </span>
                  <span>
                    Documentos usados: {turn.trust.documentos_utilizados ?? 0}
                  </span>
                  <span>
                    Fatos não confirmados:{" "}
                    {turn.trust.fatos_nao_confirmados ?? 0}
                  </span>
                  <span>
                    Citações a conferir: {turn.trust.citacoes_a_conferir ?? 0}
                  </span>
                  <span className="is-hitl">Revisão humana necessária</span>
                </div>
              )}

              {turn.sources && turn.sources.length > 0 && (
                <div className="ejc-reference-ai-sources">
                  <strong>Fontes:</strong>
                  {turn.sources.map((source, index) => (
                    <span key={`${turn.id}-source-${index}`}>{source}</span>
                  ))}
                </div>
              )}
              {turn.alerts?.map((alert, index) => (
                <small
                  key={`${turn.id}-alert-${index}`}
                  className="ejc-reference-ai-notice"
                >
                  Atenção: {alert}
                </small>
              ))}
              {turn.notice && (
                <small className="ejc-reference-ai-notice">{turn.notice}</small>
              )}

              {turn.role === "assistant" && turn.nextAction && (
                <div className="ejc-ai-next-action">
                  <div>
                    <strong>Próxima ação sugerida</strong>
                    <p>{turn.nextAction.acao}</p>
                    {turn.nextAction.justificativa && (
                      <small>{turn.nextAction.justificativa}</small>
                    )}
                  </div>
                  {turn.nextAction.confirmada ? (
                    <span className="is-confirmed">
                      <CheckCircle2 aria-hidden="true" /> Confirmada no dossiê
                    </span>
                  ) : (
                    <button
                      type="button"
                      disabled={confirmingAction === turn.id}
                      onClick={() =>
                        void confirmNextAction(turn.id, turn.nextAction!.acao)
                      }
                    >
                      Confirmar ação
                    </button>
                  )}
                  <small className="ejc-ai-next-action__safety">
                    Confirmar não cria tarefa, prazo ou movimentação. A ação só
                    será aplicada ao caso se você posteriormente criar/vincular
                    o caso e confirmar a integração do dossiê.
                  </small>
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="ejc-reference-ai-message is-assistant is-loading">
            <span className="ejc-reference-ai-message__role">EJC IA</span>
            <p>Analisando fatos, documentos, fontes e riscos…</p>
          </div>
        )}
      </div>

      {attachments.length > 0 && (
        <div className="ejc-reference-ai-sources">
          <strong>Anexos nesta análise:</strong>
          {attachments.map((a) => (
            <span key={a.id}>
              <FileText aria-hidden="true" style={{ width: 12, height: 12 }} />{" "}
              {a.nome_original}
            </span>
          ))}
        </div>
      )}
      {error && <div className="ejc-reference-ai-error">{error}</div>}
      {!iaDisponivel && iaMensagem && (
        <div className="ejc-reference-ai-error">{iaMensagem}</div>
      )}

      <div className="ejc-reference-ai-box">
        <textarea
          value={question}
          maxLength={40000}
          rows={3}
          disabled={!iaDisponivel || loading || uploading}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder={
            useEjcContext
              ? "Pergunte sobre sua carteira, prazos, casos, documentos ou escreva uma análise…"
              : "Pergunte, descreva o caso ou anexe documentos…"
          }
          aria-label="Pergunta rápida para a Inteligência Jurídica"
        />
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          accept=".pdf,.doc,.docx,.txt,.md,.xml,.xlsx,.csv,.png,.jpg,.jpeg,.tiff,.webp"
          onChange={(event) => void uploadFiles(event.target.files)}
        />
        <button
          type="button"
          className="ejc-reference-ai-send is-attach"
          onClick={() => fileRef.current?.click()}
          disabled={!iaDisponivel || loading || uploading}
          aria-label="Anexar documentos para a Inteligência Jurídica"
        >
          <Paperclip aria-hidden="true" />
        </button>
        <button
          type="button"
          className="ejc-reference-ai-send"
          onClick={() => void submit()}
          disabled={!canSubmit}
          aria-label="Enviar pergunta para a Inteligência Jurídica"
        >
          <Send aria-hidden="true" />
        </button>
      </div>
      <p className="ejc-reference-ai-hint">
        {uploading
          ? "Extraindo e preparando anexos…"
          : "Enter envia · Shift+Enter quebra linha · Contexto EJC é opt-in · vínculo com caso é opcional e posterior."}
      </p>
      <div className="ejc-reference-ai-shortcuts">
        <button
          type="button"
          className="ejc-reference-ai-shortcut"
          onClick={() => void openFull()}
        >
          <Maximize2 aria-hidden="true" /> Abrir análise completa
        </button>
        <Link
          to="/inteligencia?tab=conhecimento&sub=pesquisa"
          className="ejc-reference-ai-shortcut"
        >
          <Scale aria-hidden="true" /> Fontes e jurisprudência
        </Link>
      </div>
    </>
  );
}
