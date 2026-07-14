import { useEffect, useState } from "react";
import { Bell, ExternalLink, FileText, AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import RadarLegislativo from "../components/RadarLegislativo";

interface Item {
  fonte: string;
  keyword?: string;
  titulo?: string;
  resumo?: string;
  link?: string;
  data_publicacao?: string;
}
interface Digest {
  periodo_dias: number;
  desde: string;
  total_alertas: number;
  nao_lidos: number;
  por_fonte: Record<string, number>;
  top_keywords: { keyword: string; qtd: number }[];
  itens_recentes: Item[];
}

export default function RadarRegulatorio() {
  const [dias, setDias] = useState(7);
  const [data, setData] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .get("/v1/regulatorio/digest-semanal", { params: { dias } })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [dias]);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-primary-100 bg-white p-5 shadow-sm md:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <PageHeader
            eyebrow="Inteligencia"
            title="Radar regulatório"
            subtitle="Resumo dos alertas do Diario Oficial (DOU/DOE-MG) coletados pelo monitoramento, agregados por fonte e palavra-chave."
          />
          <select
            value={dias}
            onChange={(e) => setDias(Number(e.target.value))}
            className="input w-44"
          >
            <option value={7}>Ultimos 7 dias</option>
            <option value={14}>Ultimos 14 dias</option>
            <option value={30}>Ultimos 30 dias</option>
          </select>
        </div>
      </div>

      {loading ? (
        <Spinner />
      ) : !data ? (
        <div className="card p-8 text-center text-sm text-slate-400">
          Nao foi possivel carregar o digest.
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="card p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Total de alertas</span>
                <Bell className="h-4 w-4 text-primary-600" />
              </div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">
                {data.total_alertas}
              </div>
              <div className="text-[11px] text-slate-400">
                desde {data.desde}
              </div>
            </div>
            <div className="card p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Nao lidos</span>
                <AlertTriangle className="h-4 w-4 text-warn-600" />
              </div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">
                {data.nao_lidos}
              </div>
            </div>
            {Object.entries(data.por_fonte)
              .slice(0, 2)
              .map(([f, n]) => (
                <div key={f} className="card p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase text-slate-500">
                      {f}
                    </span>
                    <FileText className="h-4 w-4 text-slate-400" />
                  </div>
                  <div className="mt-1 text-2xl font-semibold text-slate-900">
                    {n}
                  </div>
                </div>
              ))}
          </div>

          {data.top_keywords.length > 0 && (
            <div className="card p-5">
              <span className="eyebrow">Palavras-chave mais acionadas</span>
              <div className="mt-3 flex flex-wrap gap-2">
                {data.top_keywords.map((k) => (
                  <span
                    key={k.keyword}
                    className="rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary-700"
                  >
                    {k.keyword}{" "}
                    <span className="text-primary-400">· {k.qtd}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="card p-5">
            <span className="eyebrow">
              Alertas recentes ({data.itens_recentes.length})
            </span>
            {data.itens_recentes.length === 0 ? (
              <div className="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center text-sm text-slate-500">
                Nenhum alerta no periodo. Cadastre palavras-chave em{" "}
                <Link
                  to="/diario-oficial"
                  className="font-medium text-primary-600 hover:underline"
                >
                  Diario Oficial
                </Link>{" "}
                para o monitoramento comecar a capturar publicacoes.
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                {data.itens_recentes.map((it, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-slate-100 bg-slate-50/60 p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-medium text-slate-900">
                        {it.titulo || "(sem titulo)"}
                      </p>
                      <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-[10px] uppercase text-slate-500">
                        {it.fonte}
                      </span>
                    </div>
                    {it.resumo && (
                      <p className="mt-1 text-xs text-slate-500">{it.resumo}</p>
                    )}
                    <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-400">
                      {it.data_publicacao && <span>{it.data_publicacao}</span>}
                      {it.keyword && <span>· {it.keyword}</span>}
                      {it.link && (
                        <a
                          href={it.link}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-primary-600 hover:underline"
                        >
                          abrir <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <RadarLegislativo />
    </div>
  );
}
