// ── Visual Law: Matriz de risco 3×3 (Probabilidade × Impacto · CPC 25) ───────
// Consome GET /visual-law/casos/{id}/matriz-risco.
import { useEffect, useState } from "react";
import { Target } from "lucide-react";
import api from "../../lib/api";
import { toast } from "../Toast";
import { Alert, Badge, Empty, SectionCard, Spinner, cn, fmtMoney } from "../UI";
import type {
  MatrizRiscoResponse,
  NivelQuadrante,
  TratamentoContabil,
} from "../../types/visualLaw";

const NIVEL_CELULA: Record<string, { bg: string; texto: string }> = {
  baixo: { bg: "bg-green-100 hover:bg-green-200", texto: "text-green-800" },
  moderado: {
    bg: "bg-yellow-100 hover:bg-yellow-200",
    texto: "text-yellow-800",
  },
  elevado: {
    bg: "bg-orange-100 hover:bg-orange-200",
    texto: "text-orange-800",
  },
  critico: { bg: "bg-red-100 hover:bg-red-200", texto: "text-red-800" },
};

const NIVEL_BADGE: Record<NivelQuadrante, "green" | "amber" | "red"> = {
  baixo: "green",
  moderado: "amber",
  elevado: "amber",
  critico: "red",
};

const LABEL_QUADRANTE: Record<NivelQuadrante, string> = {
  baixo: "Risco baixo",
  moderado: "Risco moderado",
  elevado: "Risco elevado",
  critico: "Risco crítico",
};

const TRATAMENTO: Record<
  TratamentoContabil,
  { titulo: string; texto: string }
> = {
  provisionar: {
    titulo: "Provisionar",
    texto:
      "Perda provável: a empresa deve reconhecer uma provisão contábil para o valor estimado da causa (CPC 25).",
  },
  divulgar_em_nota: {
    titulo: "Divulgar em nota explicativa",
    texto:
      "Perda possível: não exige provisão, mas o passivo contingente deve ser divulgado em nota explicativa (CPC 25).",
  },
  nao_divulgar: {
    titulo: "Não divulgar",
    texto:
      "Perda remota: em regra não exige provisão nem divulgação em nota explicativa (CPC 25).",
  },
};

const FONTE_PROB: Record<string, string> = {
  risco_cadastrado: "Risco cadastrado manualmente no caso",
  score_saude: "Derivada do score de saúde do caso",
};

const EIXO_X = ["Remoto", "Possível", "Provável"];
const EIXO_Y = ["Baixo", "Médio", "Alto"];

export default function MatrizRisco({ caseId }: { caseId: string }) {
  const [data, setData] = useState<MatrizRiscoResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(false);
    api
      .get<MatrizRiscoResponse>(`/visual-law/casos/${caseId}/matriz-risco`)
      .then((r) => {
        if (ativo) setData(r.data);
      })
      .catch(() => {
        if (!ativo) return;
        setErro(true);
        toast.error("Falha ao carregar a matriz de risco");
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, [caseId]);

  if (carregando) return <Spinner />;
  if (erro || !data) {
    return <Empty message="Não foi possível carregar a matriz de risco" />;
  }

  const indefinido = data.impacto.nivel === "indefinido";
  const tratamento = TRATAMENTO[data.quadrante.tratamento_contabil];

  return (
    <SectionCard
      title="Matriz de risco (Probabilidade × Impacto)"
      subtitle="Classificação visual do contingenciamento conforme CPC 25"
    >
      {indefinido && (
        <Alert variant="warning" title="Impacto indefinido" className="mb-4">
          O caso não possui valor da causa cadastrado — sem ele o impacto
          financeiro não pode ser classificado. Cadastre o valor da causa no
          caso para posicioná-lo na matriz.
        </Alert>
      )}
      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Grade 3×3 */}
        <div className="min-w-0 flex-1">
          <div className="flex">
            {/* Rótulo do eixo Y */}
            <div className="flex items-center pr-2">
              <span className="-rotate-180 text-[11px] font-semibold uppercase tracking-wide text-slate-400 [writing-mode:vertical-rl]">
                Impacto →
              </span>
            </div>
            <div className="min-w-0 flex-1">
              {/* Linhas: impacto alto (y=2) no topo → baixo (y=0) embaixo */}
              {[2, 1, 0].map((y) => (
                <div key={y} className="mb-1 flex items-stretch gap-1">
                  <div className="flex w-12 shrink-0 items-center justify-end pr-1 text-[11px] font-medium text-slate-500 sm:w-14">
                    {EIXO_Y[y]}
                  </div>
                  {[0, 1, 2].map((x) => {
                    const celula = data.matriz[y]?.[x];
                    const cores = celula
                      ? (NIVEL_CELULA[celula.nivel] ?? NIVEL_CELULA.baixo)
                      : NIVEL_CELULA.baixo;
                    const marcado =
                      !indefinido &&
                      data.quadrante.x === x &&
                      data.quadrante.y === y;
                    return (
                      <div
                        key={x}
                        title={celula?.label ?? ""}
                        className={cn(
                          "relative flex min-h-16 flex-1 items-center justify-center rounded-lg p-1 text-center transition-colors sm:min-h-20",
                          cores.bg,
                          marcado &&
                            "ring-2 ring-slate-900 ring-offset-2 ring-offset-white",
                        )}
                      >
                        <span
                          className={cn(
                            "text-[11px] font-medium leading-tight sm:text-xs",
                            cores.texto,
                          )}
                        >
                          {celula?.label ?? "—"}
                        </span>
                        {marcado && (
                          <span className="absolute -right-1.5 -top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white shadow-md">
                            <Target className="h-3.5 w-3.5" />
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
              {/* Rótulos do eixo X */}
              <div className="flex gap-1">
                <div className="w-12 shrink-0 sm:w-14" />
                {EIXO_X.map((label) => (
                  <div
                    key={label}
                    className="flex-1 text-center text-[11px] font-medium text-slate-500"
                  >
                    {label}
                  </div>
                ))}
              </div>
              <p className="mt-1 text-center text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Probabilidade →
              </p>
            </div>
          </div>
          {/* Legenda */}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
            {(
              [
                ["baixo", "Baixo"],
                ["moderado", "Moderado"],
                ["elevado", "Elevado"],
                ["critico", "Crítico"],
              ] as const
            ).map(([nivel, label]) => (
              <span key={nivel} className="inline-flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-3 w-3 rounded",
                    NIVEL_CELULA[nivel].bg.split(" ")[0],
                  )}
                />
                {label}
              </span>
            ))}
            <span className="inline-flex items-center gap-1.5">
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-slate-900 text-white">
                <Target className="h-2.5 w-2.5" />
              </span>
              Posição deste caso
            </span>
          </div>
        </div>

        {/* Cartão lateral */}
        <div className="w-full shrink-0 space-y-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4 lg:w-72">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Classificação
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <Badge tone={NIVEL_BADGE[data.quadrante.nivel]}>
                {LABEL_QUADRANTE[data.quadrante.nivel]}
              </Badge>
            </div>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Valor da causa
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
              {data.impacto.valor_causa != null
                ? fmtMoney(data.impacto.valor_causa)
                : "Não cadastrado"}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Fonte da probabilidade
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {FONTE_PROB[data.probabilidade.fonte] ?? data.probabilidade.fonte}{" "}
              <span className="capitalize text-slate-400">
                ({data.probabilidade.nivel})
              </span>
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Tratamento contábil (CPC 25)
            </p>
            <p className="mt-1 text-sm font-semibold text-slate-800">
              {tratamento.titulo}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
              {tratamento.texto}
            </p>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
