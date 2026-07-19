// ── Visual Law: Badges de alerta do caso ─────────────────────────────────────
// Linha compacta e reutilizável de badges de saúde do caso.
// Consome GET /visual-law/casos/{id}/alertas com falha silenciosa: se o
// endpoint falhar (ou ainda estiver carregando), não renderiza nada.
import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import api from "../../lib/api";
import { cn } from "../UI";
import type {
  AlertasResponse,
  ClassificacaoSaude,
  SeveridadeBadge,
} from "../../types/visualLaw";

const SEVERIDADE_CLASSES: Record<SeveridadeBadge, string> = {
  critica: "bg-red-100 text-red-800 ring-red-200",
  atencao: "bg-amber-100 text-amber-800 ring-amber-200",
  info: "bg-info-50 text-info-700 ring-info-200",
};

const SCORE_CLASSES: Record<ClassificacaoSaude, string> = {
  saudavel: "bg-green-100 text-green-800 ring-green-200",
  atencao: "bg-amber-100 text-amber-800 ring-amber-200",
  risco: "bg-orange-100 text-orange-800 ring-orange-200",
  critico: "bg-red-100 text-red-800 ring-red-200",
};

const SCORE_LABEL: Record<ClassificacaoSaude, string> = {
  saudavel: "Saudável",
  atencao: "Atenção",
  risco: "Risco",
  critico: "Crítico",
};

export default function BadgesAlerta({
  caseId,
  className,
}: {
  caseId: string;
  className?: string;
}) {
  const [data, setData] = useState<AlertasResponse | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    setData(null);
    setErro(false);
    api
      .get<AlertasResponse>(`/visual-law/casos/${caseId}/alertas`)
      .then((r) => {
        if (ativo) setData(r.data);
      })
      .catch(() => {
        // Não quebra a página do caso; sinaliza de forma discreta que os
        // alertas de saúde não puderam ser carregados (antes: falha 100% muda).
        if (ativo) setErro(true);
      });
    return () => {
      ativo = false;
    };
  }, [caseId]);

  if (!data) {
    if (!erro) return null; // ainda carregando — mantém silencioso
    return (
      <div className={cn("flex items-center", className)}>
        <span
          title="Não foi possível carregar os alertas de saúde do caso. Recarregue a página para tentar de novo."
          className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium text-gray-500 ring-1 ring-inset ring-gray-200"
        >
          <Activity className="h-3 w-3" />
          Alertas indisponíveis
        </span>
      </div>
    );
  }

  const scoreClasses =
    SCORE_CLASSES[data.classificacao] ?? SCORE_CLASSES.atencao;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <span
        title={`Score de saúde do caso: ${data.score}/100 (${SCORE_LABEL[data.classificacao] ?? data.classificacao}). Cálculo por regras internas do sistema — não é gerado por IA generativa.`}
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset",
          scoreClasses,
        )}
      >
        <Activity className="h-3 w-3" />
        Saúde {data.score} · {SCORE_LABEL[data.classificacao] ?? "—"}
      </span>
      {data.badges.map((badge) => (
        <span
          key={badge.codigo}
          title={badge.detalhe}
          className={cn(
            "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
            SEVERIDADE_CLASSES[badge.severidade] ?? SEVERIDADE_CLASSES.info,
            badge.severidade === "critica" && badge.pulsante && "animate-pulse",
          )}
        >
          {badge.label}
        </span>
      ))}
    </div>
  );
}
