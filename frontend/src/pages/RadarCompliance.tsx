import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ExternalLink,
  Leaf,
  Radar,
  ScrollText,
  ShieldAlert,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { Badge, Empty, Input, PageHeader, SectionCard, Spinner } from "../components/UI";

// ── Tipagem confirmada contra backend: app/routers/compliance.py::radar_compliance
type NivelRisco = "critico" | "alto" | "medio" | "baixo";
type FonteRadar = "diario_oficial" | "regulatorio" | "ambiental";

interface RadarItem {
  fonte: FonteRadar;
  id: string;
  titulo: string;
  resumo: string | null;
  data: string | null; // ISO date (YYYY-MM-DD) ou null
  nivel_risco: NivelRisco;
  link: string | null;
  case_id: string | null;
}

interface RadarResponse {
  total: number;
  fontes_com_erro: string[];
  filtros: { fonte: string | null; desde: string | null; limit: number };
  itens: RadarItem[];
}

// Badge de risco — reusa Badge/tone do design system; "medio" usa o dourado (ouro)
// da marca via override !important (mantém a paleta bronze/ouro/espresso existente).
const RISCO: Record<
  NivelRisco,
  { tone: "red" | "amber" | "slate"; extra: string; label: string }
> = {
  critico: { tone: "red", extra: "", label: "Critico" },
  alto: { tone: "amber", extra: "", label: "Alto" },
  medio: {
    tone: "amber",
    extra: "!bg-gold-50 !text-gold-700 !ring-gold-600/40",
    label: "Medio",
  },
  baixo: { tone: "slate", extra: "", label: "Baixo" },
};

function RiskBadge({ nivel }: { nivel: NivelRisco }) {
  const cfg = RISCO[nivel] ?? RISCO.baixo;
  return (
    <Badge tone={cfg.tone} className={cfg.extra}>
      {cfg.label}
    </Badge>
  );
}

const FONTE_META: Record<
  FonteRadar,
  { label: string; icon: typeof Radar }
> = {
  diario_oficial: { label: "Diario Oficial", icon: ScrollText },
  regulatorio: { label: "Regulatorio", icon: Radar },
  ambiental: { label: "Ambiental", icon: Leaf },
};

const FONTES: { value: "" | FonteRadar; label: string }[] = [
  { value: "", label: "Todas" },
  { value: "diario_oficial", label: "Diario Oficial" },
  { value: "regulatorio", label: "Regulatorio" },
  { value: "ambiental", label: "Ambiental" },
];

function formatData(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("pt-BR");
}

export default function RadarCompliance() {
  const [fonte, setFonte] = useState<"" | FonteRadar>("");
  const [desde, setDesde] = useState("");
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(false);

  const carregar = useCallback(() => {
    setLoading(true);
    setErro(false);
    const params: Record<string, string | number> = { limit: 50 };
    if (fonte) params.fonte = fonte;
    if (desde) params.desde = desde;
    api
      .get<RadarResponse>("/compliance/radar", { params })
      .then((r) => setData(r.data))
      .catch(() => {
        setData(null);
        setErro(true);
        toast.error("Nao foi possivel carregar o radar de compliance.");
      })
      .finally(() => setLoading(false));
  }, [fonte, desde]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const itens = data?.itens ?? [];

  return (
    <div>
      <PageHeader
        eyebrow="Inteligencia"
        title="Radar de Compliance"
        subtitle="Feed consolidado de Diario Oficial, monitoramento regulatorio e autos ambientais, priorizado por risco (critico -> baixo)."
      />

      {/* Filtros — chips por fonte + recorte por data */}
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-2">
          {FONTES.map((f) => {
            const ativo = fonte === f.value;
            return (
              <button
                key={f.value || "todas"}
                type="button"
                onClick={() => setFonte(f.value)}
                className={
                  "inline-flex items-center rounded-md px-3 py-1.5 text-xs font-semibold ring-1 ring-inset transition " +
                  (ativo
                    ? "bg-primary-600 text-white ring-primary-600"
                    : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50")
                }
              >
                {f.label}
              </button>
            );
          })}
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-600">
            A partir de
          </label>
          <Input
            type="date"
            value={desde}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setDesde(e.target.value)}
            className="w-44"
          />
        </div>
      </div>

      {data && data.fontes_com_erro.length > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-warn-200 bg-warn-50 px-3 py-2 text-xs font-medium text-warn-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Algumas fontes falharam e foram omitidas:{" "}
          {data.fontes_com_erro.join(", ")}.
        </div>
      )}

      {loading ? (
        <Spinner />
      ) : erro ? (
        <Empty message="Erro ao carregar o radar. Ajuste os filtros e tente novamente." icon={ShieldAlert} />
      ) : itens.length === 0 ? (
        <Empty message="Nenhum item de compliance no periodo selecionado." icon={ShieldAlert} />
      ) : (
        <SectionCard title={`Itens priorizados (${data?.total ?? itens.length})`}>
          <div className="space-y-2">
            {itens.map((it) => {
              const meta = FONTE_META[it.fonte];
              const Icon = meta?.icon ?? Radar;
              return (
                <div
                  key={`${it.fonte}:${it.id}`}
                  className="rounded-lg border border-slate-100 bg-white p-3 transition hover:border-slate-200 hover:shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-2.5">
                      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                        <Icon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {it.titulo}
                        </p>
                        {it.resumo && (
                          <p className="mt-0.5 text-xs text-slate-500">
                            {it.resumo}
                          </p>
                        )}
                      </div>
                    </div>
                    <RiskBadge nivel={it.nivel_risco} />
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-3 pl-[42px] text-[11px] text-slate-400">
                    <span className="uppercase tracking-wide">
                      {meta?.label ?? it.fonte}
                    </span>
                    {it.data && <span>· {formatData(it.data)}</span>}
                    {it.case_id && (
                      <Link
                        to={`/casos/${it.case_id}`}
                        className="font-medium text-primary-600 hover:underline"
                      >
                        · ver caso
                      </Link>
                    )}
                    {it.link && (
                      <a
                        href={it.link}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-primary-600 hover:underline"
                      >
                        abrir <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}
    </div>
  );
}
