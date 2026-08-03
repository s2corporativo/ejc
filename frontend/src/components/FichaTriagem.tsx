// ── Ficha de Triagem pré-peça ────────────────────────────
// Checklist obrigatório ANTES de gerar uma peça vinculada a um caso.
// A IA pré-preenche os 12 campos com um selo de confiança por campo; o
// advogado edita livremente e CONFIRMA. Só com status "confirmada" o backend
// libera POST /api/pecas/gerar para aquele case_id (gate 409 need_ficha_triagem).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Sparkles,
  ShieldCheck,
  Loader2,
  ClipboardCheck,
  Save,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { mensagemErroIA, ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { useIaStatus } from "../lib/iaStatus";
import { Badge, Spinner } from "./UI";
import { detalheErro } from "../utils/erro";

export type RiscoNivel = "baixo" | "medio" | "alto";
export type FichaStatus = "rascunho" | "confirmada";

export interface FichaTriagemCampos {
  competencia: string;
  rito: string;
  legitimidade_ativa: string;
  legitimidade_passiva: string;
  prescricao_decadencia: string;
  tutela_urgencia: boolean;
  tutela_fundamento: string;
  provas_disponiveis: string;
  provas_faltantes: string;
  valor_causa: string;
  risco_processual: RiscoNivel;
  risco_nota: string;
  pedidos_principais: string;
  pedidos_subsidiarios: string;
}

export type Confianca = Partial<Record<keyof FichaTriagemCampos, number>>;

const CAMPOS_VAZIOS: FichaTriagemCampos = {
  competencia: "",
  rito: "",
  legitimidade_ativa: "",
  legitimidade_passiva: "",
  prescricao_decadencia: "",
  tutela_urgencia: false,
  tutela_fundamento: "",
  provas_disponiveis: "",
  provas_faltantes: "",
  valor_causa: "",
  risco_processual: "medio",
  risco_nota: "",
  pedidos_principais: "",
  pedidos_subsidiarios: "",
};

// Chaves de campos aceitas do backend (blinda contra chaves extras no payload).
const CHAVES_CAMPO = Object.keys(CAMPOS_VAZIOS) as (keyof FichaTriagemCampos)[];

/** Normaliza um payload cru da API (envelope ou objeto direto) nos 12 campos. */
function mergeCampos(data: Record<string, unknown> | null): FichaTriagemCampos {
  const merged: FichaTriagemCampos = { ...CAMPOS_VAZIOS };
  if (!data) return merged;
  for (const k of CHAVES_CAMPO) {
    const v = data[k];
    if (v == null) continue;
    if (k === "tutela_urgencia") {
      merged.tutela_urgencia = Boolean(v);
    } else if (k === "valor_causa") {
      merged.valor_causa = String(v);
    } else if (k === "risco_processual") {
      if (v === "baixo" || v === "medio" || v === "alto")
        merged.risco_processual = v;
    } else {
      (merged[k] as string) = String(v);
    }
  }
  return merged;
}

// Faixa de confiança → semáforo semântico do DS (<50 vermelho, 50-79 âmbar, ≥80 verde).
function SeloConfianca({ valor }: { valor?: number }) {
  if (valor == null) return null;
  const v = Math.round(valor);
  const cls =
    v >= 80
      ? "bg-success-100 text-success-700"
      : v >= 50
        ? "bg-warn-100 text-warn-700"
        : "bg-danger-100 text-danger-700";
  const titulo =
    v >= 80
      ? "Alta confiança da IA"
      : v >= 50
        ? "Confiança média — revise"
        : "Baixa confiança — revise com atenção";
  return (
    <span
      title={titulo}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${cls}`}
    >
      <Sparkles size={10} /> {v}%
    </span>
  );
}

interface Props {
  caseId: string;
  /** Notifica o pai a cada carga/salvamento para gate + resumo. */
  onStatusChange?: (status: FichaStatus, campos: FichaTriagemCampos) => void;
  /** Incremente para forçar recarga da ficha do servidor (ex.: após 409). */
  refreshSignal?: number;
}

export default function FichaTriagem({
  caseId,
  onStatusChange,
  refreshSignal,
}: Props) {
  const [campos, setCampos] = useState<FichaTriagemCampos>(CAMPOS_VAZIOS);
  const [confianca, setConfianca] = useState<Confianca>({});
  const [status, setStatus] = useState<FichaStatus>("rascunho");
  const [carregando, setCarregando] = useState(true);
  const [preenchendo, setPreenchendo] = useState(false);
  const { disponivel: iaDisponivel } = useIaStatus();
  const [salvando, setSalvando] = useState(false);

  // Ref estável para o callback: evita re-disparar o efeito de carga.
  const onStatusRef = useRef(onStatusChange);
  onStatusRef.current = onStatusChange;

  const aplicar = useCallback(
    (data: Record<string, unknown> | null, conf?: Confianca) => {
      const merged = mergeCampos(data);
      const novoStatus: FichaStatus =
        data?.status === "confirmada" ? "confirmada" : "rascunho";
      setCampos(merged);
      if (conf) setConfianca(conf);
      setStatus(novoStatus);
      onStatusRef.current?.(novoStatus, merged);
    },
    [],
  );

  useEffect(() => {
    let cancelado = false;
    setCarregando(true);
    api
      .get("/triagem/ficha", { params: { case_id: caseId } })
      .then((r) => {
        if (cancelado) return;
        // Contrato: { ficha: <objeto>|null }. ficha null = inexistente.
        const ficha = (r.data?.ficha ?? null) as Record<string, unknown> | null;
        if (ficha) {
          aplicar(ficha, (ficha.confianca as Confianca) ?? undefined);
        } else {
          onStatusRef.current?.("rascunho", CAMPOS_VAZIOS);
        }
      })
      .catch((e) => {
        if (cancelado) return;
        // 404 = ficha ainda não existe (fluxo normal). Demais erros → toast.
        if (e.response?.status !== 404) {
          toast.error(detalheErro(e, "Falha ao carregar a ficha de triagem"));
        }
        onStatusRef.current?.("rascunho", CAMPOS_VAZIOS);
      })
      .finally(() => {
        if (!cancelado) setCarregando(false);
      });
    return () => {
      cancelado = true;
    };
  }, [caseId, refreshSignal, aplicar]);

  const set = <K extends keyof FichaTriagemCampos>(
    k: K,
    v: FichaTriagemCampos[K],
  ) => {
    setCampos((prev) => ({ ...prev, [k]: v }));
    // Edição manual invalida a confirmação anterior até novo confirmar —
    // notifica o pai para o gate re-bloquear a geração até re-confirmar.
    if (status === "confirmada") {
      setStatus("rascunho");
      onStatusRef.current?.("rascunho", { ...campos, [k]: v });
    }
  };

  const preencherComIA = async () => {
    setPreenchendo(true);
    try {
      const { data } = await api.post("/triagem/ficha/pre-preencher", {
        case_id: caseId,
      });
      // Contrato: { status, case_id, campos: {<12>}, confianca: {<chaves>:0-100|null}, ... }
      const campos = (data?.campos ?? {}) as Record<string, unknown>;
      const conf = (data?.confianca ?? {}) as Confianca;
      // Pré-preenchimento nasce como rascunho (campos não trazem status).
      aplicar(campos, conf);
      toast.success("Ficha pré-preenchida pela IA. Revise antes de confirmar.");
    } catch (e: unknown) {
      toast.error(
        mensagemErroIA(e, "Não foi possível pré-preencher a ficha com IA."),
      );
    } finally {
      setPreenchendo(false);
    }
  };

  const salvar = async (confirmar: boolean) => {
    setSalvando(true);
    try {
      const { data } = await api.post("/triagem/ficha", {
        case_id: caseId,
        ...campos,
        confirmar,
      });
      // Contrato: { ficha: <objeto com campos+confianca+status>, status }.
      const ficha = (data?.ficha ?? {}) as Record<string, unknown>;
      const conf = (ficha.confianca as Confianca) ?? confianca;
      // status é ecoado no topo (fonte de verdade); ficha.status como fallback.
      const respStatus = data?.status ?? ficha.status;
      const novoStatus: FichaStatus =
        respStatus === "confirmada" || respStatus === "rascunho"
          ? (respStatus as FichaStatus)
          : confirmar
            ? "confirmada"
            : "rascunho";
      const merged =
        Object.keys(ficha).length > 0 ? mergeCampos(ficha) : campos;
      setCampos(merged);
      setConfianca(conf);
      setStatus(novoStatus);
      onStatusRef.current?.(novoStatus, merged);
      toast.success(
        confirmar
          ? "Ficha de triagem confirmada. Geração de peça liberada."
          : "Rascunho da ficha salvo.",
      );
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Falha ao salvar a ficha"));
    } finally {
      setSalvando(false);
    }
  };

  if (carregando) {
    return (
      <div className="card p-6">
        <Spinner />
      </div>
    );
  }

  const ocupado = preenchendo || salvando;

  return (
    <section className="card p-5" aria-label="Ficha de triagem pré-peça">
      <header className="flex flex-col gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ouro-palha text-ouro-profundo">
            <ClipboardCheck size={18} />
          </div>
          <div>
            <h2 className="font-serif text-lg font-semibold text-slate-950">
              Ficha de triagem pré-peça
            </h2>
            <p className="mt-0.5 max-w-xl text-xs text-slate-500">
              Checklist obrigatório antes de gerar a peça deste caso.
              Pré-preencha com IA, revise cada campo e confirme.
            </p>
          </div>
        </div>
        <div className="shrink-0">
          {status === "confirmada" ? (
            <Badge tone="green">
              <ShieldCheck size={12} /> Ficha confirmada
            </Badge>
          ) : (
            <Badge tone="amber">Rascunho — não confirmada</Badge>
          )}
        </div>
      </header>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-secondary text-sm disabled:cursor-not-allowed disabled:opacity-50"
          onClick={preencherComIA}
          disabled={ocupado || !iaDisponivel}
          title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}
        >
          {preenchendo ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Sparkles size={15} />
          )}
          {!iaDisponivel
            ? "IA não ativada"
            : preenchendo
              ? "Analisando o caso..."
              : "Pré-preencher com IA"}
        </button>
        <span className="text-xs text-slate-400">
          O selo colorido indica a confiança da IA por campo — revise sempre.
        </span>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Campo campo="competencia" label="Competência" confianca={confianca}>
          <input
            id="competencia"
            className="input"
            value={campos.competencia}
            onChange={(e) => set("competencia", e.target.value)}
            placeholder="Ex.: Vara Cível da Comarca de..."
          />
        </Campo>

        <Campo campo="rito" label="Rito" confianca={confianca}>
          <input
            id="rito"
            className="input"
            value={campos.rito}
            onChange={(e) => set("rito", e.target.value)}
            placeholder="Ex.: procedimento comum / sumaríssimo"
          />
        </Campo>

        <Campo
          campo="legitimidade_ativa"
          label="Legitimidade ativa"
          confianca={confianca}
        >
          <textarea
            id="legitimidade_ativa"
            className="input min-h-[64px] resize-y"
            value={campos.legitimidade_ativa}
            onChange={(e) => set("legitimidade_ativa", e.target.value)}
          />
        </Campo>

        <Campo
          campo="legitimidade_passiva"
          label="Legitimidade passiva"
          confianca={confianca}
        >
          <textarea
            id="legitimidade_passiva"
            className="input min-h-[64px] resize-y"
            value={campos.legitimidade_passiva}
            onChange={(e) => set("legitimidade_passiva", e.target.value)}
          />
        </Campo>

        <Campo
          campo="prescricao_decadencia"
          label="Prescrição / decadência"
          confianca={confianca}
        >
          <textarea
            id="prescricao_decadencia"
            className="input min-h-[64px] resize-y"
            value={campos.prescricao_decadencia}
            onChange={(e) => set("prescricao_decadencia", e.target.value)}
          />
        </Campo>

        <Campo campo="valor_causa" label="Valor da causa" confianca={confianca}>
          <input
            id="valor_causa"
            className="input"
            value={campos.valor_causa}
            onChange={(e) => set("valor_causa", e.target.value)}
            inputMode="decimal"
            placeholder="Ex.: 50000.00"
          />
        </Campo>

        {/* Tutela de urgência: boolean + fundamento condicional */}
        <div className="sm:col-span-2">
          <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <div className="flex items-center justify-between">
              <label
                htmlFor="tutela_urgencia"
                className="flex items-center gap-2 text-sm font-medium text-slate-700"
              >
                <input
                  id="tutela_urgencia"
                  type="checkbox"
                  className="h-4 w-4 accent-ouro-profundo"
                  checked={campos.tutela_urgencia}
                  onChange={(e) => set("tutela_urgencia", e.target.checked)}
                />
                Requer tutela de urgência
              </label>
              <SeloConfianca valor={confianca.tutela_urgencia} />
            </div>
            {campos.tutela_urgencia && (
              <div className="mt-3">
                <div className="mb-1 flex items-center justify-between">
                  <label htmlFor="tutela_fundamento" className="label !mb-0">
                    Fundamento da tutela
                  </label>
                  <SeloConfianca valor={confianca.tutela_fundamento} />
                </div>
                <textarea
                  id="tutela_fundamento"
                  className="input min-h-[64px] resize-y"
                  value={campos.tutela_fundamento}
                  onChange={(e) => set("tutela_fundamento", e.target.value)}
                  placeholder="Probabilidade do direito e perigo de dano..."
                />
              </div>
            )}
          </div>
        </div>

        <Campo
          campo="provas_disponiveis"
          label="Provas disponíveis"
          confianca={confianca}
        >
          <textarea
            id="provas_disponiveis"
            className="input min-h-[64px] resize-y"
            value={campos.provas_disponiveis}
            onChange={(e) => set("provas_disponiveis", e.target.value)}
          />
        </Campo>

        <Campo
          campo="provas_faltantes"
          label="Provas faltantes"
          confianca={confianca}
        >
          <textarea
            id="provas_faltantes"
            className="input min-h-[64px] resize-y"
            value={campos.provas_faltantes}
            onChange={(e) => set("provas_faltantes", e.target.value)}
          />
        </Campo>

        {/* Risco processual: nível + nota */}
        <Campo
          campo="risco_processual"
          label="Risco processual"
          confianca={confianca}
        >
          <select
            id="risco_processual"
            className="input"
            value={campos.risco_processual}
            onChange={(e) =>
              set("risco_processual", e.target.value as RiscoNivel)
            }
          >
            <option value="baixo">Baixo</option>
            <option value="medio">Médio</option>
            <option value="alto">Alto</option>
          </select>
        </Campo>

        <Campo campo="risco_nota" label="Nota de risco" confianca={confianca}>
          <textarea
            id="risco_nota"
            className="input min-h-[64px] resize-y"
            value={campos.risco_nota}
            onChange={(e) => set("risco_nota", e.target.value)}
            placeholder="Justificativa da avaliação de risco..."
          />
        </Campo>

        <Campo
          campo="pedidos_principais"
          label="Pedidos principais"
          confianca={confianca}
        >
          <textarea
            id="pedidos_principais"
            className="input min-h-[80px] resize-y"
            value={campos.pedidos_principais}
            onChange={(e) => set("pedidos_principais", e.target.value)}
          />
        </Campo>

        <Campo
          campo="pedidos_subsidiarios"
          label="Pedidos subsidiários"
          confianca={confianca}
        >
          <textarea
            id="pedidos_subsidiarios"
            className="input min-h-[80px] resize-y"
            value={campos.pedidos_subsidiarios}
            onChange={(e) => set("pedidos_subsidiarios", e.target.value)}
          />
        </Campo>
      </div>

      <footer className="mt-5 flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-400">
          {status === "confirmada"
            ? "Ficha confirmada — a geração de peça para este caso está liberada."
            : "Confirme a ficha para liberar a geração de peça deste caso."}
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={() => salvar(false)}
            disabled={ocupado}
          >
            <Save size={15} /> Salvar rascunho
          </button>
          <button
            type="button"
            className="btn-gold text-sm"
            onClick={() => salvar(true)}
            disabled={ocupado}
          >
            {salvando ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <ShieldCheck size={15} />
            )}
            Confirmar ficha
          </button>
        </div>
      </footer>
    </section>
  );
}

// Wrapper de campo: label + selo de confiança alinhado à direita.
function Campo({
  campo,
  label,
  confianca,
  children,
}: {
  campo: keyof FichaTriagemCampos;
  label: string;
  confianca: Confianca;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <label htmlFor={campo} className="label !mb-0">
          {label}
        </label>
        <SeloConfianca valor={confianca[campo]} />
      </div>
      {children}
    </div>
  );
}
