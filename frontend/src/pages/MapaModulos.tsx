import { useEffect, useMemo, useState } from "react";
import api from "../lib/api";

type Modulo = {
  module_key: string;
  nome: string;
  grupo: string;
  frontend_route: string;
  backend_prefixes: string[];
  status: string;
  perfis: string[];
  dependencias: string[];
  usa_ia: boolean;
  dados_sensiveis: boolean;
  qtd_endpoints_detectados?: number;
  precisa_revisao?: boolean;
};

type Payload = {
  resumo?: Record<string, number>;
  modulos?: Modulo[];
  rotas_api_detectadas?: number;
  modo?: string;
};

type Diagnostico = {
  metricas?: { rotas_api_detectadas?: number };
  inventario?: {
    modulos_esperados?: Array<{ module_key: string; rota: string; titulo: string; grupo: string }>;
  };
};

const statusClass: Record<string, string> = {
  ativo: "bg-emerald-50 text-emerald-700 border-emerald-200",
  beta: "bg-amber-50 text-amber-700 border-amber-200",
  legado: "bg-slate-100 text-slate-700 border-slate-200",
};

function adaptarDiagnostico(d: Diagnostico): Payload {
  const modulos: Modulo[] = (d.inventario?.modulos_esperados || []).map((m) => ({
    module_key: m.module_key,
    nome: m.titulo,
    grupo: m.grupo,
    frontend_route: m.rota,
    backend_prefixes: [],
    status: "ativo",
    perfis: ["superadmin", "admin", "socio"],
    dependencias: [],
    usa_ia: ["ia", "inteligencia", "ferramentas-ia", "conhecimento", "jurimetria"].includes(m.module_key),
    dados_sensiveis: !["dashboard", "autofix"].includes(m.module_key),
    qtd_endpoints_detectados: 0,
    precisa_revisao: true,
  }));
  return {
    modo: "diagnostico_existente",
    rotas_api_detectadas: d.metricas?.rotas_api_detectadas || 0,
    resumo: {
      total: modulos.length,
      sem_endpoint_detectado: modulos.length,
      usam_ia: modulos.filter((m) => m.usa_ia).length,
      dados_sensiveis: modulos.filter((m) => m.dados_sensiveis).length,
      precisam_revisao: modulos.length,
    },
    modulos,
  };
}

export default function MapaModulos() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [grupo, setGrupo] = useState("todos");

  useEffect(() => {
    api
      .get<Payload>("/system-modules/mapa")
      .then((r) => setData(r.data))
      .catch(() =>
        api
          .get<Diagnostico>("/module-help/diagnostico-sistema")
          .then((r) => setData(adaptarDiagnostico(r.data)))
          .catch((e) => setErro(e?.response?.data?.detail || "Não foi possível carregar o mapa.")),
      )
      .finally(() => setLoading(false));
  }, []);

  const modulos = data?.modulos || [];
  const grupos = useMemo(() => ["todos", ...Array.from(new Set(modulos.map((m) => m.grupo)))], [modulos]);
  const filtrados = useMemo(() => {
    const termo = q.trim().toLowerCase();
    return modulos.filter((m) => {
      const bateGrupo = grupo === "todos" || m.grupo === grupo;
      const texto = `${m.nome} ${m.module_key} ${m.frontend_route} ${m.backend_prefixes.join(" ")}`.toLowerCase();
      return bateGrupo && (!termo || texto.includes(termo));
    });
  }, [modulos, q, grupo]);

  if (loading) return <div className="p-6 text-sm text-slate-500">Carregando mapa de módulos...</div>;
  if (erro) return <div className="p-6 text-sm text-red-700">{erro}</div>;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-primary-600">Administração</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950">Mapa de Módulos</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-500">
          Visão administrativa dos módulos críticos do EJC, com rotas, perfis, dependências, uso de IA e dados sensíveis.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        {Object.entries(data?.resumo || {}).map(([k, v]) => (
          <div key={k} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-xs uppercase tracking-wide text-slate-400">{k.replaceAll("_", " ")}</div>
            <div className="mt-1 text-2xl font-bold text-slate-950">{v}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:flex-row md:items-center">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por módulo, rota ou backend..."
          className="h-10 flex-1 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-primary-400"
        />
        <select
          value={grupo}
          onChange={(e) => setGrupo(e.target.value)}
          className="h-10 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-primary-400"
        >
          {grupos.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Módulo</th>
                <th className="px-4 py-3">Grupo</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Frontend</th>
                <th className="px-4 py-3">Backend</th>
                <th className="px-4 py-3">Perfis</th>
                <th className="px-4 py-3">Riscos</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtrados.map((m) => (
                <tr key={m.module_key} className="hover:bg-slate-50/70">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-950">{m.nome}</div>
                    <div className="text-xs text-slate-400">{m.module_key}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{m.grupo}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full border px-2 py-1 text-xs font-semibold ${statusClass[m.status] || statusClass.legado}`}>{m.status}</span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">{m.frontend_route}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {m.backend_prefixes.length ? m.backend_prefixes.map((p) => <div key={p} className="font-mono">{p}</div>) : <span className="text-slate-400">a mapear</span>}
                    <div className="mt-1 text-slate-400">endpoints: {m.qtd_endpoints_detectados ?? 0}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">{m.perfis.join(", ")}</td>
                  <td className="px-4 py-3 text-xs">
                    <div>{m.usa_ia ? "usa IA" : "sem IA"}</div>
                    <div>{m.dados_sensiveis ? "dados sensíveis" : "sem sensíveis"}</div>
                    {m.precisa_revisao && <div className="mt-1 font-semibold text-amber-700">revisar</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
