// ── Visual Law: Calculadora de acordo (breakeven do litígio) ─────────────────
// POST /visual-law/breakeven — compara VPL do litígio × acordo imediato.
//
// REMOVIDO em 2026-08-02 (Bloco 4 do plano de lançamento): a seção "Perfil do
// julgador" e o botão "Dossiê de Pressão", que consumiam
// /diplomacia-v3/analisar-magistrado e /diplomacia-v3/dossie-pressao. Os dois
// endpoints saíram do backend por decisão do escritório — risco reputacional e
// disciplinar indefensável, independentemente do que produzissem.
// Não reintroduzir sem decisão escrita do titular.
import { useEffect, useState } from "react";
import {
  Calculator,
  ChevronDown,
  Hourglass,
  Landmark,
  Scale,
  TrendingUp,
} from "lucide-react";
import api from "../../lib/api";
import { toast } from "../Toast";
import {
  Badge,
  Button,
  FieldLabel,
  IANotice,
  Input,
  SectionCard,
  Select,
  Spinner,
  cn,
  fmtMoney,
} from "../UI";
import type {
  BreakevenRequest,
  BreakevenResponse,
  SelicFonte,
} from "../../types/visualLaw";

const TRIBUNAIS = ["TJMG", "TJSP", "TRT3", "TRF6", "STJ", "outro"] as const;

/** Badge da fonte da Selic — exaustivo sobre SelicFonte (erro de tipo se o union crescer). */
const SELIC_BADGE = {
  bcb: { tone: "green", label: "Selic BCB" },
  fallback: { tone: "amber", label: "Selic estimada" },
  informada: { tone: "slate", label: "Selic informada" },
} as const satisfies Record<
  SelicFonte,
  { tone: "green" | "amber" | "slate"; label: string }
>;

function tribunalInicialNormalizado(tribunal?: string | null): string {
  if (!tribunal) return "TJMG";
  const t = tribunal.trim().toUpperCase();
  const conhecido = TRIBUNAIS.find((op) => op !== "outro" && t.includes(op));
  return conhecido ?? "outro";
}

/** detail de erro da API pode ser string ou objeto — nunca renderizar cru. */
function detalheErro(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function BarraComparativa({ resultado }: { resultado: BreakevenResponse }) {
  const litigio = Math.max(0, resultado.comparativo.litigio_vpl);
  const acordo = Math.max(0, resultado.comparativo.acordo_imediato_equivalente);
  const maximo = Math.max(litigio, acordo, 1);
  const linhas: Array<{ label: string; valor: number; barra: string }> = [
    {
      label: "Litígio (VPL)",
      valor: resultado.comparativo.litigio_vpl,
      barra: "bg-primary-600",
    },
    {
      label: "Acordo imediato equivalente",
      valor: resultado.comparativo.acordo_imediato_equivalente,
      barra: "bg-emerald-500",
    },
  ];
  return (
    <div className="space-y-2">
      {linhas.map((linha) => (
        <div key={linha.label}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="font-medium text-slate-600">{linha.label}</span>
            <span className="font-semibold tabular-nums text-slate-800">
              {fmtMoney(linha.valor)}
            </span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn("h-full rounded-full transition-all", linha.barra)}
              style={{
                width: `${(Math.max(0, linha.valor) / maximo) * 100}%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
// ── Correção monetária por índice oficial do BCB ─────────────────────────────
// GET /indices/series (catálogo + último valor divulgado) ·
// POST /indices/atualizar-valor (valor final + memória de cálculo mês a mês).
// Fonte oficial (BCB SGS) — MINUTA para conferência do advogado (HITL).
type RegraCorrecao = "correcao" | "correcao_mais_taxa_legal" | "selic_ec113";

interface SerieInfo {
  indice: string;
  nome: string;
  codigo_sgs: number;
  tipo: string;
  ultimo_valor: number | null;
  ultima_data: string | null;
}

interface EtapaMemoria {
  competencia: string;
  valor_pct: number;
  fator_periodo: number;
  fator_acumulado: number;
}

interface EtapaCorrecao {
  nome?: string;
  fator?: number;
  meses_aplicados?: number;
  percentual_acumulado?: number;
  periodo?: string;
  memoria_calculo?: EtapaMemoria[];
  base_legal?: string;
  fonte?: string;
}

interface AtualizarValorResposta {
  regra: RegraCorrecao;
  valor_original: number;
  valor_final: number;
  etapas: EtapaCorrecao[];
}

const REGRAS_CORRECAO: {
  id: RegraCorrecao;
  label: string;
  hint: string;
}[] = [
  {
    id: "correcao",
    label: "Somente correção monetária",
    hint: "Atualiza o valor pelo índice escolhido, competência a competência.",
  },
  {
    id: "correcao_mais_taxa_legal",
    label: "Correção + Taxa Legal (Lei 14.905/2024)",
    hint: "Correção pelo índice + juros da Taxa Legal (série SGS 29543) sobre o valor já corrigido.",
  },
  {
    id: "selic_ec113",
    label: "SELIC exclusiva (EC 113/2021 — Fazenda Pública)",
    hint: "Selic acumulada, vedada a cumulação com correção ou juros (débitos da Fazenda Pública).",
  },
];

// Correção monetária usa séries MENSAIS; diárias (Selic/CDI diária, meta) não
// entram no fator. Fallback usado quando o catálogo do BCB não responde.
const INDICES_FALLBACK: SerieInfo[] = [
  {
    indice: "ipca",
    nome: "IPCA (IBGE, % a.m.)",
    codigo_sgs: 433,
    tipo: "mensal",
    ultimo_valor: null,
    ultima_data: null,
  },
  {
    indice: "ipca_e",
    nome: "IPCA-E (IBGE, % acum. trim.)",
    codigo_sgs: 10764,
    tipo: "mensal",
    ultimo_valor: null,
    ultima_data: null,
  },
  {
    indice: "inpc",
    nome: "INPC (IBGE, % a.m.)",
    codigo_sgs: 188,
    tipo: "mensal",
    ultimo_valor: null,
    ultima_data: null,
  },
  {
    indice: "igpm",
    nome: "IGP-M (FGV, % a.m.)",
    codigo_sgs: 189,
    tipo: "mensal",
    ultimo_valor: null,
    ultima_data: null,
  },
  {
    indice: "selic_mensal",
    nome: "SELIC acumulada no mês (%)",
    codigo_sgs: 4390,
    tipo: "mensal",
    ultimo_valor: null,
    ultima_data: null,
  },
  {
    indice: "tr",
    nome: "TR (% a.m.)",
    codigo_sgs: 226,
    tipo: "mensal",
    ultimo_valor: null,
    ultima_data: null,
  },
];

function fmtPct(n: number | null | undefined, casas = 4): string {
  return Number(n ?? 0).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: casas,
  });
}
function fmtFator(n: number | null | undefined): string {
  return Number(n ?? 0).toLocaleString("pt-BR", {
    minimumFractionDigits: 6,
    maximumFractionDigits: 8,
  });
}

function MemoriaEtapa({ etapa }: { etapa: EtapaCorrecao }) {
  const linhas = etapa.memoria_calculo ?? [];
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-700">
          {etapa.nome || "Etapa"}
        </span>
        <span className="text-[11px] tabular-nums text-slate-500">
          fator {fmtFator(etapa.fator)}
          {etapa.meses_aplicados != null
            ? ` · ${etapa.meses_aplicados} competência(s)`
            : ""}
        </span>
      </div>
      {linhas.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[420px] text-[11px]">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="py-1 pr-2 font-medium">Competência</th>
                <th className="py-1 pr-2 text-right font-medium">Índice (%)</th>
                <th className="py-1 pr-2 text-right font-medium">
                  Fator período
                </th>
                <th className="py-1 text-right font-medium">Fator acumulado</th>
              </tr>
            </thead>
            <tbody className="tabular-nums text-slate-600">
              {linhas.map((l, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="py-1 pr-2">{l.competencia}</td>
                  <td className="py-1 pr-2 text-right">
                    {fmtPct(l.valor_pct)}
                  </td>
                  <td className="py-1 pr-2 text-right">
                    {fmtFator(l.fator_periodo)}
                  </td>
                  <td className="py-1 text-right font-medium text-slate-700">
                    {fmtFator(l.fator_acumulado)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(etapa.base_legal || etapa.fonte) && (
        <p className="mt-2 text-[10px] text-slate-500">
          {etapa.base_legal || etapa.fonte}
        </p>
      )}
    </div>
  );
}

function CorrecaoMonetariaOficial() {
  const [series, setSeries] = useState<SerieInfo[] | null>(null);
  const [catalogoIndisponivel, setCatalogoIndisponivel] = useState(false);
  const [valor, setValor] = useState("");
  const [indice, setIndice] = useState("ipca");
  const [dataInicial, setDataInicial] = useState("");
  const [dataFinal, setDataFinal] = useState("");
  const [regra, setRegra] = useState<RegraCorrecao>("correcao");
  const [calculando, setCalculando] = useState(false);
  const [resultado, setResultado] = useState<AtualizarValorResposta | null>(
    null,
  );

  useEffect(() => {
    let vivo = true;
    api
      .get<{ series: SerieInfo[] }>("/indices/series")
      .then((r) => {
        if (!vivo) return;
        const mensais = (r.data.series ?? []).filter(
          (s) => s.tipo === "mensal",
        );
        setSeries(mensais.length ? mensais : INDICES_FALLBACK);
      })
      .catch(() => {
        if (!vivo) return;
        setSeries(INDICES_FALLBACK);
        setCatalogoIndisponivel(true);
      });
    return () => {
      vivo = false;
    };
  }, []);

  const listaIndices = series ?? INDICES_FALLBACK;
  const usaIndice = regra !== "selic_ec113";
  const selInfo = listaIndices.find((s) => s.indice === indice);
  const regraInfo = REGRAS_CORRECAO.find((r) => r.id === regra);
  const variacaoPct =
    resultado && resultado.valor_original > 0
      ? (resultado.valor_final / resultado.valor_original - 1) * 100
      : 0;

  const calcular = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = Number(valor);
    if (!Number.isFinite(v) || v <= 0) {
      toast.error("Informe um valor a corrigir maior que zero");
      return;
    }
    if (!dataInicial || !dataFinal) {
      toast.error("Informe a data inicial e a data final da correção");
      return;
    }
    if (dataFinal < dataInicial) {
      toast.error("A data final não pode ser anterior à data inicial");
      return;
    }
    setCalculando(true);
    try {
      const r = await api.post<AtualizarValorResposta>(
        "/indices/atualizar-valor",
        {
          valor: v,
          indice,
          data_inicial: dataInicial,
          data_final: dataFinal,
          regra,
        },
      );
      setResultado(r.data);
    } catch (err) {
      toast.error(
        detalheErro(err, "Falha ao atualizar o valor pelo índice oficial"),
      );
    } finally {
      setCalculando(false);
    }
  };

  return (
    <SectionCard
      title="Correção monetária por índice oficial (BCB)"
      subtitle="Atualiza valores por índices oficiais do Banco Central (SGS), com memória de cálculo mês a mês para juntar aos autos"
      actions={
        catalogoIndisponivel ? (
          <Badge tone="amber">Catálogo BCB indisponível</Badge>
        ) : (
          <Badge tone="green">Fonte oficial · BCB</Badge>
        )
      }
    >
      <form onSubmit={calcular} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <FieldLabel required>Valor a corrigir (R$)</FieldLabel>
            <Input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              placeholder="Ex.: 10000"
            />
          </div>
          <div>
            <FieldLabel required>Data inicial</FieldLabel>
            <Input
              type="date"
              required
              value={dataInicial}
              onChange={(e) => setDataInicial(e.target.value)}
            />
          </div>
          <div>
            <FieldLabel required>Data final</FieldLabel>
            <Input
              type="date"
              required
              value={dataFinal}
              onChange={(e) => setDataFinal(e.target.value)}
            />
          </div>
          <div>
            <FieldLabel>Índice</FieldLabel>
            <Select
              value={indice}
              disabled={!usaIndice}
              onChange={(e) => setIndice(e.target.value)}
            >
              {listaIndices.map((s) => (
                <option key={s.indice} value={s.indice}>
                  {s.nome}
                  {s.ultimo_valor != null
                    ? ` — último ${fmtPct(s.ultimo_valor)}%`
                    : ""}
                </option>
              ))}
            </Select>
            {usaIndice && selInfo?.ultimo_valor != null && (
              <p className="mt-1 text-[11px] text-slate-400">
                Último {selInfo.nome}: {fmtPct(selInfo.ultimo_valor)}%
                {selInfo.ultima_data
                  ? ` em ${selInfo.ultima_data.split("-").reverse().join("/")}`
                  : ""}
              </p>
            )}
            {!usaIndice && (
              <p className="mt-1 text-[11px] text-slate-400">
                A regra EC 113/2021 usa a Selic acumulada — índice fixo.
              </p>
            )}
          </div>
        </div>

        <div>
          <FieldLabel>Regra de atualização</FieldLabel>
          <Select
            value={regra}
            onChange={(e) => setRegra(e.target.value as RegraCorrecao)}
          >
            {REGRAS_CORRECAO.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </Select>
          {regraInfo && (
            <p className="mt-1 text-[11px] text-slate-400">{regraInfo.hint}</p>
          )}
        </div>

        <Button
          type="submit"
          disabled={calculando}
          icon={<TrendingUp className="h-4 w-4" />}
        >
          {calculando ? "Atualizando…" : "Atualizar valor"}
        </Button>
      </form>

      {calculando && <Spinner />}

      {resultado && !calculando && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-5">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Valor original
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-slate-700">
                {fmtMoney(resultado.valor_original)}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                <Landmark className="h-4 w-4" />
                Valor atualizado
              </div>
              <p className="mt-2 text-xl font-bold tabular-nums text-emerald-800">
                {fmtMoney(resultado.valor_final)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Variação de {fmtPct(variacaoPct, 2)}% no período
              </p>
            </div>
          </div>

          <IANotice>
            Cálculo determinístico com base nos índices oficiais do BCB — MINUTA
            para conferência do advogado (HITL) antes de juntar aos autos.
          </IANotice>

          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <Calculator className="h-4 w-4" />
              Memória de cálculo ({resultado.etapas.length}{" "}
              {resultado.etapas.length === 1 ? "etapa" : "etapas"})
            </div>
            {resultado.etapas.map((etapa, i) => (
              <MemoriaEtapa key={i} etapa={etapa} />
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

export default function CalculadoraAcordo({
  caseId,
  valorCausaInicial,
  tribunalInicial,
}: {
  caseId?: string;
  valorCausaInicial?: number | null;
  tribunalInicial?: string | null;
}) {
  const [valorCausa, setValorCausa] = useState(
    valorCausaInicial != null && valorCausaInicial > 0
      ? String(valorCausaInicial)
      : "",
  );
  const [probExito, setProbExito] = useState(60);
  const [tribunal, setTribunal] = useState(
    tribunalInicialNormalizado(tribunalInicial),
  );
  const [tempoAnos, setTempoAnos] = useState("");
  const [custasPct, setCustasPct] = useState("");
  const [sucumbenciaPct, setSucumbenciaPct] = useState("");
  const [calculando, setCalculando] = useState(false);
  const [resultado, setResultado] = useState<BreakevenResponse | null>(null);

  const calcular = async (e: React.FormEvent) => {
    e.preventDefault();
    const valor = Number(valorCausa);
    if (!Number.isFinite(valor) || valor <= 0) {
      toast.error("Informe um valor da causa válido (maior que zero)");
      return;
    }
    const body: BreakevenRequest = {
      valor_causa: valor,
      prob_exito: probExito / 100,
      tribunal,
    };
    const tempo = Number(tempoAnos);
    if (tempoAnos.trim() !== "" && Number.isFinite(tempo) && tempo > 0) {
      body.tempo_anos = tempo;
    }
    const custas = Number(custasPct);
    if (custasPct.trim() !== "" && Number.isFinite(custas) && custas >= 0) {
      body.custas_pct = custas;
    }
    const sucumbencia = Number(sucumbenciaPct);
    if (
      sucumbenciaPct.trim() !== "" &&
      Number.isFinite(sucumbencia) &&
      sucumbencia >= 0
    ) {
      body.honorarios_sucumbencia_pct = sucumbencia;
    }
    if (caseId) body.case_id = caseId;

    setCalculando(true);
    try {
      const r = await api.post<BreakevenResponse>(
        "/visual-law/breakeven",
        body,
      );
      setResultado(r.data);
    } catch (err) {
      toast.error(detalheErro(err, "Falha ao calcular o ponto de equilíbrio"));
    } finally {
      setCalculando(false);
    }
  };

  return (
    <div className="space-y-5">
      <SectionCard
        title="Calculadora de acordo (breakeven)"
        subtitle="Compara o valor presente do litígio com um acordo imediato, considerando tempo médio de tramitação, custas e Selic"
      >
        <form onSubmit={calcular} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <FieldLabel required>Valor da causa (R$)</FieldLabel>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={valorCausa}
                onChange={(e) => setValorCausa(e.target.value)}
                placeholder="Ex.: 150000"
              />
            </div>
            <div>
              <FieldLabel>Tribunal</FieldLabel>
              <Select
                value={tribunal}
                onChange={(e) => setTribunal(e.target.value)}
              >
                {TRIBUNAIS.map((t) => (
                  <option key={t} value={t}>
                    {t === "outro" ? "Outro" : t}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <FieldLabel>Tempo estimado (anos, opcional)</FieldLabel>
              <Input
                type="number"
                min="0.5"
                step="0.5"
                value={tempoAnos}
                onChange={(e) => setTempoAnos(e.target.value)}
                placeholder="Média do tribunal"
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-1">
              <FieldLabel>Probabilidade de êxito</FieldLabel>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={probExito}
                  onChange={(e) => setProbExito(Number(e.target.value))}
                  className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-slate-200 accent-primary-600"
                  aria-label="Probabilidade de êxito (%)"
                />
                <span className="w-12 shrink-0 text-right text-sm font-semibold tabular-nums text-slate-800">
                  {probExito}%
                </span>
              </div>
            </div>
          </div>

          <details className="card">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
              Parâmetros avançados (custas e sucumbência)
            </summary>
            <div className="grid grid-cols-1 gap-4 border-t border-slate-100 p-4 sm:grid-cols-2">
              <div>
                <FieldLabel>Custas processuais (%)</FieldLabel>
                <Input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={custasPct}
                  onChange={(e) => setCustasPct(e.target.value)}
                  placeholder="Padrão do sistema"
                />
              </div>
              <div>
                <FieldLabel>Honorários de sucumbência (%)</FieldLabel>
                <Input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={sucumbenciaPct}
                  onChange={(e) => setSucumbenciaPct(e.target.value)}
                  placeholder="Padrão do sistema"
                />
              </div>
            </div>
          </details>

          <Button
            type="submit"
            disabled={calculando}
            icon={<Calculator className="h-4 w-4" />}
          >
            {calculando ? "Calculando…" : "Calcular ponto de equilíbrio"}
          </Button>
        </form>
      </SectionCard>

      {calculando && <Spinner />}

      {resultado && !calculando && (
        <SectionCard
          title="Resultado da simulação"
          actions={
            <Badge tone={SELIC_BADGE[resultado.parametros.selic_fonte].tone}>
              {SELIC_BADGE[resultado.parametros.selic_fonte].label} ·{" "}
              {(resultado.parametros.selic_anual * 100).toFixed(2)}% a.a.
            </Badge>
          }
        >
          <div className="space-y-5">
            {/* Cartões grandes: VPL do litígio × sugestão de acordo */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-primary-200 bg-primary-50/60 p-5">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-primary-700">
                  <Scale className="h-4 w-4" />
                  VPL do litígio
                </div>
                <p className="mt-2 text-xl font-bold tabular-nums text-primary-800">
                  {fmtMoney(resultado.vpl_litigio)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Valor esperado {fmtMoney(resultado.valor_esperado)} − custos{" "}
                  {fmtMoney(resultado.custos_estimados)}, trazidos a valor
                  presente ({resultado.parametros.tempo_anos}{" "}
                  {resultado.parametros.tempo_anos === 1 ? "ano" : "anos"}
                  {resultado.parametros.tribunal
                    ? ` · ${resultado.parametros.tribunal}`
                    : ""}
                  )
                </p>
              </div>
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                  <Calculator className="h-4 w-4" />
                  Sugestão de acordo
                </div>
                <p className="mt-2 text-xl font-bold tabular-nums text-emerald-800">
                  {fmtMoney(resultado.sugestao_acordo)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Ponto de equilíbrio (breakeven):{" "}
                  <strong className="text-slate-700">
                    {fmtMoney(resultado.breakeven)}
                  </strong>{" "}
                  — acima disso o acordo tende a superar o litígio.
                </p>
              </div>
            </div>

            {/* Barra comparativa proporcional */}
            <BarraComparativa resultado={resultado} />

            {/* Custo do tempo */}
            <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
              <Hourglass className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div className="text-sm text-amber-800">
                <span className="font-semibold">
                  Custo do tempo:{" "}
                  {fmtMoney(resultado.comparativo.custo_do_tempo)}
                </span>
                <p className="mt-0.5 text-xs">
                  Quanto o valor do litígio perde ao longo da tramitação em
                  relação a receber um acordo hoje.
                </p>
              </div>
            </div>

            {/* Memória de cálculo */}
            {resultado.memoria_calculo.length > 0 && (
              <details className="card">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
                  <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                  Memória de cálculo ({resultado.memoria_calculo.length} passos)
                </summary>
                <ol className="list-decimal space-y-1.5 border-t border-slate-100 p-4 pl-9 text-xs text-slate-600">
                  {resultado.memoria_calculo.map((passo, i) => (
                    <li key={i}>{passo}</li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        </SectionCard>
      )}

      <CorrecaoMonetariaOficial />
    </div>
  );
}
