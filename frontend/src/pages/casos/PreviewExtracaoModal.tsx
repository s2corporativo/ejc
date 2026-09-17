// Modal de preview EXPLÍCITO da materialização da extração de IA (auditoria
// §2.6 #10). O usuário vê o que SERÁ aplicado (dry_run) e confirma ou pula.
import { Modal } from "../../components/UI";
import type { AplicarExtracaoResult, ExtracaoPayload } from "../../lib/api";

export type PreviewExtracao = {
  caseId: string;
  caseTitulo: string;
  extracao: ExtracaoPayload;
  result: AplicarExtracaoResult;
};

export default function PreviewExtracaoModal({
  preview,
  aplicando,
  onFechar,
  onAplicar,
  onAbrirSemAplicar,
}: {
  preview: PreviewExtracao | null;
  aplicando: boolean;
  onFechar: () => void;
  onAplicar: () => void;
  onAbrirSemAplicar: () => void;
}) {
  const nadaAplicavel = preview
    ? preview.result.partes_criadas +
        preview.result.areas_criadas +
        preview.result.prazos_criados +
        preview.result.campos_preenchidos.length ===
      0
    : true;
  return (
    <Modal
      open={!!preview}
      onClose={onFechar}
      title="Aplicar dados extraídos ao caso"
      footer={
        <>
          <button
            className="btn-ghost"
            disabled={aplicando}
            onClick={onAbrirSemAplicar}
          >
            Abrir jornada sem aplicar
          </button>
          <button
            className="btn-primary"
            disabled={aplicando || nadaAplicavel}
            onClick={onAplicar}
          >
            {aplicando
              ? "Preenchendo jornada..."
              : "Confirmar e preencher jornada"}
          </button>
        </>
      }
    >
      {preview && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            A IA extraiu dados do documento importado para o caso{" "}
            <span className="font-medium text-slate-900">
              {preview.caseTitulo}
            </span>
            . Confira o que será aplicado:
          </p>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <span className="text-slate-600">Partes a criar</span>
              <span className="font-semibold text-slate-900">
                {preview.result.partes_criadas}
              </span>
            </li>
            <li className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <span className="text-slate-600">Áreas a criar</span>
              <span className="font-semibold text-slate-900">
                {preview.result.areas_criadas}
              </span>
            </li>
            <li className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Campos a preencher</span>
                <span className="font-semibold text-slate-900">
                  {preview.result.campos_preenchidos.length}
                </span>
              </div>
              {preview.result.campos_preenchidos.length > 0 && (
                <p className="mt-1 text-xs text-slate-500">
                  {preview.result.campos_preenchidos.join(", ")}
                </p>
              )}
            </li>
            <li className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-amber-800">
                  Prazos a criar (rascunho, a confirmar)
                </span>
                <span className="font-semibold text-amber-900">
                  {preview.result.prazos_criados}
                </span>
              </div>
              {preview.result.prazos_criados > 0 && (
                <p className="mt-1 text-xs text-amber-700">
                  {preview.result.prazos_criados} prazo(s) serão criados como
                  rascunho e já passam a alertar — confira e confirme cada um na
                  tela de Prazos.
                </p>
              )}
            </li>
          </ul>
          {nadaAplicavel && (
            <p className="text-xs text-slate-500">
              Nada novo a aplicar — as partes/área/campos já estão preenchidos
              no caso.
            </p>
          )}
          {preview.result.aviso && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
              {preview.result.aviso}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
