// Lista de peças: chips de fase, estados vazios, cartões mobile e tabela
// desktop (auditoria §2.6 #10).
//
// Extraído do monólito Pecas.tsx: componente PRESENTACIONAL — o estado
// (filtro, dados, ações) permanece na página Pecas.tsx.
import { Eye, Stamp, ShieldCheck } from "lucide-react";
import {
  Badge,
  Button,
  Empty,
  EmptyState,
  Spinner,
  fmtDate,
} from "../../components/UI";
import type { LegalDoc, Paged } from "../../types";
import {
  FASES,
  faseDaPeca,
  faseLabel,
  pecaValidacaoLabel,
  type FaseVisual,
} from "./pecasCatalogo";
import { casoLink, origemBadge } from "./pecasBadges";
import MaisAcoes from "./PecaMaisAcoes";

export default function PecasLista({
  data,
  erro,
  onRecarregar,
  filtroFase,
  onFiltroFase,
  casoFiltro,
  onRemoverFiltro,
  gerandoVL,
  onAbrir,
  onPdf,
  onDocx,
  onVisualLaw,
  onPrint,
  onJuris,
  onValidar,
  onAuditar,
  onRevisar,
  onFinalizar,
  onProtocolar,
}: {
  data: Paged<LegalDoc> | null;
  erro: boolean;
  onRecarregar: () => void;
  filtroFase: "todos" | FaseVisual;
  onFiltroFase: (f: "todos" | FaseVisual) => void;
  casoFiltro: string | null | undefined;
  onRemoverFiltro: () => void;
  gerandoVL: string | null;
  onAbrir: (id: string) => void;
  onPdf: (doc: LegalDoc) => void;
  onDocx: (doc: LegalDoc) => void;
  onVisualLaw: (doc: LegalDoc) => void;
  onPrint: (doc: LegalDoc) => void;
  onJuris: (doc: LegalDoc) => void;
  onValidar: (doc: LegalDoc) => void;
  onAuditar: (doc: LegalDoc) => void;
  onRevisar: (doc: LegalDoc) => void;
  onFinalizar: (doc: LegalDoc) => void;
  onProtocolar: (doc: LegalDoc) => void;
}) {
  const docs = data && Array.isArray(data.data) ? data.data : [];
  const docsVisiveis =
    filtroFase === "todos"
      ? docs
      : docs.filter((doc) => faseDaPeca(doc.status) === filtroFase);

  // Ação primária da linha conforme o status — mesma regra do monólito:
  // revisar (fluxo), finalizar (aprovada) e protocolar (final).
  const proximaAcao = (doc: LegalDoc) => {
    if (doc.status === "protocolada") return null;
    if (doc.status === "final") {
      return (
        <button
          className="btn-primary px-3 py-1.5 text-xs"
          onClick={() => onProtocolar(doc)}
        >
          <Stamp size={14} /> Protocolar
        </button>
      );
    }
    if (doc.status === "aprovada") {
      return (
        <button
          className="btn-primary px-3 py-1.5 text-xs"
          onClick={() => onFinalizar(doc)}
        >
          Finalizar
        </button>
      );
    }
    return (
      <button
        className="btn-primary px-3 py-1.5 text-xs"
        onClick={() => onRevisar(doc)}
      >
        <ShieldCheck size={14} /> Revisar peça
      </button>
    );
  };

  const renderMaisAcoes = (doc: LegalDoc) => (
    <MaisAcoes
      doc={doc}
      gerandoVL={gerandoVL === doc.id}
      onPdf={onPdf}
      onDocx={onDocx}
      onVisualLaw={onVisualLaw}
      onPrint={onPrint}
      onJuris={onJuris}
      onValidar={onValidar}
      onAuditar={onAuditar}
    />
  );

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onFiltroFase("todos")}
          className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
            filtroFase === "todos"
              ? "bg-navy text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Todas · {docs.length}
        </button>
        {FASES.map((fase) => {
          const total = docs.filter((doc) =>
            fase.statuses.includes(doc.status),
          ).length;
          return (
            <button
              key={fase.key}
              type="button"
              onClick={() => onFiltroFase(fase.key)}
              title={fase.descricao}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                filtroFase === fase.key
                  ? "bg-navy text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {fase.label} · {total}
            </button>
          );
        })}
      </div>

      {erro && !data ? (
        <EmptyState
          title="Falha ao carregar peças"
          message="Não foi possível carregar a lista. Verifique sua conexão e tente novamente."
          action={
            <Button variant="primary" onClick={onRecarregar}>
              Tentar novamente
            </Button>
          }
        />
      ) : !data ? (
        <Spinner />
      ) : docs.length === 0 ? (
        casoFiltro ? (
          <EmptyState
            title="Nenhuma peça neste caso"
            message="Você está vendo apenas as peças do caso filtrado."
            action={
              <Button variant="secondary" onClick={onRemoverFiltro}>
                Ver todas as peças
              </Button>
            }
          />
        ) : (
          <Empty message="Nenhuma peça cadastrada" />
        )
      ) : docsVisiveis.length === 0 ? (
        <EmptyState
          title="Nenhuma peça nesta etapa"
          message="Altere o filtro para visualizar outras fases do fluxo."
          action={
            <Button variant="secondary" onClick={() => onFiltroFase("todos")}>
              Ver todas
            </Button>
          }
        />
      ) : (
        <>
          <div className="space-y-2 md:hidden">
            {docsVisiveis.map((doc) => {
              const validacao = pecaValidacaoLabel(doc);
              return (
                <div key={doc.id} className="card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <button
                        type="button"
                        onClick={() => onAbrir(doc.id)}
                        className="text-left font-medium text-navy hover:underline"
                      >
                        {doc.titulo}
                      </button>
                      <div className="mt-1 text-xs text-slate-400">
                        {doc.tipo_peca.replace(/_/g, " ")} · v{doc.versao}.0 ·{" "}
                        {fmtDate(doc.created_at)}
                      </div>
                    </div>
                    <Badge tone="slate">{faseLabel(doc.status)}</Badge>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {origemBadge(doc)}
                    <Badge tone={validacao.tone}>{validacao.label}</Badge>
                    {casoLink(doc)}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      className="btn-ghost px-3 py-1.5 text-xs"
                      onClick={() => onAbrir(doc.id)}
                    >
                      <Eye size={14} /> Abrir
                    </button>
                    {proximaAcao(doc)}
                    {renderMaisAcoes(doc)}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="card hidden overflow-visible md:block">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3">Peça</th>
                  <th className="px-4 py-3">Fase</th>
                  <th className="px-4 py-3">Origem</th>
                  <th className="px-4 py-3">Revisão</th>
                  <th className="px-4 py-3">Caso</th>
                  <th className="px-4 py-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {docsVisiveis.map((doc) => {
                  const validacao = pecaValidacaoLabel(doc);
                  return (
                    <tr key={doc.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => onAbrir(doc.id)}
                          className="text-left font-medium text-navy hover:underline"
                        >
                          {doc.titulo}
                        </button>
                        <div className="mt-1 text-xs capitalize text-slate-400">
                          {doc.tipo_peca.replace(/_/g, " ")} · v{doc.versao}.0 ·{" "}
                          {fmtDate(doc.created_at)}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone="slate">{faseLabel(doc.status)}</Badge>
                      </td>
                      <td className="px-4 py-3">{origemBadge(doc)}</td>
                      <td className="px-4 py-3">
                        <Badge tone={validacao.tone}>{validacao.label}</Badge>
                      </td>
                      <td className="px-4 py-3">{casoLink(doc)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            className="btn-ghost px-3 py-1.5 text-xs"
                            onClick={() => onAbrir(doc.id)}
                          >
                            <Eye size={14} /> Abrir
                          </button>
                          {proximaAcao(doc)}
                          {renderMaisAcoes(doc)}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
