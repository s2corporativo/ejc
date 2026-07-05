// ── RadarLegislativo — projetos de lei reais (Dados Abertos da Câmara) ───────
// Consome GET /intelligence-v3/radar/legislativo (backend filtra proposições
// recentes pelas keywords estratégicas do escritório). Antes este componente
// exibia dados mockados e não era montado em nenhuma rota.
import { useEffect, useState } from "react";
import { ExternalLink, Landmark, RefreshCw } from "lucide-react";
import api from "../lib/api";

interface Proposicao {
  id: number;
  siglaTipo: string;
  numero: number;
  ano: number;
  ementa: string;
  casa?: "camara" | "senado";
  link?: string;
}

export default function RadarLegislativo() {
  const [alertas, setAlertas] = useState<Proposicao[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);

  const carregar = () => {
    setLoading(true);
    setErro(false);
    api
      .get("/intelligence-v3/radar/legislativo")
      .then((r) => setAlertas(r.data?.alertas_legislativos ?? []))
      .catch(() => setErro(true))
      .finally(() => setLoading(false));
  };

  useEffect(carregar, []);

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Landmark className="h-5 w-5 text-primary-600" />
          <h3 className="text-base font-semibold text-slate-900">
            Radar legislativo (Câmara e Senado)
          </h3>
        </div>
        <button
          onClick={carregar}
          disabled={loading}
          className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </button>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Proposições recentes que casam com os temas estratégicos do escritório
        (tributos, direito administrativo, medicamentos veterinários), direto
        dos Dados
        Abertos da Câmara e do Senado.
      </p>

      {loading ? (
        <div className="py-6 text-center text-sm text-slate-400">
          Consultando a Câmara...
        </div>
      ) : erro ? (
        <div className="py-6 text-center text-sm text-slate-400">
          Não foi possível consultar os Dados Abertos da Câmara agora.
        </div>
      ) : alertas.length === 0 ? (
        <div className="py-6 text-center text-sm text-slate-400">
          Nenhuma proposição recente casa com as palavras-chave monitoradas.
        </div>
      ) : (
        <ul className="space-y-3">
          {alertas.slice(0, 12).map((p) => (
            <li
              key={p.id}
              className="rounded-lg border border-slate-100 p-3 text-sm"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="font-medium text-slate-800">
                  {p.siglaTipo} {p.numero}/{p.ano}
                  <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-normal uppercase text-slate-500">
                    {p.casa === "senado" ? "Senado" : "Câmara"}
                  </span>
                </span>
                <a
                  href={
                    p.link ??
                    `https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=${p.id}`
                  }
                  target="_blank"
                  rel="noreferrer"
                  className="flex shrink-0 items-center gap-1 text-xs text-primary-600 hover:underline"
                >
                  Ver tramitação <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <p className="text-xs leading-relaxed text-slate-600">
                {p.ementa}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
