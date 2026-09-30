import { useMemo, useState } from "react";
import { FileDiff, Loader2 } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import type { Case } from "../types";

const MODALIDADES = [
  ["revisao_contratual", "Revisão contratual"],
  ["revisao_bancaria", "Revisão bancária"],
  ["multa_administrativa", "Administrativo"],
  ["multa_ambiental", "Ambiental"],
  ["multa_transito", "Trânsito"],
] as const;

function modalidadeInicial(area?: string) {
  if (area === "bancario") return "revisao_bancaria";
  if (area === "ambiental") return "multa_ambiental";
  if (area === "transito") return "multa_transito";
  if (area === "administrativo" || area === "licitacoes")
    return "multa_administrativa";
  return "revisao_contratual";
}

function Lista({ title, items }: { title: string; items: any[] }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-slate-700">{title}</h4>
      <ul className="mt-1 space-y-1 text-xs text-slate-600">
        {items.slice(0, 12).map((item, index) => (
          <li key={index} className="rounded-lg bg-slate-50 px-2.5 py-2">
            {typeof item === "string"
              ? item
              : Object.entries(item || {})
                  .filter(([, value]) => value !== null && value !== "")
                  .map(
                    ([key, value]) =>
                      key.replace(/_/g, " ") + ": " + String(value),
                  )
                  .join(" · ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ComparadorJuridicoCaso({ caso }: { caso: Case }) {
  const [base, setBase] = useState<File | null>(null);
  const [comparado, setComparado] = useState<File | null>(null);
  const [modalidade, setModalidade] = useState(() =>
    modalidadeInicial(caso.area),
  );
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<any>(null);

  const podeComparar = useMemo(
    () => Boolean(base && comparado && !loading),
    [base, comparado, loading],
  );

  const comparar = async () => {
    if (!base || !comparado) {
      toast.error("Selecione os dois documentos.");
      return;
    }
    setLoading(true);
    setResultado(null);
    try {
      const form = new FormData();
      form.append("modalidade", modalidade);
      form.append("case_id", caso.id);
      form.append("arquivo_base", base);
      form.append("arquivo_comparado", comparado);
      const { data } = await api.post(
        "/defesas-revisoes/avancado/comparar-documentos",
        form,
      );
      setResultado(data?.resultado || { texto: data?.resultado || data });
      toast.success("Comparação concluída — revise o resultado antes de usar.");
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível comparar os documentos.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="ejc-legal-compare card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="ejc-legal-compare__icon">
            <FileDiff aria-hidden="true" />
          </span>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              Comparador jurídico
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Compare Inicial × Contestação, Laudo × Impugnação ou quaisquer
              dois documentos do caso.
            </p>
          </div>
        </div>
        <span className="rounded-full bg-violet-50 px-2.5 py-1 text-[10px] font-semibold text-violet-700">
          IA · revisão humana obrigatória
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[0.8fr_1fr_1fr]">
        <label className="text-xs text-slate-600">
          Contexto
          <select
            value={modalidade}
            onChange={(e) => setModalidade(e.target.value)}
            className="input mt-1 w-full"
          >
            {MODALIDADES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-600">
          Documento A · base
          <input
            type="file"
            className="mt-1 block w-full text-xs"
            onChange={(e) => setBase(e.target.files?.[0] || null)}
          />
        </label>
        <label className="text-xs text-slate-600">
          Documento B · contraponto
          <input
            type="file"
            className="mt-1 block w-full text-xs"
            onChange={(e) => setComparado(e.target.files?.[0] || null)}
          />
        </label>
      </div>

      <button
        type="button"
        className="btn-primary mt-4 inline-flex items-center gap-2"
        disabled={!podeComparar}
        onClick={comparar}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FileDiff className="h-4 w-4" />
        )}
        {loading ? "Comparando…" : "Comparar documentos"}
      </button>

      {resultado && (
        <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
          {resultado.resumo && (
            <div>
              <h4 className="text-xs font-semibold text-slate-700">Síntese</h4>
              <p className="mt-1 text-sm leading-6 text-slate-700">
                {String(resultado.resumo)}
              </p>
            </div>
          )}
          <Lista title="Contradições" items={resultado.contradicoes || []} />
          <Lista
            title="Fatos incontroversos"
            items={resultado.fatos_incontroversos || []}
          />
          <Lista
            title="Provas ausentes"
            items={resultado.provas_ausentes || []}
          />
          <Lista
            title="Pontos que exigem resposta"
            items={resultado.pontos_que_exigem_resposta || []}
          />
          <Lista
            title="Alterações relevantes"
            items={resultado.alteracoes || []}
          />
          <Lista title="Alertas" items={resultado.alertas || []} />
        </div>
      )}
    </section>
  );
}
