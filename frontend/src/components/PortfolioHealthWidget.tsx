import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, RefreshCw } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Button, EmptyState, Modal, Spinner } from "./UI";
import PortfolioHealthList from "./PortfolioHealthList";
import {
  type PortfolioResponse,
  detalheErroCarteira,
} from "./portfolioHealthModel";

export default function PortfolioHealthWidget() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PortfolioResponse | null>(null);

  const riskCount = useMemo(
    () => (data?.totals.critical || 0) + (data?.totals.risk || 0),
    [data],
  );

  const carregar = async () => {
    setLoading(true);
    try {
      const response = await api.get("/dashboard/operational-health", {
        params: { stale_days: 30, limit: 50 },
      });
      setData(response.data as PortfolioResponse);
    } catch (error) {
      toast.error(detalheErroCarteira(error));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void carregar();
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-4 z-30 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-md transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2 sm:right-6"
        aria-label="Abrir saúde operacional da carteira"
      >
        <Activity className="h-4 w-4 text-primary-700" />
        Casos em atenção
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Saúde operacional da carteira"
        size="xl"
      >
        {loading ? (
          <div className="grid min-h-64 place-items-center">
            <Spinner />
          </div>
        ) : !data ? (
          <EmptyState
            icon={AlertTriangle}
            title="Diagnóstico indisponível"
            message="Nenhuma alteração foi feita. Tente atualizar novamente."
            action={
              <Button
                variant="secondary"
                onClick={() => void carregar()}
                icon={<RefreshCw className="h-4 w-4" />}
              >
                Atualizar
              </Button>
            }
          />
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div>
                <p className="font-semibold text-slate-950">
                  {riskCount} caso(s) em risco ou situação crítica
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  Escopo: {data.scope === "office" ? "escritório" : "casos atribuídos"} ·{" "}
                  {data.portfolio_total} caso(s) ativo(s) · inatividade após {data.stale_days} dias
                </p>
                {data.has_more && (
                  <p className="mt-1 text-xs text-amber-700">
                    Exibindo os {data.returned} casos mais críticos do escopo.
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void carregar()}
                icon={<RefreshCw className="h-4 w-4" />}
              >
                Atualizar
              </Button>
            </div>

            <PortfolioHealthList
              items={data.items}
              onNavigate={() => setOpen(false)}
            />
          </div>
        )}
      </Modal>
    </>
  );
}
