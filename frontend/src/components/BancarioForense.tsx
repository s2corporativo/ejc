// ── src/components/BancarioForense.tsx ───────────────────────────────────────
// Ferramentas forenses do ramo bancário (backend determinístico, sem IA):
//   1. Verificador de Abusividade de juros — compara a taxa do contrato com a
//      média BACEN da época (REsp 1.061.530/RS, Tema 27) e projeta o expurgo.
//   2. Calculadora de CET — TIR do fluxo de caixa (Res. CMN 3.517/2007), com
//      memória de cálculo e checagem de divergência com o CET informado.
// Tudo é indício/minuta — HITL obrigatório (OAB).
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Calculator,
  CheckCircle2,
  Copy,
  FileText,
  Loader2,
  Scale,
  Sparkles,
} from "lucide-react";
import api from "../lib/api";
import { authFetch } from "../lib/stream";
import { Modal, Button, Spinner } from "./UI";
import { toast } from "./Toast";

// ── helpers ──────────────────────────────────────────────────────────────────
function fmtBRL(v: number | null | undefined) {
  return Number(v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}
function fmtNum(v: number | null | undefined, casas = 2) {
  return Number(v ?? 0).toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}
function parseNum(s: string): number | null {
  const n = parseFloat(String(s).trim().replace(/\./g, "").replace(",", "."));
  // aceita também "1234.56" digitado com ponto decimal simples
  if (isNaN(n)) {
    const n2 = parseFloat(String(s).trim().replace(",", "."));
    return isNaN(n2) ? null : n2;
  }
  return n;
}
// Campos de taxa/percentual não têm separador de milhar — só vírgula decimal.
function parsePct(s: string): number | null {
  const n = parseFloat(String(s).trim().replace(",", "."));
  return isNaN(n) ? null : n;
}
function apiDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d
      .map((x: any) => (typeof x === "string" ? x : x?.msg || ""))
      .filter(Boolean)
      .join("; ");
  return fallback;
}

const AVISO_HITL_UI =
  "Indício técnico — a caracterização de abusividade é judicial e exige análise do advogado.";

// ── Tipos das respostas (shapes do backend — analise_bancaria.py) ────────────
interface CetDivergencia {
  achado: string;
  cet_informado_aa_pct: number;
  cet_calculado_aa_pct: number;
  diferenca_pp: number;
  base_legal: string[];
  observacao: string;
}
interface CetRes {
  cet_mensal_pct: number;
  cet_anual_pct: number;
  valor_liberado_liquido: number;
  total_pago: number;
  convergencia: Record<string, any>;
  memoria_calculo: string[];
  divergencia: CetDivergencia | null;
  base_legal: string[];
  avisos: string[];
}
interface TaxaMedia {
  periodo: string;
  instituicoes?: number;
  ao_mes: { min: number; media: number; max: number };
  ao_ano: { min: number; media: number; max: number } | null;
  modalidade_bcb?: string;
  fonte?: string;
}
type Veredito =
  | "indicio_forte_abusividade"
  | "zona_de_atencao"
  | "dentro_da_normalidade"
  | "indeterminado";
interface Expurgo {
  parcela_original: number;
  parcela_revisada: number;
  economia_mensal: number;
  economia_total: number;
  total_original: number;
  total_revisado: number;
  memoria: string[];
}
interface AbusividadeRes {
  taxa_contrato_am_pct: number;
  modalidade: string;
  data_contrato: string | null;
  taxa_media: TaxaMedia | null;
  razao: number | null;
  veredito: Veredito;
  fundamentacao: string;
  expurgo: Expurgo | null;
  base_legal: string[];
  avisos: string[];
}

// Rótulos pt-BR dos atalhos de GET /analise-bancaria/modalidades → atalhos
const MODALIDADE_LABELS: Record<string, string> = {
  credito_pessoal: "Crédito pessoal (não consignado)",
  credito_pessoal_consignado_inss: "Crédito consignado — INSS",
  credito_pessoal_consignado_privado: "Crédito consignado — setor privado",
  credito_pessoal_consignado_publico: "Crédito consignado — setor público",
  veiculos: "Financiamento de veículos",
  cheque_especial: "Cheque especial",
  cartao_rotativo: "Cartão de crédito — rotativo",
  cartao_parcelado: "Cartão de crédito — parcelado",
  aquisicao_outros_bens: "Aquisição de outros bens",
  capital_de_giro: "Capital de giro (PJ)",
  conta_garantida: "Conta garantida (PJ)",
};
function rotuloModalidade(atalho: string) {
  return (
    MODALIDADE_LABELS[atalho] ||
    atalho.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

const VEREDITO_CFG: Record<
  Veredito,
  { rotulo: string; box: string; texto: string; ponto: string }
> = {
  indicio_forte_abusividade: {
    rotulo: "Indício forte de abusividade",
    box: "bg-danger-50 border-danger-200",
    texto: "text-danger-700",
    ponto: "bg-danger-600",
  },
  zona_de_atencao: {
    rotulo: "Zona de atenção",
    box: "bg-warn-50 border-warn-200",
    texto: "text-warn-700",
    ponto: "bg-warn-500",
  },
  dentro_da_normalidade: {
    rotulo: "Dentro da normalidade",
    box: "bg-success-50 border-success-200",
    texto: "text-success-700",
    ponto: "bg-success-600",
  },
  indeterminado: {
    rotulo: "Indeterminado",
    box: "bg-slate-50 border-slate-200",
    texto: "text-slate-600",
    ponto: "bg-slate-400",
  },
};

function BadgesBaseLegal({ itens }: { itens: string[] }) {
  if (!itens?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {itens.map((b, i) => (
        <span
          key={i}
          className="text-[10px] px-2 py-0.5 rounded-full bg-gold-50 border border-gold-light text-gold-700 leading-relaxed"
        >
          {b}
        </span>
      ))}
    </div>
  );
}

function Avisos({ itens }: { itens?: string[] }) {
  if (!itens?.length) return null;
  return (
    <div className="space-y-1">
      {itens.map((a, i) => (
        <p key={i} className="text-[11px] text-warn-700">
          ⚠ {a}
        </p>
      ))}
    </div>
  );
}

// ── Régua BACEN: min/média/max como escala + marcador da taxa do contrato ────
function ReguaBacen({
  contrato,
  min,
  media,
  max,
  corPonto,
}: {
  contrato: number;
  min: number;
  media: number;
  max: number;
  corPonto: string;
}) {
  const dominio = Math.max(contrato, max) * 1.12 || 1;
  const pos = (v: number) => Math.max(0, Math.min(100, (v / dominio) * 100));
  return (
    <div className="mt-2">
      <div className="flex justify-between text-[10px] text-slate-400 mb-1">
        <span>0%</span>
        <span>taxa % a.m.</span>
        <span>{fmtNum(dominio)}%</span>
      </div>
      <div className="relative h-9">
        {/* trilho */}
        <div className="absolute top-4 left-0 right-0 h-2 rounded-full bg-slate-100" />
        {/* faixa min→max do BACEN */}
        <div
          className="absolute top-4 h-2 rounded-full bg-success-200"
          style={{
            left: `${pos(min)}%`,
            width: `${Math.max(0.8, pos(max) - pos(min))}%`,
          }}
        />
        {/* marcador da média */}
        <div
          className="absolute top-3 w-0.5 h-4 bg-navy"
          style={{ left: `${pos(media)}%` }}
          title={`Média BACEN: ${fmtNum(media)}% a.m.`}
        />
        {/* marcador do contrato */}
        <div
          className="absolute top-0 -translate-x-1/2 flex flex-col items-center"
          style={{ left: `${pos(contrato)}%` }}
          title={`Seu contrato: ${fmtNum(contrato)}% a.m.`}
        >
          <span
            className={`w-3.5 h-3.5 rounded-full border-2 border-white shadow ${corPonto}`}
          />
          <span className="w-0.5 h-3 bg-slate-300" />
        </div>
      </div>
      <div className="grid grid-cols-4 gap-1 text-center text-[10px]">
        <div>
          <div className="text-slate-400 uppercase">Mín BACEN</div>
          <div className="font-semibold text-slate-600">{fmtNum(min)}%</div>
        </div>
        <div>
          <div className="text-slate-400 uppercase">Média BACEN</div>
          <div className="font-semibold text-navy">{fmtNum(media)}%</div>
        </div>
        <div>
          <div className="text-slate-400 uppercase">Máx BACEN</div>
          <div className="font-semibold text-slate-600">{fmtNum(max)}%</div>
        </div>
        <div>
          <div className="text-slate-400 uppercase">Seu contrato</div>
          <div className="font-bold text-navy">{fmtNum(contrato)}%</div>
        </div>
      </div>
    </div>
  );
}

// ── Calculadora de CET ────────────────────────────────────────────────────────
function CalculadoraCET() {
  const [form, setForm] = useState({
    valor_liberado: "",
    data_liberacao: "",
    n_parcelas: "",
    valor_parcela: "",
    primeiro_vencimento: "",
    tarifas_incluidas: "",
    iof: "",
    cet_informado_aa_pct: "",
  });
  const [res, setRes] = useState<CetRes | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  const set = (k: keyof typeof form) => (v: string) =>
    setForm((f) => ({ ...f, [k]: v }));

  const calcular = async () => {
    const valor = parseNum(form.valor_liberado);
    const parcela = parseNum(form.valor_parcela);
    const n = parseInt(form.n_parcelas, 10);
    if (
      !valor ||
      !parcela ||
      !n ||
      !form.data_liberacao ||
      !form.primeiro_vencimento
    ) {
      setErro(
        "Preencha valor liberado, data de liberação, nº de parcelas, valor da parcela e 1º vencimento.",
      );
      return;
    }
    setLoading(true);
    setErro("");
    setRes(null);
    const body: Record<string, any> = {
      valor_liberado: valor,
      data_liberacao: form.data_liberacao,
      n_parcelas: n,
      valor_parcela: parcela,
      primeiro_vencimento: form.primeiro_vencimento,
    };
    const tarifas = parseNum(form.tarifas_incluidas);
    const iof = parseNum(form.iof);
    const cetInf = parsePct(form.cet_informado_aa_pct);
    if (tarifas) body.tarifas_incluidas = tarifas;
    if (iof) body.iof = iof;
    if (cetInf != null && form.cet_informado_aa_pct.trim() !== "")
      body.cet_informado_aa_pct = cetInf;
    try {
      const { data } = await api.post<CetRes>("/analise-bancaria/cet", body);
      setRes(data);
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao calcular o CET."));
    } finally {
      setLoading(false);
    }
  };

  const campo = (
    label: string,
    k: keyof typeof form,
    tipo: "text" | "date" = "text",
    placeholder?: string,
  ) => (
    <div>
      <label className="label text-xs">{label}</label>
      <input
        className="input text-sm"
        type={tipo}
        inputMode={tipo === "text" ? "decimal" : undefined}
        placeholder={placeholder}
        value={form[k]}
        onChange={(e) => set(k)(e.target.value)}
      />
    </div>
  );

  return (
    <div>
      <p className="text-xs text-slate-500 mb-3">
        Calcula o <b>Custo Efetivo Total</b> real do contrato (TIR do fluxo de
        caixa) e confronta com o CET informado pelo banco ·{" "}
        <span className="text-gold-700">
          Res. CMN 3.517/2007 · CDC arts. 46 e 52
        </span>
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {campo(
          "Valor liberado (R$) *",
          "valor_liberado",
          "text",
          "ex: 10.000,00",
        )}
        {campo("Data de liberação *", "data_liberacao", "date")}
        {campo("Nº de parcelas *", "n_parcelas", "text", "ex: 24")}
        {campo(
          "Valor da parcela (R$) *",
          "valor_parcela",
          "text",
          "ex: 620,00",
        )}
        {campo("1º vencimento *", "primeiro_vencimento", "date")}
        {campo(
          "Tarifas incluídas (R$)",
          "tarifas_incluidas",
          "text",
          "opcional",
        )}
        {campo("IOF (R$)", "iof", "text", "opcional")}
        {campo(
          "CET informado pelo banco (% a.a.)",
          "cet_informado_aa_pct",
          "text",
          "opcional — checa divergência",
        )}
      </div>
      <button
        className="btn-gold text-sm mt-3"
        disabled={loading}
        onClick={calcular}
      >
        <Calculator size={14} /> {loading ? "Calculando…" : "Calcular CET"}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {res && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <div className="rounded-lg p-3 border border-gold-light bg-gold-50">
              <div className="text-xl font-bold text-navy">
                {fmtNum(res.cet_mensal_pct)}%
              </div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wide">
                CET mensal
              </div>
            </div>
            <div className="rounded-lg p-3 border border-gold-light bg-gold-50">
              <div className="text-xl font-bold text-navy">
                {fmtNum(res.cet_anual_pct)}%
              </div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wide">
                CET anual
              </div>
            </div>
            <div className="rounded-lg p-3 border border-bronze-pale bg-bronze-50/10">
              <div className="text-base font-bold text-navy mt-1">
                {fmtBRL(res.total_pago)}
              </div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wide">
                Total pago
              </div>
            </div>
            <div className="rounded-lg p-3 border border-bronze-pale bg-bronze-50/10">
              <div className="text-base font-bold text-navy mt-1">
                {fmtBRL(res.valor_liberado_liquido)}
              </div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wide">
                Liberado líquido
              </div>
            </div>
          </div>

          {res.divergencia && (
            <div className="rounded-xl border-2 border-gold bg-gold-50 p-3">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={15} className="text-gold-700" />
                <span className="text-xs font-bold text-gold-700 uppercase tracking-wide">
                  Achado — divergência de CET
                </span>
              </div>
              <p className="text-sm text-navy font-medium">
                CET informado ({fmtNum(res.divergencia.cet_informado_aa_pct)}%
                a.a.) diverge do calculado (
                {fmtNum(res.divergencia.cet_calculado_aa_pct)}% a.a.) em{" "}
                <b>{fmtNum(res.divergencia.diferenca_pp)} p.p.</b>
              </p>
              {res.divergencia.observacao && (
                <p className="text-xs text-slate-600 mt-1">
                  {res.divergencia.observacao}
                </p>
              )}
              <div className="mt-2">
                <BadgesBaseLegal itens={res.divergencia.base_legal} />
              </div>
            </div>
          )}

          <details className="card bg-slate-50/60 px-3 py-2">
            <summary className="text-xs font-medium text-slate-600 cursor-pointer select-none">
              Memória de cálculo{" "}
              {res.convergencia?.metodo
                ? `(${res.convergencia.metodo}, ${res.convergencia.iteracoes ?? "?"} iterações)`
                : ""}
            </summary>
            <ol className="mt-2 space-y-1">
              {res.memoria_calculo.map((m, i) => (
                <li key={i} className="text-[11px] text-slate-600 font-mono">
                  {m}
                </li>
              ))}
            </ol>
          </details>

          <BadgesBaseLegal itens={res.base_legal} />
          <Avisos itens={res.avisos} />
        </div>
      )}
    </div>
  );
}

// ── Esteira SSE da minuta revisional (mesma de AnaliseExtratos.tsx) ──────────
const ETAPAS_MINUTA: { num: number; titulo: string }[] = [
  { num: 1, titulo: "Identificando tipo de peça" },
  { num: 2, titulo: "Estruturando enquadramento" },
  { num: 3, titulo: "Buscando fundamentos legais" },
  { num: 4, titulo: "Analisando jurisprudência" },
  { num: 5, titulo: "Organizando argumentos" },
  { num: 6, titulo: "Identificando riscos" },
  { num: 7, titulo: "Montando documento completo" },
];
type StatusEtapa = "aguardando" | "em_andamento" | "concluido";
type FaseMinuta = "escolher" | "gerando" | "concluido" | "erro";

// A seção de abusividade não tem um bank_analysis id no contexto (o cálculo é
// avulso). Caminho de menor atrito adotado: o advogado escolhe uma análise de
// extrato já existente (GET /bank-analysis/) para ancorar a esteira, e a
// resposta completa da abusividade vai no body {"abusividade": ...} — o
// backend injeta o expurgo na peça. Sem análise disponível, orientamos rodar a
// Análise de Extratos (seção acima) primeiro.
function MinutaRevisionalModal({
  open,
  onClose,
  abusividade,
}: {
  open: boolean;
  onClose: () => void;
  abusividade: AbusividadeRes | null;
}) {
  const [fase, setFase] = useState<FaseMinuta>("escolher");
  const [analises, setAnalises] = useState<any[] | null>(null);
  const [analiseSel, setAnaliseSel] = useState("");
  const [etapas, setEtapas] = useState<Record<number, StatusEtapa>>({});
  const [doc, setDoc] = useState("");
  const [legalDocId, setLegalDocId] = useState("");
  const [erro, setErro] = useState("");
  const [copiado, setCopiado] = useState(false);
  const abort = useRef<AbortController | null>(null);

  // Aborta o stream SSE em voo ao desmontar — evita setState após unmount e
  // vazamento da conexão quando o componente sai durante a geração.
  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    if (!open) return;
    setFase("escolher");
    setEtapas({});
    setDoc("");
    setLegalDocId("");
    setErro("");
    setAnalises(null);
    api
      .get("/bank-analysis/", { params: { page_size: 50 } })
      .then((r) => {
        const lista = r.data?.data ?? [];
        setAnalises(lista);
        if (lista.length === 1) setAnaliseSel(lista[0].id);
      })
      .catch(() => setAnalises([]));
  }, [open]);

  const fechar = () => {
    abort.current?.abort();
    onClose();
  };

  // Espelha o consumo de SSE de AnaliseExtratos.tsx / PecaGeneratorModal.tsx
  // (fetch direto + reader; axios não faz stream de resposta no browser).
  const gerar = async () => {
    if (!analiseSel || !abusividade) return;
    setFase("gerando");
    setEtapas({});
    setDoc("");
    setErro("");
    abort.current = new AbortController();
    try {
      const r = await authFetch(`/api/bank-analysis/${analiseSel}/gerar-peca`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ abusividade }),
        signal: abort.current.signal,
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "" }));
        throw new Error(err.detail || "Falha ao gerar a minuta revisional.");
      }
      const reader = r.body!.getReader();
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
            const num = Number(payload.etapa);
            const st: StatusEtapa =
              payload.status === "em_andamento" ? "em_andamento" : "concluido";
            setEtapas((prev) => ({ ...prev, [num]: st }));
          } else if (eventLine === "concluido") {
            setDoc(payload.documento ?? "");
            setLegalDocId(payload.legal_doc_id ?? "");
            setFase("concluido");
            toast.success("Minuta revisional gerada (rascunho — revise, OAB).");
          } else if (eventLine === "erro") {
            throw new Error(payload.detail ?? "Erro na geração da minuta.");
          }
        }
      }
    } catch (e: any) {
      if (e.name === "AbortError") return;
      setErro(e.message ?? "Erro desconhecido");
      setFase("erro");
      toast.error(e.message ?? "Falha ao gerar a minuta revisional.");
    }
  };

  const copiar = () => {
    navigator.clipboard.writeText(doc);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  return (
    <Modal
      open={open}
      onClose={fechar}
      title="Minuta revisional com os números da abusividade"
      wide
    >
      <div className="flex flex-col">
        <div className="-mt-5 -mx-5 mb-4 px-5 pb-3 border-b border-slate-100">
          <p className="text-xs text-slate-400">
            Ação revisional c/c repetição de indébito · esteira 7 etapas · o
            expurgo calculado entra na peça · HITL obrigatório
          </p>
        </div>

        {fase === "escolher" && (
          <div className="space-y-3">
            {analises === null ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Spinner /> Buscando análises de extrato…
              </div>
            ) : analises.length === 0 ? (
              <div className="bg-warn-50 border border-warn-200 rounded-lg px-4 py-3 text-sm text-warn-800">
                A esteira de peças é ancorada em uma <b>análise de extrato</b> e
                nenhuma foi encontrada. Rode primeiro a seção{" "}
                <b>"Análise de Extrato Bancário"</b> (acima, nesta página)
                enviando o extrato do cliente — depois volte aqui e gere a
                minuta com estes números.
              </div>
            ) : (
              <>
                <div>
                  <label className="label">Ancorar na análise de extrato</label>
                  <select
                    className="input w-full text-sm"
                    value={analiseSel}
                    onChange={(e) => setAnaliseSel(e.target.value)}
                  >
                    <option value="">Selecione a análise…</option>
                    {analises.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.arquivo_nome || "extrato"} ·{" "}
                        {a.banco || "banco não informado"} ·{" "}
                        {String(a.created_at ?? "").slice(0, 10)} ·{" "}
                        {a.qtd_abusivas ?? 0} cobrança(s)
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-400 mt-1">
                    Os números da abusividade (taxa, razão, expurgo) serão
                    enviados junto e incorporados à peça.
                  </p>
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={fechar}>
                    Cancelar
                  </Button>
                  <Button
                    variant="ai"
                    disabled={!analiseSel}
                    onClick={gerar}
                    icon={<Sparkles size={15} />}
                  >
                    Gerar minuta
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {(fase === "gerando" || fase === "erro") && (
          <div className="flex flex-col gap-2">
            {ETAPAS_MINUTA.map((e) => {
              const st = etapas[e.num] ?? "aguardando";
              return (
                <div
                  key={e.num}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-colors ${
                    st === "concluido"
                      ? "bg-success-50 border-success-200"
                      : st === "em_andamento"
                        ? "bg-bronze-50/40 border-bronze-pale"
                        : "bg-white border-slate-100"
                  }`}
                >
                  <div
                    className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-[11px] font-medium ${
                      st === "concluido"
                        ? "bg-success-600 text-white"
                        : st === "em_andamento"
                          ? "bg-bronze text-white"
                          : "bg-slate-100 text-slate-400"
                    }`}
                  >
                    {st === "em_andamento" ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : st === "concluido" ? (
                      <CheckCircle2 size={12} />
                    ) : (
                      e.num
                    )}
                  </div>
                  <span
                    className={`text-sm ${st === "aguardando" ? "text-slate-400" : "text-navy"}`}
                  >
                    {e.titulo}
                  </span>
                </div>
              );
            })}
            {fase === "erro" && (
              <div className="mt-3 bg-danger-50 border border-danger-200 rounded-lg px-4 py-3 text-sm text-danger-700">
                {erro}
              </div>
            )}
          </div>
        )}

        {fase === "concluido" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 bg-success-50 border border-success-200 rounded-xl px-4 py-3">
              <CheckCircle2
                size={18}
                className="text-success-600 flex-shrink-0"
              />
              <div className="flex-1">
                <div className="text-sm font-medium text-success-800">
                  Minuta gerada com sucesso
                </div>
                <div className="text-xs text-success-700">
                  {legalDocId ? `Peça: ${legalDocId} · ` : ""}
                  Rascunho (HITL) — aguarda revisão humana.
                </div>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-slate-600">
                  Documento gerado
                </label>
                <button
                  onClick={copiar}
                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-bronze transition-colors"
                >
                  <Copy size={13} />
                  {copiado ? "Copiado!" : "Copiar"}
                </button>
              </div>
              <textarea
                readOnly
                value={doc}
                rows={14}
                className="input bg-slate-50 font-mono resize-none"
              />
            </div>
            <div className="bg-warn-50 border border-warn-200 rounded-lg px-4 py-3 text-xs text-warn-800">
              <strong>⚠ RASCUNHO:</strong> minuta gerada por IA. Revise,
              complemente com os dados reais do caso e assine (advogado
              habilitado, OAB) antes de protocolar.
            </div>
          </div>
        )}

        {fase !== "escolher" && (
          <div className="-mx-5 -mb-5 px-6 py-4 mt-4 border-t border-slate-100 flex items-center justify-between gap-3 bg-white rounded-b-2xl">
            {fase === "gerando" && (
              <>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Loader2 size={13} className="animate-spin" />
                  Processando esteira…
                </div>
                <button
                  onClick={fechar}
                  className="px-4 py-2 text-sm text-danger-500 hover:text-danger-700 transition-colors"
                >
                  Cancelar
                </button>
              </>
            )}
            {fase === "erro" && (
              <>
                <Button variant="ghost" onClick={fechar}>
                  Fechar
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
              <Button variant="ai" onClick={fechar} className="ml-auto">
                Fechar
              </Button>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

// ── Verificador de Abusividade ────────────────────────────────────────────────
function VerificadorAbusividade() {
  const [atalhos, setAtalhos] = useState<string[]>([]);
  const [form, setForm] = useState({
    taxa: "",
    modalidade: "",
    data_contrato: "",
    valor_financiado: "",
    n_parcelas: "",
  });
  const [res, setRes] = useState<AbusividadeRes | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [minutaOpen, setMinutaOpen] = useState(false);

  useEffect(() => {
    api
      .get("/analise-bancaria/modalidades")
      .then((r) => setAtalhos(r.data?.atalhos ?? []))
      .catch(() => setAtalhos(Object.keys(MODALIDADE_LABELS)));
  }, []);

  const verificar = async () => {
    const taxa = parsePct(form.taxa);
    if (!taxa || taxa <= 0 || !form.modalidade) {
      setErro("Informe a taxa do contrato (% a.m.) e a modalidade.");
      return;
    }
    setLoading(true);
    setErro("");
    setRes(null);
    const body: Record<string, any> = {
      taxa_contrato_am_pct: taxa,
      modalidade: form.modalidade,
    };
    if (form.data_contrato) body.data_contrato = form.data_contrato;
    const vf = parseNum(form.valor_financiado);
    const np = parseInt(form.n_parcelas, 10);
    if (vf) body.valor_financiado = vf;
    if (np) body.n_parcelas = np;
    try {
      const { data } = await api.post<AbusividadeRes>(
        "/analise-bancaria/abusividade",
        body,
      );
      setRes(data);
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao verificar abusividade."));
    } finally {
      setLoading(false);
    }
  };

  const cfg = res ? VEREDITO_CFG[res.veredito] : null;
  const razaoTxt =
    res?.razao != null
      ? fmtNum(res.razao).replace(/0+$/, "").replace(/,$/, "")
      : null;

  return (
    <div>
      <p className="text-xs text-slate-500 mb-3">
        Compara a taxa contratada com a{" "}
        <b>média BACEN da modalidade na época da contratação</b> e classifica o
        indício (baliza de ~1,5x) ·{" "}
        <span className="text-gold-700">REsp 1.061.530/RS (Tema 27/STJ)</span>
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <div>
          <label className="label text-xs">Taxa do contrato (% a.m.) *</label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="ex: 6,5"
            value={form.taxa}
            onChange={(e) => setForm({ ...form, taxa: e.target.value })}
          />
        </div>
        <div>
          <label className="label text-xs">Modalidade *</label>
          <select
            className="input text-sm"
            value={form.modalidade}
            onChange={(e) => setForm({ ...form, modalidade: e.target.value })}
          >
            <option value="">Selecione…</option>
            {atalhos.map((a) => (
              <option key={a} value={a}>
                {rotuloModalidade(a)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label text-xs">Data do contrato</label>
          <input
            className="input text-sm"
            type="date"
            value={form.data_contrato}
            onChange={(e) =>
              setForm({ ...form, data_contrato: e.target.value })
            }
          />
        </div>
        <div>
          <label className="label text-xs">Valor financiado (R$)</label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="p/ cenário de expurgo"
            value={form.valor_financiado}
            onChange={(e) =>
              setForm({ ...form, valor_financiado: e.target.value })
            }
          />
        </div>
        <div>
          <label className="label text-xs">Nº de parcelas</label>
          <input
            className="input text-sm"
            inputMode="numeric"
            placeholder="p/ cenário de expurgo"
            value={form.n_parcelas}
            onChange={(e) => setForm({ ...form, n_parcelas: e.target.value })}
          />
        </div>
      </div>
      <button
        className="btn-gold text-sm mt-3"
        disabled={loading}
        onClick={verificar}
      >
        <Scale size={14} />{" "}
        {loading ? "Consultando BACEN…" : "Verificar abusividade"}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {res && cfg && (
        <div className="mt-4 space-y-3">
          {/* Veredito visual */}
          <div className={`rounded-xl border-2 p-4 ${cfg.box}`}>
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${cfg.ponto}`} />
              <span
                className={`text-sm font-bold uppercase tracking-wide ${cfg.texto}`}
              >
                {cfg.rotulo}
              </span>
            </div>
            {res.taxa_media && razaoTxt ? (
              <p className="text-sm text-navy mt-2">
                Sua taxa de <b>{fmtNum(res.taxa_contrato_am_pct)}% a.m.</b> é{" "}
                <b>{razaoTxt}×</b> a média BACEN da modalidade no período{" "}
                {res.taxa_media.periodo}
                {res.taxa_media.instituicoes
                  ? ` (${res.taxa_media.instituicoes} instituições)`
                  : ""}
                .
              </p>
            ) : (
              <p className="text-sm text-slate-600 mt-2">
                A média do BACEN não pôde ser obtida — a avaliação não foi
                realizada (veja os avisos abaixo).
              </p>
            )}
            {res.taxa_media && (
              <ReguaBacen
                contrato={res.taxa_contrato_am_pct}
                min={res.taxa_media.ao_mes.min}
                media={res.taxa_media.ao_mes.media}
                max={res.taxa_media.ao_mes.max}
                corPonto={cfg.ponto}
              />
            )}
          </div>

          {/* Fundamentação + base legal */}
          <div className="card bg-slate-50/60 p-3 space-y-2">
            <p className="text-xs text-slate-600 leading-relaxed">
              {res.fundamentacao}
            </p>
            <BadgesBaseLegal itens={res.base_legal} />
            {res.taxa_media?.fonte && (
              <p className="text-[10px] text-slate-400">
                Fonte: {res.taxa_media.fonte}
                {res.taxa_media.modalidade_bcb
                  ? ` · série: ${res.taxa_media.modalidade_bcb}`
                  : ""}
              </p>
            )}
          </div>

          {/* Cenário de expurgo */}
          {res.expurgo && (
            <div className="rounded-xl border-2 border-gold bg-gold-50 p-4">
              <div className="text-xs font-bold text-gold-700 uppercase tracking-wide mb-2">
                Cenário de expurgo (Price com a média BACEN)
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm text-navy">
                <span>
                  Parcela: <b>{fmtBRL(res.expurgo.parcela_original)}</b>
                </span>
                <span className="text-gold-700">→</span>
                <span>
                  revisada: <b>{fmtBRL(res.expurgo.parcela_revisada)}</b>
                </span>
                <span className="text-xs text-slate-500">
                  (economia mensal de {fmtBRL(res.expurgo.economia_mensal)})
                </span>
              </div>
              <div className="mt-2 text-lg font-bold text-gold-700">
                Economia potencial: {fmtBRL(res.expurgo.economia_total)}
              </div>
              <div className="text-[11px] text-slate-500">
                Total no prazo: {fmtBRL(res.expurgo.total_original)} →{" "}
                {fmtBRL(res.expurgo.total_revisado)}
              </div>
              <details className="mt-2">
                <summary className="text-[11px] text-slate-500 cursor-pointer select-none">
                  Memória do expurgo
                </summary>
                <ol className="mt-1 space-y-0.5">
                  {res.expurgo.memoria.map((m, i) => (
                    <li
                      key={i}
                      className="text-[11px] text-slate-600 font-mono"
                    >
                      {m}
                    </li>
                  ))}
                </ol>
              </details>
              <button
                onClick={() => setMinutaOpen(true)}
                className="mt-3 text-xs px-3 py-2 rounded-lg bg-navy text-white hover:bg-navy/90 flex items-center gap-1.5 transition-colors"
              >
                <FileText size={13} /> Gerar minuta revisional com estes números
              </button>
            </div>
          )}
          {!res.expurgo && res.veredito !== "indeterminado" && (
            <button
              onClick={() => setMinutaOpen(true)}
              className="text-xs px-3 py-2 rounded-lg bg-navy text-white hover:bg-navy/90 flex items-center gap-1.5 transition-colors"
            >
              <FileText size={13} /> Gerar minuta revisional com estes números
            </button>
          )}

          <Avisos itens={res.avisos} />
        </div>
      )}

      {/* Aviso HITL sempre visível */}
      <p className="text-[11px] text-warn-700 mt-3 pt-2 border-t border-warn-100">
        ⚠ {AVISO_HITL_UI}
      </p>

      <MinutaRevisionalModal
        open={minutaOpen}
        onClose={() => setMinutaOpen(false)}
        abusividade={res}
      />
    </div>
  );
}

// ── Taxa média de mercado (BCB / Olinda) ──────────────────────────────────────
// GET /indices/taxa-juros?modalidade=&instituicao= — permite ao advogado
// comparar a taxa do contrato do cliente com a média praticada por
// instituição/modalidade no mês de referência mais recente do BCB.
interface TaxaLinha {
  InstituicaoFinanceira?: string;
  Modalidade?: string;
  Posicao?: number;
  TaxaJurosAoMes?: number;
  TaxaJurosAoAno?: number;
}
interface TaxaJurosRes {
  mes_referencia: string;
  modalidade: string | null;
  instituicao: string | null;
  total: number;
  taxas: TaxaLinha[];
  fonte?: string;
}

function TaxaMediaMercado() {
  const [modalidade, setModalidade] = useState("");
  const [instituicao, setInstituicao] = useState("");
  const [res, setRes] = useState<TaxaJurosRes | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  const buscar = async () => {
    setLoading(true);
    setErro("");
    setRes(null);
    try {
      const { data } = await api.get<TaxaJurosRes>("/indices/taxa-juros", {
        params: {
          modalidade: modalidade.trim() || undefined,
          instituicao: instituicao.trim() || undefined,
        },
      });
      setRes(data);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 503) {
        setErro(
          "Integração de índices do BCB desabilitada no servidor (INDICES_BCB_ENABLED=false).",
        );
      } else if (status === 502) {
        setErro("O serviço do BCB (Olinda) está indisponível no momento — tente novamente em instantes.");
      } else {
        setErro(apiDetail(e, "Falha ao consultar as taxas médias do BCB."));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <p className="text-xs text-slate-500 mb-3">
        Compare a taxa do contrato do cliente com a{" "}
        <b>média de mercado praticada por instituição/modalidade</b>, no mês de
        referência mais recente ·{" "}
        <span className="text-gold-700">
          Banco Central — Olinda taxaJuros
        </span>
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label className="label text-xs">Modalidade (contém)</label>
          <input
            className="input text-sm"
            placeholder="ex: crédito pessoal não consignado"
            value={modalidade}
            onChange={(e) => setModalidade(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && buscar()}
          />
        </div>
        <div>
          <label className="label text-xs">Instituição financeira (contém)</label>
          <input
            className="input text-sm"
            placeholder="ex: Nubank, Itaú, Bradesco…"
            value={instituicao}
            onChange={(e) => setInstituicao(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && buscar()}
          />
        </div>
      </div>
      <button
        className="btn-gold text-sm mt-3"
        disabled={loading}
        onClick={buscar}
      >
        <Scale size={14} /> {loading ? "Consultando BCB…" : "Consultar taxas médias"}
      </button>
      <p className="text-[11px] text-slate-400 mt-2">
        Deixe os dois campos em branco para trazer o ranking completo do mês. Os
        filtros combinam por substring (sem distinção de maiúsculas/acentos).
      </p>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {loading && (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Spinner /> Buscando taxas no Banco Central…
        </div>
      )}

      {res && !loading && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="px-2 py-0.5 rounded-full bg-navy/5 text-navy font-medium dark:bg-white/[0.07] dark:text-slate-300">
              Mês de referência: <b>{res.mes_referencia}</b>
            </span>
            <span className="text-slate-500">
              {res.total} instituição(ões) encontrada(s)
            </span>
          </div>

          {res.taxas.length === 0 ? (
            <div className="bg-warn-50 border border-warn-200 rounded-lg px-4 py-3 text-sm text-warn-800">
              Nenhuma instituição/modalidade correspondeu aos filtros no mês{" "}
              {res.mes_referencia}. Ajuste os termos (ex.: use parte do nome) e
              tente de novo.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-100">
              <table className="w-full min-w-[520px] text-xs">
                <thead className="bg-slate-50/70">
                  <tr className="text-left text-slate-500">
                    <th className="py-2 px-3 font-medium">#</th>
                    <th className="py-2 px-3 font-medium">Instituição</th>
                    {!res.modalidade && (
                      <th className="py-2 px-3 font-medium">Modalidade</th>
                    )}
                    <th className="py-2 px-3 text-right font-medium">% a.m.</th>
                    <th className="py-2 px-3 text-right font-medium">% a.a.</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums text-slate-600">
                  {res.taxas.map((t, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-1.5 px-3 text-slate-400">
                        {t.Posicao ?? i + 1}
                      </td>
                      <td className="py-1.5 px-3 font-medium text-navy">
                        {t.InstituicaoFinanceira || "—"}
                      </td>
                      {!res.modalidade && (
                        <td className="py-1.5 px-3 text-slate-500">
                          {t.Modalidade || "—"}
                        </td>
                      )}
                      <td className="py-1.5 px-3 text-right">
                        {t.TaxaJurosAoMes != null
                          ? `${fmtNum(t.TaxaJurosAoMes)}%`
                          : "—"}
                      </td>
                      <td className="py-1.5 px-3 text-right font-medium text-navy">
                        {t.TaxaJurosAoAno != null
                          ? `${fmtNum(t.TaxaJurosAoAno)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {res.fonte && (
            <p className="text-[10px] text-slate-400">Fonte: {res.fonte}</p>
          )}
          <p className="text-[11px] text-warn-700 pt-2 border-t border-warn-100">
            ⚠ Média de mercado divulgada pelo BCB — apoio comparativo; a
            caracterização de abusividade exige análise do advogado (HITL).
          </p>
        </div>
      )}
    </div>
  );
}

// ── Card principal (sub-abas) ─────────────────────────────────────────────────
export default function BancarioForense() {
  const [aba, setAba] = useState<"abusividade" | "cet" | "taxa">("abusividade");
  const abas = [
    { id: "abusividade" as const, rotulo: "Verificador de Abusividade" },
    { id: "cet" as const, rotulo: "Calculadora de CET" },
    { id: "taxa" as const, rotulo: "Taxa média de mercado (BCB)" },
  ];
  return (
    <div className="card p-4 mb-4 border-l-4 border-bronze">
      <div className="flex items-center gap-2 mb-1">
        <Scale size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy">
          Forense Bancário — juros e CET
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Ferramentas determinísticas (sem IA): indício de abusividade frente à
        média BACEN e CET real do contrato. Resultados são apoio técnico —
        revisão do advogado obrigatória.
      </p>
      <div className="flex gap-1 mb-4 border-b border-slate-100 pb-2">
        {abas.map((a) => (
          <button
            key={a.id}
            onClick={() => setAba(a.id)}
            className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
              aba === a.id
                ? "bg-navy text-white"
                : "text-slate-500 hover:bg-slate-100"
            }`}
          >
            {a.rotulo}
          </button>
        ))}
      </div>
      {aba === "abusividade" && <VerificadorAbusividade />}
      {aba === "cet" && <CalculadoraCET />}
      {aba === "taxa" && <TaxaMediaMercado />}
    </div>
  );
}
