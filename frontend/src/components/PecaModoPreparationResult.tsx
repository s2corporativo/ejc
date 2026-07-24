import { Check, FileCheck2, ShieldCheck } from "lucide-react";

import type { PrepararModoPecaResponse } from "../types/pecaWorkflow";
import { Alert, Badge, Card } from "./UI";

interface Props {
  resultado: PrepararModoPecaResponse;
}

export default function PecaModoPreparationResult({ resultado }: Props) {
  const bloqueado = resultado.bloqueios.length > 0 || !resultado.pronto_para_redacao;

  return (
    <div className="space-y-4" aria-live="polite">
      {bloqueado ? (
        <Alert variant="danger" title="Redação bloqueada">
          {resultado.bloqueios.length ? (
            <ul className="list-disc space-y-1 pl-5">
              {resultado.bloqueios.map((bloqueio) => (
                <li key={bloqueio}>{bloqueio}</li>
              ))}
            </ul>
          ) : (
            <p>O backend ainda não autorizou o início da redação.</p>
          )}
        </Alert>
      ) : (
        <Alert variant="success" title="Modo preparado">
          Os requisitos determinísticos foram atendidos. A peça continua sujeita
          à revisão humana antes de qualquer uso ou protocolo.
        </Alert>
      )}

      {resultado.alertas.length > 0 && (
        <Alert variant="warning" title="Pontos de atenção">
          <ul className="list-disc space-y-1 pl-5">
            {resultado.alertas.map((alerta) => (
              <li key={alerta}>{alerta}</li>
            ))}
          </ul>
        </Alert>
      )}

      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Preparação
            </p>
            <p className="mt-1 text-sm font-semibold text-slate-900">
              {resultado.tipo_peca.replace(/_/g, " ")} · {resultado.area_direito}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="ai">Modo {resultado.modo}</Badge>
            {resultado.exige_aprovacao && (
              <Badge tone="amber" className="gap-1">
                <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                Aprovação obrigatória
              </Badge>
            )}
            <Badge tone="slate">
              {resultado.documentos_considerados.length} documento(s)
            </Badge>
          </div>
        </div>
      </Card>

      {resultado.etapas.length > 0 && (
        <section aria-labelledby="plano-agente-titulo">
          <h3
            id="plano-agente-titulo"
            className="mb-2 text-sm font-semibold text-slate-800"
          >
            Plano do Agente
          </h3>
          <ol className="space-y-2">
            {resultado.etapas.map((etapa) => (
              <li
                key={etapa.codigo}
                className="flex gap-3 rounded-xl border border-slate-200 bg-white p-3"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ai-50 text-xs font-semibold text-ai-700 ring-1 ring-ai-200">
                  {etapa.ordem}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-slate-800">
                      {etapa.titulo}
                    </p>
                    {etapa.exige_aprovacao && (
                      <Badge tone="amber">Exige aprovação</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {etapa.objetivo}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {resultado.checklist_revisao.length > 0 && (
        <details className="rounded-xl border border-slate-200 bg-white p-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-slate-800">
            <FileCheck2 className="h-4 w-4 text-ai-600" aria-hidden="true" />
            Checklist obrigatório de revisão
          </summary>
          <ul className="mt-3 space-y-2">
            {resultado.checklist_revisao.map((item) => (
              <li key={item} className="flex gap-2 text-sm text-slate-600">
                <Check
                  className="mt-0.5 h-4 w-4 shrink-0 text-slate-400"
                  aria-hidden="true"
                />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
