// ── Visual Law: Calculadora de acordo (breakeven do litígio) ─────────────────
// POST /visual-law/breakeven — compara VPL do litígio × acordo imediato.
// Inclui seção opcional "Perfil do julgador" (POST /diplomacia-v3/analisar-magistrado).
import { useMemo, useState } from "react";
import {
  Calculator,
  ChevronDown,
  Gavel,
  Hourglass,
  Scale,
  Sparkles,
} from "lucide-react";
import api from "../../lib/api";
import Markdown from "../Markdown";
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
  Textarea,
  cn,
} from "../UI";
import type {
  BreakevenRequest,
  BreakevenResponse,
} from "../../types/visualLaw";

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const TRIBUNAIS = ["TJMG", "TJSP", "TRT3", "TRF6", "STJ", "outro"] as const;

const MAX_DECISOES = 10;

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

/**
 * O endpoint /diplomacia-v3/analisar-magistrado pode retornar a análise como
 * string pura OU objeto com campo de texto — normaliza defensivamente.
 */
function extrairTextoAnalise(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    const campos = [
      "analise",
      "resultado",
      "resposta",
      "texto",
      "conteudo",
      "content",
      "markdown",
      "output",
      "message",
    ];
    for (const campo of campos) {
      const v = obj[campo];
      if (typeof v === "string" && v.trim()) return v;
    }
    for (const v of Object.values(obj)) {
      if (typeof v === "string" && v.trim().length > 40) return v;
    }
    return JSON.stringify(data, null, 2);
  }
  return "";
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
              {fmtBRL.format(linha.valor)}
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

function PerfilJulgador() {
  const [texto, setTexto] = useState("");
  const [analisando, setAnalisando] = useState(false);
  const [analise, setAnalise] = useState<string | null>(null);

  const decisoes = useMemo(
    () =>
      texto
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean),
    [texto],
  );

  const analisar = async () => {
    if (decisoes.length === 0) {
      toast.error("Cole ao menos uma decisão (uma por linha)");
      return;
    }
    setAnalisando(true);
    try {
      const r = await api.post("/diplomacia-v3/analisar-magistrado", {
        decisoes: decisoes.slice(0, MAX_DECISOES),
      });
      const textoAnalise = extrairTextoAnalise(r.data);
      if (!textoAnalise) {
        toast.error("A análise retornou vazia — tente novamente");
      } else {
        setAnalise(textoAnalise);
      }
    } catch (e) {
      toast.error(detalheErro(e, "Falha ao analisar as decisões"));
    } finally {
      setAnalisando(false);
    }
  };

  return (
    <details className="rounded-xl border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50">
        <Gavel className="h-4 w-4 text-slate-400" />
        Perfil do julgador (opcional)
        <ChevronDown className="ml-auto h-4 w-4 text-slate-400" />
      </summary>
      <div className="space-y-3 border-t border-slate-100 p-4">
        <p className="text-xs text-slate-500">
          Cole até {MAX_DECISOES} decisões do magistrado (uma por linha) para
          uma análise de tendência (Rigorosa/Flexível/Neutra), temas sensíveis e
          tom recomendado.
        </p>
        <Textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={6}
          placeholder={"Decisão 1...\nDecisão 2...\nDecisão 3..."}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="ai"
            onClick={analisar}
            disabled={analisando || decisoes.length === 0}
            icon={<Sparkles className="h-3.5 w-3.5" />}
          >
            {analisando ? "Analisando…" : "Analisar decisões"}
          </Button>
          <span className="text-xs text-slate-400">
            {Math.min(decisoes.length, MAX_DECISOES)}/{MAX_DECISOES} decisões
          </span>
        </div>
        {analisando && <Spinner />}
        {analise && !analisando && (
          <div className="space-y-3">
            <IANotice>
              Análise gerada por IA — revisão obrigatória do advogado.
            </IANotice>
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-sm">
              <Markdown source={analise} />
            </div>
          </div>
        )}
      </div>
    </details>
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

          <details className="rounded-xl border border-slate-200">
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
            <Badge
              tone={
                resultado.parametros.selic_fonte === "bcb" ? "green" : "amber"
              }
            >
              {resultado.parametros.selic_fonte === "bcb"
                ? "Selic BCB"
                : "Selic estimada"}{" "}
              · {(resultado.parametros.selic_anual * 100).toFixed(2)}% a.a.
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
                <p className="mt-2 text-3xl font-bold tabular-nums text-primary-800">
                  {fmtBRL.format(resultado.vpl_litigio)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Valor esperado {fmtBRL.format(resultado.valor_esperado)} −
                  custos {fmtBRL.format(resultado.custos_estimados)}, trazidos a
                  valor presente ({resultado.parametros.tempo_anos}{" "}
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
                <p className="mt-2 text-3xl font-bold tabular-nums text-emerald-800">
                  {fmtBRL.format(resultado.sugestao_acordo)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Ponto de equilíbrio (breakeven):{" "}
                  <strong className="text-slate-700">
                    {fmtBRL.format(resultado.breakeven)}
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
                  {fmtBRL.format(resultado.comparativo.custo_do_tempo)}
                </span>
                <p className="mt-0.5 text-xs">
                  Quanto o valor do litígio perde ao longo da tramitação em
                  relação a receber um acordo hoje.
                </p>
              </div>
            </div>

            {/* Memória de cálculo */}
            {resultado.memoria_calculo.length > 0 && (
              <details className="rounded-xl border border-slate-200">
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

      <PerfilJulgador />
    </div>
  );
}
