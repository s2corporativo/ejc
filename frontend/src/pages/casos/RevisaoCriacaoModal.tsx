// Modal "Revisar antes de criar o caso" (auditoria §2.6 #10).
//
// Passo de REVISÃO do fluxograma documental: o que será criado/aplicado,
// antes de qualquer escrita no backend. "Confirmar" dispara a criação
// (salvar) que permanece na página.
import { AlertTriangle } from "lucide-react";
import { Modal } from "../../components/UI";
import type { ResumoRevisao } from "./casosIntake";

export default function RevisaoCriacaoModal({
  revisao,
  salvando,
  onFechar,
  onConfirmar,
}: {
  revisao: ResumoRevisao | null;
  salvando: boolean;
  onFechar: () => void;
  onConfirmar: () => void;
}) {
  return (
    <Modal
      open={!!revisao}
      onClose={onFechar}
      title="Revisar antes de criar o caso"
      footer={
        <>
          <button className="btn-ghost" disabled={salvando} onClick={onFechar}>
            Voltar e editar
          </button>
          <button
            className="btn-primary"
            disabled={salvando}
            onClick={onConfirmar}
          >
            {salvando ? "Criando caso..." : "Confirmar criação"}
          </button>
        </>
      }
    >
      {revisao && (
        <div className="space-y-5 text-sm">
          <p className="text-xs leading-5 text-slate-500">
            Confira o que será criado. Nada é gravado até você confirmar — ao
            confirmar, o caso é criado, o documento é anexado e os dados
            extraídos abaixo são aplicados.
          </p>
          <section>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">
              Caso
            </p>
            <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
              {revisao.principais.map((it) => (
                <div
                  key={it.label}
                  className="flex justify-between gap-3 border-b border-slate-100 py-1"
                >
                  <dt className="text-slate-500">{it.label}</dt>
                  <dd className="text-right font-medium text-slate-800">
                    {it.valor}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          {revisao.aplicar.length > 0 && (
            <section>
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">
                Dados extraídos que serão aplicados
              </p>
              <ul className="space-y-1">
                {revisao.aplicar.map((it) => (
                  <li
                    key={it.label}
                    className="flex justify-between gap-3 border-b border-slate-100 py-1"
                  >
                    <span className="text-slate-500">{it.label}</span>
                    <span className="text-right font-medium text-slate-800">
                      {it.valor}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {revisao.ausentes.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <p className="text-xs font-semibold text-slate-700">
                Informação ausente — você pode completar agora ou depois
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {revisao.ausentes.join(" · ")}
              </p>
            </section>
          )}
          {revisao.alertas.length > 0 && (
            <section className="rounded-xl border border-warn-200 bg-warn-100 px-4 py-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-700" />
                <div className="space-y-1">
                  {revisao.alertas.map((a, i) => (
                    <p key={i} className="text-xs leading-5 text-warn-800">
                      {a}
                    </p>
                  ))}
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </Modal>
  );
}
