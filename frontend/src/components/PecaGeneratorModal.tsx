import { useEffect, useState, useRef, useCallback } from "react";
import { authFetch } from "../lib/stream";
import { Modal, Button } from "./UI";
import { toast } from "./Toast";
import {
  Sparkles,
  FileText,
  Scale,
  Search,
  BookOpen,
  ListOrdered,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Copy,
  Download,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

const TIPOS_PECA: Record<string, string> = {
  peticao_inicial: "Petição Inicial",
  contestacao: "Contestação",
  replica: "Réplica (Impugnação à Contestação)",
  recurso_ordinario: "Recurso Ordinário",
  apelacao: "Apelação",
  contrarrazoes: "Contrarrazões",
  embargos_declaracao: "Embargos de Declaração",
  agravo: "Agravo",
  cumprimento_sentenca: "Cumprimento de Sentença",
  impugnacao_cumprimento: "Impugnação ao Cumprimento de Sentença",
  embargos_execucao: "Embargos à Execução",
  mandado_seguranca: "Mandado de Segurança",
  memorias: "Memoriais",
  acordo: "Proposta de Acordo",
  parecer: "Parecer Jurídico",
  notificacao: "Notificação Extrajudicial",
  contrato: "Minuta de Contrato",
  impugnacao: "Impugnação",
};

const AREAS: string[] = [
  "trabalhista",
  "civil",
  "previdenciario",
  "tributario",
  "criminal",
  "consumidor",
  "administrativo",
  "familia",
];

interface Etapa {
  num: number;
  titulo: string;
  icon: React.ReactNode;
  status: "aguardando" | "em_andamento" | "concluido" | "erro";
  resultado?: string;
}

const ETAPAS_DEF: Omit<Etapa, "status">[] = [
  {
    num: 1,
    titulo: "Identificando tipo de peça",
    icon: <FileText size={15} />,
  },
  { num: 2, titulo: "Estruturando enquadramento", icon: <Scale size={15} /> },
  { num: 3, titulo: "Buscando fundamentos legais", icon: <Search size={15} /> },
  { num: 4, titulo: "Analisando jurisprudência", icon: <BookOpen size={15} /> },
  { num: 5, titulo: "Organizando argumentos", icon: <ListOrdered size={15} /> },
  { num: 6, titulo: "Identificando riscos", icon: <AlertTriangle size={15} /> },
  {
    num: 7,
    titulo: "Montando documento completo",
    icon: <CheckCircle2 size={15} />,
  },
];

function etapasInit(): Etapa[] {
  return ETAPAS_DEF.map((e) => ({ ...e, status: "aguardando" }));
}

interface Props {
  open: boolean;
  onClose: () => void;
  caseId?: string;
  onConcluido?: (logId: string, documento: string) => void;
}

type Fase = "form" | "gerando" | "concluido" | "erro";

export default function PecaGeneratorModal({
  open,
  onClose,
  caseId,
  onConcluido,
}: Props) {
  const [fase, setFase] = useState<Fase>("form");
  const [etapas, setEtapas] = useState<Etapa[]>(etapasInit());
  const [documento, setDocumento] = useState("");
  const [aiLogId, setAiLogId] = useState("");
  const [erroMsg, setErroMsg] = useState("");
  const [copiado, setCopiado] = useState(false);
  const [expandidos, setExpandidos] = useState<Set<number>>(new Set());

  const [tipoPeca, setTipoPeca] = useState("peticao_inicial");
  const [areaDireito, setAreaDireito] = useState("trabalhista");
  const [fatos, setFatos] = useState("");
  const [pedidos, setPedidos] = useState("");
  const [instrucoes, setInstrucoes] = useState("");
  const [nomesProteger, setNomesProteger] = useState("");

  const abortRef = useRef<AbortController | null>(null);

  // Aborta o stream SSE em voo ao desmontar — evita setState após unmount e
  // vazamento da conexão quando o modal é removido durante a geração.
  useEffect(() => () => abortRef.current?.abort(), []);

  const resetForm = () => {
    setFase("form");
    setEtapas(etapasInit());
    setDocumento("");
    setAiLogId("");
    setErroMsg("");
    setCopiado(false);
    setExpandidos(new Set());
  };

  const fechar = () => {
    abortRef.current?.abort();
    resetForm();
    onClose();
  };

  const setEtapaStatus = (
    num: number,
    status: Etapa["status"],
    resultado?: string,
  ) => {
    setEtapas((prev) =>
      prev.map((e) =>
        e.num === num
          ? { ...e, status, resultado: resultado ?? e.resultado }
          : e,
      ),
    );
  };

  const toggleExpandir = (num: number) => {
    setExpandidos((prev) => {
      const next = new Set(prev);
      next.has(num) ? next.delete(num) : next.add(num);
      return next;
    });
  };

  const gerar = useCallback(async () => {
    if (!fatos.trim() || fatos.trim().length < 50) {
      toast.error("Descreva os fatos com pelo menos 50 caracteres.");
      return;
    }
    if (!pedidos.trim() || pedidos.trim().length < 10) {
      toast.error("Informe os pedidos.");
      return;
    }

    setFase("gerando");
    setEtapas(etapasInit());
    setDocumento("");
    abortRef.current = new AbortController();

    const body = JSON.stringify({
      tipo_peca: tipoPeca,
      area_direito: areaDireito,
      descricao_fatos: fatos,
      pedidos,
      nomes_proteger: nomesProteger
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      case_id: caseId ?? null,
      instrucoes_adicionais: instrucoes || null,
    });

    try {
      const res = await authFetch("/api/pecas/gerar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        const err = await res
          .json()
          .catch(() => ({ detail: "Erro desconhecido" }));
        throw new Error(err.detail ?? "Erro na requisição");
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";

        for (const part of parts) {
          const eventLine = part.match(/^event:\s*(.+)$/m)?.[1]?.trim();
          const dataLine = part.match(/^data:\s*(.+)$/ms)?.[1]?.trim();
          if (!dataLine) continue;

          let payload: Record<string, any> = {};
          try {
            payload = JSON.parse(dataLine);
          } catch {
            continue;
          }

          if (eventLine === "step") {
            const { etapa, status, resultado } = payload;
            setEtapaStatus(
              etapa,
              status === "em_andamento" ? "em_andamento" : "concluido",
              resultado,
            );
          } else if (eventLine === "concluido") {
            setDocumento(payload.documento ?? "");
            setAiLogId(payload.ai_log_id ?? "");
            setFase("concluido");
            onConcluido?.(payload.ai_log_id, payload.documento);
          } else if (eventLine === "erro") {
            throw new Error(payload.detail ?? "Erro na geração");
          }
        }
      }
    } catch (e: any) {
      if (e.name === "AbortError") return;
      setErroMsg(e.message ?? "Erro desconhecido");
      setFase("erro");
    }
  }, [
    tipoPeca,
    areaDireito,
    fatos,
    pedidos,
    instrucoes,
    nomesProteger,
    caseId,
    onConcluido,
  ]);

  const copiar = () => {
    navigator.clipboard.writeText(documento);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  const baixarTxt = () => {
    const blob = new Blob([documento], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${TIPOS_PECA[tipoPeca] ?? "peca"}_EJC.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Modal open={open} onClose={fechar} title="Gerador de Peças — IA" wide>
      <div className="flex flex-col">
        <div className="-mt-5 -mx-5 mb-4 px-5 pb-3 border-b border-slate-100">
          <p className="text-xs text-slate-400">
            Pipeline 7 etapas · HITL obrigatório
          </p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* ── FASE: FORMULÁRIO ── */}
          {fase === "form" && (
            <div className="p-6 flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Tipo de peça
                  </label>
                  <select
                    value={tipoPeca}
                    onChange={(e) => setTipoPeca(e.target.value)}
                    className="input"
                  >
                    {Object.entries(TIPOS_PECA).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Área do direito
                  </label>
                  <select
                    value={areaDireito}
                    onChange={(e) => setAreaDireito(e.target.value)}
                    className="input"
                  >
                    {AREAS.map((a) => (
                      <option key={a} value={a}>
                        {a.charAt(0).toUpperCase() + a.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Descrição dos fatos <span className="text-danger-400">*</span>
                  <span className="text-slate-400 font-normal ml-1">
                    mín. 50 caracteres
                  </span>
                </label>
                <textarea
                  value={fatos}
                  onChange={(e) => setFatos(e.target.value)}
                  placeholder="Descreva os fatos de forma detalhada. A IA usa esta descrição como base para todas as 7 etapas do pipeline..."
                  rows={5}
                  className="input resize-none"
                />
                <div className="text-right text-xs text-slate-400 mt-0.5">
                  {fatos.length} caracteres
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Pedidos <span className="text-danger-400">*</span>
                </label>
                <textarea
                  value={pedidos}
                  onChange={(e) => setPedidos(e.target.value)}
                  placeholder="Liste os pedidos principais e subsidiários..."
                  rows={3}
                  className="input resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Nomes a proteger (LGPD)
                    <span className="text-slate-400 font-normal ml-1">
                      separados por vírgula
                    </span>
                  </label>
                  <input
                    type="text"
                    value={nomesProteger}
                    onChange={(e) => setNomesProteger(e.target.value)}
                    placeholder="João Silva, Maria Costa..."
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Instruções adicionais
                  </label>
                  <input
                    type="text"
                    value={instrucoes}
                    onChange={(e) => setInstrucoes(e.target.value)}
                    placeholder="Ex: incluir pedido liminar..."
                    className="input"
                  />
                </div>
              </div>

              <div className="bg-warn-50 border border-warn-200 rounded-lg px-4 py-3 text-xs text-warn-800">
                <strong>⚠️ RASCUNHO:</strong> toda peça gerada por IA exige
                revisão e assinatura por advogado habilitado (OAB). Não
                protocole sem revisão humana.
              </div>
            </div>
          )}

          {/* ── FASE: GERANDO ── */}
          {(fase === "gerando" || fase === "erro") && (
            <div className="p-6">
              <div className="mb-5">
                <h3 className="text-sm font-medium text-slate-800 mb-1">
                  {fase === "gerando"
                    ? "Gerando sua peça..."
                    : "Erro na geração"}
                </h3>
                <p className="text-xs text-slate-400">
                  {TIPOS_PECA[tipoPeca]} · {areaDireito}
                </p>
              </div>

              <div className="flex flex-col gap-2">
                {etapas.map((e) => (
                  <div
                    key={e.num}
                    className="border border-slate-100 rounded-xl overflow-hidden"
                  >
                    <div
                      className={`flex items-center gap-3 px-4 py-3 transition-colors ${
                        e.status === "concluido"
                          ? "bg-green-50"
                          : e.status === "em_andamento"
                            ? "bg-ai-50"
                            : "bg-white"
                      }`}
                    >
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-medium ${
                          e.status === "concluido"
                            ? "bg-green-500 text-white"
                            : e.status === "em_andamento"
                              ? "bg-ai-600 text-white"
                              : "bg-slate-100 text-slate-400"
                        }`}
                      >
                        {e.status === "em_andamento" ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : e.status === "concluido" ? (
                          <CheckCircle2 size={13} />
                        ) : (
                          e.num
                        )}
                      </div>
                      <div
                        className={`flex-1 text-sm ${
                          e.status === "concluido"
                            ? "text-green-800 font-medium"
                            : e.status === "em_andamento"
                              ? "text-ai-800 font-medium"
                              : "text-slate-400"
                        }`}
                      >
                        {e.titulo}
                      </div>
                      {e.status === "concluido" && e.resultado && (
                        <button
                          onClick={() => toggleExpandir(e.num)}
                          className="text-slate-400 hover:text-slate-600 p-0.5"
                        >
                          {expandidos.has(e.num) ? (
                            <ChevronUp size={14} />
                          ) : (
                            <ChevronDown size={14} />
                          )}
                        </button>
                      )}
                    </div>
                    {e.status === "concluido" &&
                      e.resultado &&
                      expandidos.has(e.num) && (
                        <div className="px-4 py-3 bg-slate-50 border-t border-slate-100 text-xs text-slate-600 leading-relaxed">
                          {e.resultado}
                        </div>
                      )}
                  </div>
                ))}
              </div>

              {fase === "erro" && (
                <div className="mt-4 bg-danger-50 border border-danger-200 rounded-lg px-4 py-3 text-sm text-danger-700">
                  {erroMsg}
                </div>
              )}
            </div>
          )}

          {/* ── FASE: CONCLUÍDO ── */}
          {fase === "concluido" && (
            <div className="p-6 flex flex-col gap-4">
              <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl px-4 py-3">
                <CheckCircle2
                  size={18}
                  className="text-green-600 flex-shrink-0"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium text-green-800">
                    Peça gerada com sucesso
                  </div>
                  <div className="text-xs text-green-600">
                    Log ID: {aiLogId} · Aguarda revisão HITL
                  </div>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-600">
                    Documento gerado
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={copiar}
                      className="flex items-center gap-1 text-xs text-slate-500 hover:text-ai-600 transition-colors"
                    >
                      <Copy size={13} />
                      {copiado ? "Copiado!" : "Copiar"}
                    </button>
                    <button
                      onClick={baixarTxt}
                      className="flex items-center gap-1 text-xs text-slate-500 hover:text-ai-600 transition-colors"
                    >
                      <Download size={13} />
                      Baixar
                    </button>
                  </div>
                </div>
                <textarea
                  readOnly
                  value={documento}
                  rows={14}
                  className="input bg-slate-50 font-mono resize-none"
                />
              </div>

              <div className="bg-warn-50 border border-warn-200 rounded-lg px-4 py-3 text-xs text-warn-800">
                <strong>⚠️ Atenção:</strong> este é um rascunho gerado por IA.
                Revise, complemente com dados reais do caso e assine antes de
                protocolar.
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="-mx-5 -mb-5 px-6 py-4 mt-4 border-t border-slate-100 flex items-center justify-between gap-3 bg-white rounded-b-2xl">
          {fase === "form" && (
            <>
              <Button variant="ghost" onClick={fechar}>
                Cancelar
              </Button>
              <Button
                variant="ai"
                onClick={gerar}
                disabled={fatos.length < 50 || pedidos.length < 10}
                icon={<Sparkles size={15} />}
              >
                Gerar peça com IA
              </Button>
            </>
          )}
          {fase === "gerando" && (
            <>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 size={13} className="animate-spin" />
                Processando pipeline...
              </div>
              <button
                onClick={() => {
                  abortRef.current?.abort();
                  resetForm();
                }}
                className="px-4 py-2 text-sm text-danger-500 hover:text-danger-700 transition-colors"
              >
                Cancelar
              </button>
            </>
          )}
          {fase === "erro" && (
            <>
              <Button variant="ghost" onClick={resetForm}>
                Voltar
              </Button>
              <Button
                variant="ai"
                onClick={gerar}
                icon={<Sparkles size={15} />}
              >
                Tentar novamente
              </Button>
            </>
          )}
          {fase === "concluido" && (
            <>
              <Button variant="ghost" onClick={resetForm}>
                Nova peça
              </Button>
              <Button variant="ai" onClick={fechar}>
                Fechar
              </Button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
