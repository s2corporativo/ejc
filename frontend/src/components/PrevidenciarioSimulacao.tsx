// ── src/components/PrevidenciarioSimulacao.tsx ───────────────────────────────
// Simulação de Aposentadoria (EC 103/2019) — vertical previdenciária.
// Compara as 5 regras de transição (pontos, idade progressiva, pedágio 50%,
// pedágio 100% e idade) para um segurado a partir de idade + tempo de
// contribuição, indica a elegibilidade, o coeficiente da RMI e — se a média do
// CNIS for informada — a RMI estimada, destacando a melhor regra.
// Backend: GET /previdenciario/ferramentas/regras-transicao · parecer PDF em
// POST /previdenciario/ferramentas/parecer-pdf. Tudo é apoio técnico (HITL/OAB).
import { useState } from "react";
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  FileDown,
  Loader2,
  PiggyBank,
  Sparkles,
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
function fmtPct(coef: number | null | undefined) {
  if (coef == null) return "—";
  return `${(coef * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}
function parseNum(s: string): number | null {
  const n = parseFloat(String(s).trim().replace(/\./g, "").replace(",", "."));
  if (isNaN(n)) {
    const n2 = parseFloat(String(s).trim().replace(",", "."));
    return isNaN(n2) ? null : n2;
  }
  return n;
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

// ── Tipos (contrato SimulacaoPrevidOut) ──────────────────────────────────────
type RegraId =
  "pontos" | "idade_progressiva" | "pedagio_50" | "pedagio_100" | "idade";

interface RegraTransicao {
  regra_id: RegraId | string;
  nome: string;
  base_legal: string;
  elegivel: boolean;
  o_que_falta: string[];
  coeficiente_rmi: number | null;
  rmi_estimada: number | null;
  observacoes: string[];
}
interface MelhorRegra {
  id: RegraId | string | null;
  motivo: string;
}
interface SimulacaoPrevidOut {
  sexo: string;
  idade: number;
  tempo_contribuicao: number;
  ano: number;
  media_informada: boolean;
  media_salarios_contribuicao: number | null;
  regras: RegraTransicao[];
  regras_elegiveis: string[];
  melhor_regra: MelhorRegra;
  aviso_hitl: string;
  base_legal_geral: string;
}

const AVISO_HITL_FALLBACK =
  "Simulação de apoio — a elegibilidade e o valor dependem do CNIS real e da análise do advogado. Não substitui o parecer previdenciário.";

// ── Card de uma regra de transição ───────────────────────────────────────────
function CardRegra({
  regra,
  recomendada,
}: {
  regra: RegraTransicao;
  recomendada: boolean;
}) {
  const elegivel = regra.elegivel;
  return (
    <div
      className={`rounded-xl border p-4 relative transition-colors ${
        recomendada
          ? "border-2 border-gold bg-gold-50/60"
          : elegivel
            ? "border-green-300 bg-green-50/40"
            : "border-slate-200 bg-slate-50/40 opacity-70"
      }`}
    >
      {recomendada && (
        <span className="absolute -top-2.5 right-3 text-[10px] font-bold uppercase tracking-wide bg-gold text-navy px-2 py-0.5 rounded-full shadow-sm flex items-center gap-1">
          <Award size={11} /> Recomendada
        </span>
      )}

      <div className="flex items-start gap-2 mb-2">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-navy leading-tight">
              {regra.nome}
            </h3>
            {elegivel ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-green-700 bg-green-100 border border-green-300 px-1.5 py-0.5 rounded-full">
                <CheckCircle2 size={11} /> Elegível
              </span>
            ) : (
              <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500 bg-slate-900/[0.05] dark:bg-white/[0.07] dark:text-slate-300 px-1.5 py-0.5 rounded-full">
                Ainda não
              </span>
            )}
          </div>
          {regra.base_legal && (
            <span className="inline-block mt-1 text-[10px] px-2 py-0.5 rounded-full bg-gold-50 border border-gold-light text-gold-700 leading-relaxed">
              {regra.base_legal}
            </span>
          )}
        </div>
      </div>

      {elegivel ? (
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <div>
            <div className="text-2xl font-bold text-gold-700">
              {fmtPct(regra.coeficiente_rmi)}
            </div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wide">
              Coeficiente da RMI
            </div>
          </div>
          <div>
            {regra.rmi_estimada != null ? (
              <>
                <div className="text-2xl font-bold text-navy">
                  {fmtBRL(regra.rmi_estimada)}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wide">
                  RMI estimada
                </div>
              </>
            ) : (
              <div className="text-xs text-slate-500 italic">
                Informe a média do CNIS para estimar a RMI.
              </div>
            )}
          </div>
        </div>
      ) : (
        regra.o_que_falta?.length > 0 && (
          <div className="mt-2">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
              O que falta
            </div>
            <ul className="space-y-1">
              {regra.o_que_falta.map((f, i) => (
                <li
                  key={i}
                  className="text-[11px] text-slate-600 flex items-start gap-1.5"
                >
                  <span className="text-slate-300 mt-0.5">•</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        )
      )}

      {regra.observacoes?.length > 0 && (
        <ul className="mt-2 space-y-1 rounded-lg bg-warn-50 border border-warn-200 px-2.5 py-2">
          {regra.observacoes.map((o, i) => (
            <li
              key={i}
              className="text-[11px] text-warn-800 flex items-start gap-1.5"
            >
              <AlertTriangle
                size={11}
                className="text-warn-600 shrink-0 mt-0.5"
              />
              <span>{o}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────
export default function PrevidenciarioSimulacao() {
  const [form, setForm] = useState({
    sexo: "M" as "M" | "F",
    idade: "",
    tempo_contribuicao_anos: "",
    ano: "2026",
    media_salarios_contribuicao: "",
  });
  const [res, setRes] = useState<SimulacaoPrevidOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [gerandoPdf, setGerandoPdf] = useState(false);
  const [erro, setErro] = useState("");

  const set = (k: keyof typeof form) => (v: string) =>
    setForm((f) => ({ ...f, [k]: v }));

  const simular = async () => {
    const idade = parseNum(form.idade);
    const tempo = parseNum(form.tempo_contribuicao_anos);
    const ano = parseNum(form.ano);
    if (idade == null || idade <= 0 || tempo == null || tempo < 0) {
      setErro("Informe a idade e o tempo de contribuição do segurado.");
      return;
    }
    setLoading(true);
    setErro("");
    setRes(null);
    const media = parseNum(form.media_salarios_contribuicao);
    const params: Record<string, number | string> = {
      idade,
      tempo_contribuicao_anos: tempo,
      sexo: form.sexo,
      ano: ano != null ? Math.trunc(ano) : 2026,
    };
    if (form.media_salarios_contribuicao.trim() !== "" && media != null) {
      params.media_salarios_contribuicao = media;
    }
    try {
      const { data } = await api.get<SimulacaoPrevidOut>(
        "/previdenciario/ferramentas/regras-transicao",
        { params },
      );
      setRes(data);
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao simular as regras de transição."));
    } finally {
      setLoading(false);
    }
  };

  // Mesmo padrão dos demais PDFs Visual Law (TributarioFiscal): POST → download_url → blob
  const gerarPdf = async () => {
    if (!res) return;
    setGerandoPdf(true);
    try {
      const r = await api.post("/previdenciario/ferramentas/parecer-pdf", res);
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      // baseURL do client é /api — remove o prefixo se o backend devolver a URL completa
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "simulacao-aposentadoria.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Parecer de simulação (Visual Law) gerado.");
    } catch (e: any) {
      toast.error(apiDetail(e, "Falha ao gerar o parecer em PDF."));
    } finally {
      setGerandoPdf(false);
    }
  };

  const temMelhor = !!res && res.melhor_regra?.id != null;

  return (
    <div
      id="previdenciario-simulacao"
      className="card p-4 mb-4 border-l-4 border-ai-500 scroll-mt-20"
    >
      <div className="flex items-center gap-2 mb-1">
        <PiggyBank size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy">
          Simulação de Aposentadoria (EC 103/2019)
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Compara as regras de transição da Reforma da Previdência — pontos, idade
        progressiva, pedágio de 50%, pedágio de 100% e idade — a partir da idade
        e do tempo de contribuição, indicando a elegibilidade, o coeficiente da
        RMI e a melhor regra.{" "}
        <span className="text-gold-700">
          Estimativa determinística · apoio técnico
        </span>
      </p>

      {/* Banner HITL fixo (âmbar) */}
      <div className="mb-4 rounded-lg bg-warn-50 border border-warn-200 px-3 py-2 flex items-start gap-2">
        <AlertTriangle
          size={15}
          className="text-warn-600 flex-shrink-0 mt-0.5"
        />
        <p className="text-[11px] text-warn-800">
          {res?.aviso_hitl || AVISO_HITL_FALLBACK}
        </p>
      </div>

      {/* Formulário */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div>
          <label className="label text-xs">Sexo</label>
          <select
            className="input text-sm"
            value={form.sexo}
            onChange={(e) => set("sexo")(e.target.value)}
          >
            <option value="M">Masculino</option>
            <option value="F">Feminino</option>
          </select>
        </div>
        <div>
          <label className="label text-xs">Idade *</label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="ex: 57"
            value={form.idade}
            onChange={(e) => set("idade")(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">
            Tempo de contribuição (anos) *
          </label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="ex: 32"
            value={form.tempo_contribuicao_anos}
            onChange={(e) => set("tempo_contribuicao_anos")(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">Ano da análise</label>
          <input
            className="input text-sm"
            type="number"
            placeholder="2026"
            value={form.ano}
            onChange={(e) => set("ano")(e.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className="label text-xs">
            Média dos salários de contribuição (R$)
          </label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="opcional"
            value={form.media_salarios_contribuicao}
            onChange={(e) => set("media_salarios_contribuicao")(e.target.value)}
          />
          <p className="text-[10px] text-slate-400 mt-0.5">
            Do CNIS — se não informar, mostramos só o coeficiente e a
            elegibilidade.
          </p>
        </div>
      </div>

      <button
        className="btn-gold text-sm mt-3"
        disabled={loading}
        onClick={simular}
      >
        {loading ? (
          <>
            <Loader2 size={14} className="animate-spin" /> Simulando…
          </>
        ) : (
          <>
            <PiggyBank size={14} /> Simular aposentadoria
          </>
        )}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {/* Resultado */}
      {res && (
        <div className="mt-4 space-y-4">
          {/* Banner da melhor regra */}
          {temMelhor ? (
            <div className="rounded-xl border-2 border-gold bg-gold-50 p-4">
              <div className="flex items-center gap-2 mb-1">
                <Award size={16} className="text-gold-700" />
                <span className="text-xs font-bold text-gold-700 uppercase tracking-wide">
                  Melhor regra —{" "}
                  {res.regras.find((r) => r.regra_id === res.melhor_regra.id)
                    ?.nome || res.melhor_regra.id}
                </span>
              </div>
              <p className="text-sm text-navy leading-relaxed">
                {res.melhor_regra.motivo}
              </p>
            </div>
          ) : (
            <div className="rounded-xl border-2 border-warn-300 bg-warn-50 p-4">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={16} className="text-warn-700" />
                <span className="text-xs font-bold text-warn-700 uppercase tracking-wide">
                  Nenhuma regra elegível ainda
                </span>
              </div>
              <p className="text-sm text-warn-800 leading-relaxed">
                {res.melhor_regra?.motivo ||
                  "O segurado ainda não preenche os requisitos de nenhuma regra de transição no ano informado."}
              </p>
            </div>
          )}

          {/* Cards por regra (as 5) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {res.regras.map((r) => (
              <CardRegra
                key={r.regra_id}
                regra={r}
                recomendada={
                  res.melhor_regra?.id != null &&
                  r.regra_id === res.melhor_regra.id
                }
              />
            ))}
          </div>

          {res.base_legal_geral && (
            <p className="text-[10px] text-slate-400 border-t border-slate-100 pt-2">
              {res.base_legal_geral}
            </p>
          )}

          {/* Parecer PDF Visual Law */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              className="text-xs px-3 py-2 rounded-lg bg-navy text-white hover:bg-navy/90 flex items-center gap-1.5 transition-colors disabled:opacity-60"
              disabled={gerandoPdf}
              onClick={gerarPdf}
            >
              {gerandoPdf ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Gerando PDF…
                </>
              ) : (
                <>
                  <FileDown size={14} /> Gerar parecer de simulação (Visual Law)
                </>
              )}
            </button>
            <span className="text-[11px] text-slate-400 inline-flex items-center gap-1">
              <Sparkles size={12} className="text-gold-600" />
              Minuta em PDF com os números desta simulação — rascunho (HITL).
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
