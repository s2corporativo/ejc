import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Filter,
  Link2,
  RefreshCw,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import {
  Badge,
  Button,
  Card,
  PageHeader,
  Select,
  Spinner,
  StatCard,
} from "../components/UI";
import {
  listarTesesNacionais,
  obterTeseNacional,
  type NationalThesis,
  type ThesisSide,
} from "../lib/legalThesisBank";

const AREAS = [
  "",
  "Consumidor",
  "Bancário",
  "Juizados Especiais",
  "Civil",
  "Trabalhista",
  "Empresarial",
  "Tributário",
  "Administrativo/Licitações",
  "Ambiental",
  "Penal",
  "Digital/LGPD",
];

const SIDE_OPTIONS: Array<{ value: "todos" | ThesisSide; label: string }> = [
  { value: "todos", label: "Todas as posições" },
  { value: "ataque", label: "Teses de ataque" },
  { value: "defesa", label: "Teses de defesa" },
  { value: "ambos", label: "Aplicável a ambos" },
];

function formatDate(value?: string | null): string {
  if (!value) return "Sem revisão registrada";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(date);
}

function listText(items: unknown[], empty = "Não informado") {
  if (!items.length) return empty;
  return items
    .map((item) => (typeof item === "string" ? item : JSON.stringify(item)))
    .join(" • ");
}

function sideLabel(side: ThesisSide): string {
  return side === "ataque"
    ? "Ataque"
    : side === "defesa"
      ? "Defesa"
      : "Ambos";
}

function scoreTone(score: number): "green" | "blue" | "amber" | "slate" {
  if (score >= 80) return "green";
  if (score >= 60) return "blue";
  if (score >= 35) return "amber";
  return "slate";
}

function ThesisCard({
  thesis,
  selected,
  onOpen,
}: {
  thesis: NationalThesis;
  selected: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`group w-full rounded-2xl border p-5 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
        selected
          ? "border-primary-400 bg-primary-50/50 shadow-card-hover"
          : "border-slate-200 bg-white hover:-translate-y-0.5 hover:border-primary-300 hover:shadow-card-hover"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2">
          <Badge tone={thesis.lado === "defesa" ? "blue" : "ouro"}>
            {sideLabel(thesis.lado)}
          </Badge>
          <Badge tone={scoreTone(thesis.score_forca)}>
            Força {thesis.score_forca}/100
          </Badge>
        </div>
        <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-primary-600" />
      </div>
      <h2 className="mt-4 text-base font-bold leading-snug text-primary-950">
        {thesis.titulo}
      </h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        {thesis.tese_principal}
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] font-medium text-slate-500">
        <span>{thesis.area}</span>
        {thesis.subarea && <span>{thesis.subarea}</span>}
        <span className="inline-flex items-center gap-1">
          <Clock3 className="h-3.5 w-3.5" /> {formatDate(thesis.revisada_em)}
        </span>
      </div>
    </button>
  );
}

function DetailPanel({ thesis }: { thesis: NationalThesis }) {
  return (
    <Card className="sticky top-5 overflow-hidden border-primary-100 bg-white/95 shadow-card-hover">
      <div className="border-b border-primary-100 bg-primary-950 px-5 py-5 text-white">
        <div className="flex items-center justify-between gap-3">
          <Badge tone="ouro">Tese selecionada</Badge>
          <span className="text-xs text-primary-100">v{thesis.versao}</span>
        </div>
        <h2 className="mt-4 text-lg font-bold leading-snug">{thesis.titulo}</h2>
        <p className="mt-2 text-sm leading-6 text-primary-100">
          {thesis.fundamento_resumido || "Fundamento resumido ainda não informado."}
        </p>
      </div>
      <div className="space-y-5 p-5">
        <section>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary-700">
            Quando utilizar
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {thesis.estrategia.quando_utilizar
              ? String(thesis.estrategia.quando_utilizar)
              : thesis.situacao_fatica || "A aplicação depende da conferência dos fatos e dos pressupostos."}
          </p>
        </section>
        <section className="rounded-xl bg-slate-50 p-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">
            O que demonstrar
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {listText(thesis.elementos_demonstrar)}
          </p>
        </section>
        <section>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">
            Provas e documentos
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {listText([
              ...thesis.provas_necessarias,
              ...thesis.documentos_necessarios,
            ])}
          </p>
        </section>
        {thesis.argumento_adversario && (
          <section className="border-l-2 border-warn-400 pl-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-warn-700">
              Contratese provável
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-700">
              {thesis.argumento_adversario}
            </p>
            {thesis.resposta_adversaria && (
              <p className="mt-2 text-sm leading-6 text-slate-700">
                <strong>Resposta:</strong> {thesis.resposta_adversaria}
              </p>
            )}
          </section>
        )}
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
          <Badge tone={thesis.recomendavel ? "green" : "amber"}>
            {thesis.recomendavel ? "Validada para consulta" : "Não recomendável automaticamente"}
          </Badge>
          <span className="text-xs text-slate-500">
            {thesis.vigente ? "Vigente" : "Fora de vigência"} · {thesis.status}
          </span>
        </div>
        <p className="flex items-start gap-2 text-xs leading-5 text-slate-500">
          <Link2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary-600" />
          Precedentes e fontes oficiais são exibidos no detalhe após sua validação.
          A força da tese não é probabilidade garantida de resultado.
        </p>
      </div>
    </Card>
  );
}

export default function BancoNacionalTeses() {
  const [query, setQuery] = useState("");
  const [area, setArea] = useState("");
  const [side, setSide] = useState<"todos" | ThesisSide>("todos");
  const [result, setResult] = useState<{ total: number; items: NationalThesis[] }>({
    total: 0,
    items: [],
  });
  const [selected, setSelected] = useState<NationalThesis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (manual = false) => {
    setError(null);
    if (manual) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const data = await listarTesesNacionais({
        busca: query.trim() || undefined,
        area: area || undefined,
        lado: side === "todos" ? undefined : side,
        limit: 50,
      });
      setResult({ total: data.total, items: data.items });
      setSelected((current) =>
        current && data.items.some((item) => item.id === current.id) ? current : null,
      );
    } catch {
      setError("Não foi possível consultar o banco agora. Verifique a sessão e tente novamente.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [area, query, side]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 280);
    return () => window.clearTimeout(timer);
  }, [load]);

  const attack = useMemo(
    () => result.items.filter((item) => item.lado === "ataque" || item.lado === "ambos"),
    [result.items],
  );
  const defense = useMemo(
    () => result.items.filter((item) => item.lado === "defesa" || item.lado === "ambos"),
    [result.items],
  );

  async function openDetail(thesis: NationalThesis) {
    setSelected(thesis);
    try {
      const detail = await obterTeseNacional(thesis.id);
      setSelected(detail);
    } catch {
      // O card já contém uma visão segura; não substitui o resultado por uma mensagem vazia.
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inteligência jurídica · fontes rastreáveis"
        title="Banco Nacional de Teses"
        subtitle="Pesquise linhas argumentativas de ataque e defesa sem confundir tese, precedente, norma e estratégia. Apenas registros validados podem ser recomendados automaticamente."
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />}
            onClick={() => void load(true)}
            disabled={loading || refreshing}
          >
            Atualizar
          </Button>
        }
      />

      <section className="relative overflow-hidden rounded-2xl bg-primary-950 px-6 py-7 text-white shadow-card-hover sm:px-8">
        <div className="pointer-events-none absolute -right-12 -top-20 h-64 w-64 rounded-full border border-ouro-claro/30" />
        <div className="pointer-events-none absolute -bottom-28 right-20 h-64 w-64 rounded-full border border-white/10" />
        <div className="relative max-w-3xl">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-ouro-claro">
            <Sparkles className="h-4 w-4" /> Pesquisa por pergunta ou tema
          </div>
          <h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
            Encontre a linha argumentativa antes de redigir.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-primary-100">
            A fundação atual pesquisa título, tema, fundamento e tese principal. A camada semântica só será ativada quando o índice tiver fontes validadas e auditáveis.
          </p>
          <div className="mt-6 max-w-2xl rounded-xl bg-white p-1 shadow-lg shadow-black/20">
            <div className="relative flex items-center">
              <Search className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex.: fraude PIX, negativação indevida, defesa em execução fiscal"
                className="h-11 min-w-0 flex-1 rounded-lg border-0 pl-9 pr-3 text-sm text-slate-800 outline-none ring-0 placeholder:text-slate-400"
                aria-label="Pesquisar teses jurídicas"
              />
              <span className="hidden rounded-lg bg-primary-50 px-3 py-2 text-[11px] font-bold text-primary-700 sm:block">
                {result.total} encontradas
              </span>
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Registros encontrados"
          value={result.total}
          subtitle="Com os filtros atuais"
          icon={<BookOpen className="h-4 w-4" />}
          tone="ouro"
        />
        <StatCard
          label="Teses de ataque"
          value={attack.length}
          subtitle="Inclui posições aplicáveis a ambos"
          icon={<Target className="h-4 w-4" />}
          tone="blue"
        />
        <StatCard
          label="Teses de defesa"
          value={defense.length}
          subtitle="Sem tratar força como prognóstico"
          icon={<ShieldCheck className="h-4 w-4" />}
          tone="green"
        />
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500">
          <Filter className="h-4 w-4" /> Filtros
        </div>
        <Select
          value={area}
          onChange={(event) => setArea(event.target.value)}
          aria-label="Filtrar por área"
          className="h-9 min-w-48 text-xs"
        >
          <option value="">Todas as áreas</option>
          {AREAS.filter(Boolean).map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </Select>
        <Select
          value={side}
          onChange={(event) => setSide(event.target.value as "todos" | ThesisSide)}
          aria-label="Filtrar por posição processual"
          className="h-9 min-w-48 text-xs"
        >
          {SIDE_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </Select>
        {(query || area || side !== "todos") && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQuery("");
              setArea("");
              setSide("todos");
            }}
          >
            Limpar filtros
          </Button>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-danger-200 bg-danger-50 p-4 text-sm text-danger-800">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-slate-200 bg-white">
          <Spinner />
        </div>
      ) : result.items.length === 0 ? (
        <Card className="border-dashed border-slate-300 bg-slate-50/70 p-8 text-center">
          <Scale className="mx-auto h-8 w-8 text-primary-500" />
          <h2 className="mt-4 text-base font-bold text-primary-950">
            Banco em preparação curatorial
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">
            Nenhuma tese validada corresponde à consulta. Registros não validados permanecem fora da recomendação automática até que fonte, atualidade e revisão humana sejam conferidas.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2 text-xs text-slate-500">
            <span className="rounded-full bg-white px-3 py-1.5 ring-1 ring-inset ring-slate-200">Fonte rastreável</span>
            <span className="rounded-full bg-white px-3 py-1.5 ring-1 ring-inset ring-slate-200">Precedente real</span>
            <span className="rounded-full bg-white px-3 py-1.5 ring-1 ring-inset ring-slate-200">Revisão humana</span>
          </div>
        </Card>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.78fr)]">
          <div className="space-y-5">
            {attack.length > 0 && (
              <section>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary-700">
                      Ataque
                    </p>
                    <h2 className="mt-1 text-lg font-bold text-primary-950">Linhas para fundamentar o pedido</h2>
                  </div>
                  <span className="text-xs text-slate-500">{attack.length} registros</span>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {attack.map((thesis) => (
                    <ThesisCard
                      key={`attack-${thesis.id}`}
                      thesis={thesis}
                      selected={selected?.id === thesis.id}
                      onOpen={() => void openDetail(thesis)}
                    />
                  ))}
                </div>
              </section>
            )}
            {defense.length > 0 && (
              <section>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-info-700">
                      Defesa e contratese
                    </p>
                    <h2 className="mt-1 text-lg font-bold text-primary-950">Linhas para responder e distinguir</h2>
                  </div>
                  <span className="text-xs text-slate-500">{defense.length} registros</span>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {defense.map((thesis) => (
                    <ThesisCard
                      key={`defense-${thesis.id}`}
                      thesis={thesis}
                      selected={selected?.id === thesis.id}
                      onOpen={() => void openDetail(thesis)}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
          {selected ? (
            <DetailPanel thesis={selected} />
          ) : (
            <Card className="hidden min-h-64 items-center justify-center border-dashed border-slate-300 bg-slate-50/60 p-8 text-center xl:flex">
              <div>
                <CheckCircle2 className="mx-auto h-8 w-8 text-success-600" />
                <h2 className="mt-3 text-sm font-bold text-primary-950">Selecione uma tese</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">O detalhe reúne pressupostos, provas, riscos e a trilha de fonte quando disponível.</p>
              </div>
            </Card>
          )}
        </div>
      )}

      <p className="flex items-center gap-2 text-xs leading-5 text-slate-500">
        <ArrowUpRight className="h-3.5 w-3.5 text-primary-600" />
        O botão “Usar no processo” será habilitado somente após a integração do caso, revisão humana e seleção explícita do advogado.
      </p>
    </div>
  );
}
