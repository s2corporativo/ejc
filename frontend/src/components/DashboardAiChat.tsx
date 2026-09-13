import { useState } from "react";
import { Scale, Send, Sparkles } from "lucide-react";
import { Link } from "react-router";
import Markdown from "./Markdown";
import api from "../lib/api";
import { mensagemErroIA } from "../lib/iaErro";
import { useIaStatus } from "../lib/iaStatus";

type AiTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  notice?: string;
};

export default function DashboardAiChat({
  canUseLegal,
}: {
  canUseLegal: boolean;
}) {
  const { disponivel: iaDisponivel, mensagem: iaMensagem } = useIaStatus();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<AiTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!canUseLegal) {
    return (
      <div className="ejc-reference-empty">
        Inteligência Jurídica disponível apenas aos perfis jurídicos
        autorizados.
      </div>
    );
  }

  const submit = async () => {
    const text = question.trim();
    if (!text || loading || !iaDisponivel) return;

    setTurns((current) => [
      ...current,
      { id: `${Date.now()}-user`, role: "user", content: text },
    ]);
    setQuestion("");
    setError("");
    setLoading(true);

    try {
      const { data } = await api.post("/ia/conversar", {
        texto: text,
        area: "pesquisa_juridica",
      });
      const content = String(data?.conteudo ?? data?.resposta ?? "").trim();
      const rawSources = data?.fontes_rag ?? data?.fontes ?? [];
      const sources = Array.isArray(rawSources)
        ? rawSources
            .slice(0, 4)
            .map((source: any) =>
              typeof source === "string"
                ? source
                : String(
                    source?.titulo ??
                      source?.referencia ??
                      source?.fonte ??
                      source?.url ??
                      "Fonte consultada",
                  ),
            )
        : [];

      setTurns((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: content || "A IA não retornou conteúdo para esta pergunta.",
          sources,
          notice: String(data?.aviso_hitl ?? data?.aviso ?? "").trim(),
        },
      ]);
    } catch (err: any) {
      setError(mensagemErroIA(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="ejc-reference-ai-status">
        <span className={iaDisponivel ? "is-online" : "is-offline"}>
          <i aria-hidden="true" />
          {iaDisponivel ? "IA disponível" : "IA indisponível"}
        </span>
        <small>Mesmo núcleo jurídico do Assistente IA</small>
      </div>

      <div className="ejc-reference-ai-chat" aria-live="polite">
        {turns.length === 0 && !loading ? (
          <div className="ejc-reference-ai-welcome">
            <Sparkles aria-hidden="true" />
            <div>
              <strong>Pergunte diretamente à IA do EJC</strong>
              <span>
                Use para pesquisa e orientação inicial. Fontes e revisão humana
                continuam obrigatórias.
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
                <Markdown source={turn.content} />
              ) : (
                <p>{turn.content}</p>
              )}
              {turn.sources && turn.sources.length > 0 && (
                <div className="ejc-reference-ai-sources">
                  <strong>Fontes:</strong>
                  {turn.sources.map((source, index) => (
                    <span key={`${turn.id}-source-${index}`}>{source}</span>
                  ))}
                </div>
              )}
              {turn.notice && (
                <small className="ejc-reference-ai-notice">{turn.notice}</small>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="ejc-reference-ai-message is-assistant is-loading">
            <span className="ejc-reference-ai-message__role">EJC IA</span>
            <p>Analisando e preparando a resposta…</p>
          </div>
        )}
      </div>

      {error && <div className="ejc-reference-ai-error">{error}</div>}
      {!iaDisponivel && iaMensagem && (
        <div className="ejc-reference-ai-error">{iaMensagem}</div>
      )}

      <div className="ejc-reference-ai-box">
        <textarea
          value={question}
          maxLength={12000}
          rows={3}
          disabled={!iaDisponivel || loading}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="Pergunte à IA do EJC…"
          aria-label="Pergunta rápida para a Inteligência Jurídica"
        />
        <button
          type="button"
          className="ejc-reference-ai-send"
          onClick={() => void submit()}
          disabled={!question.trim() || !iaDisponivel || loading}
          aria-label="Enviar pergunta para a Inteligência Jurídica"
        >
          <Send aria-hidden="true" />
        </button>
      </div>
      <p className="ejc-reference-ai-hint">
        Enter envia · Shift+Enter quebra a linha · respostas são rascunhos
        sujeitos a conferência.
      </p>
      <div className="ejc-reference-ai-shortcuts">
        <Link
          to="/inteligencia?tab=conhecimento&sub=pesquisa"
          className="ejc-reference-ai-shortcut"
        >
          <Scale aria-hidden="true" /> Fontes e jurisprudência
        </Link>
        <Link
          to="/inteligencia?tab=assistente&sub=rapido"
          className="ejc-reference-ai-shortcut"
        >
          <Sparkles aria-hidden="true" /> Assistente completo
        </Link>
      </div>
    </>
  );
}
