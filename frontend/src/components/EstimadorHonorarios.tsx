// ── src/components/EstimadorHonorarios.tsx ───────────────────────────────────
// P2.1 — Estimador de honorários estruturado, ancorado na tabela OAB/MG (RAG).
// Três cenários (mínimo/recomendado/estratégico) + memória de cálculo + contrato
// sugerido. Tudo é referência (HITL): o advogado define o valor final.
import { useState } from "react";
import { Calculator, FileSignature, Info } from "lucide-react";
import api from "../lib/api";

const AREAS = [
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "ambiental",
  "criminal",
  "previdenciario",
  "empresarial",
  "tributario",
];
const AREA_LABEL: Record<string, string> = {
  civil: "Cível",
  trabalhista: "Trabalhista",
  consumidor: "Consumidor",
  familia: "Família",
  ambiental: "Ambiental",
  criminal: "Criminal",
  previdenciario: "Previdenciário",
  empresarial: "Empresarial",
  tributario: "Tributário",
};

export default function EstimadorHonorarios() {
  const [form, setForm] = useState<any>({
    area: "civil",
    complexidade: "media",
    instancia: "1grau",
  });
  const [r, setR] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const estimar = async () => {
    if (!form.tipo_acao?.trim()) {
      setErro("Informe o tipo de ação.");
      return;
    }
    setLoading(true);
    setErro("");
    setR(null);
    try {
      const { data } = await api.post("/honorarios-oab/estimar", {
        area: form.area,
        tipo_acao: form.tipo_acao,
        valor_causa: form.valor_causa ? Number(form.valor_causa) : undefined,
        complexidade: form.complexidade,
        tempo_meses: form.tempo_meses ? Number(form.tempo_meses) : undefined,
        num_atos: form.num_atos ? Number(form.num_atos) : undefined,
        instancia: form.instancia,
        observacoes: form.observacoes,
      });
      setR(data);
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha ao estimar.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <Calculator size={18} className="text-bronze" />
        <h1 className="text-xl font-semibold text-navy-900">
          Estimador de Honorários (OAB/MG)
        </h1>
      </div>
      <p className="text-sm text-slate-500 mb-5">
        Calcula três cenários ancorados na tabela OAB/MG, ponderando
        complexidade, tempo e atos. Referência — o advogado define o valor
        final.
      </p>

      <div className="card p-5 grid sm:grid-cols-2 gap-4">
        <div>
          <label className="label">Área *</label>
          <select
            className="input"
            value={form.area}
            onChange={(e) => set("area", e.target.value)}
          >
            {AREAS.map((a) => (
              <option key={a} value={a}>
                {AREA_LABEL[a]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Tipo de ação *</label>
          <input
            className="input"
            placeholder="Ex.: indenização por dano moral"
            value={form.tipo_acao || ""}
            onChange={(e) => set("tipo_acao", e.target.value)}
          />
        </div>
        <div>
          <label className="label">Valor da causa (R$)</label>
          <input
            className="input"
            type="number"
            value={form.valor_causa || ""}
            onChange={(e) => set("valor_causa", e.target.value)}
          />
        </div>
        <div>
          <label className="label">Complexidade</label>
          <select
            className="input"
            value={form.complexidade}
            onChange={(e) => set("complexidade", e.target.value)}
          >
            <option value="baixa">Baixa</option>
            <option value="media">Média</option>
            <option value="alta">Alta</option>
          </select>
        </div>
        <div>
          <label className="label">Tempo estimado (meses)</label>
          <input
            className="input"
            type="number"
            value={form.tempo_meses || ""}
            onChange={(e) => set("tempo_meses", e.target.value)}
          />
        </div>
        <div>
          <label className="label">Nº de atos processuais</label>
          <input
            className="input"
            type="number"
            value={form.num_atos || ""}
            onChange={(e) => set("num_atos", e.target.value)}
          />
        </div>
        <div>
          <label className="label">Instância</label>
          <select
            className="input"
            value={form.instancia}
            onChange={(e) => set("instancia", e.target.value)}
          >
            <option value="1grau">1º grau</option>
            <option value="2grau">2º grau</option>
            <option value="superior">Superior</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label">Observações (opcional)</label>
          <input
            className="input"
            value={form.observacoes || ""}
            onChange={(e) => set("observacoes", e.target.value)}
          />
        </div>
        <div className="sm:col-span-2">
          <button className="btn-gold" disabled={loading} onClick={estimar}>
            <Calculator size={15} />{" "}
            {loading ? "Calculando…" : "Estimar honorários"}
          </button>
          {erro && <span className="text-xs text-red-600 ml-3">{erro}</span>}
        </div>
      </div>

      {r && (
        <div className="mt-5 space-y-4">
          <div className="grid sm:grid-cols-3 gap-3">
            {[
              { l: "Mínimo", v: r.minimo, c: "border-slate-200" },
              {
                l: "Recomendado",
                v: r.recomendado,
                c: "border-bronze ring-1 ring-bronze/20",
              },
              { l: "Estratégico", v: r.estrategico, c: "border-emerald-200" },
            ].map(({ l, v, c }) => (
              <div key={l} className={`card p-4 text-center ${c}`}>
                <p className="text-[11px] uppercase tracking-wide text-ink-light">
                  {l}
                </p>
                <p className="text-lg font-bold text-navy-900 mt-1">
                  {v || "—"}
                </p>
              </div>
            ))}
          </div>

          <div className="card p-4 space-y-2 text-sm">
            {r.fundamento && (
              <p>
                <b className="text-slate-600">Fundamento:</b> {r.fundamento}
              </p>
            )}
            {r.memoria_calculo && (
              <p>
                <b className="text-slate-600">Memória de cálculo:</b>{" "}
                {r.memoria_calculo}
              </p>
            )}
            {r.contrato_sugerido && (
              <p className="flex items-start gap-1">
                <FileSignature
                  size={14}
                  className="text-bronze mt-0.5 shrink-0"
                />
                <span>
                  <b className="text-slate-600">Contrato sugerido:</b>{" "}
                  {r.contrato_sugerido}
                </span>
              </p>
            )}
            {r.tabela_oficial_disponivel === false && (
              <p className="text-xs text-amber-700 bg-amber-50 rounded-lg p-2 flex items-start gap-1">
                <Info size={13} className="mt-0.5 shrink-0" /> Tabela oficial
                OAB/MG não está na base — valores são referência genérica de
                mercado.
              </p>
            )}
            {r._aviso && (
              <p className="text-[11px] text-slate-500 border-t border-bronze-50 pt-2">
                ⚠ {r._aviso}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
