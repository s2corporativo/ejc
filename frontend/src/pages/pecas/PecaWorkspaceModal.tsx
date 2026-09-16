// Workspace Jurídico da peça (auditoria §2.6 #10).
//
// Extraído do monólito Pecas.tsx: texto editável + painel de inteligência
// jurídica. Estado e persistência (PATCH canônico) permanecem na página.
import { Link } from "react-router";
import {
  FolderOpen,
  PenLine,
  Save,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Stamp,
} from "lucide-react";
import { Badge, Modal } from "../../components/UI";
import Markdown from "../../components/Markdown";
import type { LegalDoc } from "../../types";
import { faseLabel } from "./pecasCatalogo";
import { origemBadge } from "./pecasBadges";

export default function PecaWorkspaceModal({
  view,
  editandoConteudo,
  conteudoEdicao,
  setConteudoEdicao,
  salvandoConteudo,
  onStartEdicao,
  onCancelEdicao,
  onSalvarConteudo,
  onFechar,
  onValidar,
  onJuris,
  onAuditar,
  onProtocolar,
  onFinalizar,
  onRevisar,
}: {
  view: LegalDoc | null;
  editandoConteudo: boolean;
  conteudoEdicao: string;
  setConteudoEdicao: (v: string) => void;
  salvandoConteudo: boolean;
  onStartEdicao: () => void;
  onCancelEdicao: () => void;
  onSalvarConteudo: () => void;
  onFechar: () => void;
  onValidar: (doc: LegalDoc) => void;
  onJuris: (doc: LegalDoc) => void;
  onAuditar: (doc: LegalDoc) => void;
  onProtocolar: (doc: LegalDoc) => void;
  onFinalizar: (doc: LegalDoc) => void;
  onRevisar: (doc: LegalDoc) => void;
}) {
  return (
    <Modal
      open={!!view}
      onClose={onFechar}
      title={
        view?.titulo
          ? `Workspace Jurídico · ${view.titulo}`
          : "Workspace Jurídico"
      }
      wide
    >
      {view && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="slate">{faseLabel(view.status)}</Badge>
                {origemBadge(view)}
                <Badge tone="slate">v{view.versao}.0</Badge>
                {view.codigo_peca && (
                  <Badge tone="ouro" className="font-mono">
                    {view.codigo_peca}
                  </Badge>
                )}
              </div>
              {view.status !== "final" && view.status !== "protocolada" && (
                <div className="flex items-center gap-2">
                  {editandoConteudo ? (
                    <>
                      <button
                        type="button"
                        className="btn-ghost px-3 py-1.5 text-xs"
                        disabled={salvandoConteudo}
                        onClick={onCancelEdicao}
                      >
                        Cancelar
                      </button>
                      <button
                        type="button"
                        className="btn-primary px-3 py-1.5 text-xs"
                        disabled={salvandoConteudo}
                        onClick={onSalvarConteudo}
                      >
                        <Save size={14} />
                        {salvandoConteudo
                          ? "Salvando..."
                          : "Salvar nova versão"}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn-ghost px-3 py-1.5 text-xs"
                      onClick={onStartEdicao}
                    >
                      <PenLine size={14} /> Editar texto
                    </button>
                  )}
                </div>
              )}
            </div>

            {editandoConteudo ? (
              <div className="space-y-2">
                <textarea
                  className="input min-h-[62vh] w-full font-mono text-sm leading-6"
                  value={conteudoEdicao}
                  onChange={(e) => setConteudoEdicao(e.target.value)}
                  aria-label="Conteúdo editável da peça"
                />
                <p className="text-xs text-amber-700">
                  Salvar cria nova versão lógica e exige nova validação/revisão
                  antes da aprovação.
                </p>
              </div>
            ) : (
              <div className="min-h-[55vh] rounded-xl border border-slate-100 bg-white p-5">
                <Markdown
                  source={view.conteudo}
                  className="text-sm text-slate-700"
                />
              </div>
            )}
          </div>

          <aside className="space-y-3 border-t border-slate-100 pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Inteligência jurídica
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Fontes, validação e crítica ficam separados do texto. A IA não
                altera a peça sem ação explícita do advogado.
              </p>
            </div>

            {view.validacao_juridica ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                <div className="font-medium text-slate-800">Validação</div>
                <div className="mt-1">
                  {view.validacao_juridica.status} · score{" "}
                  {view.validacao_juridica.score ?? "—"}/
                  {view.validacao_juridica.score_minimo ?? 75}
                </div>
                {view.validacao_juridica.motivo && (
                  <div className="mt-1">{view.validacao_juridica.motivo}</div>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
                Ainda sem validação jurídica registrada.
              </div>
            )}

            {view.notas_revisao && (
              <div className="rounded-lg border border-success-200 bg-success-50 p-3 text-xs text-slate-700">
                <div className="font-medium">Notas da revisão</div>
                <div className="mt-1">{view.notas_revisao}</div>
              </div>
            )}

            {view.case_id && (
              <Link
                to={`/casos/${view.case_id}`}
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs text-primary-700 hover:bg-slate-50"
              >
                <FolderOpen size={14} /> Abrir caso vinculado
              </Link>
            )}

            <button
              className="btn-ghost w-full justify-start text-xs"
              onClick={() => onValidar(view)}
            >
              <ShieldCheck size={14} /> Revisão jurídica
            </button>
            <button
              className="btn-ghost w-full justify-start text-xs"
              onClick={() => onJuris(view)}
            >
              <SearchCheck size={14} /> Jurisprudência e citações
            </button>
            <button
              className="btn-ghost w-full justify-start text-xs"
              onClick={() => onAuditar(view)}
            >
              <Sparkles size={14} /> Crítica da peça
            </button>

            <div className="border-t border-slate-100 pt-3">
              {view.status === "final" ? (
                <button
                  className="btn-primary w-full justify-center"
                  onClick={() => onProtocolar(view)}
                >
                  <Stamp size={14} /> Protocolar
                </button>
              ) : view.status === "aprovada" ? (
                <button
                  className="btn-primary w-full justify-center"
                  onClick={() => onFinalizar(view)}
                >
                  Finalizar peça
                </button>
              ) : view.status !== "protocolada" ? (
                <button
                  className="btn-primary w-full justify-center"
                  disabled={editandoConteudo}
                  title={
                    editandoConteudo
                      ? "Salve ou cancele a edição antes de revisar"
                      : undefined
                  }
                  onClick={() => onRevisar(view)}
                >
                  <ShieldCheck size={14} /> Revisar peça
                </button>
              ) : (
                <div className="rounded-lg bg-success-50 p-3 text-center text-xs font-medium text-success-700">
                  Protocolo registrado
                </div>
              )}
            </div>
          </aside>
        </div>
      )}
    </Modal>
  );
}
