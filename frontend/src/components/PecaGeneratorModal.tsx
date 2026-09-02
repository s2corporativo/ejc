import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  Loader2,
  PenLine,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import api from "../lib/api";
import { authFetch } from "../lib/stream";
import { Badge, Button, Modal } from "./UI";
import { toast } from "./Toast";
import GuiadoForm from "./GuiadoForm";

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

interface Etapa {
  num: number;
  titulo: string;
  status: "aguardando" | "em_andamento" | "concluido" | "erro";
  resultado?: string;
}

const ETAPAS = [
  "Identificando a peça",
  "Estruturando o enquadramento",
  "Buscando fundamentos",
  "Analisando jurisprudência",
  "Organizando argumentos",
  "Identificando riscos",
  "Montando a minuta",
];

const NIVEL_LABEL: Record<string, string> = {
  comum: "Procedimento comum",
  simples: "Simples / enxuta",
  completa: "Completa",
  estrategica: "Estratégica",
  juizado_especial: "Juizado Especial",
};

const FLAGS_TESES = [
  ["dano_moral", "Dano moral"],
  ["relacao_consumo", "Relação de consumo"],
  ["hipossuficiencia", "Hipossuficiência"],
  ["prova_documental_suficiente", "Prova documental suficiente"],
  ["pedido_tutela", "Tutela de urgência"],
] as const;

type CitacaoStatus =
  | "verificada"
  | "identificada"
  | "suspeita"
  | "generica"
  | "possivelmente_desatualizada";

interface CitacaoVerificada {
  citacao?: string;
  trecho?: string;
  status: CitacaoStatus;
  aviso?: string | null;
}

interface VerificacaoCitacoes {
  total?: number;
  score?: number | null;
  citacoes?: CitacaoVerificada[];
  avisos?: string[];
}

interface ResiduoAchado {
  categoria: "cliente" | "parte_contraria" | "documento" | "processo";
  rotulo: string;
  termo: string;
  mensagem: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  caseId?: string;
  onConcluido?: (logId: string, documento: string) => void;
  onNeedFicha?: (caseId: string) => void;
}

type Fase = "form" | "gerando" | "concluido" | "erro";
type ModoVisivel = "guiado" | "livre";

function etapasInit(): Etapa[] {
  return ETAPAS.map((titulo, index) => ({
    num: index + 1,
    titulo,
    status: "aguardando",
  }));
}

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

  const [tipoPeca, setTipoPeca] = useState("peticao_inicial");
  const [areaDireito, setAreaDireito] = useState("trabalhista");
  const [nivelComplexidade, setNivelComplexidade] = useState("comum");
  const [modo, setModo] = useState<ModoVisivel>("guiado");
  const [mostrarAvancado, setMostrarAvancado] = useState(false);

  const [respostasGuiadas, setRespostasGuiadas] = useState<Record<string, string>>({});
  const [fatos, setFatos] = useState("");
  const [pedidos, setPedidos] = useState("");
  const [instrucoes, setInstrucoes] = useState("");
  const [nomesProteger, setNomesProteger] = useState("");
  const [flagsTeses, setFlagsTeses] = useState<Set<string>>(new Set());

  const [tipos, setTipos] = useState<TipoMeta[]>([]);
  const [areas, setAreas] = useState<AreaMeta[]>([]);
  const [niveis, setNiveis] = useState<string[]>([]);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaErro, setMetaErro] = useState<string | null>(null);
  const metaLoadedRef = useRef(false);

  const [verificacao, setVerificacao] = useState<VerificacaoCitacoes | null>(null);
  const [alertasIa, setAlertasIa] = useState<string[]>([]);
  const [residuos, setResiduos] = useState<ResiduoAchado[]>([]);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (!open || metaLoadedRef.current) return;
    metaLoadedRef.current = true;
    setMetaLoading(true);
    setMetaErro(null);

    api
      .get<PecasMeta>("/pecas/meta")
      .then(({ data }) => {
        if (
          !Array.isArray(data.tipos) ||
          data.tipos.length === 0 ||
          !Array.isArray(data.areas) ||
          data.areas.length === 0 ||
          !Array.isArray(data.niveis_complexidade) ||
          data.niveis_complexidade.length === 0
        ) {
          throw new Error("Catálogo canônico incompleto");
        }

        setTipos(data.tipos);
        setAreas(data.areas);
        setNiveis(data.niveis_complexidade);
        setTipoPeca((atual) =>
          data.tipos!.some((t) => t.value === atual)
            ? atual
            : data.tipos![0].value,
        );
        setAreaDireito((atual) =>
          data.areas!.some((a) => a.value === atual)
            ? atual
            : data.areas![0].value,
        );
        setNivelComplexidade((atual) =>
          data.niveis_complexidade!.includes(atual)
            ? atual
            : data.niveis_complexidade![0],
        );
      })
      .catch(() => {
        metaLoadedRef.current = false;
        setTipos([]);
        setAreas([]);
        setNiveis([]);
        setMetaErro(
          "Catálogo jurídico indisponível. A geração foi bloqueada para evitar taxonomia desatualizada.",
        );
        toast.error("Não foi possível carregar o catálogo de peças");
      })
      .finally(() => setMetaLoading(false));
  }, [open]);

  const tipoLabel = (value: string) =>
    tipos.find((tipo) => tipo.value === value)?.label ?? value;

  const areaLabel = (value: string) =>
    areas.find((area) => area.value === value)?.label ?? value;

  const catalogoIndisponivel =
    metaLoading ||
    !!metaErro ||
    tipos.length === 0 ||
    areas.length === 0 ||
    niveis.length === 0;

  const resetForm = () => {
    setFase("form");
    setEtapas(etapasInit());
    setDocumento("");
    setAiLogId("");
    setCodigoPeca("");
    setErroMsg("");
    setCopiado(false);
    setModo("guiado");
    setMostrarAvancado(false);
    setRespostasGuiadas({});
    setFatos("");
    setPedidos("");
    setInstrucoes("");
    setNomesProteger("");
    setFlagsTeses(new Set());
    setVerificacao(null);
    setAlertasIa([]);
    setResiduos([]);
  };

  const fechar = () => {
    abortRef.current?.abort();
    if (fase === "concluido" && documento) {
      onConcluido?.(aiLogId, documento);
    }
    resetForm();
    onClose();
  };

  const toggleFlag = (flag: string) => {
    setFlagsTeses((atual) => {
      const novo = new Set(atual);
      if (novo.has(flag)) novo.delete(flag);
      else novo.add(flag);
      return novo;
    });
  };

  const setEtapaStatus = (
    num: number,
    status: Etapa["status"],
    resultado?: string,
  ) => {
    setEtapas((atual) =>
      atual.map((etapa) =>
        etapa.num === num
          ? { ...etapa, status, resultado: resultado ?? etapa.resultado }
          : etapa,
      ),
    );
  };

  const gerar = useCallback(async () => {
    if (catalogoIndisponivel) {
      toast.error("Catálogo jurídico indisponível. Reabra o gerador e tente novamente.");
      return;
    }

    const isGuiado = modo === "guiado";
    const effectiveFatos = isGuiado
      ? Object.entries(respostasGuiadas)
          .filter(([, valor]) => valor.trim().length > 0)
          .map(([campo, valor]) => `${campo.replace(/_/g, " ")}: ${valor}`)
          .join("\n\n")
      : fatos;
    const effectivePedidos = isGuiado
      ? respostasGuiadas["pedidos"] || pedidos
      : pedidos;

    if (!effectiveFatos.trim() || effectiveFatos.trim().length < 50) {
      toast.error(
        isGuiado
          ? "Preencha os dados essenciais do formulário guiado."
          : "Descreva os fatos com pelo menos 50 caracteres.",
      );
      return;
    }
    if (!effectivePedidos.trim() || effectivePedidos.trim().length < 10) {
      toast.error("Informe o resultado jurídico pretendido / pedidos.");
      return;
    }

    setFase("gerando");
    setEtapas(etapasInit());
    setDocumento("");
    setVerificacao(null);
    setAlertasIa([]);
    setResiduos([]);
    abortRef.current = new AbortController();

    const modoProducao = {
      modo,
      tipo_peca: tipoPeca,
      area_direito: areaDireito,
      instrucao_livre: modo === "livre" ? instrucoes || null : null,
      respostas_guiadas: isGuiado ? respostasGuiadas : {},
      aprovado_para_redacao: false,
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
        .map((nome) => nome.trim())
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
        const err = await res.json().catch(() => ({ detail: "Erro desconhecido" }));
        const detailObj =
          typeof err.detail === "object" && err.detail !== null
            ? (err.detail as Record<string, any>)
            : null;

        if (res.status === 409 && detailObj?.need_ficha_triagem) {
          setFase("form");
          onNeedFicha?.(detailObj.case_id ?? caseId ?? "");
          return;
        }

        if (res.status === 409 && Array.isArray(detailObj?.bloqueios)) {
          setFase("form");
          toast.error(detailObj.bloqueios.join(" · "));
          return;
        }

        const detail = detailObj
          ? detailObj.mensagem ?? detailObj.detail ?? JSON.stringify(detailObj)
          : err.detail;
        throw new Error(detail || "Falha na geração");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("Stream de geração indisponível");
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const partes = buffer.split("\n\n");
        buffer = partes.pop() ?? "";

        for (const parte of partes) {
          const eventName = parte.match(/^event:\s*(.+)$/m)?.[1]?.trim();
          const dataLine = parte.match(/^data:\s*(.+)$/ms)?.[1]?.trim();
          if (!dataLine) continue;

          let payload: Record<string, any>;
          try {
            payload = JSON.parse(dataLine);
          } catch {
            continue;
          }

          if (eventName === "step") {
            setEtapaStatus(
              payload.etapa,
              payload.status === "em_andamento" ? "em_andamento" : "concluido",
              payload.resultado,
            );
          } else if (eventName === "concluido") {
            setDocumento(payload.documento ?? "");
            setAiLogId(payload.ai_log_id ?? "");
            setCodigoPeca(payload.codigo_peca ?? "");
            setVerificacao(payload.verificacao_citacoes ?? null);
            setAlertasIa(
              Array.isArray(payload.alertas)
                ? payload.alertas.filter((a: unknown) => typeof a === "string")
                : [],
            );
            setFase("concluido");
          } else if (eventName === "residuos") {
            setResiduos(Array.isArray(payload.achados) ? payload.achados : []);
          } else if (eventName === "erro") {
            throw new Error(payload.detail ?? "Erro na geração");
          }
        }
      }
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      setErroMsg(e?.message ?? "Erro desconhecido");
      setFase("erro");
    }
  }, [
    catalogoIndisponivel,
    modo,
    respostasGuiadas,
    fatos,
    pedidos,
    instrucoes,
    nomesProteger,
    tipoPeca,
    areaDireito,
    nivelComplexidade,
    flagsTeses,
    caseId,
    onNeedFicha,
  ]);

  const copiar = () => {
    navigator.clipboard.writeText(documento);
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 1800);
  };

  const baixar = () => {
    const blob = new Blob([documento], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${tipoLabel(tipoPeca)}_EJC.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Modal open={open} onClose={fechar} title="Criar peça" wide>
      {fase === "form" && (
        <div className="space-y-5">
          <div className="rounded-xl border border-primary-100 bg-primary-50/50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-navy">
              <Sparkles size={16} /> Fluxo recomendado
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Informe o tipo e os dados do caso. O EJC organiza a estrutura, pesquisa fundamentos e gera a minuta para revisão humana.
            </p>
          </div>

          {metaErro && (
            <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 px-4 py-3 text-xs text-danger-700">
              <ShieldAlert size={16} className="mt-0.5 shrink-0" />
              {metaErro}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="label text-xs">Tipo de peça</label>
              <select
                className="input"
                value={tipoPeca}
                disabled={catalogoIndisponivel}
                onChange={(e) => {
                  setTipoPeca(e.target.value);
                  setRespostasGuiadas({});
                }}
              >
                {tipos.map((tipo) => (
                  <option key={tipo.value} value={tipo.value}>
                    {tipo.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label text-xs">Área</label>
              <select
                className="input"
                value={areaDireito}
                disabled={catalogoIndisponivel}
                onChange={(e) => setAreaDireito(e.target.value)}
              >
                {areas.map((area) => (
                  <option key={area.value} value={area.value}>
                    {area.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label text-xs">Nível / rito</label>
              <select
                className="input"
                value={nivelComplexidade}
                disabled={catalogoIndisponivel}
                onChange={(e) => setNivelComplexidade(e.target.value)}
              >
                {niveis.map((nivel) => (
                  <option key={nivel} value={nivel}>
                    {NIVEL_LABEL[nivel] ?? nivel}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <div className="text-sm font-medium text-slate-700">
                {modo === "guiado" ? "Preenchimento guiado" : "Preenchimento livre"}
              </div>
              <div className="text-xs text-slate-400">
                {modo === "guiado"
                  ? "O formulário adapta as perguntas ao tipo de peça."
                  : "Use campos abertos quando já souber exatamente o que deseja redigir."}
              </div>
            </div>
            <button
              type="button"
              className="btn-ghost px-3 py-1.5 text-xs"
              onClick={() => setMostrarAvancado((v) => !v)}
            >
              <PenLine size={14} /> Opções avançadas
            </button>
          </div>

          {mostrarAvancado && (
            <div className="flex gap-2 rounded-xl bg-slate-100 p-1">
              <button
                type="button"
                onClick={() => setModo("guiado")}
                className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium ${
                  modo === "guiado"
                    ? "bg-white text-primary-700 shadow-sm"
                    : "text-slate-500"
                }`}
              >
                Guiado
              </button>
              <button
                type="button"
                onClick={() => setModo("livre")}
                className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium ${
                  modo === "livre"
                    ? "bg-white text-primary-700 shadow-sm"
                    : "text-slate-500"
                }`}
              >
                Livre
              </button>
            </div>
          )}

          {modo === "guiado" ? (
            <GuiadoForm
              tipoPeca={tipoPeca}
              respostas={respostasGuiadas}
              onChange={(campo, valor) =>
                setRespostasGuiadas((atual) => ({ ...atual, [campo]: valor }))
              }
            />
          ) : (
            <div className="space-y-3">
              <div>
                <label className="label text-xs">Fatos *</label>
                <textarea
                  className="input min-h-[130px]"
                  value={fatos}
                  onChange={(e) => setFatos(e.target.value)}
                  placeholder="Descreva cronologicamente os fatos relevantes..."
                />
              </div>
              <div>
                <label className="label text-xs">Pedidos / resultado pretendido *</label>
                <textarea
                  className="input min-h-[90px]"
                  value={pedidos}
                  onChange={(e) => setPedidos(e.target.value)}
                  placeholder="Informe os pedidos principais e subsidiários..."
                />
              </div>
            </div>
          )}

          <details className="rounded-xl border border-slate-200 bg-slate-50/50">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-600 [&::-webkit-details-marker]:hidden">
              Ajustes jurídicos e LGPD
            </summary>
            <div className="space-y-4 border-t border-slate-200 p-4">
              <div>
                <div className="mb-2 text-xs font-medium text-slate-600">
                  Teses condicionais
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {FLAGS_TESES.map(([value, label]) => (
                    <label key={value} className="flex items-center gap-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        checked={flagsTeses.has(value)}
                        onChange={() => toggleFlag(value)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="label text-xs">Nomes a proteger</label>
                  <input
                    className="input"
                    value={nomesProteger}
                    onChange={(e) => setNomesProteger(e.target.value)}
                    placeholder="Separados por vírgula"
                  />
                </div>
                <div>
                  <label className="label text-xs">Instruções adicionais</label>
                  <input
                    className="input"
                    value={instrucoes}
                    onChange={(e) => setInstrucoes(e.target.value)}
                    placeholder="Ex.: destacar urgência, manter linguagem objetiva..."
                  />
                </div>
              </div>
            </div>
          </details>

          <div className="flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 px-4 py-3 text-xs text-warn-800">
            <ShieldAlert size={15} className="mt-0.5 shrink-0" />
            <span>
              A saída é uma minuta. Aprovação e assinatura permanecem obrigatoriamente humanas no fluxo de Peças.
            </span>
          </div>

          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="ghost" onClick={fechar}>
              Cancelar
            </Button>
            <Button
              variant="ai"
              onClick={gerar}
              disabled={catalogoIndisponivel}
              icon={<Sparkles size={15} />}
            >
              Gerar minuta
            </Button>
          </div>
        </div>
      )}

      {(fase === "gerando" || fase === "erro") && (
        <div className="space-y-4">
          <div>
            <div className="text-sm font-semibold text-navy">
              {fase === "gerando" ? "Preparando a minuta" : "Não foi possível gerar"}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {tipoLabel(tipoPeca)} · {areaLabel(areaDireito)}
            </div>
          </div>

          <div className="space-y-2">
            {etapas.map((etapa) => (
              <div
                key={etapa.num}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-sm ${
                  etapa.status === "concluido"
                    ? "border-success-200 bg-success-50 text-success-700"
                    : etapa.status === "em_andamento"
                      ? "border-primary-200 bg-primary-50 text-primary-700"
                      : "border-slate-100 text-slate-400"
                }`}
              >
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white text-xs shadow-sm">
                  {etapa.status === "em_andamento" ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : etapa.status === "concluido" ? (
                    <CheckCircle2 size={13} />
                  ) : (
                    etapa.num
                  )}
                </div>
                <span>{etapa.titulo}</span>
              </div>
            ))}
          </div>

          {fase === "erro" && (
            <div className="rounded-lg border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
              {erroMsg}
            </div>
          )}

          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            {fase === "gerando" ? (
              <Button
                variant="ghost"
                onClick={() => {
                  abortRef.current?.abort();
                  resetForm();
                }}
              >
                Cancelar
              </Button>
            ) : (
              <>
                <Button variant="ghost" onClick={resetForm}>
                  Voltar
                </Button>
                <Button variant="ai" onClick={gerar} icon={<Sparkles size={15} />}>
                  Tentar novamente
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      {fase === "concluido" && (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-success-200 bg-success-50 p-4">
            <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-success-600" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-success-800">
                  Minuta criada
                </span>
                {codigoPeca && <Badge tone="ouro">{codigoPeca}</Badge>}
              </div>
              <p className="mt-1 text-xs text-success-700">
                A peça foi salva e seguirá para revisão humana no módulo Peças.
              </p>
              {aiLogId && (
                <p className="mt-1 text-[11px] text-success-600">Log: {aiLogId}</p>
              )}
            </div>
          </div>

          <PainelQualidade
            verificacao={verificacao}
            alertas={alertasIa}
            residuos={residuos}
          />

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs font-medium text-slate-600">Minuta</label>
              <div className="flex gap-3">
                <button
                  type="button"
                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-primary-700"
                  onClick={copiar}
                >
                  <Copy size={13} /> {copiado ? "Copiado" : "Copiar"}
                </button>
                <button
                  type="button"
                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-primary-700"
                  onClick={baixar}
                >
                  <Download size={13} /> Baixar
                </button>
              </div>
            </div>
            <textarea
              readOnly
              className="input min-h-[280px] bg-slate-50 font-mono text-xs"
              value={documento}
            />
          </div>

          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="ghost" onClick={resetForm}>
              Criar outra
            </Button>
            <Button variant="primary" onClick={fechar}>
              Ir para Peças
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function PainelQualidade({
  verificacao,
  alertas,
  residuos,
}: {
  verificacao: VerificacaoCitacoes | null;
  alertas: string[];
  residuos: ResiduoAchado[];
}) {
  const citacoes = Array.isArray(verificacao?.citacoes) ? verificacao!.citacoes! : [];
  const criticas = citacoes.filter(
    (citacao) =>
      citacao.status === "suspeita" ||
      citacao.status === "possivelmente_desatualizada" ||
      citacao.status === "generica",
  );

  if (!verificacao && alertas.length === 0 && residuos.length === 0) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
        <ShieldAlert size={15} className="mt-0.5 shrink-0" />
        Verificação automática indisponível ou sem achados. A revisão humana continua obrigatória.
      </div>
    );
  }

  const haAtencao = criticas.length > 0 || alertas.length > 0 || residuos.length > 0;

  return (
    <div
      className={`rounded-xl border p-4 ${
        haAtencao
          ? "border-warn-200 bg-warn-50"
          : "border-success-200 bg-success-50"
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
        {haAtencao ? <AlertTriangle size={16} /> : <ShieldCheck size={16} />}
        Controle de qualidade
        {typeof verificacao?.score === "number" && (
          <Badge tone={haAtencao ? "amber" : "green"}>
            {Math.round(verificacao.score)}/100
          </Badge>
        )}
      </div>

      {!haAtencao && (
        <p className="mt-2 text-xs text-success-700">
          Nenhum alerta automático relevante foi encontrado. Isso não substitui a conferência do advogado.
        </p>
      )}

      {criticas.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-warn-800">
          {criticas.map((citacao, index) => (
            <li key={index}>
              <strong>{citacao.status.replace(/_/g, " ")}:</strong>{" "}
              {citacao.citacao || citacao.trecho || "citação"}
              {citacao.aviso ? ` — ${citacao.aviso}` : ""}
            </li>
          ))}
        </ul>
      )}

      {alertas.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-warn-800">
          {alertas.map((alerta, index) => (
            <li key={index}>{alerta}</li>
          ))}
        </ul>
      )}

      {residuos.length > 0 && (
        <div className="mt-3 rounded-lg border border-danger-200 bg-danger-50 p-3 text-xs text-danger-700">
          <strong>Dados residuais detectados:</strong> revise antes de aprovar.
          <ul className="mt-1 list-disc pl-5">
            {residuos.map((residuo, index) => (
              <li key={index}>
                {residuo.rotulo}: {residuo.termo}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
