// ── src/components/LiquidacaoTrabalhista.tsx ─────────────────────────────────
// Vertical Trabalhista — Liquidação de sentença. Editor de verbas + parâmetros
// → consolidação determinística (ADC 58/59, Selic real do BCB) devolvida pelo
// backend, com FGTS + multa 40%, correção, honorários (CLT 791-A) e INSS/IRRF
// "a apurar". Tudo é MINUTA — conferência do contador/advogado (HITL).
//   POST /trabalhista/liquidacao/calcular      → LiquidacaoOut
//   POST /trabalhista/liquidacao/planilha-pdf   → { download_url } (Visual Law)
import { useState } from "react";
import {
  AlertTriangle,
  Calculator,
  Coins,
  FileDown,
  Gavel,
  Landmark,
  Loader2,
  Percent,
  Plus,
  Scale,
  Trash2,
  TrendingUp,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";

// ── helpers ──────────────────────────────────────────────────────────────────
function fmtBRL(v: number | null | undefined) {
  return Number(v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}
// "2024-03-01" → "01/03/2024" (sem Date para evitar drift de fuso)
function fmtDataISO(iso: string | null | undefined) {
  if (!iso) return "—";
  const [a, m, d] = String(iso).slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : String(iso);
}
function fmtFator(v: number | null | undefined) {
  return v == null
    ? "—"
    : Number(v).toLocaleString("pt-BR", {
        minimumFractionDigits: 4,
        maximumFractionDigits: 6,
      });
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

const MAX_VERBAS = 100;

// ── Tipos (contrato de /trabalhista/liquidacao) ─────────────────────────────
type Natureza = "salarial" | "indenizatoria";

interface VerbaLinha {
  rubrica: string;
  valor: string; // string no editor; convertido para float no envio
  natureza: Natureza;
}
interface VerbaOut {
  rubrica: string;
  valor: number;
  natureza: string;
}
interface EncargoOut {
  aliquota_pct: number;
  base: number;
  valor: number;
  base_legal: string;
}
interface HonorariosOut {
  percentual_pct: number;
  base: number;
  valor: number;
  base_legal: string;
}
interface CorrecaoOut {
  regime: string;
  fator_ipcae_pre_ajuizamento: number | null;
  principal_pos_ipcae: number;
  fator_selic: number;
  fonte_selic: string;
  meses_selic: number;
  principal_corrigido: number;
}
interface TributoOut {
  base_calculo: number;
  base_calculo_nominal: number | null;
  valor: number | null;
  status: string;
  observacao: string;
}
interface LiquidacaoOut {
  data_ajuizamento: string;
  data_calculo: string;
  verbas: VerbaOut[];
  principal_bruto: number;
  base_salarial: number;
  base_indenizatoria: number;
  fgts: EncargoOut;
  multa_fgts: EncargoOut;
  correcao: CorrecaoOut;
  honorarios: HonorariosOut;
  inss: TributoOut;
  irrf: TributoOut;
  subtotal_credito_trabalhista: number;
  total_bruto_com_honorarios: number;
  total_liquido_estimado: number;
  memoria_calculo: string[];
  alertas: string[];
  base_legal: string[];
  aviso_hitl: string;
}

// ── Peças de UI reutilizadas nos resultados ─────────────────────────────────
function LinhaValor({
  label,
  valor,
  destaque = false,
}: {
  label: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-slate-500">{label}</span>
      <span
        className={
          destaque
            ? "font-bold text-gold-700 whitespace-nowrap"
            : "font-medium text-navy whitespace-nowrap"
        }
      >
        {valor}
      </span>
    </div>
  );
}

function BaseLegalBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] px-2 py-0.5 rounded-full bg-gold-50 border border-gold-light text-gold-700 leading-relaxed">
      {children}
    </span>
  );
}

function BlocoCard({
  icon: Icon,
  titulo,
  children,
}: {
  icon: any;
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={14} className="text-gold-600" />
        <h3 className="font-serif font-semibold text-navy text-sm">{titulo}</h3>
      </div>
      {children}
    </div>
  );
}

// INSS / IRRF: podem vir com valor null + status "a_apurar" → nunca mostrar número.
function TributoLinha({ label, t }: { label: string; t: TributoOut }) {
  const aApurar = t.valor == null || t.status === "a_apurar";
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-navy">{label}</span>
        {aApurar ? (
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-warn-50 border border-warn-200 text-warn-700">
            a apurar
          </span>
        ) : (
          <span className="text-xs font-bold text-navy whitespace-nowrap">
            {fmtBRL(t.valor)}
          </span>
        )}
      </div>
      <div className="mt-1 text-[11px] text-slate-500">
        Base de cálculo:{" "}
        <b className="text-slate-600">{fmtBRL(t.base_calculo)}</b>
      </div>
      {t.observacao && (
        <p className="mt-1 text-[11px] text-warn-700 leading-relaxed">
          {t.observacao}
        </p>
      )}
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────
export default function LiquidacaoTrabalhista() {
  const [verbas, setVerbas] = useState<VerbaLinha[]>([
    { rubrica: "", valor: "", natureza: "salarial" },
  ]);
  const [dataAjuizamento, setDataAjuizamento] = useState("");
  const [dataCalculo, setDataCalculo] = useState("");
  const [percentualHonorarios, setPercentualHonorarios] = useState("10");
  const [fatorIpcae, setFatorIpcae] = useState("");
  // Índice oficial do BCB (IPCA-E) para o fator pré-ajuizamento: quando ligado
  // e sem fator manual, o backend calcula de data_inicio_correcao → ajuizamento.
  const [usarIndiceOficial, setUsarIndiceOficial] = useState(false);
  const [dataInicioCorrecao, setDataInicioCorrecao] = useState("");

  const [calculando, setCalculando] = useState(false);
  const [gerandoPdf, setGerandoPdf] = useState(false);
  const [erro, setErro] = useState("");
  const [res, setRes] = useState<LiquidacaoOut | null>(null);

  const atualizarVerba = (i: number, patch: Partial<VerbaLinha>) =>
    setVerbas((prev) => prev.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  const adicionarVerba = () =>
    setVerbas((prev) =>
      prev.length >= MAX_VERBAS
        ? prev
        : [...prev, { rubrica: "", valor: "", natureza: "salarial" }],
    );
  const removerVerba = (i: number) =>
    setVerbas((prev) =>
      prev.length <= 1 ? prev : prev.filter((_, j) => j !== i),
    );

  const calcular = async () => {
    const verbasValidas = verbas
      .map((v) => ({
        rubrica: v.rubrica.trim(),
        valor: Number(String(v.valor).replace(",", ".")),
        natureza: v.natureza,
      }))
      .filter((v) => v.rubrica && v.valor > 0);

    if (!verbasValidas.length) {
      setErro("Informe ao menos uma verba com rubrica e valor maior que zero.");
      return;
    }
    if (!dataAjuizamento || !dataCalculo) {
      setErro("Informe a data de ajuizamento e a data do cálculo.");
      return;
    }
    if (dataCalculo < dataAjuizamento) {
      setErro("A data do cálculo não pode ser anterior ao ajuizamento.");
      return;
    }
    const pct = Number(String(percentualHonorarios).replace(",", "."));
    if (isNaN(pct) || pct < 0 || pct > 100) {
      setErro("Percentual de honorários inválido (0 a 100%).");
      return;
    }
    const fator = fatorIpcae.trim()
      ? Number(String(fatorIpcae).replace(",", "."))
      : null;
    if (fator != null && (isNaN(fator) || fator <= 0)) {
      setErro(
        "Fator IPCA-E inválido — deixe em branco ou informe um número > 0.",
      );
      return;
    }
    // Índice oficial só entra quando não há fator manual (que tem precedência).
    const usarOficial = usarIndiceOficial && fator == null;
    if (usarOficial) {
      if (!dataInicioCorrecao) {
        setErro(
          "Informe a data de início da correção (IPCA-E oficial) ou desligue a opção.",
        );
        return;
      }
      if (dataInicioCorrecao >= dataAjuizamento) {
        setErro(
          "A data de início da correção deve ser anterior ao ajuizamento.",
        );
        return;
      }
    }

    setCalculando(true);
    setErro("");
    setRes(null);
    try {
      const { data } = await api.post<LiquidacaoOut>(
        "/trabalhista/liquidacao/calcular",
        {
          verbas: verbasValidas,
          data_ajuizamento: dataAjuizamento,
          data_calculo: dataCalculo,
          percentual_honorarios: pct,
          fator_ipcae_pre_ajuizamento: fator,
          usar_indice_oficial: usarOficial,
          data_inicio_correcao: usarOficial ? dataInicioCorrecao : null,
        },
      );
      setRes(data);
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao calcular a liquidação de sentença."));
    } finally {
      setCalculando(false);
    }
  };

  // Mesmo padrão dos demais PDFs Visual Law (TributarioFiscal.tsx): POST → download_url → blob
  const gerarPdf = async () => {
    if (!res) return;
    setGerandoPdf(true);
    try {
      const r = await api.post("/trabalhista/liquidacao/planilha-pdf", res);
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      // baseURL do client é /api — remove o prefixo se o backend devolver a URL completa
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "planilha-liquidacao-trabalhista.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Planilha de liquidação (Visual Law) gerada.");
    } catch (e: any) {
      toast.error(apiDetail(e, "Falha ao gerar a planilha em PDF."));
    } finally {
      setGerandoPdf(false);
    }
  };

  return (
    <div
      id="liquidacao-trabalhista"
      className="card p-4 mb-4 border-l-4 border-gold scroll-mt-20"
    >
      <div className="flex items-center gap-2 mb-1">
        <Scale size={16} className="text-gold-600" />
        <h2 className="font-serif font-semibold text-navy">
          Liquidação de Sentença Trabalhista
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Monte as verbas deferidas e o sistema consolida a planilha de liquidação
        — FGTS + multa de 40%, correção pelo regime ADC 58/59 (Selic real do
        BCB), honorários (CLT 791-A) e INSS/IRRF. Cálculo determinístico e
        preliminar — conferência do contador/advogado obrigatória.
      </p>

      {/* ── Editor de verbas ────────────────────────────────────────────── */}
      <div className="card bg-slate-50/40 p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-600">
            Verbas deferidas
          </span>
          <span className="text-[10px] text-slate-400">
            {verbas.length}/{MAX_VERBAS}
          </span>
        </div>
        <div className="space-y-2">
          {verbas.map((v, i) => (
            <div
              key={i}
              className="grid grid-cols-1 sm:grid-cols-[1fr_130px_150px_auto] gap-2 items-end"
            >
              <div>
                {i === 0 && <label className="label text-xs">Rubrica</label>}
                <input
                  className="input text-sm"
                  placeholder="Ex.: Horas extras"
                  value={v.rubrica}
                  onChange={(e) =>
                    atualizarVerba(i, { rubrica: e.target.value })
                  }
                />
              </div>
              <div>
                {i === 0 && <label className="label text-xs">Valor (R$)</label>}
                <input
                  className="input text-sm"
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  placeholder="0,00"
                  value={v.valor}
                  onChange={(e) => atualizarVerba(i, { valor: e.target.value })}
                />
              </div>
              <div>
                {i === 0 && <label className="label text-xs">Natureza</label>}
                <select
                  className="input text-sm"
                  value={v.natureza}
                  onChange={(e) =>
                    atualizarVerba(i, { natureza: e.target.value as Natureza })
                  }
                >
                  <option value="salarial">Salarial</option>
                  <option value="indenizatoria">Indenizatória</option>
                </select>
              </div>
              <button
                type="button"
                className="btn-ghost text-slate-300 hover:text-danger-600 h-[38px] px-2 disabled:opacity-30 disabled:hover:text-slate-300"
                title="Remover verba"
                disabled={verbas.length <= 1}
                onClick={() => removerVerba(i)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-slate-400 mt-2">
          <b>Salarial</b> entra na base de FGTS/INSS (ex.: horas extras,
          salário). <b>Indenizatória</b> não integra essas bases (ex.:
          indenização do art. 477, danos morais).
        </p>
        <button
          type="button"
          className="btn-ghost text-xs mt-2"
          disabled={verbas.length >= MAX_VERBAS}
          onClick={adicionarVerba}
        >
          <Plus size={13} /> Adicionar verba
        </button>
      </div>

      {/* ── Parâmetros ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
        <div>
          <label className="label text-xs">Data de ajuizamento</label>
          <input
            className="input text-sm"
            type="date"
            value={dataAjuizamento}
            onChange={(e) => setDataAjuizamento(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">Data do cálculo</label>
          <input
            className="input text-sm"
            type="date"
            value={dataCalculo}
            onChange={(e) => setDataCalculo(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">Percentual de honorários (%)</label>
          <input
            className="input text-sm"
            type="number"
            min="0"
            max="100"
            step="0.1"
            inputMode="decimal"
            value={percentualHonorarios}
            onChange={(e) => setPercentualHonorarios(e.target.value)}
          />
          <p className="text-[10px] text-slate-400 mt-1">
            5–15% sobre o valor liquidado (CLT 791-A).
          </p>
        </div>
        <div>
          <label className="label text-xs">
            Fator IPCA-E pré-ajuizamento{" "}
            <span className="text-slate-400 font-normal">(opcional)</span>
          </label>
          <input
            className="input text-sm"
            type="number"
            min="0"
            step="0.0001"
            inputMode="decimal"
            placeholder="Ex.: 1,05"
            value={fatorIpcae}
            onChange={(e) => setFatorIpcae(e.target.value)}
          />
          <p className="text-[10px] text-slate-400 mt-1">
            Se não informado, o sistema aplica só a Selic desde o ajuizamento
            (ou busca o IPCA-E oficial, se ativado abaixo).
          </p>
        </div>
      </div>

      {/* ── Índice oficial do BCB (IPCA-E) para o fator pré-ajuizamento ─────── */}
      <div className="card bg-slate-50/40 p-3 mt-3">
        <label className="flex items-start gap-2.5 cursor-pointer">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-gold-600 focus:ring-gold-500"
            checked={usarIndiceOficial}
            onChange={(e) => setUsarIndiceOficial(e.target.checked)}
          />
          <span className="text-xs">
            <span className="font-semibold text-navy flex items-center gap-1">
              <TrendingUp size={13} className="text-gold-600" />
              Usar índice oficial do BCB (IPCA-E)
            </span>
            <span className="text-slate-500 leading-relaxed">
              Calcula o fator de correção pré-ajuizamento direto da fonte
              oficial (BCB SGS, série IPCA-E) entre a data de início da correção
              e o ajuizamento.
            </span>
          </span>
        </label>

        {usarIndiceOficial && (
          <div className="mt-3 pl-6">
            {fatorIpcae.trim() ? (
              <p className="text-[11px] text-warn-700 flex items-start gap-1.5">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                Há um fator IPCA-E manual informado acima — ele tem precedência,
                então o índice oficial não será usado. Limpe o campo manual para
                buscar o fator oficial.
              </p>
            ) : (
              <>
                <label className="label text-xs">
                  Data de início da correção
                </label>
                <input
                  className="input text-sm max-w-[220px]"
                  type="date"
                  value={dataInicioCorrecao}
                  max={dataAjuizamento || undefined}
                  onChange={(e) => setDataInicioCorrecao(e.target.value)}
                />
                <p className="text-[10px] text-gold-700 mt-1.5 flex items-start gap-1.5">
                  <Landmark size={11} className="mt-0.5 shrink-0" />O fator
                  IPCA-E virá da fonte oficial (Banco Central). Se o BCB estiver
                  indisponível, o cálculo segue sem a correção pré-ajuizamento e
                  emite alerta.
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <button
        className="btn-gold text-sm mt-4"
        disabled={calculando}
        onClick={calcular}
      >
        {calculando ? (
          <>
            <Loader2 size={14} className="animate-spin" /> Calculando…
          </>
        ) : (
          <>
            <Calculator size={14} /> Calcular liquidação
          </>
        )}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {/* ── Resultado ───────────────────────────────────────────────────── */}
      {res && (
        <div className="mt-5 space-y-3">
          {/* Hero — total líquido estimado */}
          <div className="rounded-2xl border-2 border-gold bg-gold-50 p-5">
            <div className="text-xs font-bold text-gold-700 uppercase tracking-wide">
              Total líquido estimado
            </div>
            <div className="text-3xl font-bold text-navy mt-1">
              {fmtBRL(res.total_liquido_estimado)}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
              <span>
                Subtotal do crédito:{" "}
                <b>{fmtBRL(res.subtotal_credito_trabalhista)}</b>
              </span>
              <span>
                Com honorários: <b>{fmtBRL(res.total_bruto_com_honorarios)}</b>
              </span>
              <span>
                Período: <b>{fmtDataISO(res.data_ajuizamento)}</b> a{" "}
                <b>{fmtDataISO(res.data_calculo)}</b>
              </span>
            </div>
          </div>

          {/* Aviso HITL — sempre visível */}
          <div className="rounded-xl border-2 border-warn-200 bg-warn-50 p-3 flex items-start gap-2">
            <AlertTriangle
              size={15}
              className="text-warn-700 shrink-0 mt-0.5"
            />
            <p className="text-xs text-warn-700 leading-relaxed">
              {res.aviso_hitl}
            </p>
          </div>

          {/* Alertas */}
          {res.alertas?.length > 0 && (
            <ul className="rounded-xl border border-warn-200 bg-warn-50/60 p-3 space-y-1">
              {res.alertas.map((a, i) => (
                <li
                  key={i}
                  className="text-[11px] text-warn-700 flex items-start gap-1.5"
                >
                  <AlertTriangle size={12} className="mt-0.5 shrink-0" /> {a}
                </li>
              ))}
            </ul>
          )}

          {/* Blocos */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Principal */}
            <BlocoCard icon={Coins} titulo="Principal">
              <div className="space-y-1.5">
                <LinhaValor
                  label="Principal bruto"
                  valor={fmtBRL(res.principal_bruto)}
                  destaque
                />
                <LinhaValor
                  label="Base salarial"
                  valor={fmtBRL(res.base_salarial)}
                />
                <LinhaValor
                  label="Base indenizatória"
                  valor={fmtBRL(res.base_indenizatoria)}
                />
              </div>
            </BlocoCard>

            {/* FGTS + multa 40% */}
            <BlocoCard icon={Landmark} titulo="FGTS + multa de 40%">
              <div className="space-y-1.5">
                <LinhaValor
                  label={`FGTS (${res.fgts.aliquota_pct}% s/ ${fmtBRL(res.fgts.base)})`}
                  valor={fmtBRL(res.fgts.valor)}
                />
                <LinhaValor
                  label={`Multa FGTS (${res.multa_fgts.aliquota_pct}% s/ ${fmtBRL(res.multa_fgts.base)})`}
                  valor={fmtBRL(res.multa_fgts.valor)}
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <BaseLegalBadge>{res.fgts.base_legal}</BaseLegalBadge>
                {res.multa_fgts.base_legal !== res.fgts.base_legal && (
                  <BaseLegalBadge>{res.multa_fgts.base_legal}</BaseLegalBadge>
                )}
              </div>
            </BlocoCard>

            {/* Correção */}
            <BlocoCard icon={TrendingUp} titulo="Correção monetária + juros">
              <div className="mb-2 inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-full bg-navy/5 text-navy font-medium dark:bg-white/[0.07] dark:text-slate-300">
                <Gavel size={11} className="text-gold-600" />{" "}
                {res.correcao.regime}
              </div>
              <div className="space-y-1.5">
                {res.correcao.fator_ipcae_pre_ajuizamento != null && (
                  <LinhaValor
                    label="Fator IPCA-E (pré-ajuizamento)"
                    valor={fmtFator(res.correcao.fator_ipcae_pre_ajuizamento)}
                  />
                )}
                <LinhaValor
                  label="Principal após IPCA-E"
                  valor={fmtBRL(res.correcao.principal_pos_ipcae)}
                />
                <LinhaValor
                  label={`Fator Selic (${res.correcao.meses_selic} meses)`}
                  valor={fmtFator(res.correcao.fator_selic)}
                />
                <LinhaValor
                  label="Principal corrigido"
                  valor={fmtBRL(res.correcao.principal_corrigido)}
                  destaque
                />
              </div>
              <p className="mt-2 text-[10px] text-slate-400">
                Selic real desde o ajuizamento — fonte:{" "}
                <b className="uppercase">{res.correcao.fonte_selic}</b> (Banco
                Central).
              </p>
            </BlocoCard>

            {/* Honorários */}
            <BlocoCard icon={Percent} titulo="Honorários sucumbenciais">
              <div className="space-y-1.5">
                <LinhaValor
                  label={`Honorários (${res.honorarios.percentual_pct}% s/ ${fmtBRL(res.honorarios.base)})`}
                  valor={fmtBRL(res.honorarios.valor)}
                  destaque
                />
              </div>
              <div className="mt-2">
                <BaseLegalBadge>{res.honorarios.base_legal}</BaseLegalBadge>
              </div>
            </BlocoCard>
          </div>

          {/* INSS / IRRF — podem estar "a apurar" */}
          <BlocoCard
            icon={Scale}
            titulo="Encargos do trabalhador (INSS / IRRF)"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <TributoLinha label="INSS" t={res.inss} />
              <TributoLinha label="IRRF" t={res.irrf} />
            </div>
          </BlocoCard>

          {/* Memória de cálculo */}
          {res.memoria_calculo?.length > 0 && (
            <details className="card bg-slate-50/60 px-3 py-2">
              <summary className="text-xs font-medium text-slate-600 cursor-pointer select-none">
                Memória de cálculo
              </summary>
              <ol className="mt-2 space-y-1">
                {res.memoria_calculo.map((m, i) => (
                  <li key={i} className="text-[11px] text-slate-600 font-mono">
                    {m}
                  </li>
                ))}
              </ol>
            </details>
          )}

          {/* PDF Visual Law */}
          <button
            className="btn-gold text-sm"
            disabled={gerandoPdf}
            onClick={gerarPdf}
          >
            {gerandoPdf ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Gerando planilha…
              </>
            ) : (
              <>
                <FileDown size={14} /> Gerar planilha de liquidação (Visual Law)
              </>
            )}
          </button>

          {/* Base legal — rodapé */}
          {res.base_legal?.length > 0 && (
            <div className="pt-2 border-t border-slate-100">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">
                Base legal
              </p>
              <div className="flex flex-wrap gap-1.5">
                {res.base_legal.map((b, i) => (
                  <BaseLegalBadge key={i}>{b}</BaseLegalBadge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
