// ── src/components/EstimadorHonorarios.tsx ───────────────────────────────────
// Estimador assistivo. Só usa o rótulo OAB/MG quando o backend confirma que
// encontrou contexto real da tabela oficial; fallback é explicitamente mercado.
import { useState } from "react";
import {
  AlertTriangle,
  Calculator,
  FileSignature,
  Info,
  ShieldCheck,
} from "lucide-react";
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

  const ancoradoOab = r?.tabela_oficial_disponivel === true;

  return (
    <div className="max-w-4xl">
      <p className="text-sm text-slate-500 mb-5 flex items-start gap-2">
        <Calculator size={16} className="text-bronze mt-0.5 shrink-0" />
        Calcula três cenários considerando complexidade, tempo e atos. Quando a
        tabela oficial OAB/MG estiver disponível na base, o resultado é ancorado
        nela; caso contrário, o sistema identifica o resultado como estimativa
        interna de mercado. O advogado define o valor final.
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
          {erro && <span className="text-xs text-danger-600 ml-3">{erro}</span>}
        </div>
      </div>

      {r && (
        <div className="mt-5 space-y-4">
          <div
            className={`rounded-xl border p-3 text-sm flex items-start gap-2 ${
              ancoradoOab
                ? "border-success-200 bg-success-50 text-success-800"
                : "border-warn-200 bg-warn-50 text-warn-800"
            }`}
          >
            {ancoradoOab ? (
              <ShieldCheck size={17} className="mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle size={17} className="mt-0.5 shrink-0" />
            )}
            <div>
              <b>
                {ancoradoOab
                  ? "Referência ancorada em itens OAB/MG disponíveis na base"
                  : "Estimativa interna de mercado — não é referência da tabela OAB/MG"}
              </b>
              <p className="text-xs mt-0.5 opacity-80">
                {ancoradoOab
                  ? "Confira o item/fonte exibido no fundamento e a vigência antes de contratar."
                  : "A tabela oficial não foi localizada para esta consulta. Não use estes números como mínimo ou parâmetro oficial da OAB."}
              </p>
            </div>
          </div>

          <div className="grid sm:grid-cols-3 gap-3">
            {[
              {
                l: ancoradoOab ? "Referência mínima" : "Cenário conservador",
                v: r.minimo,
                c: "border-slate-200",
              },
              {
                l: "Recomendado",
                v: r.recomendado,
                c: "border-bronze ring-1 ring-bronze/20",
              },
              { l: "Estratégico", v: r.estrategico, c: "border-success-200" },
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
              <p className="text-xs text-warn-700 bg-warn-50 rounded-lg p-2 flex items-start gap-1">
                <Info size={13} className="mt-0.5 shrink-0" /> A tabela oficial
                OAB/MG não está disponível para esta consulta. O sistema está
                exibindo somente uma estimativa interna de mercado.
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
