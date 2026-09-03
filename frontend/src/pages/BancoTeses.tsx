// ── Banco de Teses ────────────────────────────────────────────────────────────
// Primeira interface do Banco de Teses. O router `backend/app/routers/teses.py`
// tem 707 linhas — CRUD, ranking, busca avançada, vínculo com caso — e até aqui
// NENHUMA tela consumia qualquer uma dessas rotas: o frontend só chamava
// `/teses/motor/async` (o gerador). O catálogo existia e ninguém conseguia
// abrir.
//
// A tela faz duas coisas, e a segunda é a que interessa:
//   1. lista as teses do escritório, com desempenho histórico;
//   2. para a tese selecionada, roda a VARREDURA REVERSA
//      (`GET /teses/{id}/casos-candidatos`) e mostra em quais processos ela
//      pode caber — que é o que converte catálogo em ferramenta de trabalho.
//
// A sugestão é determinística (casamento de termos, sem IA) e NUNCA vincula
// sozinha: cada candidato traz os termos que casaram, para o advogado conferir
// antes de decidir.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Library, Radio, Search, Target } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "../components/Toast";
import { Badge, Card, Empty, PageHeader, Spinner } from "../components/UI";
import FichaVivaPanel from "../components/FichaVivaPanel";

type Tese = {
  id: string;
  titulo: string;
  descricao: string;
  area_juridica?: string | null;
  tribunal?: string | null;
  tags?: string | null;
  vezes_usada: number;
  vezes_venceu: number;
  taxa_sucesso?: number | null;
};

type Candidato = {
  case_id: string;
  numero_interno?: string | null;
  titulo?: string | null;
  area?: string | null;
  status?: string | null;
  score: number;
  termos_casados: string[];
  area_coincide: boolean;
};

type VarreduraResp = {
  tese_id: string;
  titulo: string;
  area_juridica?: string | null;
  termos: string[];
  casos_varridos?: number;
  teto_de_varredura_atingido?: boolean;
  total: number;
  candidatos: Candidato[];
  aviso?: string;
};

type PublicacaoImpacto = {
  alerta_id: string;
  fonte?: string | null;
  titulo?: string | null;
  link?: string | null;
  data_publicacao?: string | null;
  area_classificada?: string | null;
  score: number;
  termos_casados: string[];
  area_alinhada: boolean;
};

type TeseAfetada = {
  tese_id: string;
  titulo: string;
  area_juridica?: string | null;
  score_maximo: number;
  total_publicacoes: number;
  publicacoes: PublicacaoImpacto[];
};

type ImpactoResp = {
  periodo_dias: number;
  publicacoes_varridas: number;
  total: number;
  teses_afetadas: TeseAfetada[];
  aviso?: string;
};

function toneDoScore(score: number): "green" | "amber" | "slate" {
  if (score >= 55) return "green";
  if (score >= 40) return "amber";
  return "slate";
}

export default function BancoTeses() {
  const [teses, setTeses] = useState<Tese[]>([]);
  const [carregandoTeses, setCarregandoTeses] = useState(true);
  const [busca, setBusca] = useState("");
  const [selecionada, setSelecionada] = useState<Tese | null>(null);
  const [varredura, setVarredura] = useState<VarreduraResp | null>(null);
  const [varrendo, setVarrendo] = useState(false);
  const [impacto, setImpacto] = useState<ImpactoResp | null>(null);

  useEffect(() => {
    let ativo = true;
    api
      .get("/teses", { params: { status: "ativa", limit: 200 } })
      .then((r) => {
        if (ativo) setTeses(asList<Tese>(r.data));
      })
      .catch(() => {
        if (ativo) {
          setTeses([]);
          toast.error("Não foi possível carregar o Banco de Teses.");
        }
      })
      .finally(() => {
        if (ativo) setCarregandoTeses(false);
      });
    return () => {
      ativo = false;
    };
  }, []);

  // Radar regulatório → teses. Falha em silêncio de propósito: é um painel
  // acessório, e derrubar o Banco de Teses porque o Diário não respondeu seria
  // trocar uma ausência de informação por uma tela quebrada.
  useEffect(() => {
    let ativo = true;
    api
      .get<ImpactoResp>("/teses/impacto-regulatorio", {
        params: { dias: 7, limite: 10 },
      })
      .then((r) => {
        if (ativo) setImpacto(r.data);
      })
      .catch(() => {
        if (ativo) setImpacto(null);
      });
    return () => {
      ativo = false;
    };
  }, []);

  const varrer = useCallback(async (tese: Tese) => {
    setSelecionada(tese);
    setVarredura(null);
    setVarrendo(true);
    try {
      const r = await api.get<VarreduraResp>(
        `/teses/${tese.id}/casos-candidatos`,
        { params: { limite: 20 } },
      );
      setVarredura(r.data);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Não foi possível varrer os casos para esta tese.",
      );
    } finally {
      setVarrendo(false);
    }
  }, []);

  const filtradas = teses.filter((t) => {
    if (!busca.trim()) return true;
    const alvo =
      `${t.titulo} ${t.area_juridica ?? ""} ${t.tags ?? ""}`.toLowerCase();
    return alvo.includes(busca.trim().toLowerCase());
  });

  return (
    <div>
      <PageHeader
        eyebrow="Conhecimento do escritório"
        title="Banco de Teses"
        subtitle="Selecione uma tese para descobrir em quais processos ela pode caber."
      />

      {impacto && impacto.teses_afetadas.length > 0 && (
        <Card className="mb-4">
          <div className="mb-3 flex items-center gap-2">
            <Radio className="h-4 w-4 text-bronze" />
            <p className="eyebrow">Teses a reler pelo que saiu no Diário</p>
            <Badge tone="amber">{impacto.total}</Badge>
            <span className="text-[11px] text-slate-400">
              últimos {impacto.periodo_dias} dias ·{" "}
              {impacto.publicacoes_varridas} publicação(ões)
            </span>
          </div>

          <ul className="divide-y divide-bronze-pale/50">
            {impacto.teses_afetadas.map((t) => (
              <li key={t.tese_id} className="py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <button
                    onClick={() => {
                      const tese = teses.find((x) => x.id === t.tese_id);
                      if (tese) varrer(tese);
                    }}
                    className="min-w-0 flex-1 text-left text-sm font-medium text-navy-900 hover:text-bronze"
                  >
                    {t.titulo}
                  </button>
                  <Badge tone={toneDoScore(t.score_maximo)}>
                    {t.score_maximo}
                  </Badge>
                </div>
                <ul className="mt-1 space-y-1">
                  {t.publicacoes.map((p) => (
                    <li
                      key={p.alerta_id}
                      className="text-[11px] text-slate-500"
                    >
                      {p.link ? (
                        <a
                          href={p.link}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:text-bronze hover:underline"
                        >
                          {p.titulo}
                        </a>
                      ) : (
                        p.titulo
                      )}
                      {p.data_publicacao && ` · ${p.data_publicacao}`}
                      {p.area_alinhada && " · mesma área"}
                    </li>
                  ))}
                  {t.total_publicacoes > t.publicacoes.length && (
                    <li className="text-[11px] text-slate-400">
                      +{t.total_publicacoes - t.publicacoes.length} outra(s)
                      publicação(ões)
                    </li>
                  )}
                </ul>
              </li>
            ))}
          </ul>

          {impacto.aviso && (
            <p className="mt-3 border-t border-bronze-pale/50 pt-2 text-[11px] text-slate-500">
              {impacto.aviso}
            </p>
          )}
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Coluna 1: catálogo ─────────────────────────────────────────── */}
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Library className="h-4 w-4 text-bronze" />
            <p className="eyebrow">Teses ativas</p>
            {!carregandoTeses && <Badge tone="slate">{filtradas.length}</Badge>}
          </div>

          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              className="input py-1.5 pl-8 text-xs"
              placeholder="Filtrar por título, área ou tag"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              aria-label="Filtrar teses"
            />
          </div>

          {carregandoTeses && <Spinner />}

          {!carregandoTeses && filtradas.length === 0 && (
            <Empty
              titulo="Nenhuma tese encontrada"
              descricao={
                teses.length === 0
                  ? "O Banco de Teses está vazio. Teses cadastradas aqui passam a ser procuradas automaticamente nos processos do escritório."
                  : "Nenhuma tese casa com o filtro."
              }
            />
          )}

          <ul className="divide-y divide-bronze-pale/50">
            {filtradas.map((t) => {
              const ativa = selecionada?.id === t.id;
              return (
                <li key={t.id}>
                  <button
                    onClick={() => varrer(t)}
                    aria-pressed={ativa}
                    className={`w-full px-1 py-2.5 text-left transition-colors hover:bg-bronze-50/40 ${
                      ativa ? "bg-bronze-50/60" : ""
                    }`}
                  >
                    <span className="block truncate text-sm font-medium text-navy-900">
                      {t.titulo}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      {t.area_juridica && (
                        <span className="text-[10px] uppercase text-slate-400">
                          {t.area_juridica}
                        </span>
                      )}
                      {t.vezes_usada > 0 && (
                        <Badge tone="slate">
                          {t.vezes_venceu}/{t.vezes_usada} êxito
                        </Badge>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>

        {/* ── Coluna 2: varredura reversa ────────────────────────────────── */}
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Target className="h-4 w-4 text-bronze" />
            <p className="eyebrow">Onde esta tese pode caber</p>
          </div>

          {!selecionada && (
            <Empty
              titulo="Escolha uma tese"
              descricao="A varredura procura, nos processos que você pode ver, aqueles cujo texto casa com os termos da tese."
            />
          )}

          {selecionada && varrendo && <Spinner />}

          {selecionada && !varrendo && varredura && (
            <div>
              <p className="mb-2 text-xs text-slate-500">
                {varredura.casos_varridos ?? 0} caso(s) varrido(s) ·{" "}
                {varredura.total} candidato(s)
              </p>

              {varredura.termos.length > 0 && (
                <p className="mb-3 flex flex-wrap gap-1">
                  {varredura.termos.map((t) => (
                    <Badge key={t} tone="slate">
                      {t}
                    </Badge>
                  ))}
                </p>
              )}

              {varredura.teto_de_varredura_atingido && (
                <p className="mb-2 text-[11px] text-orange-600">
                  Teto de varredura atingido — há mais processos do que o limite
                  desta consulta, e podem existir candidatos fora da lista.
                </p>
              )}

              {varredura.candidatos.length === 0 && (
                <Empty
                  titulo="Nenhum processo aderente"
                  descricao="Nenhum caso visível para você casou termos suficientes desta tese."
                />
              )}

              <ul className="divide-y divide-bronze-pale/50">
                {varredura.candidatos.map((c) => (
                  <li key={c.case_id} className="py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        to={`/casos/${c.case_id}`}
                        className="min-w-0 flex-1 text-sm font-medium text-navy-900 hover:text-bronze"
                      >
                        {c.numero_interno ? `${c.numero_interno} — ` : ""}
                        {c.titulo}
                      </Link>
                      <Badge tone={toneDoScore(c.score)}>{c.score}</Badge>
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-1">
                      {c.area_coincide && (
                        <Badge tone="green">mesma área</Badge>
                      )}
                      {c.termos_casados.map((t) => (
                        <span
                          key={t}
                          className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
                        >
                          {t}
                        </span>
                      ))}
                    </p>
                  </li>
                ))}
              </ul>

              {varredura.aviso && (
                <p className="mt-3 border-t border-bronze-pale/50 pt-2 text-[11px] text-slate-500">
                  {varredura.aviso}
                </p>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* ── Ficha viva da tese selecionada ─────────────────────────────────
          Abaixo das colunas, em largura total: o histórico e o lastro são
          leitura em prosa, e espremê-los numa coluna ao lado da varredura
          faria o advogado ignorar exatamente o que precisa conferir antes de
          usar a tese numa peça. Só monta com tese selecionada — a busca é
          preguiçosa e não custa nada até haver o que mostrar. */}
      {selecionada && (
        <div className="mt-4">
          <FichaVivaPanel key={selecionada.id} teseId={selecionada.id} />
        </div>
      )}
    </div>
  );
}
