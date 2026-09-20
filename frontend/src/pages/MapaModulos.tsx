import { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { getModuleCatalog } from "../config/moduleRegistry";

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
  tem_manual?: boolean | null;
  precisa_documentacao?: boolean | null;
  precisa_revisao?: boolean;
  origem?: "frontend" | "backend" | "ambos";
};

type Payload = {
  resumo?: Record<string, number>;
  modulos?: Modulo[];
  rotas_api_detectadas?: number;
  modo?: string;
  documentacao_modo?: "persistida" | "indisponivel";
};

const statusClass: Record<string, string> = {
  ativo: "bg-emerald-50 text-emerald-700 border-emerald-200",
  beta: "bg-amber-50 text-amber-700 border-amber-200",
  legado: "bg-slate-100 text-slate-700 border-slate-200",
  oculto: "bg-slate-100 text-slate-600 border-slate-200",
};

const statusMap = {
  active: "ativo",
  beta: "beta",
  legacy: "legado",
  hidden: "oculto",
} as const;

export default function MapaModulos() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [grupo, setGrupo] = useState("todos");

  useEffect(() => {
    api
      .get<Payload>("/system-modules/mapa")
      .then((response) => setData(response.data))
      .catch((error) =>
        setErro(
          error?.response?.data?.detail ||
            "Não foi possível carregar o inventário backend.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  const modulos = useMemo<Modulo[]>(() => {
    const backend = data?.modulos ?? [];
    const backendByKey = new Map(
      backend.map((module) => [module.module_key, module]),
    );
    const frontend = getModuleCatalog();

    const merged: Modulo[] = frontend.map((module) => {
      const backendModule = backendByKey.get(module.key);
      if (backendModule) backendByKey.delete(module.key);
      return {
        module_key: module.key,
        nome: module.label,
        grupo: module.group,
        frontend_route: module.path,
        backend_prefixes:
          backendModule?.backend_prefixes ?? module.backendPrefixes ?? [],
        status: statusMap[module.status ?? "active"],
        perfis: backendModule?.perfis ?? [...(module.roles ?? [])],
        dependencias: backendModule?.dependencias ?? module.dependencies ?? [],
        usa_ia: module.usesAI ?? backendModule?.usa_ia ?? false,
        dados_sensiveis:
          module.sensitive ?? backendModule?.dados_sensiveis ?? true,
        qtd_endpoints_detectados: backendModule?.qtd_endpoints_detectados ?? 0,
        tem_manual: backendModule?.tem_manual,
        precisa_documentacao: backendModule?.precisa_documentacao,
        precisa_revisao:
          Boolean(backendModule?.precisa_revisao) || !backendModule,
        origem: backendModule ? "ambos" : "frontend",
      };
    });

    for (const module of backendByKey.values()) {
      merged.push({
        ...module,
        precisa_revisao: true,
        origem: "backend",
      });
    }
    return merged;
  }, [data]);

  const grupos = useMemo(
    () => [
      "todos",
      ...Array.from(new Set(modulos.map((module) => module.grupo))),
    ],
    [modulos],
  );

  const filtrados = useMemo(() => {
    const termo = q.trim().toLowerCase();
    return modulos.filter((module) => {
      const bateGrupo = grupo === "todos" || module.grupo === grupo;
      const texto =
        `${module.nome} ${module.module_key} ${module.frontend_route} ${module.backend_prefixes.join(" ")}`.toLowerCase();
      return bateGrupo && (!termo || texto.includes(termo));
    });
  }, [modulos, q, grupo]);

  const resumo = useMemo(
    () => ({
      total: modulos.length,
      frontend: modulos.filter((module) => module.origem === "frontend").length,
      backend: modulos.filter((module) => module.origem === "backend").length,
      usam_ia: modulos.filter((module) => module.usa_ia).length,
      revisar: modulos.filter((module) => module.precisa_revisao).length,
      manual_pendente:
        data?.documentacao_modo === "indisponivel"
          ? null
          : modulos.filter((module) => module.precisa_documentacao === true)
              .length,
    }),
    [data?.documentacao_modo, modulos],
  );

  if (loading) return <Spinner />;
  if (erro)
    return (
      <div className="p-6 text-sm text-red-700">
        {erro} O manifesto frontend continua disponível em Configurações.
      </div>
    );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administração"
        title="Mapa de Módulos"
        subtitle="Cruzamento entre frontend, backend e ajuda persistida. Divergência funcional e documentação pendente são indicadores distintos."
      />

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
        {Object.entries(resumo).map(([key, value]) => (
          <div key={key} className="card p-4">
            <div className="text-xs uppercase tracking-wide text-slate-400">
              {key.split("_").join(" ")}
            </div>
            <div className="mt-1 text-2xl font-bold text-slate-950">
              {value ?? "—"}
            </div>
          </div>
        ))}
      </div>

      <div className="card flex flex-col gap-3 p-4 md:flex-row md:items-center">
        <input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Buscar por módulo, rota ou backend..."
          className="input h-10 flex-1"
        />
        <select
          value={grupo}
          onChange={(event) => setGrupo(event.target.value)}
          className="input h-10 w-auto"
        >
          {grupos.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </div>

      <div className="card overflow-hidden">
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
              {filtrados.map((module) => (
                <tr key={module.module_key} className="hover:bg-slate-50/70">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-950">
                      {module.nome}
                    </div>
                    <div className="text-xs text-slate-400">
                      {module.module_key} · {module.origem}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{module.grupo}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full border px-2 py-1 text-xs font-semibold ${statusClass[module.status] || statusClass.legado}`}
                    >
                      {module.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">
                    {module.frontend_route}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {module.backend_prefixes.length ? (
                      module.backend_prefixes.map((prefix) => (
                        <div key={prefix} className="font-mono">
                          {prefix}
                        </div>
                      ))
                    ) : (
                      <span className="text-slate-400">a mapear</span>
                    )}
                    <div className="mt-1 text-slate-400">
                      endpoints: {module.qtd_endpoints_detectados ?? 0}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {module.perfis.length
                      ? module.perfis.join(", ")
                      : "todos os perfis internos"}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <div>{module.usa_ia ? "usa IA" : "sem IA"}</div>
                    <div>
                      {module.dados_sensiveis
                        ? "dados sensíveis"
                        : "sem sensíveis"}
                    </div>
                    {module.precisa_revisao && (
                      <div className="mt-1 font-semibold text-amber-700">
                        revisar divergência
                      </div>
                    )}
                    {module.precisa_documentacao === true && (
                      <div className="mt-1 font-semibold text-sky-700">
                        manual pendente
                      </div>
                    )}
                    {module.precisa_documentacao === null && (
                      <div className="mt-1 font-semibold text-slate-500">
                        manual: estado indisponível
                      </div>
                    )}
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
