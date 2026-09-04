import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { FileText, ShieldCheck, Sparkles } from "lucide-react";

import Pecas from "../Pecas";
import PecaGeneratorModal from "../../components/PecaGeneratorModal";
import { toast } from "../../components/Toast";

/**
 * Produção Jurídica contextual ao caso.
 *
 * A fila continua sendo o componente canônico `Pecas`: não há segundo CRUD,
 * segundo motor, segundo fluxo de aprovação ou regras duplicadas. Esta aba só
 * oferece uma porta de entrada contextual para o mesmo `PecaGeneratorModal`,
 * já com `caseId`, e depois remonta a fila para refletir a nova minuta.
 */
export default function TabPecas({ caseId }: { caseId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [geradorAberto, setGeradorAberto] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (searchParams.get("acao") !== "produzir") return;
    setGeradorAberto(true);
    setSearchParams({ tab: "pecas" }, { replace: true });
  }, [searchParams, setSearchParams]);

  return (
    <div className="space-y-5" data-case-context={caseId}>
      <section className="rounded-2xl border border-primary-100 bg-gradient-to-br from-primary-50/80 to-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary-700">
              <ShieldCheck className="h-4 w-4" /> Produção Jurídica
            </div>
            <h2 className="mt-2 text-xl font-semibold text-slate-950">
              Produzir peça a partir deste caso
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              O EJC mantém o contexto do caso durante a redação. Tipo, fatos,
              documentos, teses, fontes e validações continuam sujeitos aos
              mesmos gates de revisão humana, RBAC e auditoria do módulo Peças.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setGeradorAberto(true)}
            className="btn btn-primary inline-flex h-10 shrink-0 items-center justify-center gap-2 px-4"
          >
            <Sparkles className="h-4 w-4" /> Produzir peça
          </button>
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <Etapa icon={<FileText className="h-4 w-4" />} titulo="1. Preparar" texto="Tipo, fatos, pedidos e contexto" />
          <Etapa icon={<Sparkles className="h-4 w-4" />} titulo="2. Redigir" texto="Minuta com controle de qualidade" />
          <Etapa icon={<ShieldCheck className="h-4 w-4" />} titulo="3. Revisar" texto="HITL, aprovação e protocolo" />
        </div>
      </section>

      <div>
        <div className="mb-3">
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
            Fila do caso
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Em elaboração, revisadas, aprovadas e protocoladas deste caso.
          </p>
        </div>
        <Pecas key={refreshKey} />
      </div>

      <PecaGeneratorModal
        open={geradorAberto}
        onClose={() => setGeradorAberto(false)}
        caseId={caseId}
        onNeedFicha={() => {
          setGeradorAberto(false);
          toast.info(
            "Confirme a ficha de triagem exibida na fila do caso antes de produzir a peça.",
          );
        }}
        onConcluido={() => setRefreshKey((atual) => atual + 1)}
      />
    </div>
  );
}

function Etapa({
  icon,
  titulo,
  texto,
}: {
  icon: ReactNode;
  titulo: string;
  texto: string;
}) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-slate-100 bg-white/80 p-3">
      <span className="mt-0.5 text-primary-700">{icon}</span>
      <span>
        <span className="block text-xs font-semibold text-slate-800">{titulo}</span>
        <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">{texto}</span>
      </span>
    </div>
  );
}
