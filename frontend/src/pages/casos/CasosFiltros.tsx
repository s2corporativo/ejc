// Barra de filtros da lista de casos (auditoria §2.6 #10).
//
// Extraída do monólito Casos.tsx: componente PRESENTACIONAL — todo o estado
// continua na página (Casos.tsx), que passa valores + setters. A extração
// preserva marcação, acessibilidade (aria-labels medidos) e ordem dos filtros.
import { Archive, ArchiveRestore, List, Search } from "lucide-react";
import type { User } from "../../types";
import { CASE_STATUS, CASE_STATUS_LABEL } from "../../types/caseStatus";
import { CASE_TYPES } from "./casosCatalogo";

type ArquivoFiltro = "ativos" | "arquivados" | "todos";

export default function CasosFiltros({
  search,
  setSearch,
  areas,
  areaF,
  setAreaF,
  advogados,
  advogadoF,
  setAdvogadoF,
  user,
  statusF,
  setStatusF,
  tipoF,
  setTipoF,
  arquivoF,
  setArquivoF,
}: {
  search: string;
  setSearch: (v: string) => void;
  areas: { slug: string; nome: string }[];
  areaF: string;
  setAreaF: (v: string) => void;
  advogados: User[];
  advogadoF: string;
  setAdvogadoF: (v: string | ((prev: string) => string)) => void;
  user?: { id?: string };
  statusF: string;
  setStatusF: (v: string) => void;
  tipoF: string;
  setTipoF: (v: string) => void;
  arquivoF: ArquivoFiltro;
  setArquivoF: (v: ArquivoFiltro) => void;
}) {
  return (
    <div className="flex flex-wrap gap-3 mb-4">
      <div className="relative flex-1 min-w-[220px] max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
        <input
          className="input pl-9"
          placeholder="Buscar título, processo, parte..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {/* Sem rótulo acessível, este filtro era anunciado apenas pela
          opção selecionada ("Todas as áreas") — o leitor de tela dizia o
          VALOR sem dizer do que ele é valor. Medido em 22/08/2026. */}
      <select
        className="input w-44"
        aria-label="Filtrar por área do Direito"
        value={areaF}
        onChange={(e) => setAreaF(e.target.value)}
      >
        <option value="">Todas as áreas</option>
        {areas.map((a) => (
          <option key={a.slug} value={a.slug}>
            {a.nome}
          </option>
        ))}
      </select>
      {user?.id && (
        <button
          onClick={() =>
            setAdvogadoF((prev) => (prev === user.id ? "" : user.id!))
          }
          title="Ver somente os casos em que você é responsável ou auxiliar"
          className={`px-3 py-1.5 transition-colors duration-150 rounded-lg text-sm font-medium whitespace-nowrap ${
            advogadoF === user.id
              ? "bg-primary-600 text-white"
              : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"
          }`}
        >
          Meus casos
        </button>
      )}
      {/* `title` sozinho é nome acessível fraco — vira tooltip e nem
          todo leitor de tela o anuncia. `aria-label` é o mecanismo
          próprio; o `title` fica para o usuário de mouse. */}
      <select
        className="input w-52"
        value={advogadoF}
        onChange={(e) => setAdvogadoF(e.target.value)}
        aria-label="Filtrar por advogado responsável ou auxiliar"
        title="Filtrar por advogado responsável ou auxiliar"
      >
        <option value="">Todos os advogados</option>
        {advogados.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.email}
          </option>
        ))}
      </select>
      <select
        className="input w-44"
        value={statusF}
        onChange={(e) => setStatusF(e.target.value)}
        title="Filtrar por status do caso"
      >
        <option value="">Todos os status</option>
        {CASE_STATUS.map((s) => (
          <option key={s} value={s}>
            {CASE_STATUS_LABEL[s]}
          </option>
        ))}
      </select>
      <div className="flex gap-1">
        <button
          onClick={() => setTipoF("")}
          className={`px-3 py-1.5 transition-colors duration-150 rounded-lg text-sm font-medium ${tipoF === "" ? "bg-primary-900 text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
        >
          Todos
        </button>
        {CASE_TYPES.map((t) => (
          <button
            key={t.k}
            onClick={() => setTipoF(t.k)}
            className={`flex items-center gap-1 px-3 py-1.5 transition-colors duration-150 rounded-lg text-sm font-medium ${tipoF === t.k ? "bg-primary-900 text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            <t.icon size={13} /> {t.l}
          </button>
        ))}
      </div>
      {/* R2 — alterna entre casos ativos/arquivados/todos */}
      <div className="flex rounded-lg overflow-hidden bg-slate-900/[0.05] dark:bg-white/[0.07]">
        {(
          [
            ["ativos", "Ativos", List],
            ["arquivados", "Arquivados", Archive],
            ["todos", "Todos", ArchiveRestore],
          ] as [ArquivoFiltro, string, typeof List][]
        ).map(([k, label, Icon]) => (
          <button
            key={k}
            onClick={() => setArquivoF(k)}
            className={`flex items-center gap-1 px-3 py-1.5 transition-colors duration-150 text-sm font-medium ${arquivoF === k ? "bg-primary-900 text-white" : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"}`}
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>
    </div>
  );
}
