// ── Aba Indicadores (Fase 3 / QA): consolida jurisprudência RAG, precedentes,
// score jurídico e índice de risco numa única aba de leitura estratégica ──────
// Ex-sub-abas: "jurisprudencia", "precedentes", "score", "risco" (plano 2.5).
import { useEffect, useState } from "react";
import { toast } from "../../components/Toast";
import { Empty, Spinner, fmtDate } from "../../components/UI";
import api from "../../lib/api";
import TabRisco from "./TabRisco";
import TabScore from "./TabScore";
import type { Case } from "../../types";

export default function TabIndicadoresJuridicos({
  caseId,
  caso,
}: {
  caseId: string;
  caso: Case;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const [precedentes, setPrecedentes] = useState<any[]>([]);
  const [loadingPrec, setLoadingPrec] = useState(true);

  useEffect(() => {
    let ativo = true;
    setLoadingPrec(true);
    api
      .get(
        `/jurisprudencias?area=${encodeURIComponent(caso.area || "")}&per_page=50`,
      )
      .then((r) => {
        const data = r.data;
        if (ativo)
          setPrecedentes(Array.isArray(data) ? data : (data?.data ?? []));
      })
      .catch(() => {})
      .finally(() => {
        if (ativo) setLoadingPrec(false);
      });
    return () => {
      ativo = false;
    };
  }, [caso.area]);

  const buscar = async () => {
    const q = query || caso.descricao_fatos || "";
    if (!q.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const { data } = await api.get("/rag/buscar", {
        params: { q, limite: 10 },
      });
      setResults(data?.resultados ?? []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Jurisprudência via RAG ─────────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="font-semibold">Jurisprudência (RAG)</h2>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && buscar()}
            placeholder="Buscar jurisprudência relevante para este caso..."
            className="input flex-1 text-sm"
          />
          <button
            onClick={buscar}
            disabled={loading}
            className="btn-primary text-sm"
          >
            {loading ? "Buscando..." : "🔍 Buscar"}
          </button>
        </div>
        {!searched && caso.descricao_fatos && (
          <button
            onClick={buscar}
            className="text-sm text-primary-600 hover:underline"
          >
            Buscar jurisprudência relevante automaticamente
          </button>
        )}
        <div className="space-y-3">
          {results.map((r, i) => (
            <div key={i} className="card p-4">
              <div className="flex justify-between mb-2">
                <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded">
                  {r.categoria}
                </span>
                <span className="text-xs text-gray-400">
                  Relevância: {(r.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed">
                {r.conteudo}
              </p>
              {r.fonte && (
                <p className="text-xs text-gray-400 mt-2">Fonte: {r.fonte}</p>
              )}
            </div>
          ))}
          {searched && results.length === 0 && !loading && (
            <Empty message="Nenhum resultado encontrado para esta busca" />
          )}
          {!searched && (
            <p className="text-center py-8 text-gray-400 text-sm">
              Digite um termo para buscar jurisprudência na base de conhecimento
            </p>
          )}
        </div>
      </section>

      {/* ── Precedentes internos ──────────────────────────────────────── */}
      <section className="space-y-2">
        <h2 className="font-semibold">
          Precedentes internos
          {precedentes.length > 0 ? ` (${precedentes.length})` : ""}
        </h2>
        <p className="text-xs text-slate-400">
          Jurisprudência do escritório na área do caso
          {caso.area ? ` (${caso.area})` : ""}.
        </p>
        {loadingPrec ? (
          <Spinner />
        ) : precedentes.length === 0 ? (
          <p className="text-center py-6 text-gray-400 text-sm">
            Nenhuma jurisprudência interna cadastrada nesta área
          </p>
        ) : (
          precedentes.map((j, i) => (
            <div key={j.id || i} className="card p-3 text-sm">
              <div className="flex justify-between items-start gap-2">
                <span className="font-medium text-gray-800">{j.titulo}</span>
                {j.tribunal && (
                  <span className="text-xs text-gray-400 shrink-0">
                    {j.tribunal}
                  </span>
                )}
              </div>
              {j.ementa && (
                <p className="text-gray-600 text-xs mt-1">
                  {j.ementa.slice(0, 180)}
                  {j.ementa.length > 180 ? "…" : ""}
                </p>
              )}
              <div className="flex gap-2 mt-1 text-xs text-gray-400">
                {j.area_juridica && <span>{j.area_juridica}</span>}
                {j.resultado && <span>· {j.resultado}</span>}
                {j.favorito && <span>· ★</span>}
                {typeof j.vezes_citada === "number" && (
                  <span>· {j.vezes_citada}× citada</span>
                )}
              </div>
            </div>
          ))
        )}
      </section>

      {/* ── Score jurídico e índice de risco (lado a lado) ────────────── */}
      <section className="grid gap-6 lg:grid-cols-2">
        <TabScore caseId={caseId} />
        <TabRisco caseId={caseId} />
      </section>
    </div>
  );
}
