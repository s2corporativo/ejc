import { useEffect, useState } from "react";
import Markdown from "../components/Markdown";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "../components/UI";
import {
  AlertTriangle,
  Clock,
  Users,
  FileText,
  BarChart2,
  CheckSquare,
  ArrowLeft,
  Edit2,
  Save,
  X,
  TrendingUp,
  Briefcase,
  Shield,
  BookOpen,
} from "lucide-react";
import api from "../lib/api";

interface TimeEntry {
  usuario: string;
  horas: number;
  horas_faturavel: number;
  lancamentos: number;
}
interface Prazo {
  id: string;
  descricao: string;
  due_date: string | null;
  dias_restantes: number | null;
  urgente: boolean;
  tipo: string;
}
interface Checklist {
  id: string;
  nome: string;
  progresso: number;
  total_itens: number;
  itens_ok: number;
}
interface Doc {
  id: string;
  nome: string;
  tipo: string;
  created_at: string | null;
}
interface Movimento {
  id: string;
  tipo: string;
  descricao: string;
  data_movimento: string | null;
}
interface Tese {
  id: string;
  titulo: string;
  taxa_sucesso: number | null;
  resultado: string | null;
  observacoes: string | null;
}
interface TeamMember {
  id: string;
  nome: string;
  role: string;
  responsavel: boolean;
}

interface SalaData {
  caso: {
    id: string;
    numero_interno: string;
    titulo: string;
    area: string;
    status: string;
    fase: string;
    prioridade: string;
    numero_processo: string | null;
    tribunal: string | null;
    comarca: string | null;
    vara: string | null;
    parte_contraria: string | null;
    valor_causa: number | null;
    tese_principal: string | null;
    pontos_fortes: string | null;
    pontos_fracos: string | null;
    observacoes: string | null;
    resultado: string | null;
    licoes_aprendidas: string | null;
    created_at: string | null;
  };
  time: TeamMember[];
  prazos: Prazo[];
  horas: { por_pessoa: TimeEntry[]; total: number };
  checklists: Checklist[];
  documentos_recentes: Doc[];
  movimentos_recentes: Movimento[];
  teses_vinculadas: Tese[];
  risco: {
    indice: number | null;
    nivel: string | null;
    // jsonb no backend: pode vir string, lista, objeto {} ou null
    fatores: unknown;
  };
}

const PRIORIDADE_COLOR: Record<string, string> = {
  urgente: "bg-danger-100 text-danger-700 border border-danger-200",
  alta: "bg-orange-100 text-orange-700 border border-orange-200",
  media: "bg-yellow-100 text-yellow-700 border border-yellow-200",
  baixa: "bg-green-100 text-green-700 border border-green-200",
};

const RISCO_COLOR: Record<string, string> = {
  critico: "text-danger-600",
  alto: "text-orange-500",
  medio: "text-yellow-500",
  baixo: "text-green-500",
};

const SEM_FATORES = "Nenhum fator de risco cadastrado.";

/**
 * `cases.risco_fatores` é jsonb no backend: na prática costuma vir como objeto
 * vazio `{}`, mas também pode ser string, lista de strings ou lista de objetos.
 * Converte qualquer forma para texto Markdown, tratando vazio explicitamente
 * (evita renderizar "[object Object]" — BUG-02).
 */
function fatoresRiscoToText(fatores: unknown): string {
  if (fatores == null) return SEM_FATORES;

  if (typeof fatores === "string") {
    const t = fatores.trim();
    return t.length ? t : SEM_FATORES;
  }

  if (Array.isArray(fatores)) {
    if (fatores.length === 0) return SEM_FATORES;
    const linhas = fatores
      .map((item) => {
        if (item == null) return "";
        if (typeof item === "string") return item.trim();
        if (typeof item === "object") {
          const obj = item as Record<string, unknown>;
          const desc =
            typeof obj.descricao === "string"
              ? obj.descricao
              : typeof obj.fator === "string"
                ? obj.fator
                : JSON.stringify(obj);
          const nivel = typeof obj.nivel === "string" ? ` (${obj.nivel})` : "";
          return `${desc}${nivel}`.trim();
        }
        return String(item);
      })
      .filter((l) => l.length > 0)
      .map((l) => `- ${l}`);
    return linhas.length ? linhas.join("\n") : SEM_FATORES;
  }

  if (typeof fatores === "object") {
    // Objeto genérico (incluindo `{}`, que é truthy). Se vazio → sem fatores.
    const entries = Object.entries(fatores as Record<string, unknown>);
    if (entries.length === 0) return SEM_FATORES;
    return entries
      .map(
        ([k, v]) =>
          `- **${k}:** ${typeof v === "object" ? JSON.stringify(v) : String(v)}`,
      )
      .join("\n");
  }

  return String(fatores);
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-zinc-400 uppercase tracking-wider font-medium">
        {label}
      </span>
      <span className="text-xl font-light text-zinc-800">{value}</span>
      {sub && <span className="text-xs text-zinc-400">{sub}</span>}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-zinc-100 shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-zinc-50">
        <span className="text-bronze">{icon}</span>
        <h3 className="font-medium text-zinc-700 text-sm tracking-wide">
          {title}
        </h3>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

export default function SalaDeGuerra() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<SalaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [editando, setEditando] = useState(false);
  const [notas, setNotas] = useState({
    tese_principal: "",
    pontos_fortes: "",
    pontos_fracos: "",
    observacoes: "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    api
      .get(`/cases/${caseId}/sala-de-guerra`)
      .then((r: { data: SalaData }) => {
        setData(r.data);
        const c = r.data.caso;
        setNotas({
          tese_principal: c.tese_principal ?? "",
          pontos_fortes: c.pontos_fortes ?? "",
          pontos_fracos: c.pontos_fracos ?? "",
          observacoes: c.observacoes ?? "",
        });
      })
      .finally(() => setLoading(false));
  }, [caseId]);

  const salvarNotas = async () => {
    if (!caseId) return;
    setSaving(true);
    await api.patch(`/cases/${caseId}/sala-de-guerra/notas`, notas);
    setSaving(false);
    setEditando(false);
    // refresh
    const r = (await api.get(`/cases/${caseId}/sala-de-guerra`)) as {
      data: SalaData;
    };
    setData(r.data);
  };

  if (loading)
    return (
      <div className="flex items-center justify-center h-64 text-zinc-400 text-sm">
        Carregando Sala de Guerra…
      </div>
    );
  if (!data)
    return (
      <div className="flex items-center justify-center h-64 text-danger-400 text-sm">
        Caso não encontrado.
      </div>
    );

  const {
    caso,
    time,
    prazos,
    horas,
    checklists,
    documentos_recentes,
    movimentos_recentes,
    teses_vinculadas,
    risco,
  } = data;
  const prazosUrgentes = prazos.filter(
    (p) => p.urgente || (p.dias_restantes !== null && p.dias_restantes <= 7),
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="mt-1 h-auto w-auto p-1.5 text-zinc-400"
            aria-label="Voltar"
            onClick={() => navigate(-1)}
            icon={<ArrowLeft className="w-4 h-4" />}
          />
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-zinc-400 font-medium uppercase tracking-wider">
                Sala de Guerra
              </span>
              <span className="text-zinc-300">·</span>
              <span className="text-xs text-zinc-400">
                {caso.numero_interno}
              </span>
              {caso.prioridade && (
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${PRIORIDADE_COLOR[caso.prioridade] ?? "bg-zinc-100 text-zinc-500"}`}
                >
                  {caso.prioridade.toUpperCase()}
                </span>
              )}
            </div>
            <h1 className="text-2xl font-light text-zinc-800 mt-0.5">
              {caso.titulo}
            </h1>
            <p className="text-sm text-zinc-400 mt-0.5">
              {caso.parte_contraria && `vs. ${caso.parte_contraria} · `}
              {caso.tribunal ?? caso.comarca ?? ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {risco.nivel && (
            <span
              className={`text-sm font-medium ${RISCO_COLOR[risco.nivel] ?? "text-zinc-500"}`}
            >
              Risco {risco.nivel}{" "}
              {risco.indice !== null ? `(${risco.indice})` : ""}
            </span>
          )}
        </div>
      </div>

      {/* Alertas urgentes */}
      {prazosUrgentes.length > 0 && (
        <div className="bg-danger-50 border border-danger-200 rounded-xl px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-danger-500" />
            <span className="text-sm font-medium text-danger-700">
              Atenção — {prazosUrgentes.length} prazo(s) crítico(s)
            </span>
          </div>
          <div className="space-y-1.5">
            {prazosUrgentes.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-danger-700">{p.descricao}</span>
                <span
                  className={`text-xs font-medium ${p.urgente ? "text-danger-600" : "text-orange-500"}`}
                >
                  {p.urgente ? "VENCIDO" : `${p.dias_restantes}d`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat
            label="HH Total"
            value={`${horas.total}h`}
            sub={`${horas.por_pessoa.length} profissional(is)`}
          />
        </div>
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat
            label="Prazos abertos"
            value={prazos.length}
            sub={`${prazosUrgentes.length} urgentes`}
          />
        </div>
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat
            label="Valor da causa"
            value={
              caso.valor_causa
                ? `R$ ${caso.valor_causa.toLocaleString("pt-BR", { minimumFractionDigits: 0 })}`
                : "—"
            }
          />
        </div>
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat label="Fase" value={caso.fase ?? "—"} sub={caso.status} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column (2/3) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Notas estratégicas */}
          <Section
            title="Análise Estratégica"
            icon={<Shield className="w-4 h-4" />}
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs text-zinc-400">
                Tese, pontos fortes/fracos e observações
              </span>
              {!editando ? (
                <button
                  onClick={() => setEditando(true)}
                  className="flex items-center gap-1 text-xs text-bronze hover:underline"
                >
                  <Edit2 className="w-3 h-3" /> Editar
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => setEditando(false)}
                    className="flex items-center gap-1 text-xs text-zinc-400 hover:underline"
                  >
                    <X className="w-3 h-3" /> Cancelar
                  </button>
                  <button
                    onClick={salvarNotas}
                    disabled={saving}
                    className="flex items-center gap-1 text-xs text-bronze hover:underline"
                  >
                    <Save className="w-3 h-3" />{" "}
                    {saving ? "Salvando…" : "Salvar"}
                  </button>
                </div>
              )}
            </div>
            <div className="space-y-4">
              {(
                [
                  "tese_principal",
                  "pontos_fortes",
                  "pontos_fracos",
                  "observacoes",
                ] as const
              ).map((field) => (
                <div key={field}>
                  <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1.5">
                    {field === "tese_principal"
                      ? "Tese Principal"
                      : field === "pontos_fortes"
                        ? "Pontos Fortes"
                        : field === "pontos_fracos"
                          ? "Pontos Fracos"
                          : "Observações"}
                  </label>
                  {editando ? (
                    <textarea
                      className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                      rows={3}
                      value={notas[field]}
                      onChange={(e) =>
                        setNotas((n) => ({ ...n, [field]: e.target.value }))
                      }
                    />
                  ) : (
                    <p className="text-sm text-zinc-600 whitespace-pre-wrap">
                      {notas[field] || (
                        <span className="text-zinc-300 italic">
                          Não preenchido
                        </span>
                      )}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </Section>

          {/* Prazos */}
          <Section title="Prazos" icon={<Clock className="w-4 h-4" />}>
            {prazos.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhum prazo nos próximos 30 dias.
              </p>
            ) : (
              <div className="space-y-2">
                {prazos.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between py-2 border-b border-zinc-50 last:border-0"
                  >
                    <div>
                      <p className="text-sm text-zinc-700">{p.descricao}</p>
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {p.tipo} ·{" "}
                        {p.due_date
                          ? new Date(p.due_date).toLocaleDateString("pt-BR")
                          : "—"}
                      </p>
                    </div>
                    <span
                      className={`text-xs font-medium shrink-0 ml-4 ${p.urgente ? "text-danger-600" : p.dias_restantes !== null && p.dias_restantes <= 7 ? "text-orange-500" : "text-zinc-400"}`}
                    >
                      {p.urgente
                        ? "VENCIDO"
                        : p.dias_restantes !== null
                          ? `${p.dias_restantes}d`
                          : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Horas */}
          <Section
            title="Horas Trabalhadas"
            icon={<BarChart2 className="w-4 h-4" />}
          >
            {horas.por_pessoa.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhum lançamento de horas.
              </p>
            ) : (
              <div className="space-y-3">
                {horas.por_pessoa.map((p, i) => (
                  <div key={i}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-700">{p.usuario}</span>
                      <span className="text-sm font-light text-zinc-700">
                        {p.horas}h{" "}
                        <span className="text-xs text-zinc-400">
                          ({p.horas_faturavel}h fat.)
                        </span>
                      </span>
                    </div>
                    <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-bronze/60 rounded-full"
                        style={{
                          width: `${horas.total > 0 ? (p.horas / horas.total) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
                <div className="pt-2 border-t border-zinc-50 flex justify-between text-xs text-zinc-400">
                  <span>Total</span>
                  <span className="font-medium text-zinc-600">
                    {horas.total}h
                  </span>
                </div>
              </div>
            )}
          </Section>

          {/* Movimentos */}
          <Section
            title="Movimentos Recentes"
            icon={<Briefcase className="w-4 h-4" />}
          >
            {movimentos_recentes.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhum movimento registrado.
              </p>
            ) : (
              <div className="space-y-2">
                {movimentos_recentes.map((m) => (
                  <div
                    key={m.id}
                    className="py-2 border-b border-zinc-50 last:border-0"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-zinc-400 uppercase tracking-wide">
                        {m.tipo}
                      </span>
                      <span className="text-xs text-zinc-300">
                        {m.data_movimento
                          ? new Date(m.data_movimento).toLocaleDateString(
                              "pt-BR",
                            )
                          : ""}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-600 mt-0.5 line-clamp-2">
                      {m.descricao}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        {/* Right column (1/3) */}
        <div className="space-y-6">
          {/* Time */}
          <Section title="Time" icon={<Users className="w-4 h-4" />}>
            {time.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Sem advogados vinculados.
              </p>
            ) : (
              <div className="space-y-3">
                {time.map((m) => (
                  <div key={m.id} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-bronze/10 flex items-center justify-center text-bronze text-sm font-medium shrink-0">
                      {m.nome[0]?.toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm text-zinc-700">{m.nome}</p>
                      <p className="text-xs text-zinc-400">
                        {m.responsavel ? "Responsável" : "Auxiliar"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Checklists */}
          <Section
            title="Checklists"
            icon={<CheckSquare className="w-4 h-4" />}
          >
            {checklists.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">Nenhum checklist.</p>
            ) : (
              <div className="space-y-3">
                {checklists.map((ck) => (
                  <div key={ck.id}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-700 truncate mr-2">
                        {ck.nome}
                      </span>
                      <span className="text-xs text-zinc-400 shrink-0">
                        {ck.itens_ok}/{ck.total_itens}
                      </span>
                    </div>
                    <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-success-400 rounded-full transition-all"
                        style={{
                          width: `${ck.total_itens > 0 ? (ck.itens_ok / ck.total_itens) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Teses */}
          <Section
            title="Teses Vinculadas"
            icon={<BookOpen className="w-4 h-4" />}
          >
            {teses_vinculadas.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhuma tese vinculada.
              </p>
            ) : (
              <div className="space-y-3">
                {teses_vinculadas.map((t) => (
                  <div
                    key={t.id}
                    className="py-2 border-b border-zinc-50 last:border-0"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-zinc-700 line-clamp-2">
                        {t.titulo}
                      </p>
                      {t.taxa_sucesso !== null && (
                        <span className="text-xs font-medium text-success-600 shrink-0">
                          {t.taxa_sucesso}%
                        </span>
                      )}
                    </div>
                    {t.resultado && (
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {t.resultado}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Documentos */}
          <Section
            title="Documentos Recentes"
            icon={<FileText className="w-4 h-4" />}
          >
            {documentos_recentes.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">Nenhum documento.</p>
            ) : (
              <div className="space-y-2">
                {documentos_recentes.map((d) => (
                  <div
                    key={d.id}
                    className="flex items-center justify-between py-1.5 border-b border-zinc-50 last:border-0"
                  >
                    <div>
                      <p className="text-sm text-zinc-700 line-clamp-1">
                        {d.nome}
                      </p>
                      <p className="text-xs text-zinc-400">{d.tipo}</p>
                    </div>
                    <span className="text-xs text-zinc-300 shrink-0 ml-2">
                      {d.created_at
                        ? new Date(d.created_at).toLocaleDateString("pt-BR")
                        : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Risco */}
          <Section
            title="Fatores de Risco"
            icon={<TrendingUp className="w-4 h-4" />}
          >
            <Markdown
              source={fatoresRiscoToText(risco.fatores)}
              className="text-sm text-zinc-600"
            />
          </Section>
        </div>
      </div>
    </div>
  );
}
