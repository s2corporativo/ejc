// Tabela de casos + estados vazios/carregamento (auditoria §2.6 #10).
//
// Extraída do monólito Casos.tsx: componente PRESENTACIONAL. A página decide
// quando carregar/desarquivar/excluir — aqui só renderizamos e delegamos.
import { Link } from "react-router";
import { ArchiveRestore, Plus, Trash2 } from "lucide-react";
import type { Case, Paged } from "../../types";
import { areaLabel } from "../../lib/areas";
import {
  Button,
  Empty,
  EmptyState,
  SkeletonTable,
  StatusBadge,
  fmtDate,
} from "../../components/UI";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  EXTRAJ_TYPES,
} from "./casosCatalogo";

type ArquivoFiltro = "ativos" | "arquivados" | "todos";

export default function CasosTabela({
  erro,
  data,
  arquivoF,
  tipoF,
  podeExcluir,
  desarquivandoId,
  onRecarregar,
  onDesarquivar,
  onPedirExclusao,
}: {
  erro: boolean;
  data: Paged<Case> | null;
  arquivoF: ArquivoFiltro;
  tipoF: string;
  podeExcluir: boolean;
  desarquivandoId: string | null;
  onRecarregar: () => void;
  onDesarquivar: (id: string) => void;
  onPedirExclusao: (caso: Case) => void;
}) {
  return erro && !data ? (
    <EmptyState
      title="Falha ao carregar casos"
      message="Não foi possível carregar a lista. Verifique sua conexão e tente novamente."
      action={
        <Button variant="primary" onClick={onRecarregar}>
          Tentar novamente
        </Button>
      }
    />
  ) : !data ? (
    <SkeletonTable
      rows={6}
      cols={arquivoF === "arquivados" || podeExcluir ? 8 : 7}
    />
  ) : data.data.length === 0 ? (
    arquivoF === "arquivados" ? (
      <Empty
        titulo="Nenhum caso arquivado"
        descricao="Casos que você arquivar ficam guardados aqui — nenhum foi arquivado ainda."
      />
    ) : (
      <Empty
        titulo="Nenhum caso por aqui ainda"
        descricao="Os casos são o centro do EJC: cada um reúne prazos, documentos, peças e honorários. Comece abrindo o primeiro pelo cadastro guiado."
        acao={
          <Link to="/casos/novo">
            <Button variant="primary" icon={<Plus className="h-4 w-4" />}>
              Criar seu primeiro caso
            </Button>
          </Link>
        }
      />
    )
  ) : (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-primary-50/60 text-left dark:bg-white/[0.04]">
          <tr>
            <th className="px-4 py-2.5 label-caps">Nº interno</th>
            <th className="px-4 py-2.5 label-caps">Título</th>
            <th className="px-4 py-2.5 label-caps">Área</th>
            <th className="px-4 py-2.5 label-caps">Tipo</th>
            <th className="px-4 py-2.5 label-caps">Status</th>
            <th className="px-4 py-2.5 label-caps">Parte contrária</th>
            <th className="px-4 py-2.5 label-caps">Aberto em</th>
            {(arquivoF === "arquivados" || podeExcluir) && (
              <th className="px-4 py-2.5 label-caps">Ações</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-white/[0.06]">
          {(tipoF
            ? data.data.filter(
                (c: any) => (c.case_type || "judicial") === tipoF,
              )
            : data.data
          ).map((c) => (
            <tr
              key={c.id}
              className="transition-colors duration-150 hover:bg-primary-50/40 dark:hover:bg-white/[0.03]"
            >
              <td className="px-4 py-3 font-mono text-xs text-bronze-deep font-medium tracking-tight">
                <Link to={`/casos/${c.id}`}>{c.numero_interno}</Link>
              </td>
              <td
                className="px-4 py-3 text-navy-800"
                style={{ fontWeight: 400 }}
              >
                <Link to={`/casos/${c.id}`} className="hover:underline">
                  {c.titulo}
                </Link>
              </td>
              <td className="px-4 py-3 text-sm text-slate-500 capitalize">
                {areaLabel((c as any).area) || c.area}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${CASE_TYPE_COLOR[(c as any).case_type || "judicial"]}`}
                >
                  {CASE_TYPE_LABEL[(c as any).case_type || "judicial"]}
                  {(c as any).extrajudicial_type
                    ? ` · ${EXTRAJ_TYPES.find((e) => e.k === (c as any).extrajudicial_type)?.l || ""}`
                    : ""}
                </span>
              </td>
              <td className="px-4 py-3">
                <StatusBadge value={c.status} />
              </td>
              <td className="px-4 py-3 text-slate-500">
                {c.parte_contraria || "—"}
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">
                {fmtDate(c.created_at)}
              </td>
              {(arquivoF === "arquivados" || podeExcluir) && (
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    {arquivoF === "arquivados" && (
                      <button
                        onClick={() => onDesarquivar(c.id)}
                        disabled={desarquivandoId === c.id}
                        className="flex items-center gap-1 text-xs font-medium text-primary-700 hover:underline disabled:opacity-50"
                      >
                        <ArchiveRestore size={13} />
                        {desarquivandoId === c.id
                          ? "Desarquivando..."
                          : "Desarquivar"}
                      </button>
                    )}
                    {podeExcluir && (
                      <button
                        onClick={() => {
                          onPedirExclusao(c);
                        }}
                        title="Excluir caso (reversível pela Lixeira)"
                        className="flex min-h-[24px] items-center gap-1 text-xs font-medium text-danger-600 hover:underline"
                      >
                        <Trash2 size={13} /> Excluir
                      </button>
                    )}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
