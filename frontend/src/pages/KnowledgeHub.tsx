import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BookOpen,
  Library,
  Brain,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Copy,
  Database,
  ExternalLink,
  FolderOpen,
  Quote,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner, fmtDate } from "../components/UI";
import { useAuth } from "../stores/auth";
import { toast } from "../components/Toast";
import { ConhecimentoStats } from "../components/Dashboards";
import { asList } from "../lib/list";

const CATEGORIAS = [
  {
    to: "/conhecimento",
    label: "Base de Conhecimento",
    desc: "Leis, súmulas e doutrina indexadas para RAG",
    icon: BookOpen,
  },
  {
    to: "/biblioteca",
    label: "Biblioteca de Estratégias",
    desc: "Teses e peças de referência do escritório",
    icon: Library,
  },
  {
    to: "/memoria",
    label: "Memória Institucional",
    desc: "Casos, resultados e lições aprendidas",
    icon: Brain,
  },
] as const;

// ── Tipos: espelham os campos REAIS das respostas dos endpoints ──────────────
// GET /rag/buscar → { query, modo, resultados: RagHit[] }
//   (branch semântica: chunk_id, doc_id, conteudo, titulo, categoria,
//    confianca, score; branch textual/RRF acrescenta fonte e rrf. doc_id
//    aponta para knowledge_docs — habilita o atalho de curadoria abaixo.
//    Pendência: "Ver documento" continua sem ação porque não existe endpoint
//    de conteúdo/download por doc — GET /rag/docs é só listagem de metadados.)
interface RagHit {
  chunk_id?: string;
  doc_id?: string | null;
  conteudo?: string;
  titulo?: string;
  categoria?: string;
  fonte?: string | null;
  confianca?: string | null;
  score?: number | null;
  rrf?: number | null;
}

// GET /teses → { total, page, per_page, items: TeseHit[] }
interface TeseHit {
  id: string;
  titulo: string;
  descricao?: string | null;
  fundamentacao?: string | null;
  jurisprudencia?: string | null;
  contra_argumento?: string | null;
  area_juridica?: string | null;
  tribunal?: string | null;
  magistrado?: string | null;
  tags?: string | null;
  observacoes?: string | null;
  tipo?: string | null;
  status?: string | null;
  vezes_usada?: number | null;
  vezes_venceu?: number | null;
  vezes_perdeu?: number | null;
  taxa_sucesso?: number | null;
  created_at?: string | null;
}

// GET /jurisprudencias → { total, page, per_page, items: JurisHit[] }
interface JurisHit {
  id: string;
  titulo: string;
  ementa?: string | null;
  fundamentacao?: string | null;
  tribunal?: string | null;
  relator?: string | null;
  numero_acordao?: string | null;
  data_julgamento?: string | null;
  fonte?: string | null;
  link_original?: string | null;
  area_juridica?: string | null;
  tags?: string | null;
  resultado?: string | null;
  favorito?: boolean | null;
  vezes_citada?: number | null;
  created_at?: string | null;
}

// GET /memoria-institucional → MemHit[] (array cru)
interface MemHit {
  id: string;
  case_id?: string | null;
  tipo?: string | null;
  titulo: string;
  conteudo?: string | null;
  resultado?: string | null;
  area_direito?: string | null;
  tags?: string[] | null;
  created_at?: string | null;
}

type Fonte = "rag" | "tese" | "juris" | "memoria";

const FONTE_META: Record<Fonte, { label: string; badge: string; dot: string }> =
  {
    rag: {
      label: "Base RAG",
      badge: "bg-ai-100 text-ai-700",
      dot: "bg-ai-500",
    },
    tese: {
      label: "Tese",
      badge: "bg-primary-100 text-primary-700",
      dot: "bg-primary-500",
    },
    juris: {
      label: "Jurisprudência",
      badge: "bg-green-100 text-green-700",
      dot: "bg-green-500",
    },
    memoria: {
      label: "Memória",
      badge: "bg-warn-100 text-warn-700",
      dot: "bg-warn-500",
    },
  };

// Resultado unificado das 4 fontes, com metadados normalizados para filtro/ordenação.
interface ResultadoUnificado {
  key: string;
  fonte: Fonte;
  // Fontes adicionais quando o MESMO item (mesmo título normalizado) veio de
  // mais de um índice — ex.: tese também ingerida na base RAG.
  fontesExtras: Fonte[];
  titulo: string;
  trecho: string;
  area?: string | null;
  tribunal?: string | null;
  data?: string | null;
  score?: number | null; // score REAL de busca (só o RAG devolve)
  relevancia: number; // relevância combinada (ver comentário em relevanciaDe)
  chunksAgrupados?: number; // RAG: nº de trechos do mesmo doc unificados
  rag?: RagHit;
  tese?: TeseHit;
  juris?: JurisHit;
  memoria?: MemHit;
}

const normTitulo = (t?: string | null) =>
  (t ?? "").trim().toLowerCase().replace(/\s+/g, " ");

// ── Critério de ordenação por relevância combinada ───────────────────────────
// Apenas o /rag/buscar devolve score real de busca (similaridade de cosseno
// pgvector 0–1, ou rank textual). Esse score é usado diretamente. As demais
// fontes NÃO retornam score de busca, então usamos proxies documentados a
// partir dos campos que suas respostas realmente trazem:
//   tese    → 0.35 + 0.5·taxa_sucesso + até +0.10 por uso (vezes_usada, cap 10)
//   juris   → 0.35 + 0.10 se favorito + até +0.10 por citações (cap 20)
//   memória → 0.30 fixo (o backend já ordena por recência; o sort estável do
//             Array.prototype.sort preserva essa ordem nos empates)
// Item presente em mais de um índice usa o MAIOR valor entre as fontes.
function relevanciaDe(r: Omit<ResultadoUnificado, "relevancia" | "key">) {
  const valores: number[] = [];
  if (r.rag?.score != null) valores.push(r.rag.score);
  if (r.tese) {
    valores.push(
      0.35 +
        0.5 * (r.tese.taxa_sucesso ?? 0) +
        Math.min(r.tese.vezes_usada ?? 0, 10) * 0.01,
    );
  }
  if (r.juris) {
    valores.push(
      0.35 +
        (r.juris.favorito ? 0.1 : 0) +
        Math.min(r.juris.vezes_citada ?? 0, 20) * 0.005,
    );
  }
  if (r.memoria) valores.push(0.3);
  return valores.length ? Math.max(...valores) : 0;
}

// Unifica as 4 respostas: agrupa chunks RAG do mesmo documento e funde itens
// com o mesmo título vindos de índices diferentes (dedup cross-fonte).
function unificar(
  rag: RagHit[],
  teses: TeseHit[],
  juris: JurisHit[],
  memoria: MemHit[],
): ResultadoUnificado[] {
  const out: ResultadoUnificado[] = [];
  const porTitulo = new Map<string, ResultadoUnificado>();

  const push = (r: Omit<ResultadoUnificado, "relevancia">) => {
    const item: ResultadoUnificado = { ...r, relevancia: relevanciaDe(r) };
    out.push(item);
    const nt = normTitulo(item.titulo);
    if (nt && !porTitulo.has(nt)) porTitulo.set(nt, item);
    return item;
  };

  teses.forEach((t) =>
    push({
      key: `tese:${t.id}`,
      fonte: "tese",
      fontesExtras: [],
      titulo: t.titulo,
      trecho: t.descricao ?? t.fundamentacao ?? "",
      area: t.area_juridica,
      tribunal: t.tribunal,
      data: t.created_at,
      tese: t,
    }),
  );
  juris.forEach((j) =>
    push({
      key: `juris:${j.id}`,
      fonte: "juris",
      fontesExtras: [],
      titulo: j.titulo,
      trecho: j.ementa ?? "",
      area: j.area_juridica,
      tribunal: j.tribunal,
      data: j.data_julgamento ?? j.created_at,
      juris: j,
    }),
  );
  memoria.forEach((m) =>
    push({
      key: `memoria:${m.id}`,
      fonte: "memoria",
      fontesExtras: [],
      titulo: m.titulo,
      trecho: m.conteudo ?? "",
      area: m.area_direito,
      data: m.created_at,
      memoria: m,
    }),
  );

  // RAG: a resposta é por CHUNK — vários trechos do mesmo documento vêm como
  // itens separados. Agrupa por título+categoria mantendo o melhor score.
  const docsRag = new Map<string, { hit: RagHit; chunks: number }>();
  rag.forEach((r) => {
    const k = `${normTitulo(r.titulo)}|${r.categoria ?? ""}`;
    const atual = docsRag.get(k);
    if (!atual) docsRag.set(k, { hit: r, chunks: 1 });
    else {
      atual.chunks += 1;
      if ((r.score ?? -1) > (atual.hit.score ?? -1)) atual.hit = r;
    }
  });

  docsRag.forEach(({ hit, chunks }) => {
    // Dedup cross-fonte: mesmo título já veio de tese/juris/memória → funde.
    const existente = porTitulo.get(normTitulo(hit.titulo));
    if (existente) {
      existente.fontesExtras.push("rag");
      existente.rag = hit;
      existente.score = hit.score ?? existente.score;
      existente.chunksAgrupados = chunks;
      existente.relevancia = relevanciaDe(existente);
      return;
    }
    push({
      key: `rag:${hit.chunk_id ?? normTitulo(hit.titulo)}`,
      fonte: "rag",
      fontesExtras: [],
      titulo: hit.titulo ?? "(sem título)",
      trecho: hit.conteudo ?? "",
      score: hit.score,
      chunksAgrupados: chunks > 1 ? chunks : undefined,
      rag: hit,
    });
  });

  return out.sort((a, b) => b.relevancia - a.relevancia);
}

// Citação formatada para a área de transferência, por tipo de fonte.
function citacaoDe(r: ResultadoUnificado): string {
  if (r.juris) {
    const j = r.juris;
    const partes = [
      j.titulo,
      j.tribunal,
      j.numero_acordao && `Acórdão ${j.numero_acordao}`,
      j.relator && `Rel. ${j.relator}`,
      j.data_julgamento && `j. ${fmtDate(j.data_julgamento)}`,
    ].filter(Boolean);
    return `${partes.join(", ")}.\n${j.ementa ?? ""}`.trim();
  }
  if (r.tese) {
    const t = r.tese;
    return [
      `${t.titulo}${t.area_juridica ? ` (${t.area_juridica})` : ""}`,
      t.descricao,
      t.fundamentacao && `Fundamentação: ${t.fundamentacao}`,
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (r.memoria) {
    const m = r.memoria;
    return [
      `${m.titulo}${m.tipo ? ` [${m.tipo}]` : ""}${m.resultado ? ` — resultado: ${m.resultado}` : ""}`,
      m.conteudo,
    ]
      .filter(Boolean)
      .join("\n");
  }
  const g = r.rag;
  return [
    `${g?.titulo ?? r.titulo}${g?.categoria ? ` (${g.categoria})` : ""}${g?.fonte ? ` — fonte: ${g.fonte}` : ""}`,
    g?.conteudo,
  ]
    .filter(Boolean)
    .join("\n");
}

async function copiar(texto: string, msg: string) {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success(msg);
  } catch {
    toast.error("Não foi possível copiar para a área de transferência");
  }
}

// ── Linha de metadado (só renderiza campos que existem na resposta) ──────────
function Meta({ label, value }: { label: string; value?: unknown }) {
  if (value == null || value === "") return null;
  return (
    <div className="text-xs">
      <span className="text-gray-400">{label}: </span>
      <span className="text-gray-700">{String(value)}</span>
    </div>
  );
}

// Mesmos perfis de ROLES.gestores (moduleRegistry) — donos da Curadoria RAG.
const ROLES_CURADORIA = ["superadmin", "admin", "socio"];

function ResultCard({ r }: { r: ResultadoUnificado }) {
  const [aberto, setAberto] = useState(false);
  const role = useAuth((s) => s.user?.role ?? "");
  const podeCurar = ROLES_CURADORIA.includes(role);
  const fontes: Fonte[] = [r.fonte, ...r.fontesExtras];

  // "Abrir origem": rotas existentes no app. Não há rota dedicada de
  // jurisprudência interna (só o link_original externo, quando cadastrado).
  const origem =
    r.fonte === "tese"
      ? { to: "/biblioteca", label: "Abrir Biblioteca de Teses" }
      : r.fonte === "memoria"
        ? { to: "/memoria", label: "Abrir Memória Institucional" }
        : r.fonte === "rag"
          ? { to: "/conhecimento", label: "Abrir Base de Conhecimento" }
          : null;

  return (
    <div className="card p-4">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        className="w-full text-left"
        aria-expanded={aberto}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5 mb-1">
              {fontes.map((f) => (
                <span
                  key={f}
                  className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${FONTE_META[f].badge}`}
                >
                  {FONTE_META[f].label}
                </span>
              ))}
              {r.chunksAgrupados && r.chunksAgrupados > 1 && (
                <span className="text-[10px] text-gray-400">
                  {r.chunksAgrupados} trechos unificados
                </span>
              )}
            </div>
            <p className="font-medium text-sm text-gray-800">{r.titulo}</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {[
                r.area,
                r.tribunal,
                r.data ? fmtDate(r.data) : null,
                r.tese?.taxa_sucesso != null
                  ? `${Math.round(r.tese.taxa_sucesso * 100)}% sucesso`
                  : null,
                r.juris?.resultado,
                r.memoria?.tipo,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            {!aberto && r.trecho && (
              <p className="text-xs text-gray-600 mt-1 line-clamp-2">
                {r.trecho}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {r.score != null && (
              <span
                className="text-xs text-gray-400"
                title="Score de similaridade da busca RAG"
              >
                {Math.round(r.score * 100)}%
              </span>
            )}
            {aberto ? (
              <ChevronUp className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-400" />
            )}
          </div>
        </div>
      </button>

      {aberto && (
        <div className="mt-3 border-t border-gray-100 pt-3 space-y-2">
          {/* Metadados reais da resposta — campos ausentes não são exibidos */}
          <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1">
            <Meta label="Área" value={r.area} />
            <Meta label="Tribunal" value={r.tribunal} />
            <Meta label="Categoria" value={r.rag?.categoria} />
            <Meta label="Fonte" value={r.rag?.fonte ?? r.juris?.fonte} />
            <Meta label="Confiança" value={r.rag?.confianca} />
            <Meta label="Nº do acórdão" value={r.juris?.numero_acordao} />
            <Meta label="Relator" value={r.juris?.relator} />
            <Meta label="Magistrado" value={r.tese?.magistrado} />
            <Meta
              label="Data de julgamento"
              value={
                r.juris?.data_julgamento
                  ? fmtDate(r.juris.data_julgamento)
                  : undefined
              }
            />
            <Meta
              label="Resultado"
              value={r.juris?.resultado ?? r.memoria?.resultado}
            />
            <Meta label="Tipo" value={r.tese?.tipo ?? r.memoria?.tipo} />
            <Meta label="Status" value={r.tese?.status} />
            <Meta label="Vezes usada" value={r.tese?.vezes_usada} />
            <Meta label="Vezes citada" value={r.juris?.vezes_citada} />
            <Meta
              label="Tags"
              value={
                Array.isArray(r.memoria?.tags)
                  ? r.memoria?.tags.join(", ")
                  : (r.tese?.tags ?? r.juris?.tags)
              }
            />
          </div>

          {/* Conteúdo completo disponível na resposta */}
          {(r.trecho || r.tese?.fundamentacao || r.juris?.fundamentacao) && (
            <div className="text-xs text-gray-700 whitespace-pre-wrap bg-gray-50 rounded p-2 max-h-64 overflow-y-auto">
              {r.trecho}
              {r.tese?.fundamentacao && (
                <>
                  {"\n\n"}Fundamentação: {r.tese.fundamentacao}
                </>
              )}
              {r.tese?.contra_argumento && (
                <>
                  {"\n\n"}Contra-argumento: {r.tese.contra_argumento}
                </>
              )}
              {r.juris?.fundamentacao && (
                <>
                  {"\n\n"}Fundamentação: {r.juris.fundamentacao}
                </>
              )}
            </div>
          )}

          {/* Ações — apenas as que têm endpoint/rota existente */}
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              className="btn-secondary text-xs inline-flex items-center gap-1"
              onClick={() => copiar(citacaoDe(r), "Citação copiada")}
            >
              <Quote className="h-3.5 w-3.5" /> Copiar citação
            </button>
            {r.trecho && (
              <button
                type="button"
                className="btn-secondary text-xs inline-flex items-center gap-1"
                onClick={() => copiar(r.trecho, "Trecho copiado")}
              >
                <Copy className="h-3.5 w-3.5" /> Copiar trecho
              </button>
            )}
            {origem && (
              <Link
                to={origem.to}
                className="btn-secondary text-xs inline-flex items-center gap-1"
              >
                <FolderOpen className="h-3.5 w-3.5" /> {origem.label}
              </Link>
            )}
            {/* doc_id (novo em /rag/buscar) → abre a Curadoria RAG já
                focada no documento. Não chama PATCH /ia-governanca/
                rag-curadoria/{doc_id} daqui: o endpoint exige o veredicto
                (confidence_level/rag_status), decisão que pertence à tela
                de curadoria (admin/sócio). Só gestores veem o atalho —
                /ia-governanca é ROLES.gestores no moduleRegistry e o
                RouteGuard redirecionaria os demais perfis. */}
            {r.rag?.doc_id && podeCurar && (
              <Link
                to={`/ia-governanca?tab=curadoria&doc_id=${r.rag.doc_id}`}
                className="btn-secondary text-xs inline-flex items-center gap-1"
              >
                <Database className="h-3.5 w-3.5" /> Enviar para curadoria
              </Link>
            )}
            {r.memoria?.case_id && (
              <Link
                to={`/casos/${r.memoria.case_id}`}
                className="btn-secondary text-xs inline-flex items-center gap-1"
              >
                <FolderOpen className="h-3.5 w-3.5" /> Abrir caso vinculado
              </Link>
            )}
            {r.juris?.link_original &&
              /^https?:\/\//i.test(r.juris.link_original) && (
                <a
                  href={r.juris.link_original}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-secondary text-xs inline-flex items-center gap-1"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Fonte original
                </a>
              )}
          </div>
        </div>
      )}
    </div>
  );
}

// Busca unificada: agrega RAG semântico + teses + jurisprudência interna + memória institucional.
// Não cria tabela própria — é uma camada de busca sobre o conhecimento que já existe.
export default function KnowledgeHub() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [resultados, setResultados] = useState<ResultadoUnificado[]>([]);
  const [fonteFiltro, setFonteFiltro] = useState<Fonte | "todas">("todas");
  const [areaFiltro, setAreaFiltro] = useState("");
  const [tribunalFiltro, setTribunalFiltro] = useState("");

  const buscar = async () => {
    if (q.trim().length < 3) return;
    setLoading(true);
    setSearched(true);
    setFonteFiltro("todas");
    setAreaFiltro("");
    setTribunalFiltro("");
    const [rag, teses, juris, mem] = await Promise.allSettled([
      api.get(`/rag/buscar?q=${encodeURIComponent(q)}&limite=8`),
      api.get(`/teses?busca=${encodeURIComponent(q)}&per_page=8`),
      api.get(`/jurisprudencias?busca=${encodeURIComponent(q)}&per_page=8`),
      api.get(`/memoria-institucional?q=${encodeURIComponent(q)}&limit=8`),
    ]);
    // Nenhuma falha é silenciosa: cada fonte rejeitada gera um toast nominal.
    const falhas: Array<[PromiseSettledResult<unknown>, string]> = [
      [rag, "Base RAG"],
      [teses, "Banco de Teses"],
      [juris, "Jurisprudência interna"],
      [mem, "Memória institucional"],
    ];
    falhas.forEach(([res, nome]) => {
      if (res.status === "rejected") toast.error(`Falha na busca em ${nome}`);
    });
    setResultados(
      unificar(
        rag.status === "fulfilled"
          ? ((rag.value.data?.resultados ?? []) as RagHit[])
          : [],
        teses.status === "fulfilled" ? asList<TeseHit>(teses.value.data) : [],
        juris.status === "fulfilled" ? asList<JurisHit>(juris.value.data) : [],
        mem.status === "fulfilled" ? asList<MemHit>(mem.value.data) : [],
      ),
    );
    setLoading(false);
  };

  // Opções de filtro derivadas dos próprios resultados (client-side).
  const areas = useMemo(
    () =>
      Array.from(
        new Set(resultados.map((r) => r.area).filter((a): a is string => !!a)),
      ).sort(),
    [resultados],
  );
  const tribunais = useMemo(
    () =>
      Array.from(
        new Set(
          resultados.map((r) => r.tribunal).filter((t): t is string => !!t),
        ),
      ).sort(),
    [resultados],
  );

  const filtrados = useMemo(
    () =>
      resultados.filter((r) => {
        if (
          fonteFiltro !== "todas" &&
          r.fonte !== fonteFiltro &&
          !r.fontesExtras.includes(fonteFiltro)
        )
          return false;
        if (areaFiltro && r.area !== areaFiltro) return false;
        if (tribunalFiltro && r.tribunal !== tribunalFiltro) return false;
        return true;
      }),
    [resultados, fonteFiltro, areaFiltro, tribunalFiltro],
  );

  const contagem = (f: Fonte) =>
    resultados.filter((r) => r.fonte === f || r.fontesExtras.includes(f))
      .length;

  return (
    <div>
      <PageHeader
        title="Knowledge Hub"
        subtitle="Busca unificada em todo o conhecimento jurídico do escritório: base RAG, teses, jurisprudência interna e memória institucional"
      />

      <ConhecimentoStats />

      <div className="mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">
          Categorias
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CATEGORIAS.map(({ to, label, desc, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="card p-4 flex items-start gap-3 transition-all hover:border-primary-300 hover:shadow-sm"
            >
              <span className="rounded-xl bg-primary-50 p-2.5 text-primary-600 ring-1 ring-inset ring-primary-100">
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1 text-sm font-semibold text-slate-800">
                  {label}
                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="flex gap-2 mb-4 max-w-2xl">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && buscar()}
          placeholder="Buscar tese, jurisprudência, conceito… (mín. 3 letras)"
          className="input flex-1"
        />
        <button
          onClick={buscar}
          disabled={loading || q.trim().length < 3}
          className="btn-primary"
        >
          {loading ? "Buscando…" : "🔍 Buscar"}
        </button>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {!loading && searched && (
        <>
          {/* Filtros client-side: tipo de fonte + área/tribunal derivados das respostas */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            {(["todas", "rag", "tese", "juris", "memoria"] as const).map(
              (f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFonteFiltro(f)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    fonteFiltro === f
                      ? "bg-primary-600 text-white border-primary-600"
                      : "bg-white text-gray-600 border-gray-200 hover:border-primary-300"
                  }`}
                >
                  {f === "todas"
                    ? `Todas (${resultados.length})`
                    : `${FONTE_META[f].label} (${contagem(f)})`}
                </button>
              ),
            )}
            {areas.length > 0 && (
              <select
                value={areaFiltro}
                onChange={(e) => setAreaFiltro(e.target.value)}
                className="input !w-auto text-xs py-1"
                aria-label="Filtrar por área"
              >
                <option value="">Todas as áreas</option>
                {areas.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            )}
            {tribunais.length > 0 && (
              <select
                value={tribunalFiltro}
                onChange={(e) => setTribunalFiltro(e.target.value)}
                className="input !w-auto text-xs py-1"
                aria-label="Filtrar por tribunal"
              >
                <option value="">Todos os tribunais</option>
                {tribunais.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
          </div>

          <p className="text-sm text-gray-500 mb-3">
            {filtrados.length} resultado(s) para “{q}”
            {filtrados.length !== resultados.length &&
              ` (de ${resultados.length} no total)`}{" "}
            · ordenados por relevância combinada
          </p>

          {filtrados.length === 0 ? (
            <p className="text-gray-400 text-sm py-8 text-center">
              Nenhum resultado com os filtros atuais.
            </p>
          ) : (
            <div className="space-y-3 max-w-4xl">
              {filtrados.map((r) => (
                <ResultCard key={r.key} r={r} />
              ))}
            </div>
          )}
        </>
      )}

      {!searched && (
        <p className="text-center text-gray-400 text-sm py-12">
          Digite um termo para buscar em todas as fontes de conhecimento ao
          mesmo tempo.
        </p>
      )}
    </div>
  );
}
