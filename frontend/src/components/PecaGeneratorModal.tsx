import { useEffect, useState, useRef, useCallback } from "react";
import { authFetch } from "../lib/stream";
import api from "../lib/api";
import { Modal, Button, Badge } from "./UI";
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
  ShieldAlert,
  ShieldCheck,
  PenLine,
  CopyPlus,
  Bot,
} from "lucide-react";
import GuiadoForm from "./GuiadoForm";

// Catálogo de peças e áreas vem de GET /pecas/meta (fonte única no backend).
// O modal não espelha mais essas listas manualmente — busca no mount.
interface TipoMeta {
  value: string;
  label: string;
  grupo: string;
}
interface AreaMeta {
  value: string;
  label: string;
}
interface PecasMeta {
  tipos?: TipoMeta[];
  areas?: AreaMeta[];
  niveis_complexidade?: string[];
}

// Rótulos legíveis dos grupos de tipo (TIPOS_PECA_GRUPO no backend) e a ordem
// em que os <optgroup> aparecem no <select>.
const GRUPO_LABEL: Record<string, string> = {
  judicial_inicial: "Peça inicial",
  judicial_pos: "Fase pós-inicial",
  recurso: "Recursos",
  extrajudicial: "Extrajudicial",
};
const GRUPO_ORDEM = [
  "judicial_inicial",
  "judicial_pos",
  "recurso",
  "extrajudicial",
];

// Fallback mínimo embutido — usado APENAS se GET /pecas/meta falhar, para não
// quebrar o modal. Cobre um tipo de cada grupo e as áreas mais comuns.
const TIPOS_FALLBACK: TipoMeta[] = [
  {
    value: "peticao_inicial",
    label: "Petição Inicial",
    grupo: "judicial_inicial",
  },
  { value: "contestacao", label: "Contestação", grupo: "judicial_pos" },
  {
    value: "replica",
    label: "Réplica (Impugnação à Contestação)",
    grupo: "judicial_pos",
  },
  { value: "recurso_ordinario", label: "Recurso Ordinário", grupo: "recurso" },
  { value: "apelacao", label: "Apelação", grupo: "recurso" },
  { value: "acordo", label: "Proposta de Acordo", grupo: "extrajudicial" },
  {
    value: "notificacao",
    label: "Notificação Extrajudicial",
    grupo: "extrajudicial",
  },
  { value: "contrato", label: "Minuta de Contrato", grupo: "extrajudicial" },
];
const AREAS_FALLBACK: AreaMeta[] = [
  { value: "trabalhista", label: "Trabalhista" },
  { value: "civil", label: "Cível" },
  { value: "previdenciario", label: "Previdenciário" },
  { value: "tributario", label: "Tributário" },
  { value: "criminal", label: "Criminal" },
  { value: "consumidor", label: "Consumidor" },
  { value: "administrativo", label: "Administrativo" },
  { value: "familia", label: "Família" },
];

// Nível de complexidade / rito (GET /pecas/meta → niveis_complexidade). Fallback
// embutido usado APENAS se o meta não trouxer a lista. Rótulos legíveis abaixo.
const NIVEIS_FALLBACK = [
  "comum",
  "simples",
  "completa",
  "estrategica",
  "juizado_especial",
];
const NIVEL_LABEL: Record<string, string> = {
  comum: "Procedimento comum",
  simples: "Simples/enxuta",
  completa: "Completa",
  estrategica: "Estratégica (+ teses alternativas)",
  juizado_especial: "Juizado Especial (sumaríssimo)",
};

// Teses condicionais — adição/override MANUAL do advogado. O backend também
// deriva algumas automaticamente pelo caso/ficha; estas somam às automáticas.
// Flags desconhecidas são ignoradas pelo backend.
const FLAGS_TESES: { value: string; label: string }[] = [
  { value: "dano_moral", label: "Dano moral" },
  { value: "relacao_consumo", label: "Relação de consumo" },
  { value: "hipossuficiencia", label: "Hipossuficiência" },
  {
    value: "prova_documental_suficiente",
    label: "Prova documental suficiente",
  },
  { value: "pedido_tutela", label: "Pedido de tutela de urgência" },
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

// ── Verificação de citações (anti-alucinação #46) ──────────────────────────
// Shape emitido pelo backend no evento SSE `concluido` (verificacao_citacoes),
// produzido por verificador_jurisprudencia. Cada citação vem com um `status`
// e, quando aplicável, um `aviso` explicando o motivo.
type CitacaoStatus = "verificada" | "identificada" | "suspeita" | "generica";

interface CitacaoVerificada {
  citacao?: string;
  trecho?: string;
  tipo?: string;
  status: CitacaoStatus;
  aviso?: string | null;
  fonte_verificacao?: string | null;
}

interface VerificacaoCitacoes {
  total?: number;
  confirmadas?: number;
  nao_encontradas?: number;
  score?: number | null;
  citacoes?: CitacaoVerificada[];
  contagem_status?: Partial<Record<CitacaoStatus, number>>;
  avisos?: string[];
}

const CIT_STATUS_CFG: Record<
  CitacaoStatus,
  { label: string; row: string; chip: string }
> = {
  suspeita: {
    label: "Suspeita",
    row: "bg-danger-50 border-danger-200",
    chip: "bg-danger-100 text-danger-800",
  },
  generica: {
    label: "Genérica",
    row: "bg-warn-50 border-warn-200",
    chip: "bg-warn-100 text-warn-800",
  },
  identificada: {
    label: "Identificada",
    row: "bg-slate-50 border-slate-200",
    chip: "bg-slate-200 text-slate-700",
  },
  verificada: {
    label: "Verificada",
    row: "bg-green-50 border-green-200",
    chip: "bg-green-100 text-green-700",
  },
};

// Ordem de exibição: primeiro o que exige conferência (suspeita → genérica →
// identificada → verificada). Suspeita e genérica precisam saltar aos olhos.
const CIT_ORDEM: CitacaoStatus[] = [
  "suspeita",
  "generica",
  "identificada",
  "verificada",
];

function VerificacaoCitacoesPanel({
  verificacao,
}: {
  verificacao: VerificacaoCitacoes | null;
}) {
  // Sinal indisponível → aviso NEUTRO (nunca um falso "tudo verificado").
  if (!verificacao) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
        <ShieldAlert size={16} className="flex-shrink-0 text-slate-400" />
        <span>
          Verificação de citações indisponível para esta peça — confira súmulas,
          artigos e processos manualmente antes de protocolar.
        </span>
      </div>
    );
  }

  const citacoes = Array.isArray(verificacao.citacoes)
    ? verificacao.citacoes
    : [];
  const total = verificacao.total ?? citacoes.length;

  if (total === 0) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
        <ShieldAlert size={16} className="flex-shrink-0 text-slate-400" />
        <span>
          Nenhuma citação jurisprudencial detectada no texto — nada a verificar.
        </span>
      </div>
    );
  }

  const cont: Partial<Record<CitacaoStatus, number>> =
    verificacao.contagem_status ??
    citacoes.reduce<Partial<Record<CitacaoStatus, number>>>((acc, c) => {
      acc[c.status] = (acc[c.status] ?? 0) + 1;
      return acc;
    }, {});
  const nSuspeita = cont.suspeita ?? 0;
  const nGenerica = cont.generica ?? 0;
  const nIdentificada = cont.identificada ?? 0;
  const score = verificacao.score;

  // Tom do cabeçalho: vermelho se há suspeita (bloqueia aprovação no backend),
  // âmbar se há genérica/identificada não confirmada, verde se tudo verificado.
  const alerta = nSuspeita > 0;
  const atencao = !alerta && (nGenerica > 0 || nIdentificada > 0);
  const headTone = alerta
    ? "border-danger-200 bg-danger-50"
    : atencao
      ? "border-warn-200 bg-warn-50"
      : "border-green-200 bg-green-50";
  const scoreTone = alerta
    ? "bg-danger-100 text-danger-800"
    : atencao
      ? "bg-warn-100 text-warn-800"
      : "bg-green-100 text-green-700";

  const ordenadas = [...citacoes].sort(
    (a, b) => CIT_ORDEM.indexOf(a.status) - CIT_ORDEM.indexOf(b.status),
  );

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <div className={`flex items-center gap-2 px-4 py-3 border-b ${headTone}`}>
        {alerta ? (
          <ShieldAlert size={16} className="flex-shrink-0 text-danger-600" />
        ) : atencao ? (
          <AlertTriangle size={16} className="flex-shrink-0 text-warn-600" />
        ) : (
          <ShieldCheck size={16} className="flex-shrink-0 text-green-600" />
        )}
        <span className="text-sm font-medium text-slate-800">
          Verificação de citações
        </span>
        {score != null && (
          <span
            className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-semibold ${scoreTone}`}
          >
            Score {score}/100
          </span>
        )}
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Contadores por status (só os presentes) */}
        <div className="flex flex-wrap gap-1.5">
          {CIT_ORDEM.filter((s) => (cont[s] ?? 0) > 0).map((s) => (
            <span
              key={s}
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${CIT_STATUS_CFG[s].chip}`}
            >
              {cont[s]} {CIT_STATUS_CFG[s].label.toLowerCase()}
            </span>
          ))}
        </div>

        {nSuspeita > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 px-3 py-2 text-xs text-danger-700">
            <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
            <span>
              <strong>
                {nSuspeita} citação(ões) suspeita(s) de alucinação.
              </strong>{" "}
              A política do sistema <strong>bloqueia a aprovação</strong>{" "}
              enquanto houver citação suspeita — confira ou remova cada uma
              antes de revisar e assinar.
            </span>
          </div>
        )}

        <ul className="space-y-1.5">
          {ordenadas.map((c, i) => {
            const cfg = CIT_STATUS_CFG[c.status] ?? CIT_STATUS_CFG.identificada;
            return (
              <li key={i} className={`rounded-lg border px-3 py-2 ${cfg.row}`}>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cfg.chip}`}
                  >
                    {cfg.label}
                  </span>
                  <span className="text-xs font-medium text-slate-800 break-words">
                    {c.citacao || c.trecho || "(citação)"}
                  </span>
                </div>
                {c.aviso && (
                  <p className="mt-1 text-[11px] leading-snug text-slate-500">
                    {c.aviso}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  caseId?: string;
  onConcluido?: (logId: string, documento: string) => void;
  /**
   * Chamado quando o backend barra a geração por falta de ficha de triagem
   * confirmada (HTTP 409 { need_ficha_triagem: true, case_id }). O pai deve
   * levar o usuário à ficha. Recebe o case_id devolvido pelo backend.
   */
  onNeedFicha?: (caseId: string) => void;
}

type Fase = "form" | "gerando" | "concluido" | "erro";

export default function PecaGeneratorModal({
  open,
  onClose,
  caseId,
  onConcluido,
  onNeedFicha,
}: Props) {
  const [fase, setFase] = useState<Fase>("form");
  const [etapas, setEtapas] = useState<Etapa[]>(etapasInit());
  const [documento, setDocumento] = useState("");
  const [aiLogId, setAiLogId] = useState("");
  const [codigoPeca, setCodigoPeca] = useState("");
  const [erroMsg, setErroMsg] = useState("");
  const [copiado, setCopiado] = useState(false);
  const [expandidos, setExpandidos] = useState<Set<number>>(new Set());
  const [verificacao, setVerificacao] = useState<VerificacaoCitacoes | null>(
    null,
  );

  const [tipoPeca, setTipoPeca] = useState("peticao_inicial");
  const [areaDireito, setAreaDireito] = useState("trabalhista");
  const [nivelComplexidade, setNivelComplexidade] = useState("comum");
  const [flagsTeses, setFlagsTeses] = useState<Set<string>>(new Set());
  const [fatos, setFatos] = useState("");
  const [pedidos, setPedidos] = useState("");
  const [instrucoes, setInstrucoes] = useState("");
  const [nomesProteger, setNomesProteger] = useState("");
  const [modo, setModo] = useState<"livre" | "guiado" | "molde" | "agente">(
    "livre",
  );
  const [respostasGuiadas, setRespostasGuiadas] = useState<
    Record<string, string>
  >({});

  // Catálogo (/pecas/meta): parte do fallback e é substituído ao carregar.
  const [tipos, setTipos] = useState<TipoMeta[]>(TIPOS_FALLBACK);
  const [areas, setAreas] = useState<AreaMeta[]>(AREAS_FALLBACK);
  const [niveis, setNiveis] = useState<string[]>(NIVEIS_FALLBACK);
  const [metaLoading, setMetaLoading] = useState(false);
  const metaLoadedRef = useRef(false);

  const abortRef = useRef<AbortController | null>(null);

  // Aborta o stream SSE em voo ao desmontar — evita setState após unmount e
  // vazamento da conexão quando o modal é removido durante a geração.
  useEffect(() => () => abortRef.current?.abort(), []);

  // Busca o catálogo de peças/áreas na primeira abertura do modal. Falha é
  // silenciosa (mantém o fallback embutido + toast discreto) para não quebrar
  // o fluxo. Permite retry numa próxima abertura se a chamada falhar.
  useEffect(() => {
    if (!open || metaLoadedRef.current) return;
    metaLoadedRef.current = true;
    setMetaLoading(true);
    api
      .get<PecasMeta>("/pecas/meta")
      .then(({ data }) => {
        if (Array.isArray(data.tipos) && data.tipos.length)
          setTipos(data.tipos);
        if (Array.isArray(data.areas) && data.areas.length)
          setAreas(data.areas);
        if (
          Array.isArray(data.niveis_complexidade) &&
          data.niveis_complexidade.length
        )
          setNiveis(data.niveis_complexidade);
      })
      .catch(() => {
        metaLoadedRef.current = false;
        toast.error(
          "Não foi possível carregar o catálogo de peças. Usando lista básica.",
        );
      })
      .finally(() => setMetaLoading(false));
  }, [open]);

  const tipoLabel = (v: string) => tipos.find((t) => t.value === v)?.label ?? v;
  const areaLabel = (v: string) => areas.find((a) => a.value === v)?.label ?? v;

  const resetForm = () => {
    setFase("form");
    setEtapas(etapasInit());
    setDocumento("");
    setAiLogId("");
    setCodigoPeca("");
    setErroMsg("");
    setCopiado(false);
    setExpandidos(new Set());
    setVerificacao(null);
    setModo("livre");
    setRespostasGuiadas({});
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

  const toggleFlagTese = (value: string) => {
    setFlagsTeses((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const toggleExpandir = (num: number) => {
    setExpandidos((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  };

  const gerar = useCallback(async () => {
    const isGuiado = modo === "guiado";
    const effectiveFatos = isGuiado
      ? Object.entries(respostasGuiadas)
          .filter(([k, v]) => v.trim().length > 0)
          .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
          .join("\n\n")
      : fatos;
    const effectivePedidos = isGuiado
      ? respostasGuiadas["pedidos"] || pedidos
      : pedidos;

    if (!effectiveFatos.trim() || effectiveFatos.trim().length < 50) {
      toast.error(
        isGuiado
          ? "Preencha pelo menos o campo 'fatos' no formulário guiado."
          : "Descreva os fatos com pelo menos 50 caracteres.",
      );
      return;
    }
    if (!effectivePedidos.trim() || effectivePedidos.trim().length < 10) {
      toast.error(
        isGuiado
          ? "Preencha o campo 'pedidos' no formulário guiado."
          : "Informe os pedidos.",
      );
      return;
    }

    setFase("gerando");
    setEtapas(etapasInit());
    setDocumento("");
    abortRef.current = new AbortController();

    // Contrato estruturado dos modos (P1 — fim das tags de modo embutidas no
    // prompt): o backend valida via preparar_modo_producao e devolve 409 com
    // os bloqueios quando o modo não está pronto para redação.
    const modoProducao = {
      modo,
      tipo_peca: tipoPeca,
      area_direito: areaDireito,
      instrucao_livre: instrucoes || null,
      respostas_guiadas: isGuiado ? respostasGuiadas : {},
      // Agente: o clique em "Gerar" é a aprovação explícita do plano exibido.
      aprovado_para_redacao: modo === "agente",
    };

    const body = JSON.stringify({
      tipo_peca: tipoPeca,
      area_direito: areaDireito,
      nivel_complexidade: nivelComplexidade,
      flags_teses: Array.from(flagsTeses),
      descricao_fatos: effectiveFatos,
      pedidos: effectivePedidos,
      nomes_proteger: nomesProteger
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      case_id: caseId ?? null,
      instrucoes_adicionais: instrucoes || null,
      modo_producao: modoProducao,
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
        // Gate da ficha de triagem: peça com case_id exige ficha confirmada.
        // FastAPI aninha o payload sob `detail`:
        //   { detail: { detail, need_ficha_triagem: true, case_id } }
        // O pai leva o usuário até a ficha; abortamos a geração sem erro cru.
        const detailObj =
          typeof err.detail === "object" && err.detail !== null
            ? (err.detail as Record<string, any>)
            : null;
        if (res.status === 409 && detailObj?.need_ficha_triagem) {
          setFase("form");
          onNeedFicha?.(detailObj.case_id ?? caseId ?? "");
          return;
        }
        // Bloqueio dos modos controlados: lista objetiva do que falta.
        if (res.status === 409 && Array.isArray(detailObj?.bloqueios)) {
          setFase("form");
          toast.error(
            `Modo ${detailObj.modo ?? modo}: ${detailObj.bloqueios.join(" · ")}`,
          );
          return;
        }
        const detail = detailObj
          ? (detailObj.mensagem ??
            detailObj.detail ??
            JSON.stringify(detailObj))
          : err.detail;
        throw new Error(detail ?? "Erro na requisição");
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
            setCodigoPeca(payload.codigo_peca ?? "");
            // Relatório anti-alucinação do pipeline (súmulas/artigos/processos
            // conferidos contra a base oficial) — pode vir null (fail-safe do
            // backend), tratado como "verificação indisponível" no painel.
            setVerificacao(payload.verificacao_citacoes ?? null);
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
    modo,
    respostasGuiadas,
    tipoPeca,
    areaDireito,
    nivelComplexidade,
    flagsTeses,
    fatos,
    pedidos,
    instrucoes,
    nomesProteger,
    caseId,
    onConcluido,
    onNeedFicha,
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
    a.download = `${tipoLabel(tipoPeca)}_EJC.txt`;
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
                    disabled={metaLoading}
                  >
                    {GRUPO_ORDEM.filter((g) =>
                      tipos.some((t) => t.grupo === g),
                    ).map((g) => (
                      <optgroup key={g} label={GRUPO_LABEL[g] ?? g}>
                        {tipos
                          .filter((t) => t.grupo === g)
                          .map((t) => (
                            <option key={t.value} value={t.value}>
                              {t.label}
                            </option>
                          ))}
                      </optgroup>
                    ))}
                    {/* Defensivo: tipos com grupo fora dos quatro conhecidos */}
                    {(() => {
                      const extras = tipos.filter(
                        (t) => !GRUPO_ORDEM.includes(t.grupo),
                      );
                      return extras.length ? (
                        <optgroup label="Outros">
                          {extras.map((t) => (
                            <option key={t.value} value={t.value}>
                              {t.label}
                            </option>
                          ))}
                        </optgroup>
                      ) : null;
                    })()}
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
                    disabled={metaLoading}
                  >
                    {areas.map((a) => (
                      <option key={a.value} value={a.value}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label
                  htmlFor="peca-nivel"
                  className="block text-xs font-medium text-slate-600 mb-1"
                >
                  Nível / rito
                </label>
                <select
                  id="peca-nivel"
                  value={nivelComplexidade}
                  onChange={(e) => setNivelComplexidade(e.target.value)}
                  className="input"
                  disabled={metaLoading}
                >
                  {niveis.map((n) => (
                    <option key={n} value={n}>
                      {NIVEL_LABEL[n] ?? n}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-2">
                  Modo de produção
                </label>
                <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
                  {(
                    [
                      {
                        id: "livre",
                        label: "Livre",
                        icon: <PenLine size={14} />,
                        desc: "Campos abertos",
                      },
                      {
                        id: "guiado",
                        label: "Guiado",
                        icon: <ListOrdered size={14} />,
                        desc: "Passo a passo",
                      },
                      {
                        id: "molde",
                        label: "Molde",
                        icon: <CopyPlus size={14} />,
                        desc: "Espelhar peça",
                      },
                      {
                        id: "agente",
                        label: "Agente",
                        icon: <Bot size={14} />,
                        desc: "10 etapas",
                      },
                    ] as const
                  ).map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setModo(m.id)}
                      className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                        modo === m.id
                          ? "bg-white text-ai-700 shadow-sm"
                          : "text-slate-500 hover:text-slate-700"
                      }`}
                      title={m.desc}
                    >
                      {m.icon}
                      {m.label}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-slate-400 mt-1.5">
                  {modo === "livre" &&
                    "Preencha os campos livremente — a IA interpreta sua redação."}
                  ,
                  {modo === "guiado" &&
                    "Formulário estruturado por tipo de peça — cada campo alimenta uma etapa específica."}
                  ,
                  {modo === "molde" &&
                    "Selecione uma peça existente como modelo para espelhar estrutura e estilo."}
                  ,
                  {modo === "agente" &&
                    "Pipeline completo com 10 etapas — o agente executa busca, análise e síntese autonomamente."}
                  ,
                </p>
              </div>

              <fieldset className="border border-slate-100 rounded-xl px-4 py-3">
                <legend className="text-xs font-medium text-slate-600 px-1">
                  Teses condicionais (opcional)
                </legend>
                <p className="text-xs text-slate-400 mb-2">
                  O sistema já detecta algumas automaticamente pelo caso/ficha.
                  Marque aqui apenas as que deseja adicionar manualmente — elas
                  somam às automáticas.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
                  {FLAGS_TESES.map((f) => (
                    <label
                      key={f.value}
                      className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={flagsTeses.has(f.value)}
                        onChange={() => toggleFlagTese(f.value)}
                        className="rounded border-slate-300 text-ai-600 focus:ring-ai-500"
                      />
                      {f.label}
                    </label>
                  ))}
                </div>
              </fieldset>

              {/* ── CAMPOS POR MODO ── */}
              {modo === "guiado" ? (
                <GuiadoForm
                  tipoPeca={tipoPeca}
                  respostas={respostasGuiadas}
                  onChange={(campo, valor) =>
                    setRespostasGuiadas((prev) => ({ ...prev, [campo]: valor }))
                  }
                />
              ) : modo === "molde" ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                  <CopyPlus size={24} className="mx-auto mb-2 text-slate-400" />
                  <p>
                    Selecione uma peça existente no passo seguinte para usar
                    como modelo. A IA manterá a estrutura e estilo do molde.
                  </p>
                </div>
              ) : modo === "agente" ? (
                <div className="rounded-xl border border-dashed border-ai-200 bg-ai-50 px-4 py-6 text-center text-sm text-ai-700">
                  <Bot size={24} className="mx-auto mb-2 text-ai-400" />
                  <p>
                    O agente executará 10 etapas automaticamente: Extração →
                    Classificação → Tese → Precedentes → Fundamentação → Pedidos
                    → Estrutura → Redação → Revisão → Versão Final.
                  </p>
                  <p className="mt-1 text-xs text-ai-500">
                    Preencha os campos abaixo com as informações básicas — o
                    agente irá expandir e enriquecer cada seção.
                  </p>
                </div>
              ) : null}

              {modo !== "guiado" && (
                <>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Descrição dos fatos{" "}
                      <span className="text-danger-400">*</span>
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
                </>
              )}

              {modo === "guiado" && (
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
              )}

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
                  {tipoLabel(tipoPeca)} · {areaLabel(areaDireito)}
                  <span className="ml-2 inline-flex items-center rounded-md bg-ai-50 px-1.5 py-0.5 text-[10px] font-medium text-ai-700 ring-1 ring-inset ring-ai-200">
                    {modo === "livre"
                      ? "Livre"
                      : modo === "guiado"
                        ? "Guiado"
                        : modo === "molde"
                          ? "Molde"
                          : "Agente"}
                  </span>
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
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-green-800">
                      Peça gerada com sucesso
                    </span>
                    {codigoPeca && (
                      <Badge tone="ouro" className="font-mono">
                        {codigoPeca}
                      </Badge>
                    )}
                    <span className="inline-flex items-center rounded-md bg-ai-50 px-1.5 py-0.5 text-[10px] font-medium text-ai-700 ring-1 ring-inset ring-ai-200">
                      Modo:{" "}
                      {modo === "livre"
                        ? "Livre"
                        : modo === "guiado"
                          ? "Guiado"
                          : modo === "molde"
                            ? "Molde"
                            : "Agente"}
                    </span>
                  </div>
                  <div className="text-xs text-green-600">
                    Log ID: {aiLogId} · Aguarda revisão HITL
                  </div>
                </div>
              </div>

              {/* Painel anti-alucinação — score + citações destacadas por
                  status (suspeita/genérica em vermelho/amarelo, verificadas em
                  verde). Fica junto ao documento para a revisão HITL. */}
              <VerificacaoCitacoesPanel verificacao={verificacao} />

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
