import { useEffect, useState } from "react";
import Markdown from "../components/Markdown";
import { Send, AlertTriangle, Loader2 } from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { PageHeader } from "../components/UI";

// Tarefas expostas (correspondem ao TarefaIA do backend). Rótulos amigáveis.
const TAREFAS: { k: string; label: string; dica: string }[] = [
  {
    k: "triagem",
    label: "Triagem de caso",
    dica: "Relato inicial → área, urgência, prescrição, viabilidade (JSON).",
  },
  {
    k: "analise_caso",
    label: "Análise estratégica",
    dica: "Relatório completo: tese, riscos, cenários, estratégia.",
  },
  {
    k: "minutas",
    label: "Minuta / peça",
    dica: "Rascunho de petição, contestação, parecer, notificação…",
  },
  {
    k: "prazos",
    label: "Cálculo de prazo",
    dica: "Ato + data de intimação → data fatal (CPC/CLT/IBAMA).",
  },
  {
    k: "honorarios",
    label: "Honorários (OAB)",
    dica: "Estimativa e proposta conforme tabela OAB/MG.",
  },
  {
    k: "ambiental",
    label: "Ambiental (IBAMA)",
    dica: "Análise de auto de infração + rascunho de defesa.",
  },
  {
    k: "pesquisa_juridica",
    label: "Pesquisa jurídica",
    dica: "Síntese de teses e jurisprudência (use RAG).",
  },
  {
    k: "audiencia",
    label: "Preparação de audiência",
    dica: "Roteiro, perguntas, pontos de atenção.",
  },
  {
    k: "resumo",
    label: "Resumo",
    dica: "Resumo técnico objetivo de um texto.",
  },
];

export default function AgenteIA() {
  const [status, setStatus] = useState<any>(null);
  const [tarefa, setTarefa] = useState("analise_caso");
  const [mensagem, setMensagem] = useState("");
  const [caseId, setCaseId] = useState("");
  const [usarRag, setUsarRag] = useState(false);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<any>(null);

  useEffect(() => {
    api
      .get("/ai/status")
      .then((r) => setStatus(r.data))
      .catch(() => setStatus(null));
  }, []);

  const dica = TAREFAS.find((t) => t.k === tarefa)?.dica || "";
  const habilitado = status?.ai_enabled === true;

  const executar = async () => {
    if (mensagem.trim().length < 5) {
      toast.error("Descreva a solicitação (mín. 5 caracteres).");
      return;
    }
    setLoading(true);
    setRes(null);
    try {
      const { data } = await api.post("/ai/executar", {
        tarefa,
        mensagem,
        case_id: caseId.trim() || null,
        usar_rag: usarRag,
      });
      setRes(data);
    } catch (e: any) {
      const code = e?.response?.status;
      const detail = e?.response?.data?.detail || "Falha ao executar";
      if (code === 503)
        toast.error(
          "Módulo de IA desligado. Ative no servidor (AI_ENABLED=true + chave).",
        );
      else toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Agente Jurídico (Claude + Skills)"
        subtitle="Raciocínio jurídico avançado por tarefa, ancorado na base do escritório (RAG). Resultado é rascunho — revisão humana obrigatória (OAB)."
        actions={
          status ? (
            <span
              className={`text-xs font-semibold px-2.5 py-1 rounded-full ${habilitado ? "bg-green-100 text-green-700" : "bg-warn-100 text-warn-700"}`}
            >
              {habilitado ? "● IA ativa" : "● IA desligada"}
            </span>
          ) : undefined
        }
      />

      {status && !habilitado && (
        <div className="card p-3 border border-warn-200 bg-warn-50 text-sm text-warn-800 flex gap-2">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <div>
            Módulo de IA <b>desligado</b> (custo R$ 0). Para ativar: definir{" "}
            <code>ANTHROPIC_API_KEY</code> e <code>AI_ENABLED=true</code> no
            servidor.
            {!status?.anthropic_configurado &&
              " Chave Anthropic ainda não configurada."}{" "}
            Tarefas simples (resumo/triagem) usam Groq (grátis).
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Entrada */}
        <div className="card p-4 space-y-3">
          <div>
            <label className="label">Tarefa</label>
            <select
              value={tarefa}
              onChange={(e) => setTarefa(e.target.value)}
              className="input w-full"
            >
              {TAREFAS.map((t) => (
                <option key={t.k} value={t.k}>
                  {t.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">{dica}</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="label">Caso (opcional)</label>
              <input
                value={caseId}
                onChange={(e) => setCaseId(e.target.value)}
                className="input w-full"
                placeholder="ID do caso p/ contexto"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm text-gray-600 pb-2">
                <input
                  type="checkbox"
                  checked={usarRag}
                  onChange={(e) => setUsarRag(e.target.checked)}
                />
                Usar base jurídica (RAG)
              </label>
            </div>
          </div>
          <div>
            <label className="label">Solicitação</label>
            <textarea
              value={mensagem}
              onChange={(e) => setMensagem(e.target.value)}
              rows={9}
              className="input w-full"
              placeholder="Descreva o caso / pergunta / texto a processar…"
            />
          </div>
          <button
            onClick={executar}
            disabled={loading}
            className="btn-primary flex items-center gap-2"
          >
            {loading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Send size={15} />
            )}
            {loading ? "Processando…" : "Executar"}
          </button>
        </div>

        {/* Resultado */}
        <div className="card p-4">
          {!res && (
            <p className="text-sm text-gray-400 py-10 text-center">
              O resultado aparecerá aqui.
            </p>
          )}
          {res && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2 text-[11px]">
                <span className="px-2 py-0.5 rounded-full bg-primary-50 text-primary-700">
                  {res.modelo}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                  {res.tokens_usados} tokens
                </span>
                {res.custo_estimado_brl > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                    R$ {res.custo_estimado_brl}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded-full bg-warn-100 text-warn-700">
                  RASCUNHO
                </span>
              </div>
              <Markdown source={res.conteudo} className="text-sm text-navy-900 max-h-[28rem] overflow-auto bg-slate-50 rounded-lg p-3" />
              <p className="text-[11px] text-warn-700">{res.aviso}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
