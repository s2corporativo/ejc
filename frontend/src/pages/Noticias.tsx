import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";

export default function Noticias() {
  const [itens, setItens] = useState<any[]>([]);
  const [fontes, setFontes] = useState<string[]>([]);
  const [props, setProps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const carregar = (forcar = false) => {
    if (forcar) setRefreshing(true);
    Promise.allSettled([
      api.get(`/noticias?limit=30${forcar ? "&forcar=true" : ""}`),
      api.get("/rag/monitor-legislativo?limit=15"),
    ])
      .then(([n, l]) => {
        if (n.status === "fulfilled") {
          setItens(n.value.data?.itens ?? []);
          setFontes(n.value.data?.fontes ?? []);
        }
        if (l.status === "fulfilled") setProps(l.value.data?.proposicoes ?? []);
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  };
  useEffect(() => {
    carregar();
  }, []);

  const corFonte: Record<string, string> = {
    ConJur: "bg-sky-100 text-sky-700",
    JOTA: "bg-purple-100 text-purple-700",
  };
  const fmtData = (s: string) => {
    if (!s) return "";
    const d = new Date(s);
    return isNaN(d.getTime())
      ? ""
      : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
  };

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="Notícias Jurídicas"
        subtitle={`Atualidades do Direito (${fontes.join(" · ") || "ConJur · JOTA"}) e radar legislativo`}
        actions={
          <button
            onClick={() => carregar(true)}
            disabled={refreshing}
            className="btn-outline text-sm"
          >
            {refreshing ? "Atualizando…" : "↻ Atualizar"}
          </button>
        }
      />

      <div className="grid lg:grid-cols-3 gap-5">
        {/* Notícias externas */}
        <div className="lg:col-span-2 space-y-3">
          {itens.length === 0 && (
            <p className="text-sm text-slate-400 py-8 text-center">
              Sem notícias no momento
            </p>
          )}
          {itens.map((it, i) => (
            <a
              key={i}
              href={it.link}
              target="_blank"
              rel="noopener noreferrer"
              className="card p-4 block hover:shadow-card-hover transition-shadow"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${corFonte[it.fonte] || "bg-bronze-50 text-bronze-deep"}`}
                >
                  {it.fonte}
                </span>
                {it.data && (
                  <span className="text-xs text-slate-400">
                    {fmtData(it.data)}
                  </span>
                )}
              </div>
              <h3 className="font-semibold text-navy text-[15px] leading-snug mb-1">
                {it.titulo}
              </h3>
              {it.resumo && (
                <p className="text-sm text-slate-500 leading-relaxed">
                  {it.resumo}
                </p>
              )}
            </a>
          ))}
          <p className="text-[11px] text-slate-400 pt-1">
            Manchetes e resumos das fontes; clique para ler o texto integral no
            portal de origem.
          </p>
        </div>

        {/* Radar legislativo (interno) */}
        <div>
          <div className="card p-4 sticky top-20">
            <h3 className="font-semibold text-ink mb-1">Radar legislativo</h3>
            <p className="text-xs text-slate-400 mb-3">
              Proposições recentes — Câmara e Senado
            </p>
            <div className="space-y-2.5 max-h-[32rem] overflow-auto">
              {props.length === 0 && (
                <p className="text-sm text-slate-400 py-4 text-center">
                  Sem proposições ingeridas ainda
                </p>
              )}
              {props.map((p, i) => (
                <div
                  key={i}
                  className="pb-2.5 border-b border-bronze-50 last:border-0"
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    {(p.sigla || p.numero) && (
                      <span className="text-[10px] font-bold bg-navy-50 text-navy-700 px-1.5 py-0.5 rounded">
                        {p.sigla} {p.numero}
                        {p.ano ? `/${p.ano}` : ""}
                      </span>
                    )}
                    {p.casa && (
                      <span className="text-[10px] uppercase text-bronze-deep font-semibold">
                        {p.casa}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-700 leading-snug">
                    {p.titulo}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
