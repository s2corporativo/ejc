// Modal "Revisão jurídica da peça" (auditoria §2.6 #10).
//
// Devolução vs aprovação+assinatura, bloqueio de citações com override
// justificado. Estado (revisao) e chamadas permanecem na página.
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { Modal } from "../../components/UI";
import type { LegalDoc } from "../../types";
import type { CitacaoBloqueio } from "./pecasCatalogo";

export type RevisaoPeca = {
  doc: LegalDoc;
  notas: string;
  erro?: string;
  bloqueio?: CitacaoBloqueio;
  justificativa?: string;
};

export default function RevisaoJuridicaModal({
  revisao,
  revisando,
  onChange,
  onFechar,
  onDevolver,
  onAprovar,
}: {
  revisao: RevisaoPeca | null;
  revisando: boolean;
  onChange: (r: RevisaoPeca) => void;
  onFechar: () => void;
  onDevolver: () => void;
  onAprovar: () => void;
}) {
  return (
    <Modal
      open={!!revisao}
      onClose={onFechar}
      title="Revisão jurídica da peça"
      wide
    >
      {revisao && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
            <strong className="text-slate-800">{revisao.doc.titulo}</strong>
            <p className="mt-1 text-xs">
              Revise o conteúdo, registre suas observações e escolha entre
              devolver para ajustes ou concluir a aprovação e assinatura.
            </p>
          </div>

          <textarea
            className="input min-h-[130px]"
            placeholder={
              revisao.doc.ai_generated
                ? "Observações da revisão (obrigatórias para aprovar peça de IA)"
                : "Observações da revisão"
            }
            value={revisao.notas}
            onChange={(e) =>
              onChange({ ...revisao, notas: e.target.value, erro: undefined })
            }
          />

          {revisao.bloqueio && (
            <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-3">
              <div className="flex items-center gap-2 text-sm font-bold text-amber-800">
                <ShieldAlert size={16} /> Citações não confirmadas
              </div>
              <p className="mt-1 text-xs text-amber-800">
                {revisao.bloqueio.mensagem ||
                  "O sistema encontrou citações que não pôde confirmar na base oficial."}
              </p>
              {!!revisao.bloqueio.bloqueantes?.length && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-800">
                  {revisao.bloqueio.bloqueantes.map((b, i) => (
                    <li key={i}>
                      <strong>{b.rotulo || "citação"}</strong>
                      {b.aviso ? ` — ${b.aviso}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              <textarea
                className="input mt-3 min-h-[80px] text-xs"
                placeholder="Justificativa para eventual override (obrigatória)"
                value={revisao.justificativa || ""}
                onChange={(e) =>
                  onChange({
                    ...revisao,
                    justificativa: e.target.value,
                    erro: undefined,
                  })
                }
              />
            </div>
          )}

          {revisao.erro && (
            <div className="rounded-lg border border-danger-300 bg-danger-50 px-3 py-2 text-xs text-danger-700">
              <strong>Não foi possível concluir:</strong> {revisao.erro}
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <button
              className="btn-ghost"
              disabled={revisando}
              onClick={onDevolver}
            >
              Devolver para revisão
            </button>
            <button
              className="btn-primary"
              disabled={
                revisando || (revisao.doc.ai_generated && !revisao.notas.trim())
              }
              onClick={onAprovar}
            >
              <ShieldCheck size={15} />
              {revisando ? "Processando..." : "Aprovar e assinar"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
