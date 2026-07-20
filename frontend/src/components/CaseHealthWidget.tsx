import { useEffect, useState } from "react";
import { Activity, AlertTriangle, RefreshCw } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Button, EmptyState, Modal, Spinner } from "./UI";
import CaseHealthIndicators from "./CaseHealthIndicators";
import CaseHealthSummary from "./CaseHealthSummary";
import CaseTimelineRecent from "./CaseTimelineRecent";
import {
  type CaseHealth,
  type TimelineResponse,
  detalheErroSaude,
} from "./caseHealthModel";

export default function CaseHealthWidget({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<CaseHealth | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);

  const carregar = async () => {
    setLoading(true);
    try {
      const [healthResponse, timelineResponse] = await Promise.all([
        api.get(`/cases/${caseId}/operational-health`),
        api.get(`/cases/${caseId}/timeline`, {
          params: { page: 1, per_page: 15 },
        }),
      ]);
      setHealth(healthResponse.data as CaseHealth);
      setTimeline(timelineResponse.data as TimelineResponse);
    } catch (error) {
      toast.error(detalheErroSaude(error));
      setHealth(null);
      setTimeline(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void carregar();
  }, [open, caseId]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-4 z-30 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-md transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2 sm:bottom-6 sm:right-48"
        aria-label="Abrir saúde operacional do caso"
      >
        <Activity className="h-4 w-4 text-primary-700" />
        Saúde do caso
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Saúde operacional e linha do tempo"
        size="xl"
      >
        {loading ? (
          <div className="grid min-h-64 place-items-center">
            <Spinner />
          </div>
        ) : !health ? (
          <EmptyState
            icon={AlertTriangle}
            title="Diagnóstico indisponível"
            message="Tente atualizar novamente. Nenhuma alteração foi feita no caso."
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
          <div className="space-y-6">
            <CaseHealthSummary
              health={health}
              onReload={() => void carregar()}
            />
            <CaseHealthIndicators indicators={health.indicators} />
            <CaseTimelineRecent timeline={timeline} />
          </div>
        )}
      </Modal>
    </>
  );
}
