import React, { useState } from "react";
import api from "../lib/api";

interface TeseSimilar {
  id: string;
  titulo: string;
  ementa: string;
  area_juridica: string;
  data_vitoria: string;
  link?: string | null;
}
interface JurisSuporte {
  id: string;
  ementa: string;
  tribunal: string;
  data: string;
  link?: string | null;
}
interface Sugestao {
  tipo: string;
  descricao: string;
}
interface VeredutoResponse {
  // null = amostra historica insuficiente (o backend nao inventa numero)
  probabilidade_exito: number | null;
  fonte_probabilidade?: string | null;
  n_amostra?: number;
  teses_vitoriosas_similares: TeseSimilar[];
  jurisprudencia_suporte: JurisSuporte[];
  sugestoes_contextualizadas: Sugestao[];
  score_citacoes?: number | null;
  avisos?: string[];
  status_hitl?: string;
}

const AREAS = [
  "Administrativa",
  "Tributaria",
  "Trabalhista",
  "Ambiental",
  "Bancaria",
  "Civel",
  "Penal",
];

export const VeredutoIAWithVictoryVault: React.FC = () => {
  const [thesis, setThesis] = useState("");
  const [area, setArea] = useState(AREAS[0]);
  const [courts, setCourts] = useState("");
  const [result, setResult] = useState<VeredutoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pct = (p: number) => `${Math.round(p <= 1 ? p * 100 : p)}%`;

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const tribunais_selecionados = courts
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      const r = await api.post("/veredito_ia/analisar", {
        tese_juridica: thesis,
        area_juridica: area,
        tribunais_selecionados,
      });
      setResult(r.data);
    } catch (err) {
      setError("Erro ao analisar a tese. Tente novamente.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <form onSubmit={handleAnalyze} className="card space-y-4 p-5">
        <div>
          <label className="label">Tese juridica</label>
          <textarea
            value={thesis}
            onChange={(e) => setThesis(e.target.value)}
            placeholder="Descreva a tese juridica que deseja analisar..."
            className="input min-h-[110px] resize-y"
            required
          />
        </div>
        <div>
          <label className="label">Area juridica</label>
          <select
            value={area}
            onChange={(e) => setArea(e.target.value)}
            className="input"
          >
            {AREAS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">
            Tribunais relevantes (separados por virgula)
          </label>
          <input
            type="text"
            value={courts}
            onChange={(e) => setCourts(e.target.value)}
            placeholder="Ex: STF, STJ, TJMG"
            className="input"
          />
        </div>
        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Analisando..." : "Analisar tese"}
        </button>
        {error && (
          <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
            {error}
          </div>
        )}
      </form>

      <div className="space-y-4">
        {!result ? (
          <div className="card flex h-full items-center justify-center p-8 text-center text-sm text-slate-400">
            Preencha a tese e clique em "Analisar" para ver a probabilidade de
            exito.
          </div>
        ) : (
          <>
            <div className="card p-5">
              <div className="mb-2 flex items-center justify-between">
                <span className="eyebrow">Probabilidade de exito</span>
                <span className="text-2xl font-semibold text-primary-700">
                  {result.probabilidade_exito != null
                    ? pct(result.probabilidade_exito)
                    : "N/D"}
                </span>
              </div>
              {result.probabilidade_exito != null ? (
                <>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-2 rounded-full bg-primary-600 transition-all"
                      style={{ width: pct(result.probabilidade_exito) }}
                    />
                  </div>
                  {result.fonte_probabilidade && (
                    <p className="mt-2 text-xs text-slate-500">
                      {result.fonte_probabilidade}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-xs text-slate-500">
                  Amostra historica insuficiente
                  {result.n_amostra != null
                    ? ` (${result.n_amostra} caso(s) encerrado(s) na area)`
                    : ""}{" "}
                  — nenhuma probabilidade e inventada.
                </p>
              )}
            </div>

            {(result.avisos?.length ?? 0) > 0 && (
              <div className="card border border-amber-200 bg-amber-50/60 p-5">
                <span className="eyebrow">Avisos</span>
                <ul className="mt-2 space-y-1">
                  {result.avisos!.map((a, i) => (
                    <li key={i} className="text-xs text-amber-800">
                      {a}
                    </li>
                  ))}
                </ul>
                {result.score_citacoes != null && (
                  <p className="mt-2 text-xs font-medium text-amber-900">
                    Score de verificacao das citacoes: {result.score_citacoes}
                    /100
                  </p>
                )}
              </div>
            )}

            {result.teses_vitoriosas_similares?.length > 0 && (
              <div className="card p-5">
                <span className="eyebrow">
                  Teses similares ({result.teses_vitoriosas_similares.length})
                </span>
                <div className="mt-3 space-y-2">
                  {result.teses_vitoriosas_similares.map((t) => (
                    <div
                      key={t.id}
                      className="rounded-lg border border-slate-100 bg-slate-50/60 p-3"
                    >
                      <p className="text-sm font-medium text-slate-900">
                        {t.titulo}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">{t.ementa}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.jurisprudencia_suporte?.length > 0 && (
              <div className="card p-5">
                <span className="eyebrow">Jurisprudencia de suporte</span>
                <div className="mt-3 space-y-2">
                  {result.jurisprudencia_suporte.map((j) => (
                    <div
                      key={j.id}
                      className="rounded-lg border border-slate-100 bg-slate-50/60 p-3"
                    >
                      <p className="text-sm font-medium text-slate-900">
                        {j.tribunal}
                        {j.data ? ` — ${j.data}` : ""}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">{j.ementa}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.sugestoes_contextualizadas?.length > 0 && (
              <div className="card p-5">
                <span className="eyebrow">Sugestoes</span>
                <ul className="mt-3 space-y-2">
                  {result.sugestoes_contextualizadas.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm text-slate-600">
                      <span className="text-primary-600">&bull;</span>
                      <span>
                        <span className="font-medium text-slate-900">
                          {s.tipo}:
                        </span>{" "}
                        {s.descricao}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
