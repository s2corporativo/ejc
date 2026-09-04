// ── Aba Teses (Fase 3 / QA): teses vinculadas + teses sugeridas consolidadas ──
// Substitui as duas abas anteriores "Teses" e "Teses sugeridas" (plano 2.5):
// motor de teses do escritório + banco de teses mais aderentes do caso,
// ranqueadas por desempenho histórico e com selo "Sugerida por IA" (rascunho —
// revisão humana obrigatória OAB).
import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Badge, Empty, Spinner } from "../../components/UI";
import { fmtTaxaSucesso } from "../../utils/formato";
import MotorTeses from "../../components/MotorTeses";
import type { Case } from "../../types";

interface TeseSugerida {
  id: string;
  titulo: string;
  tema?: string | null;
  resumo?: string | null;
  ramo?: string | null;
  tribunal?: string | null;
  taxa_sucesso?: number | null;
  vezes_venceu?: number | null;
  vezes_usada?: number | null;
}

interface TesesSugeridasResp {
  case_id: string;
  estrategia: string | null;
  area: string | null;
  palavras_chave: string[];
  total: number;
  teses: TeseSugerida[];
}

export default function TabTeses({ caso }: { caso: Case }) {
  const [loading, setLoading] = useState(true);
  const [resp, setResp] = useState<TesesSugeridasResp | null>(null);
  const caseId = caso.id;

  useEffect(() => {
    let ativo = true;
    setLoading(true);
    api
      .get<TesesSugeridasResp>(`/cases/${caseId}/teses-sugeridas`, {
        params: { k: 5 },
      })
      .then((r) => {
        if (ativo) setResp(r.data);
      })
      .catch(() => {
        if (ativo) {
          setResp(null);
          toast.error("Falha ao carregar teses sugeridas.");
        }
      })
      .finally(() => {
        if (ativo) setLoading(false);
      });
    return () => {
      ativo = false;
    };
  }, [caseId]);

  const teses = resp?.teses ?? [];
  return (
    <div className="space-y-6">
      {/* ── Teses do escritório (Motor de Teses + vinculadas) ───────────── */}
      <div className="space-y-4">
        <h2 className="font-semibold">Teses do caso</h2>
        <MotorTeses caso={caso} />
        <div className="space-y-2">
          <TesesVinculadas caseId={caseId} />
        </div>
      </div>

      {/* ── Teses sugeridas pela IA ─────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold">Sugeridas pela IA</h2>
          <span className="inline-flex items-center gap-1 rounded-full bg-ai-100 px-2 py-0.5 text-[11px] font-medium text-ai-700">
            <Sparkles className="h-3 w-3" />
            rascunho de apoio
          </span>
        </div>
        <p className="text-xs text-slate-400">
          Teses do Banco de Teses mais aderentes a este caso, ranqueadas por
          desempenho histórico. Rascunho de apoio — revisão humana obrigatória
          (OAB).
          {resp?.palavras_chave.length && (
            <> Palavras-chave: {resp.palavras_chave.join(", ")}.</>
          )}
        </p>
        {loading ? (
          <Spinner />
        ) : !resp || resp.total === 0 || teses.length === 0 ? (
          <Empty message="Nenhuma tese aderente encontrada" />
        ) : (
          <div className="space-y-3">
            {teses.map((t) => (
              <div key={t.id} className="card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="font-medium text-sm text-slate-800">
                      {t.titulo}
                    </h3>
                    {t.tema && (
                      <p className="text-xs text-slate-400 mt-0.5">{t.tema}</p>
                    )}
                  </div>
                  {t.ramo && <Badge tone="purple">{t.ramo}</Badge>}
                </div>
                {t.resumo && (
                  <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                    {t.resumo}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  <Badge tone="green">
                    Êxito {fmtTaxaSucesso(t.taxa_sucesso)}
                  </Badge>
                  <Badge tone="slate">{t.vezes_venceu ?? 0} vitória(s)</Badge>
                  {typeof t.vezes_usada === "number" && (
                    <Badge tone="slate">{t.vezes_usada} uso(s)</Badge>
                  )}
                  {t.tribunal && <Badge tone="slate">{t.tribunal}</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Teses vinculadas ao caso (extraída do antigo case "teses" do switch) ────
function TesesVinculadas({ caseId }: { caseId: string }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    api
      .get(`/teses/casos/${caseId}`)
      .then((r) => setItems(asList(r.data)))
      .catch(() => setItems([]));
  }, [caseId]);
  return (
    <div className="space-y-2">
      {items.length > 0 && (
        <h3 className="text-sm font-semibold text-slate-700">
          Teses Vinculadas ({items.length})
        </h3>
      )}
      {items.map((t, i) => (
        <div key={t.id || i} className="card p-3 text-sm">
          <span className="font-medium text-gray-800">
            {t.titulo || t.tese_id || t.id}
          </span>
          {t.descricao && (
            <p className="text-gray-500 text-xs mt-1">{t.descricao}</p>
          )}
        </div>
      ))}
      {items.length === 0 && (
        <p className="text-center py-6 text-gray-400 text-sm">
          Nenhuma tese vinculada a este caso
        </p>
      )}
    </div>
  );
}
