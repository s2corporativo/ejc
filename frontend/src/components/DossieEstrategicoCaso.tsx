// ── DossieEstrategicoCaso ─────────────────────────────────────────────────────
// Dossiê Estratégico como TELA ÚNICA: módulos determinísticos (linha do tempo,
// mapa probatório, riscos, teses) sempre disponíveis — o advogado PENSA antes
// de produzir — e, por fim, a análise estratégica gerada por IA (HITL).
import { useEffect, useState } from "react";
import {
  Sparkles,
  FileDown,
  CheckCircle2,
  AlertTriangle,
  Clock,
  CalendarClock,
  Scale,
  FileSearch,
  ShieldAlert,
  History,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "./Toast";
import { Badge, Button, Empty, Spinner, fmtDate } from "./UI";

// ── Tipos (contrato de GET /dossie/{caseId}/modulos) ─────────────────────────

interface FaseTimeline {
  fase: string;
  label: string;
  status: "concluida" | "atual" | "futura";
}
interface EventoTimeline {
  data: string;
  categoria: "movimento" | "prazo" | "documento" | "honorario";
  tipo: string;
  descricao: string;
}
interface ProximoPasso {
  titulo: string;
  origem: "prazo" | "estimativa";
  data_estimada: string | null;
  detalhe: string;
}
interface ProvaModulo {
  id: string;
  tipo: string;
  titulo: string;
  fato_probando: string | null;
  tese_id: string | null;
  tese_titulo: string | null;
}
interface FatorRisco {
  fator: string;
  impacto: number;
  detalhe: string;
  severidade: "alta" | "media" | "baixa";
}
interface TeseModulo {
  id: string;
  titulo: string;
  descricao: string;
  fundamentacao: string;
  contra_argumento: string;
  area_juridica: string;
  taxa_sucesso: number | null;
  resultado: string | null;
  vinculada_em: string | null;
}
// Sugestões de provas faltantes — contrato do POST /casos/{id}/provas/
// sugerir-faltantes (schemas/prova.py:SugestaoProvaFaltante). Buscadas SOB
// DEMANDA (custo de IA), nunca embutidas no payload determinístico do dossiê.
type ProvaFaltante = {
  titulo: string;
  por_que_importa?: string;
  como_obter?: string;
  criticidade?: "alta" | "media" | "baixa";
};

interface Modulos {
  case_id?: string;
  linha_do_tempo: {
    fase_atual: string;
    fases: FaseTimeline[];
    eventos: EventoTimeline[];
    total_eventos: number;
    proximos_passos: ProximoPasso[];
    estagnacao: { dias_parado: number; nivel: "ok" | "atencao" | "critico" };
  };
  mapa_probatorio: {
    total: number;
    provas: ProvaModulo[];
    por_tipo: Record<string, number>;
    sem_fato_probando: number;
  };
  riscos: {
    score: number;
    classificacao: "saudavel" | "atencao" | "risco" | "critico";
    dias_parado: number;
    fatores: FatorRisco[];
    saudavel: boolean;
  };
  teses: {
    principal: TeseModulo | null;
    subsidiarias: TeseModulo[];
    total: number;
  };
  gerado_em?: string;
}

interface DossieMeta {
  id: string;
  case_id: string;
  versao: number;
  titulo: string | null;
  status: "rascunho" | "aprovado" | "arquivado";
  modelo_ia: string | null;
  provedor_ia: string | null;
  tokens_usados: number | null;
  gerado_por: string | null;
  aprovado_por: string | null;
  aprovado_em: string | null;
  created_at: string | null;
}
interface Dossie extends DossieMeta {
  conteudo_texto: string | null;
}

// ── Paletas por classificação/severidade ─────────────────────────────────────

const RISCO_CORES: Record<
  Modulos["riscos"]["classificacao"],
  { texto: string; fundo: string; borda: string; label: string }
> = {
  saudavel: {
    texto: "text-green-700",
    fundo: "bg-green-50",
    borda: "border-green-200",
    label: "Saudável",
  },
  atencao: {
    texto: "text-amber-700",
    fundo: "bg-amber-50",
    borda: "border-amber-200",
    label: "Atenção",
  },
  risco: {
    texto: "text-orange-700",
    fundo: "bg-orange-50",
    borda: "border-orange-200",
    label: "Risco",
  },
  critico: {
    texto: "text-red-700",
    fundo: "bg-red-50",
    borda: "border-red-200",
    label: "Crítico",
  },
};

const SEVERIDADE_TONE: Record<
  FatorRisco["severidade"],
  "red" | "amber" | "slate"
> = { alta: "red", media: "amber", baixa: "slate" };

const CATEGORIA_EVENTO: Record<EventoTimeline["categoria"], string> = {
  movimento: "bg-primary-400",
  prazo: "bg-red-400",
  documento: "bg-slate-400",
  honorario: "bg-green-400",
};

const EVENTOS_VISIVEIS = 15;

function detalheErro(err: any, fallback: string): string {
  const d = err?.response?.data?.detail;
  return typeof d === "string" && d ? d : fallback;
}

// ── Componente ────────────────────────────────────────────────────────────────

export default function DossieEstrategicoCaso({ caseId }: { caseId: string }) {
  const [modulos, setModulos] = useState<Modulos | null>(null);
  const [loadingModulos, setLoadingModulos] = useState(true);
  const [dossie, setDossie] = useState<Dossie | null>(null);
  const [loadingDossie, setLoadingDossie] = useState(true);
  const [historico, setHistorico] = useState<DossieMeta[]>([]);
  const [gerando, setGerando] = useState(false);
  const [aprovando, setAprovando] = useState(false);
  const [faltantes, setFaltantes] = useState<ProvaFaltante[] | null>(null);
  const [avisoFaltantes, setAvisoFaltantes] = useState<string | null>(null);
  const [sugerindo, setSugerindo] = useState(false);

  // Integração com o mapa probatório: reusa o endpoint de sugestão de provas
  // faltantes (rota do módulo de provas) em vez de duplicar lógica de IA aqui.
  const sugerirFaltantes = async () => {
    if (sugerindo) return;
    setSugerindo(true);
    try {
      const { data } = await api.post(
        `/casos/${caseId}/provas/sugerir-faltantes`,
      );
      setFaltantes(asList<ProvaFaltante>(data));
      setAvisoFaltantes(data?.aviso ?? null);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha ao sugerir provas faltantes.",
      );
    } finally {
      setSugerindo(false);
    }
  };
  const [baixandoPdf, setBaixandoPdf] = useState(false);
  const [todosEventos, setTodosEventos] = useState(false);

  const carregarHistorico = () => {
    api
      .get(`/dossie/${caseId}/historico`)
      .then((r) => setHistorico(Array.isArray(r.data) ? r.data : []))
      .catch(() => setHistorico([]));
  };

  useEffect(() => {
    setLoadingModulos(true);
    setLoadingDossie(true);
    setTodosEventos(false);
    // Módulos determinísticos: SEMPRE disponíveis, mesmo sem dossiê gerado.
    api
      .get(`/dossie/${caseId}/modulos`)
      .then((r) => setModulos(r.data))
      .catch(() => {
        setModulos(null);
        toast.error("Não foi possível carregar os módulos do dossiê.");
      })
      .finally(() => setLoadingModulos(false));
    // Dossiê atual: 404 é estado normal ("nenhuma análise gerada ainda").
    api
      .get(`/dossie/${caseId}`)
      .then((r) => setDossie(r.data))
      .catch((err) => {
        setDossie(null);
        if (err?.response?.status !== 404) {
          toast.error(detalheErro(err, "Erro ao carregar o dossiê."));
        }
      })
      .finally(() => setLoadingDossie(false));
    carregarHistorico();
  }, [caseId]);

  const gerar = async () => {
    setGerando(true);
    try {
      const r = await api.post(`/dossie/${caseId}/gerar`, {});
      setDossie(r.data);
      if (r.data?.modulos) setModulos(r.data.modulos);
      carregarHistorico();
      toast.success(`Dossiê v${r.data?.versao ?? ""} gerado como rascunho.`);
    } catch (err: any) {
      toast.error(detalheErro(err, "Não foi possível gerar o dossiê."));
    } finally {
      setGerando(false);
    }
  };

  const aprovar = async () => {
    if (!dossie) return;
    setAprovando(true);
    try {
      const r = await api.patch(`/dossie/${caseId}/${dossie.id}/aprovar`);
      setDossie({ ...dossie, ...r.data });
      carregarHistorico();
      toast.success("Dossiê aprovado.");
    } catch (err: any) {
      toast.error(
        detalheErro(err, "Não foi possível aprovar (somente sócios)."),
      );
    } finally {
      setAprovando(false);
    }
  };

  const baixarPdf = async () => {
    if (!dossie) return;
    setBaixandoPdf(true);
    try {
      const r = await api.get(`/dossie/${caseId}/${dossie.id}/pdf`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dossie_v${dossie.versao}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Não foi possível baixar o PDF do dossiê.");
    } finally {
      setBaixandoPdf(false);
    }
  };

  if (loadingModulos && loadingDossie) return <Spinner />;

  const lt = modulos?.linha_do_tempo;
  const provas = modulos?.mapa_probatorio;
  const riscos = modulos?.riscos;
  const teses = modulos?.teses;
  const riscoCor = riscos ? RISCO_CORES[riscos.classificacao] : null;
  const eventos = lt?.eventos ?? [];
  const eventosVisiveis = todosEventos
    ? eventos
    : eventos.slice(0, EVENTOS_VISIVEIS);

  return (
    <div className="space-y-4">
      {/* ── Cabeçalho ─────────────────────────────────────────────────────── */}
      <div className="card p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Dossiê Estratégico
          </h2>
          <p className="text-xs text-slate-500">
            Pense antes de produzir: saúde do caso, linha do tempo, provas e
            teses — depois a análise IA.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dossie && (
            <Button
              variant="secondary"
              size="sm"
              icon={<FileDown size={14} />}
              onClick={baixarPdf}
              disabled={baixandoPdf}
            >
              {baixandoPdf ? "Baixando…" : "PDF"}
            </Button>
          )}
          <Button
            size="sm"
            icon={<Sparkles size={14} />}
            onClick={gerar}
            disabled={gerando}
          >
            {gerando ? "Gerando…" : "Gerar análise (IA)"}
          </Button>
        </div>
      </div>

      {loadingModulos ? (
        <Spinner />
      ) : !modulos ? (
        <div className="card p-4">
          <Empty message="Módulos do dossiê indisponíveis" />
        </div>
      ) : (
        <>
          {/* ── Saúde / Riscos ────────────────────────────────────────────── */}
          {riscos && riscoCor && (
            <div className={`card p-4 border ${riscoCor.borda}`}>
              <div className="flex items-center gap-2 mb-3">
                <ShieldAlert size={16} className="text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-800">
                  Saúde do caso
                </h3>
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <div
                  className={`flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-full border-4 ${riscoCor.borda} ${riscoCor.fundo}`}
                >
                  <span className={`text-2xl font-bold ${riscoCor.texto}`}>
                    {riscos.score}
                  </span>
                  <span className="text-[10px] text-slate-500">/100</span>
                </div>
                <div className="min-w-0 flex-1">
                  <span className={`text-sm font-semibold ${riscoCor.texto}`}>
                    {riscoCor.label}
                  </span>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {riscos.dias_parado} dia(s) sem movimentação
                  </p>
                  {riscos.fatores.length > 0 && (
                    <ul className="mt-2 space-y-1.5">
                      {riscos.fatores.map((f, i) => (
                        <li
                          key={i}
                          className="flex flex-wrap items-center gap-2 text-xs text-slate-600"
                        >
                          <Badge tone={SEVERIDADE_TONE[f.severidade]}>
                            {f.severidade}
                          </Badge>
                          <span className="font-medium text-slate-700">
                            {f.fator}
                          </span>
                          <span className="text-slate-400">
                            (impacto −{Math.abs(f.impacto)})
                          </span>
                          <span className="text-slate-500">{f.detalhe}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── Linha do tempo ────────────────────────────────────────────── */}
          {lt && (
            <div className="card p-4 space-y-4">
              <div className="flex items-center gap-2">
                <Clock size={16} className="text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-800">
                  Linha do tempo
                </h3>
                <span className="text-xs text-slate-400">
                  {lt.total_eventos} evento(s)
                </span>
              </div>

              {/* Fases (stepper em pills) */}
              <div className="flex flex-wrap items-center gap-1.5">
                {lt.fases.map((f) => (
                  <span
                    key={f.fase}
                    className={
                      f.status === "atual"
                        ? "inline-flex items-center gap-1 rounded-full bg-primary-600 px-3 py-1 text-[11px] font-semibold text-white"
                        : f.status === "concluida"
                          ? "inline-flex items-center gap-1 rounded-full bg-green-50 px-3 py-1 text-[11px] font-medium text-green-700 ring-1 ring-inset ring-green-200"
                          : "inline-flex items-center gap-1 rounded-full bg-slate-50 px-3 py-1 text-[11px] font-medium text-slate-400 ring-1 ring-inset ring-slate-200"
                    }
                  >
                    {f.status === "concluida" && <CheckCircle2 size={11} />}
                    {f.label}
                  </span>
                ))}
              </div>

              {/* Estagnação */}
              {lt.estagnacao.nivel !== "ok" && (
                <div
                  className={`flex items-center gap-2 rounded-xl border p-3 text-xs ${
                    lt.estagnacao.nivel === "critico"
                      ? "border-red-200 bg-red-50 text-red-700"
                      : "border-amber-200 bg-amber-50 text-amber-700"
                  }`}
                >
                  <AlertTriangle size={14} className="shrink-0" />
                  <span>
                    Caso parado há <strong>{lt.estagnacao.dias_parado}</strong>{" "}
                    dia(s) — nível{" "}
                    {lt.estagnacao.nivel === "critico"
                      ? "crítico"
                      : "de atenção"}
                    .
                  </span>
                </div>
              )}

              {/* Próximos passos */}
              {lt.proximos_passos.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
                    <CalendarClock size={13} /> Próximos passos
                  </h4>
                  <ul className="space-y-1.5">
                    {lt.proximos_passos.map((p, i) => (
                      <li
                        key={i}
                        className="flex flex-wrap items-center gap-2 text-xs text-slate-600"
                      >
                        <Badge tone={p.origem === "prazo" ? "red" : "slate"}>
                          {p.origem === "prazo" ? "prazo" : "estimativa"}
                        </Badge>
                        <span className="font-medium text-slate-700">
                          {p.titulo}
                        </span>
                        {p.data_estimada && (
                          <span className="text-slate-400">
                            {fmtDate(p.data_estimada)}
                          </span>
                        )}
                        {p.detalhe && (
                          <span className="text-slate-500">{p.detalhe}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Eventos */}
              {eventos.length === 0 ? (
                <p className="text-xs text-slate-400">
                  Nenhum evento registrado.
                </p>
              ) : (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
                    Eventos
                  </h4>
                  <ul className="space-y-1">
                    {eventosVisiveis.map((e, i) => (
                      <li
                        key={i}
                        className="flex items-center gap-2 text-xs text-slate-600"
                      >
                        <span
                          className={`h-2 w-2 shrink-0 rounded-full ${CATEGORIA_EVENTO[e.categoria] || "bg-slate-300"}`}
                          title={e.categoria}
                        />
                        <span className="w-20 shrink-0 text-slate-400">
                          {fmtDate(e.data)}
                        </span>
                        <span className="truncate">{e.descricao}</span>
                      </li>
                    ))}
                  </ul>
                  {eventos.length > EVENTOS_VISIVEIS && !todosEventos && (
                    <button
                      className="mt-2 text-xs font-medium text-primary-600 hover:underline"
                      onClick={() => setTodosEventos(true)}
                    >
                      Ver mais ({eventos.length - EVENTOS_VISIVEIS} restantes)
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Provas existentes ─────────────────────────────────────────── */}
          {provas && (
            <div className="card p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <FileSearch size={16} className="text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-800">
                  Mapa probatório
                </h3>
                <span className="text-xs text-slate-400">
                  {provas.total} prova(s)
                </span>
                <div className="ml-auto flex flex-wrap gap-1.5">
                  {Object.entries(provas.por_tipo).map(([tipo, n]) => (
                    <Badge key={tipo} tone="slate">
                      {tipo}: {n}
                    </Badge>
                  ))}
                </div>
              </div>
              {provas.sem_fato_probando > 0 && (
                <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
                  <AlertTriangle size={14} className="shrink-0" />
                  <span>
                    <strong>{provas.sem_fato_probando}</strong> prova(s) sem
                    fato probando definido — o que cada prova demonstra?
                  </span>
                </div>
              )}
              {provas.provas.length === 0 ? (
                <Empty message="Nenhuma prova cadastrada neste caso" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-slate-500">
                        <th className="py-1.5 pr-3 font-medium">Tipo</th>
                        <th className="py-1.5 pr-3 font-medium">Título</th>
                        <th className="py-1.5 pr-3 font-medium">
                          Fato probando
                        </th>
                        <th className="py-1.5 font-medium">Tese vinculada</th>
                      </tr>
                    </thead>
                    <tbody>
                      {provas.provas.map((p) => (
                        <tr
                          key={p.id}
                          className="border-b border-slate-100 last:border-0"
                        >
                          <td className="py-1.5 pr-3 text-slate-500 capitalize">
                            {p.tipo}
                          </td>
                          <td className="py-1.5 pr-3 font-medium text-slate-700">
                            {p.titulo}
                          </td>
                          <td className="py-1.5 pr-3 text-slate-600">
                            {p.fato_probando || (
                              <span className="text-amber-600">
                                não definido
                              </span>
                            )}
                          </td>
                          <td className="py-1.5 text-slate-600">
                            {p.tese_titulo || (
                              <span className="text-slate-300">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Provas faltantes (sugestão de IA, sob demanda) ────────────── */}
          <div className="card p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <AlertTriangle size={16} className="text-amber-500" />
                <h3 className="text-sm font-semibold text-slate-800">
                  Provas faltantes
                </h3>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={sugerirFaltantes}
                disabled={sugerindo}
              >
                {sugerindo ? "Analisando..." : "Sugerir com IA"}
              </Button>
            </div>
            {faltantes === null && !sugerindo && (
              <p className="text-xs text-slate-400">
                Peça à IA sugestões de provas típicas que ainda faltam no acervo
                deste caso (rascunho — revisão do advogado).
              </p>
            )}
            {avisoFaltantes && (
              <p className="text-xs text-amber-600">{avisoFaltantes}</p>
            )}
            {Array.isArray(faltantes) &&
              faltantes.length === 0 &&
              !avisoFaltantes && (
                <p className="text-xs text-slate-500">
                  Nenhuma sugestão — o acervo cobre as provas típicas da ação.
                </p>
              )}
            {Array.isArray(faltantes) && faltantes.length > 0 && (
              <ul className="space-y-1.5">
                {faltantes.map((item, i) => (
                  <li key={i} className="text-xs text-slate-600">
                    <span className="font-medium text-slate-700">
                      ⚠ {item.titulo}
                    </span>
                    {item.criticidade && (
                      <Badge
                        tone={
                          item.criticidade === "alta"
                            ? "red"
                            : item.criticidade === "media"
                              ? "amber"
                              : "slate"
                        }
                      >
                        {item.criticidade}
                      </Badge>
                    )}
                    {item.por_que_importa && (
                      <p className="text-slate-500 mt-0.5">
                        {item.por_que_importa}
                      </p>
                    )}
                    {item.como_obter && (
                      <p className="text-slate-400 mt-0.5">
                        Como obter: {item.como_obter}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* ── Teses ─────────────────────────────────────────────────────── */}
          {teses && (
            <div className="card p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Scale size={16} className="text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-800">Teses</h3>
                <span className="text-xs text-slate-400">
                  {teses.total} vinculada(s)
                </span>
              </div>
              {!teses.principal && teses.subsidiarias.length === 0 ? (
                <Empty message="Nenhuma tese vinculada a este caso" />
              ) : (
                <div className="space-y-2">
                  {teses.principal && (
                    <TeseCard tese={teses.principal} principal />
                  )}
                  {teses.subsidiarias.map((t) => (
                    <TeseCard key={t.id} tese={t} />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Análise estratégica (IA) ─────────────────────────────────────── */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Sparkles size={16} className="text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-800">
            Análise estratégica (IA)
          </h3>
          {dossie && (
            <>
              <Badge tone="slate">v{dossie.versao}</Badge>
              {dossie.status === "aprovado" ? (
                <Badge tone="green">
                  <CheckCircle2 size={11} className="mr-1" /> aprovado
                </Badge>
              ) : dossie.status === "arquivado" ? (
                <Badge tone="slate">arquivado</Badge>
              ) : (
                <Badge tone="amber">rascunho</Badge>
              )}
              {(dossie.provedor_ia || dossie.modelo_ia) && (
                <span className="text-xs text-slate-400">
                  {[dossie.provedor_ia, dossie.modelo_ia]
                    .filter(Boolean)
                    .join(" / ")}
                </span>
              )}
            </>
          )}
          {dossie && dossie.status === "rascunho" && (
            <Button
              variant="secondary"
              size="sm"
              className="ml-auto"
              icon={<CheckCircle2 size={14} />}
              onClick={aprovar}
              disabled={aprovando}
            >
              {aprovando ? "Aprovando…" : "Aprovar"}
            </Button>
          )}
        </div>

        {loadingDossie ? (
          <Spinner />
        ) : !dossie ? (
          <Empty message='Nenhuma análise gerada ainda — use "Gerar análise (IA)" acima' />
        ) : (
          <>
            {dossie.status !== "aprovado" && (
              <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
                <AlertTriangle size={14} className="shrink-0" />
                <span>
                  Rascunho gerado por IA —{" "}
                  <strong>revisão humana obrigatória</strong> antes de uso.
                </span>
              </div>
            )}
            {dossie.titulo && (
              <p className="text-sm font-medium text-slate-800">
                {dossie.titulo}
              </p>
            )}
            <div className="whitespace-pre-wrap text-sm text-slate-700 leading-relaxed">
              {dossie.conteudo_texto || "Sem conteúdo."}
            </div>
            <p className="text-[11px] text-slate-400">
              Gerado em {fmtDate(dossie.created_at)}
              {dossie.aprovado_em &&
                ` · aprovado em ${fmtDate(dossie.aprovado_em)}`}
            </p>
          </>
        )}
      </div>

      {/* ── Histórico de versões ─────────────────────────────────────────── */}
      <div className="card p-4 space-y-2">
        <div className="flex items-center gap-2">
          <History size={16} className="text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-800">
            Histórico de versões
          </h3>
        </div>
        {historico.length === 0 ? (
          <Empty message="Nenhum dossiê estratégico gerado" />
        ) : (
          <div className="space-y-2">
            {historico.map((d) => (
              <div
                key={d.id}
                className="card p-3 text-sm flex justify-between items-center"
              >
                <span className="font-medium text-gray-800">
                  {d.titulo ||
                    `Versão ${d.versao ?? ""}`.trim() ||
                    "Snapshot Estratégico"}
                </span>
                <span className="text-gray-400 text-xs">
                  {d.status === "aprovado" ? "✓ aprovado" : d.status} ·{" "}
                  {fmtDate(d.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Card de tese (principal em destaque; contra-argumento quando houver) ─────

function TeseCard({
  tese,
  principal,
}: {
  tese: TeseModulo;
  principal?: boolean;
}) {
  return (
    <div
      className={
        principal
          ? "rounded-xl border border-primary-200 bg-primary-50/50 p-3"
          : "rounded-xl border border-black/[0.05] dark:border-white/10 p-3"
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={principal ? "green" : "slate"}>
          {principal ? "principal" : "subsidiária"}
        </Badge>
        <span className="text-sm font-medium text-slate-800">
          {tese.titulo}
        </span>
        {tese.area_juridica && (
          <span className="text-xs text-slate-400">{tese.area_juridica}</span>
        )}
        {tese.taxa_sucesso != null && (
          <span className="ml-auto text-xs text-slate-500">
            êxito: {tese.taxa_sucesso}%
          </span>
        )}
      </div>
      {tese.descricao && (
        <p className="mt-1 text-xs text-slate-600">{tese.descricao}</p>
      )}
      {tese.fundamentacao && (
        <p className="mt-1 text-xs text-slate-500">
          <span className="font-medium text-slate-600">Fundamentação:</span>{" "}
          {tese.fundamentacao}
        </p>
      )}
      {tese.contra_argumento && (
        <p className="mt-1 text-xs text-red-600">
          <span className="font-medium">Contra-argumento:</span>{" "}
          {tese.contra_argumento}
        </p>
      )}
    </div>
  );
}
