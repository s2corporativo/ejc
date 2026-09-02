import { AlertTriangle, FileText, FolderOpen, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { getDocumentStats, type DocumentStats } from "../../services/documents";

export default function DocumentWorkflowStats({ refreshKey = 0 }: { refreshKey?: number }) {
  const [stats, setStats] = useState<DocumentStats | null>(null);

  useEffect(() => {
    let active = true;
    getDocumentStats()
      .then((data) => {
        if (active) setStats(data);
      })
      .catch(() => {
        if (active) setStats(null);
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);

  if (!stats || stats.total === 0) return null;

  const cards = [
    {
      label: "Documentos",
      value: stats.total,
      icon: FolderOpen,
      hint: `${stats.este_mes} neste mês`,
    },
    {
      label: "Caixa de entrada",
      value: stats.inbox,
      icon: AlertTriangle,
      hint: stats.inbox ? "Precisam de ação" : "Tudo organizado",
    },
    {
      label: "Protegidos",
      value: stats.confidenciais,
      icon: ShieldCheck,
      hint: "Internos ou restritos",
    },
    {
      label: "Tipos",
      value: stats.tipos_distintos,
      icon: FileText,
      hint: "Categorias no acervo",
    },
  ];

  return (
    <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, icon: Icon, hint }) => (
        <div key={label} className="card flex items-center gap-3 p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            <Icon size={18} />
          </div>
          <div className="min-w-0">
            <div className="text-2xl font-semibold tracking-tight text-navy dark:text-white">
              {Number(value).toLocaleString("pt-BR")}
            </div>
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">{label}</div>
            <div className="truncate text-xs text-slate-400">{hint}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
