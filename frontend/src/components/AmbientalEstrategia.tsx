// ── src/components/AmbientalEstrategia.tsx ───────────────────────────────────
// Simulador de Estratégia do Auto de Infração Ambiental (diferencial do ramo).
// Comparador econômico determinístico (sem IA) dos caminhos possíveis diante de
// um AI: pagar à vista, converter multa em serviços (IN IBAMA 4/2026, -40%),
// defender/impugnar e prescrição. Backend: /ambiental/estrategia/*.
// Tudo é apoio técnico — a decisão é do advogado (HITL/OAB).
import { useState } from "react";
import {
  AlertTriangle,
  Award,
  Hourglass,
  Leaf,
  Recycle,
  Scale,
  Shield,
  Sparkles,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { Modal, Button } from "./UI";
import { toast } from "./Toast";

// ── helpers ──────────────────────────────────────────────────────────────────
function fmtBRL(v: number | null | undefined) {
  return Number(v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
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

// ── Tipos da resposta (contrato /ambiental/estrategia/simular) ───────────────
type CenarioId =
  "pagar_a_vista" | "converter_servicos" | "defender" | "prescricao";

interface Cenario {
  id: CenarioId;
  titulo: string;
  base_legal: string;
  aplicavel: boolean;
  desembolso_estimado: number;
  memoria_calculo: string[];
  observacoes: string[];
}
interface Recomendacao {
  cenario_id: CenarioId;
  racional: string;
}
interface SimulacaoRes {
  cenarios: Cenario[];
  recomendacao: Recomendacao;
  aviso_hitl: string;
  base_legal_geral: string;
}

const AVISO_HITL_FALLBACK =
  "Simulação econômica de apoio — a escolha da estratégia é do advogado e depende do caso concreto. Não substitui o parecer jurídico.";

const CENARIO_ICON: Record<CenarioId, typeof Wallet> = {
  pagar_a_vista: Wallet,
  converter_servicos: Recycle,
  defender: Shield,
  prescricao: Hourglass,
};

// ── Barra comparativa (CSS puro) — menor desembolso em dourado ───────────────
function ComparacaoDesembolsos({
  cenarios,
  recomendadoId,
}: {
  cenarios: Cenario[];
  recomendadoId: CenarioId;
}) {
  const aplicaveis = cenarios.filter((c) => c.aplicavel);
  if (aplicaveis.length < 2) return null;
  const max = Math.max(...aplicaveis.map((c) => c.desembolso_estimado), 1);
  const min = Math.min(...aplicaveis.map((c) => c.desembolso_estimado));
  return (
    <div className="rounded-xl border border-black/[0.05] dark:border-white/10 bg-slate-50/60 p-4 space-y-2.5">
      <div className="text-xs font-bold text-slate-500 uppercase tracking-wide">
        Comparação de desembolso estimado
      </div>
      {aplicaveis.map((c) => {
        const melhor = c.desembolso_estimado === min;
        const largura = Math.max(4, (c.desembolso_estimado / max) * 100);
        return (
          <div key={c.id} className="flex items-center gap-3">
            <div className="w-32 sm:w-40 flex-shrink-0 text-[11px] text-slate-600 flex items-center gap-1 truncate">
              {c.id === recomendadoId && (
                <Award size={12} className="text-gold-600 flex-shrink-0" />
              )}
              <span className="truncate">{c.titulo}</span>
            </div>
            <div className="flex-1 h-5 rounded-full bg-slate-100 overflow-hidden">
              <div
                className={`h-full rounded-full flex items-center justify-end px-2 ${
                  melhor ? "bg-gold" : "bg-slate-300"
                }`}
                style={{ width: `${largura}%` }}
              >
                <span
                  className={`text-[10px] font-bold whitespace-nowrap ${
                    melhor ? "text-navy" : "text-slate-600"
                  }`}
                >
                  {fmtBRL(c.desembolso_estimado)}
                </span>
              </div>
            </div>
          </div>
        );
      })}
      <p className="text-[10px] text-slate-400">
        Barra em dourado = menor desembolso estimado entre os caminhos
        aplicáveis. Valores preliminares.
      </p>
    </div>
  );
}

// ── Card de um cenário ────────────────────────────────────────────────────────
function CardCenario({
  cenario,
  recomendado,
}: {
  cenario: Cenario;
  recomendado: boolean;
}) {
  const Icone = CENARIO_ICON[cenario.id] ?? Scale;
  const inaplicavel = !cenario.aplicavel;
  return (
    <div
      className={`rounded-xl border p-4 relative transition-colors ${
        recomendado
          ? "border-2 border-gold bg-gold-50/50"
          : inaplicavel
            ? "border-slate-200 bg-slate-50/40 opacity-60"
            : "border-black/[0.05] dark:border-white/10 bg-white"
      }`}
    >
      {recomendado && (
        <span className="absolute -top-2.5 right-3 text-[10px] font-bold uppercase tracking-wide bg-gold text-navy px-2 py-0.5 rounded-full shadow-sm flex items-center gap-1">
          <Award size={11} /> Recomendado
        </span>
      )}
      <div className="flex items-start gap-2 mb-2">
        <Icone
          size={18}
          className={recomendado ? "text-gold-700" : "text-green-600"}
        />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-navy leading-tight">
            {cenario.titulo}
          </h3>
          {cenario.base_legal && (
            <span className="inline-block mt-1 text-[10px] px-2 py-0.5 rounded-full bg-gold-50 border border-gold-light text-gold-700 leading-relaxed">
              {cenario.base_legal}
            </span>
          )}
        </div>
      </div>

      {inaplicavel ? (
        <div className="text-lg font-bold text-slate-400">Não aplicável</div>
      ) : (
        <div className="text-2xl font-bold text-gold-700">
          {fmtBRL(cenario.desembolso_estimado)}
          <span className="text-[11px] font-normal text-slate-500 ml-1">
            desembolso estimado
          </span>
        </div>
      )}

      {cenario.memoria_calculo?.length > 0 && (
        <details className="mt-2">
          <summary className="text-[11px] text-slate-500 cursor-pointer select-none hover:text-slate-700">
            Como chegamos neste número
          </summary>
          <ol className="mt-1.5 space-y-0.5">
            {cenario.memoria_calculo.map((m, i) => (
              <li key={i} className="text-[11px] text-slate-600 font-mono">
                {m}
              </li>
            ))}
          </ol>
        </details>
      )}

      {cenario.observacoes?.length > 0 && (
        <ul className="mt-2 space-y-1">
          {cenario.observacoes.map((o, i) => (
            <li
              key={i}
              className="text-[11px] text-slate-500 flex items-start gap-1.5"
            >
              <span className="text-slate-300 mt-0.5">•</span>
              <span>{o}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Modal de geração da peça de conversão (Visual Law → PDF) ──────────────────
function PecaConversaoModal({
  open,
  onClose,
  simulacao,
}: {
  open: boolean;
  onClose: () => void;
  simulacao: SimulacaoRes | null;
}) {
  const [orgao, setOrgao] = useState("");
  const [numeroAuto, setNumeroAuto] = useState("");
  const [gerando, setGerando] = useState(false);
  const [erro, setErro] = useState("");

  const fechar = () => {
    if (gerando) return;
    setErro("");
    onClose();
  };

  // Mesmo padrão dos demais PDFs Visual Law (TributarioFiscal/SalaDeGuerra):
  // POST → download_url → blob (baseURL do client é /api → remove o prefixo).
  const gerar = async () => {
    if (!simulacao) return;
    if (!orgao.trim() || !numeroAuto.trim()) {
      setErro("Informe o órgão autuador e o número do auto de infração.");
      return;
    }
    setGerando(true);
    setErro("");
    try {
      const r = await api.post("/ambiental/estrategia/peca-conversao", {
        ...simulacao,
        orgao_autuador: orgao.trim(),
        numero_auto: numeroAuto.trim(),
      });
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "requerimento-conversao-multa.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Requerimento de conversão (Visual Law) gerado.");
      onClose();
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao gerar o requerimento de conversão."));
    } finally {
      setGerando(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={fechar}
      title="Requerimento de conversão de multa (Visual Law)"
    >
      <div className="space-y-3">
        <p className="text-xs text-slate-500">
          Gera a minuta do requerimento de conversão da multa em serviços de
          preservação/recuperação (IN IBAMA 4/2026 — desconto de 40%), com os
          números da simulação. Rascunho — revisão do advogado obrigatória.
        </p>
        <div>
          <label className="label text-xs">Órgão autuador *</label>
          <input
            className="input text-sm"
            placeholder="ex: IBAMA · IEF/MG · SEMAD"
            value={orgao}
            onChange={(e) => setOrgao(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">Número do auto de infração *</label>
          <input
            className="input text-sm"
            placeholder="ex: 0001234/2026"
            value={numeroAuto}
            onChange={(e) => setNumeroAuto(e.target.value)}
          />
        </div>
        {erro && <p className="text-xs text-danger-600">{erro}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={fechar} disabled={gerando}>
            Cancelar
          </Button>
          <Button
            variant="ai"
            onClick={gerar}
            disabled={gerando}
            icon={<Sparkles size={15} />}
          >
            {gerando ? "Gerando…" : "Gerar requerimento"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────
export default function AmbientalEstrategia() {
  const [form, setForm] = useState({
    valor_multa: "",
    data_ciencia: "",
    fase: "antes_defesa" as "antes_defesa" | "apos_defesa",
    prob_manutencao_pct: 50,
    custo_recuperacao_estimado: "",
    data_infracao: "",
  });
  const [res, setRes] = useState<SimulacaoRes | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [pecaOpen, setPecaOpen] = useState(false);

  const set = (k: keyof typeof form) => (v: any) =>
    setForm((f) => ({ ...f, [k]: v }));

  const simular = async () => {
    const valor = parseNum(form.valor_multa);
    if (!valor || valor <= 0 || !form.data_ciencia) {
      setErro("Informe o valor da multa e a data da ciência do auto.");
      return;
    }
    setLoading(true);
    setErro("");
    setRes(null);
    const custo = parseNum(form.custo_recuperacao_estimado);
    const body = {
      valor_multa: valor,
      data_ciencia: form.data_ciencia,
      fase: form.fase,
      prob_manutencao_pct: form.prob_manutencao_pct,
      custo_recuperacao_estimado:
        form.custo_recuperacao_estimado.trim() !== "" ? custo : null,
      data_infracao: form.data_infracao || null,
    };
    try {
      const { data } = await api.post<SimulacaoRes>(
        "/ambiental/estrategia/simular",
        body,
      );
      setRes(data);
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao simular os cenários."));
    } finally {
      setLoading(false);
    }
  };

  const recomendado = res?.cenarios.find(
    (c) => c.id === res.recomendacao?.cenario_id,
  );

  return (
    <div
      id="ambiental-estrategia"
      className="card p-4 mb-4 border-l-4 border-green-600 scroll-mt-20"
    >
      <div className="flex items-center gap-2 mb-1">
        <Leaf size={16} className="text-green-600" />
        <h2 className="font-serif font-semibold text-navy">
          Simulador de Estratégia do Auto de Infração
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Compara o custo econômico dos caminhos diante de um AI ambiental — pagar
        à vista, converter a multa em serviços (IN IBAMA 4/2026, −40%),
        defender/impugnar e prescrição — para orientar a decisão.{" "}
        <span className="text-gold-700">
          Estimativa determinística (sem IA) · apoio técnico
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
          <label className="label text-xs">Valor da multa (R$) *</label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="ex: 50.000,00"
            value={form.valor_multa}
            onChange={(e) => set("valor_multa")(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">Data da ciência do auto *</label>
          <input
            className="input text-sm"
            type="date"
            value={form.data_ciencia}
            onChange={(e) => set("data_ciencia")(e.target.value)}
          />
        </div>
        <div>
          <label className="label text-xs">Fase do processo</label>
          <select
            className="input text-sm"
            value={form.fase}
            onChange={(e) => set("fase")(e.target.value)}
          >
            <option value="antes_defesa">Antes da defesa</option>
            <option value="apos_defesa">Após a defesa</option>
          </select>
          <p className="text-[10px] text-slate-400 mt-0.5">
            O desconto de conversão (40%) exige requerer junto com a defesa.
          </p>
        </div>
        <div className="col-span-2 sm:col-span-3">
          <label className="label text-xs">
            Probabilidade estimada de manutenção do auto:{" "}
            <b className="text-navy">{form.prob_manutencao_pct}%</b>
          </label>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={form.prob_manutencao_pct}
            onChange={(e) => set("prob_manutencao_pct")(Number(e.target.value))}
            className="w-full accent-green-600"
          />
          <p className="text-[10px] text-slate-400 mt-0.5">
            Sua estimativa como advogado, não do sistema — usada para o valor
            esperado do caminho de defesa.
          </p>
        </div>
        <div>
          <label className="label text-xs">
            Custo de recuperação já previsto (R$)
          </label>
          <input
            className="input text-sm"
            inputMode="decimal"
            placeholder="opcional"
            value={form.custo_recuperacao_estimado}
            onChange={(e) => set("custo_recuperacao_estimado")(e.target.value)}
          />
          <p className="text-[10px] text-slate-400 mt-0.5">
            Serviço que o cliente já faria — abate no cenário de conversão.
          </p>
        </div>
        <div>
          <label className="label text-xs">Data do fato / infração</label>
          <input
            className="input text-sm"
            type="date"
            value={form.data_infracao}
            onChange={(e) => set("data_infracao")(e.target.value)}
          />
          <p className="text-[10px] text-slate-400 mt-0.5">
            Opcional — dispara a análise de prescrição (Lei 9.873/99).
          </p>
        </div>
      </div>

      <button
        className="btn-gold text-sm mt-3"
        disabled={loading}
        onClick={simular}
      >
        <Scale size={14} /> {loading ? "Comparando…" : "Comparar cenários"}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {/* Resultado */}
      {res && (
        <div className="mt-4 space-y-4">
          {/* Banner de recomendação */}
          {recomendado && res.recomendacao?.racional && (
            <div className="rounded-xl border-2 border-gold bg-gold-50 p-4">
              <div className="flex items-center gap-2 mb-1">
                <Award size={16} className="text-gold-700" />
                <span className="text-xs font-bold text-gold-700 uppercase tracking-wide">
                  Caminho recomendado — {recomendado.titulo}
                </span>
              </div>
              <p className="text-sm text-navy leading-relaxed">
                {res.recomendacao.racional}
              </p>
            </div>
          )}

          {/* Comparação visual */}
          <ComparacaoDesembolsos
            cenarios={res.cenarios}
            recomendadoId={res.recomendacao?.cenario_id}
          />

          {/* Cards por cenário */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {res.cenarios.map((c) => (
              <CardCenario
                key={c.id}
                cenario={c}
                recomendado={c.id === res.recomendacao?.cenario_id}
              />
            ))}
          </div>

          {res.base_legal_geral && (
            <p className="text-[10px] text-slate-400 border-t border-slate-100 pt-2">
              {res.base_legal_geral}
            </p>
          )}

          {/* Peça de conversão */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              onClick={() => setPecaOpen(true)}
              className="text-xs px-3 py-2 rounded-lg bg-navy text-white hover:bg-navy/90 flex items-center gap-1.5 transition-colors"
            >
              <Recycle size={14} /> Gerar requerimento de conversão (Visual Law)
            </button>
            <span className="text-[11px] text-slate-400">
              Minuta em PDF com os números desta simulação — rascunho (HITL).
            </span>
          </div>
        </div>
      )}

      <PecaConversaoModal
        open={pecaOpen}
        onClose={() => setPecaOpen(false)}
        simulacao={res}
      />
    </div>
  );
}
