import { useState } from "react";
import { Banknote, Calculator, Loader2, TrendingUp } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { detalheErro } from "../utils/erro";

const MODALIDADES = [
  ["credito_pessoal", "Crédito pessoal não consignado"],
  ["credito_pessoal_consignado_inss", "Consignado INSS"],
  ["credito_pessoal_consignado_privado", "Consignado privado"],
  ["credito_pessoal_consignado_publico", "Consignado servidor público"],
  ["veiculos", "Financiamento de veículos"],
  ["cheque_especial", "Cheque especial"],
  ["cartao_rotativo", "Cartão rotativo"],
  ["cartao_parcelado", "Cartão parcelado"],
  ["aquisicao_outros_bens", "Aquisição de outros bens"],
  ["capital_de_giro", "Capital de giro"],
  ["conta_garantida", "Conta garantida"],
] as const;

const num = (valor: string) => {
  if (!valor.trim()) return undefined;
  const normalizado = valor.trim().replace(/\./g, "").replace(",", ".");
  const parsed = Number(normalizado);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const baseCetAtual = (linha: string) =>
  linha.replace(/Res\. CMN 3\.517\/2007/g, "Res. CMN 4.881/2020");

export default function RevisaoBancariaDeterministica() {
  const [taxa, setTaxa] = useState("");
  const [modalidade, setModalidade] = useState("credito_pessoal");
  const [dataContrato, setDataContrato] = useState("");
  const [valorFinanciado, setValorFinanciado] = useState("");
  const [nParcelas, setNParcelas] = useState("");
  const [parcela, setParcela] = useState("");
  const [abusividade, setAbusividade] = useState<any>(null);
  const [loadingAbusividade, setLoadingAbusividade] = useState(false);

  const [valorLiberado, setValorLiberado] = useState("");
  const [dataLiberacao, setDataLiberacao] = useState("");
  const [cetParcelas, setCetParcelas] = useState("");
  const [valorParcela, setValorParcela] = useState("");
  const [primeiroVencimento, setPrimeiroVencimento] = useState("");
  const [tarifas, setTarifas] = useState("0");
  const [iof, setIof] = useState("0");
  const [cetInformado, setCetInformado] = useState("");
  const [cet, setCet] = useState<any>(null);
  const [loadingCet, setLoadingCet] = useState(false);

  const avaliar = async () => {
    const taxaNumerica = num(taxa);
    if (taxaNumerica === undefined)
      return toast.error("Informe a taxa mensal contratada.");
    setLoadingAbusividade(true);
    setAbusividade(null);
    try {
      const payload: Record<string, any> = {
        taxa_contrato_am_pct: taxaNumerica,
        modalidade,
      };
      if (dataContrato) payload.data_contrato = dataContrato;
      const financiado = num(valorFinanciado);
      const quantidade = num(nParcelas);
      const pmt = num(parcela);
      if (financiado !== undefined) payload.valor_financiado = financiado;
      if (quantidade !== undefined) payload.n_parcelas = quantidade;
      if (pmt !== undefined) payload.parcela_contratual = pmt;
      const { data } = await api.post("/analise-bancaria/abusividade", payload);
      setAbusividade(data);
    } catch (error: unknown) {
      toast.error(
        detalheErro(error, "Falha ao consultar a média do Banco Central."),
      );
    } finally {
      setLoadingAbusividade(false);
    }
  };

  const calcularCet = async () => {
    const liberado = num(valorLiberado);
    const parcelas = num(cetParcelas);
    const pmt = num(valorParcela);
    if (
      liberado === undefined ||
      !dataLiberacao ||
      parcelas === undefined ||
      pmt === undefined ||
      !primeiroVencimento
    ) {
      return toast.error(
        "Preencha valor liberado, datas, número e valor das parcelas.",
      );
    }
    setLoadingCet(true);
    setCet(null);
    try {
      const payload: Record<string, any> = {
        valor_liberado: liberado,
        data_liberacao: dataLiberacao,
        n_parcelas: parcelas,
        valor_parcela: pmt,
        primeiro_vencimento: primeiroVencimento,
        tarifas_incluidas: num(tarifas) ?? 0,
        iof: num(iof) ?? 0,
      };
      const informado = num(cetInformado);
      if (informado !== undefined) payload.cet_informado_aa_pct = informado;
      const { data } = await api.post("/analise-bancaria/cet", payload);
      setCet(data);
    } catch (error: unknown) {
      toast.error(detalheErro(error, "Falha ao calcular o CET."));
    } finally {
      setLoadingCet(false);
    }
  };

  const veredito = abusividade?.veredito;
  const vereditoClass =
    veredito === "indicio_forte_abusividade"
      ? "bg-danger-50 text-danger-800 ring-danger-200"
      : veredito === "zona_de_atencao"
        ? "bg-warn-50 text-warn-800 ring-warn-200"
        : veredito === "sem_indicio_relevante"
          ? "bg-success-50 text-success-800 ring-success-200"
          : "bg-slate-100 text-slate-700 ring-slate-200";
  const expurgo = abusividade?.expurgo ?? abusividade?.cenario_expurgo;

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary-700 dark:text-primary-200">
          <Banknote className="h-4 w-4" /> Revisão bancária determinística
        </div>
        <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
          Juros, taxa média e Custo Efetivo Total
        </h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600 dark:text-slate-300">
          A IA localiza as cláusulas; estes motores refazem a conferência
          numérica. A comparação usa modalidade e época do contrato. O resultado
          é indício técnico, não declaração automática de abusividade.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
            <TrendingUp className="h-4 w-4" /> Comparar juros com o BACEN
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="sm:col-span-2">
              <span className="label">Modalidade de crédito</span>
              <select
                className="input w-full"
                value={modalidade}
                onChange={(event) => setModalidade(event.target.value)}
              >
                {MODALIDADES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="label">Taxa contratada (% ao mês)</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={taxa}
                onChange={(event) => setTaxa(event.target.value)}
                placeholder="Ex.: 3,25"
              />
            </label>
            <label>
              <span className="label">Data do contrato</span>
              <input
                className="input w-full"
                type="date"
                value={dataContrato}
                onChange={(event) => setDataContrato(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Valor financiado (opcional)</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={valorFinanciado}
                onChange={(event) => setValorFinanciado(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Número de parcelas (opcional)</span>
              <input
                className="input w-full"
                type="number"
                value={nParcelas}
                onChange={(event) => setNParcelas(event.target.value)}
              />
            </label>
            <label className="sm:col-span-2">
              <span className="label">Parcela contratual (opcional)</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={parcela}
                onChange={(event) => setParcela(event.target.value)}
              />
            </label>
          </div>
          <button
            className="btn-gold mt-3 flex items-center gap-2"
            onClick={avaliar}
            disabled={loadingAbusividade}
          >
            {loadingAbusividade ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <TrendingUp className="h-4 w-4" />
            )}{" "}
            Avaliar indício de abusividade
          </button>

          {abusividade && (
            <div className="mt-4 space-y-3">
              <div
                className={`rounded-2xl p-3 text-sm ring-1 ${vereditoClass}`}
              >
                <div className="font-semibold">
                  {String(veredito || "resultado indeterminado").replace(
                    /_/g,
                    " ",
                  )}
                </div>
                <div className="mt-1 text-xs">
                  Contrato: {abusividade.taxa_contrato_am_pct}% a.m. · Média:{" "}
                  {abusividade.taxa_media?.ao_mes?.media ??
                    abusividade.taxa_media_am_pct ??
                    "indisponível"}
                  % a.m.
                  {abusividade.razao != null
                    ? ` · Razão: ${Number(abusividade.razao).toFixed(2)}x`
                    : ""}
                </div>
              </div>
              {expurgo && (
                <div className="grid grid-cols-2 gap-2 text-center text-sm">
                  <div className="rounded-xl bg-slate-50 p-2">
                    <span className="block text-xs text-slate-500">
                      Parcela revisada
                    </span>
                    <b>R$ {Number(expurgo.parcela_revisada ?? 0).toFixed(2)}</b>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-2">
                    <span className="block text-xs text-slate-500">
                      Economia estimada
                    </span>
                    <b>R$ {Number(expurgo.economia_total ?? 0).toFixed(2)}</b>
                  </div>
                </div>
              )}
              {(Array.isArray(abusividade.avisos)
                ? abusividade.avisos
                : []
              ).map((aviso: string, index: number) => (
                <p key={index} className="text-xs text-warn-700">
                  {aviso}
                </p>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
            <Calculator className="h-4 w-4" /> Recalcular o CET
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label>
              <span className="label">Valor efetivamente liberado</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={valorLiberado}
                onChange={(event) => setValorLiberado(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Data da liberação</span>
              <input
                className="input w-full"
                type="date"
                value={dataLiberacao}
                onChange={(event) => setDataLiberacao(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Número de parcelas</span>
              <input
                className="input w-full"
                type="number"
                value={cetParcelas}
                onChange={(event) => setCetParcelas(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Valor da parcela</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={valorParcela}
                onChange={(event) => setValorParcela(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Primeiro vencimento</span>
              <input
                className="input w-full"
                type="date"
                value={primeiroVencimento}
                onChange={(event) => setPrimeiroVencimento(event.target.value)}
              />
            </label>
            <label>
              <span className="label">CET informado (% a.a., opcional)</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={cetInformado}
                onChange={(event) => setCetInformado(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Tarifas incluídas</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={tarifas}
                onChange={(event) => setTarifas(event.target.value)}
              />
            </label>
            <label>
              <span className="label">IOF</span>
              <input
                className="input w-full"
                inputMode="decimal"
                value={iof}
                onChange={(event) => setIof(event.target.value)}
              />
            </label>
          </div>
          <button
            className="btn-secondary mt-3 flex items-center gap-2"
            onClick={calcularCet}
            disabled={loadingCet}
          >
            {loadingCet ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Calculator className="h-4 w-4" />
            )}{" "}
            Calcular CET real
          </button>

          {cet && (
            <div className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-2 text-center text-sm">
                <div className="rounded-xl bg-primary-50 p-3 text-primary-900">
                  <span className="block text-xs">CET mensal</span>
                  <b>{cet.cet_mensal_pct ?? cet.cet_mensal}%</b>
                </div>
                <div className="rounded-xl bg-primary-50 p-3 text-primary-900">
                  <span className="block text-xs">CET anual</span>
                  <b>{cet.cet_anual_pct ?? cet.cet_anual}%</b>
                </div>
              </div>
              {cet.divergencia && (
                <p className="rounded-xl bg-warn-50 p-3 text-sm text-warn-800 ring-1 ring-warn-200">
                  CET informado diverge do calculado em{" "}
                  <b>{cet.divergencia.diferenca_pp} ponto(s) percentual(is)</b>.
                </p>
              )}
              {(Array.isArray(cet.memoria_calculo ?? cet.memoria)
                ? (cet.memoria_calculo ?? cet.memoria)
                : []
              ).map((linha: string, index: number) => (
                <p key={index} className="text-xs text-slate-500">
                  {baseCetAtual(linha)}
                </p>
              ))}
              {(Array.isArray(cet.avisos) ? cet.avisos : []).map(
                (aviso: string, index: number) => (
                  <p key={index} className="text-xs text-warn-700">
                    {aviso}
                  </p>
                ),
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
