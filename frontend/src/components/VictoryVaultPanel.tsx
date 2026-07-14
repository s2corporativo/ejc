import React, { useState, useEffect } from "react";
import { Search } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { Spinner } from "./UI";

interface TeseVitoriosa {
  id: string;
  titulo: string;
  area_juridica: string;
  ementa: string;
  processo_referencia?: string;
  data_vitoria: string;
}

interface ModeloDocumento {
  id: string;
  nome?: string;
  descricao?: string;
  area_juridica: string;
  tipo_documento: string;
}

const AREAS = [
  "Administrativa",
  "Tributaria",
  "Trabalhista",
  "Ambiental",
  "Bancaria",
];

export const VictoryVaultPanel: React.FC = () => {
  const [teses, setTeses] = useState<TeseVitoriosa[]>([]);
  const [modelos, setModelos] = useState<ModeloDocumento[]>([]);
  const [selectedTab, setSelectedTab] = useState<"teses" | "modelos">("teses");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData();
  }, [selectedTab, selectedArea]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = {
        query: searchQuery || undefined,
        area_juridica: selectedArea || undefined,
      };
      if (selectedTab === "teses") {
        const r = await api.get("/victory_vault/teses", { params });
        setTeses(asList<TeseVitoriosa>(r.data));
      } else {
        const r = await api.get("/victory_vault/modelos", { params });
        setModelos(asList<ModeloDocumento>(r.data));
      }
    } catch (e) {
      console.error("Erro ao buscar dados do Victory Vault:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchData();
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2 border-b border-slate-200">
        {(["teses", "modelos"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSelectedTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              selectedTab === t
                ? "border-primary-600 text-primary-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t === "teses" ? "Teses vitoriosas" : "Modelos de documentos"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSearch} className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar por titulo ou ementa..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input pl-9"
            />
          </div>
          <button type="submit" className="btn-primary">
            Buscar
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setSelectedArea(null)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              selectedArea === null
                ? "bg-primary-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Todas as areas
          </button>
          {AREAS.map((area) => (
            <button
              key={area}
              type="button"
              onClick={() => setSelectedArea(area)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                selectedArea === area
                  ? "bg-primary-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {area}
            </button>
          ))}
        </div>
      </form>

      {loading ? (
        <Spinner />
      ) : selectedTab === "teses" ? (
        <div className="space-y-3">
          {teses.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-400">
              Nenhuma tese encontrada
            </div>
          ) : (
            teses.map((tese) => (
              <div key={tese.id} className="card p-4">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {tese.titulo}
                  </h3>
                  <span className="badge badge-info shrink-0">
                    {tese.area_juridica}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{tese.ementa}</p>
                {tese.processo_referencia && (
                  <p className="mt-2 text-xs text-slate-400">
                    Processo: {tese.processo_referencia}
                  </p>
                )}
                <p className="mt-2 text-xs text-slate-400">
                  Vitoria em{" "}
                  {new Date(tese.data_vitoria).toLocaleDateString("pt-BR")}
                </p>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {modelos.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-400">
              Nenhum modelo encontrado
            </div>
          ) : (
            modelos.map((modelo) => (
              <div key={modelo.id} className="card p-4">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {modelo.descricao || modelo.tipo_documento}
                  </h3>
                  <span className="badge badge-neutral shrink-0">
                    {modelo.tipo_documento}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Area: {modelo.area_juridica}
                </p>
                <button className="btn-outline mt-3 text-xs">
                  Usar modelo
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
