import { useEffect, useRef, useState } from "react";
import {
  Archive,
  Calculator,
  FileDiff,
  FileSearch,
  FolderArchive,
  Loader2,
  PackageCheck,
  Scale,
  ShieldAlert,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";

type Props = {
  modalidade: string;
  caseId: string;
  resultado: any;
};

type Aba = "operacao" | "comparar" | "calculos" | "viabilidade" | "decisao" | "memoria";

const numero = (valor: string) => {
  const normalizado = valor.trim().replace(/\./g, "").replace(",", ".");
  const parsed = Number(normalizado);
  return Number.isFinite(parsed) ? parsed : 0;
};

const ABAS: { id: Aba; label: string; icon: typeof Scale }[] = [
  { id: "operacao", label: "Operação", icon: PackageCheck },
  { id: "comparar", label: "Comparar", icon: FileDiff },
  { id: "calculos", label: "Cálculos", icon: Calculator },
  { id: "viabilidade", label: "Viabilidade", icon: Scale },
  { id: "decisao", label: "Nova decisão", icon: FileSearch },
  { id: "memoria", label: "Memória", icon: Archive },
];

export default function DefesasRevisoesComplementos({ modalidade, caseId, resultado }: Props) {
  const [aba, setAba] = useState<Aba>("operacao");
  const [loading, setLoading] = useState("");
  const [saida, setSaida] = useState<any>(null);
  const [base, setBase] = useState<File | null>(null);
  const [comparado, setComparado] = useState<File | null>(null);
  const [decisao, setDecisao] = useState<File | null>(null);
  const [valores, setValores] = useState<Record<string, string>>({
    beneficio_provavel: "",
    honorarios: "",
    custas: "",
    pericia: "",
    outras_despesas: "",
    risco_sucumbencia: "",
    probabilidade_exito_pct: "50",
    valor_base: "",
    agravantes_pct: "",
    atenuantes_pct: "",
    reincidencia_pct: "",
    valor_contrato: "",
    multa: "",
    dano_estimado: "",
    valor_controvertido: "",
    valor_liberado: "",
    parcela: "",
    parcelas: "",
    tarifas: "",
    seguros: "",
    pontuacoes: "",
    limite_informado: "",
  });

  // Guarda de corrida: identifica a requisição vigente. Trocar de aba (ou de
  // modalidade/caso) invalida respostas em voo, para que uma operação da aba
  // anterior não preencha a `saida` da aba nova.
  const reqIdRef = useRef(0);

  useEffect(() => {
    reqIdRef.current += 1; // descarta qualquer resposta em voo
    setSaida(null);
    setLoading("");
  }, [aba, modalidade, caseId]);

  const executar = async (nome: string, acao: () => Promise<any>, sucesso: string) => {
    const meuReqId = ++reqIdRef.current;
    setLoading(nome);
    setSaida(null);
    try {
      const data = await acao();
      if (reqIdRef.current !== meuReqId) return; // resposta obsoleta
      setSaida(data);
      toast.success(sucesso);
    } catch (error: any) {
      if (reqIdRef.current !== meuReqId) return; // erro obsoleto
      toast.error(error.response?.data?.detail || "Não foi possível concluir a operação.");
    } finally {
      if (reqIdRef.current === meuReqId) setLoading("");
    }
  };

  const persistir = () => {
    if (!caseId) return toast.error("Selecione um caso para persistir o diagnóstico.");
    return executar(
      "persistir",
      async () => (await api.post("/defesas-revisoes/avancado/persistir", { case_id: caseId, modalidade, resultado })).data,
      "Dossiê, checklist e tarefas registrados no caso.",
    );
  };

  const pacote = () => {
    if (!caseId) return toast.error("Selecione um caso para gerar o pacote.");
    return executar(
      "pacote",
      async () => (await api.post("/defesas-revisoes/avancado/pacote", { case_id: caseId, modalidade, resultado })).data,
      "Pacote documental criado como rascunho.",
    );
  };

  const adversarial = () => executar(
    "adversarial",
    async () => (await api.post("/defesas-revisoes/avancado/adversarial", { case_id: caseId || undefined, modalidade, resultado })).data,
    "Crítica adversarial concluída.",
  );

  const comparar = () => {
    if (!base || !comparado) return toast.error("Selecione os dois documentos para comparação.");
    const form = new FormData();
    form.append("modalidade", modalidade);
    if (caseId) form.append("case_id", caseId);
    form.append("arquivo_base", base);
    form.append("arquivo_comparado", comparado);
    return executar(
      "comparar",
      async () => (await api.post("/defesas-revisoes/avancado/comparar-documentos", form)).data,
      "Comparação documental concluída.",
    );
  };

  const calcular = () => {
    const payload: Record<string, any> = { modalidade };
    Object.entries(valores).forEach(([chave, valor]) => {
      if (!valor.trim()) return;
      payload[chave] = chave === "pontuacoes"
        ? valor.split(/[,;\s]+/).filter(Boolean).map((item) => Number(item))
        : numero(valor);
    });
    return executar(
      "calcular",
      async () => (await api.post("/defesas-revisoes/avancado/calcular-especialidade", payload)).data,
      "Simulação determinística concluída.",
    );
  };

  const viabilidade = () => {
    const payload: Record<string, number> = {};
    [
      "beneficio_provavel", "honorarios", "custas", "pericia",
      "outras_despesas", "risco_sucumbencia", "probabilidade_exito_pct",
    ].forEach((chave) => { payload[chave] = numero(valores[chave] || "0"); });
    return executar(
      "viabilidade",
      async () => (await api.post("/defesas-revisoes/avancado/viabilidade", payload)).data,
      "Viabilidade econômica calculada.",
    );
  };

  const analisarDecisao = () => {
    if (!caseId || !decisao) return toast.error("Selecione o caso e a nova decisão.");
    const form = new FormData();
    form.append("modalidade", modalidade);
    form.append("case_id", caseId);
    form.append("resultado_anterior", JSON.stringify(resultado || {}));
    form.append("decisao", decisao);
    return executar(
      "decisao",
      async () => (await api.post("/defesas-revisoes/avancado/analisar-decisao", form)).data,
      "Decisão comparada com a estratégia anterior.",
    );
  };

  const memoria = () => executar(
    "memoria",
    async () => (await api.get(`/defesas-revisoes/avancado/memoria/${modalidade}`)).data,
    "Memória institucional carregada.",
  );

  const campo = (chave: string, label: string, placeholder = "0") => (
    <label className="block">
      <span className="label">{label}</span>
      <input
        className="input w-full"
        inputMode="decimal"
        value={valores[chave] || ""}
        onChange={(event) => setValores((atual) => ({ ...atual, [chave]: event.target.value }))}
        placeholder={placeholder}
      />
    </label>
  );

  const calculosPorModalidade = () => {
    if (modalidade === "multa_transito") return (
      <div className="grid gap-3 md:grid-cols-2">
        {campo("pontuacoes", "Pontuações das infrações", "Ex.: 4, 5, 7")}
        {campo("limite_informado", "Limite aplicável confirmado", "Informe somente após conferir")}
      </div>
    );
    if (modalidade === "multa_ambiental" || modalidade === "multa_administrativa") return (
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {campo("valor_base", "Valor-base")}
        {campo("agravantes_pct", "Agravantes (%)")}
        {campo("reincidencia_pct", "Reincidência (%)")}
        {campo("atenuantes_pct", "Atenuantes (%)")}
      </div>
    );
    if (modalidade === "revisao_contratual") return (
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {campo("valor_contrato", "Valor do contrato")}
        {campo("multa", "Multa contratual")}
        {campo("dano_estimado", "Dano estimado")}
        {campo("valor_controvertido", "Valor controvertido")}
      </div>
    );
    return (
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {campo("valor_liberado", "Valor efetivamente liberado")}
        {campo("parcela", "Valor da parcela")}
        {campo("parcelas", "Quantidade de parcelas")}
        {campo("tarifas", "Tarifas")}
        {campo("seguros", "Seguros")}
      </div>
    );
  };

  return (
    <section className="space-y-4 rounded-[2rem] border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary-700">
          <ShieldAlert className="h-4 w-4" /> Jornada avançada
        </div>
        <h3 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">Concluir, validar e acompanhar o caso</h3>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">
          Persista a estratégia, gere o pacote, confronte a tese, compare documentos, faça cálculos e analise a próxima decisão.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {ABAS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setAba(id)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition ${aba === id ? "bg-primary-700 text-white ring-primary-700" : "bg-slate-50 text-slate-600 ring-slate-200 dark:bg-white/5 dark:text-slate-200 dark:ring-white/10"}`}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

      {aba === "operacao" && (
        <div className="grid gap-3 md:grid-cols-3">
          <button className="btn-secondary flex items-center justify-center gap-2" onClick={persistir} disabled={!caseId || Boolean(loading)}>
            {loading === "persistir" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderArchive className="h-4 w-4" />} Persistir dossiê e checklist
          </button>
          <button className="btn-gold flex items-center justify-center gap-2" onClick={pacote} disabled={!caseId || Boolean(loading)}>
            {loading === "pacote" ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackageCheck className="h-4 w-4" />} Gerar pacote documental
          </button>
          <button className="btn-ghost flex items-center justify-center gap-2" onClick={adversarial} disabled={Boolean(loading)}>
            {loading === "adversarial" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />} Atacar a estratégia
          </button>
        </div>
      )}

      {aba === "comparar" && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <label><span className="label">Documento-base</span><input className="input w-full" type="file" onChange={(e) => setBase(e.target.files?.[0] || null)} /></label>
            <label><span className="label">Documento novo/aditivo</span><input className="input w-full" type="file" onChange={(e) => setComparado(e.target.files?.[0] || null)} /></label>
          </div>
          <button className="btn-gold flex items-center gap-2" onClick={comparar} disabled={Boolean(loading)}><FileDiff className="h-4 w-4" /> Comparar integralmente</button>
        </div>
      )}

      {aba === "calculos" && <div className="space-y-3">{calculosPorModalidade()}<button className="btn-secondary flex items-center gap-2" onClick={calcular} disabled={Boolean(loading)}><Calculator className="h-4 w-4" /> Calcular</button></div>}

      {aba === "viabilidade" && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {campo("beneficio_provavel", "Benefício provável")}
            {campo("honorarios", "Honorários")}
            {campo("custas", "Custas")}
            {campo("pericia", "Perícia")}
            {campo("outras_despesas", "Outras despesas")}
            {campo("risco_sucumbencia", "Risco de sucumbência")}
            {campo("probabilidade_exito_pct", "Probabilidade estimada (%)", "50")}
          </div>
          <button className="btn-secondary flex items-center gap-2" onClick={viabilidade} disabled={Boolean(loading)}><Scale className="h-4 w-4" /> Avaliar viabilidade</button>
        </div>
      )}

      {aba === "decisao" && (
        <div className="space-y-3">
          <label><span className="label">Nova decisão, julgamento ou resposta</span><input className="input w-full" type="file" onChange={(e) => setDecisao(e.target.files?.[0] || null)} /></label>
          <button className="btn-gold flex items-center gap-2" onClick={analisarDecisao} disabled={!caseId || Boolean(loading)}><FileSearch className="h-4 w-4" /> Comparar e indicar próxima medida</button>
        </div>
      )}

      {aba === "memoria" && <button className="btn-secondary flex items-center gap-2" onClick={memoria} disabled={Boolean(loading)}><Archive className="h-4 w-4" /> Consultar casos semelhantes do escritório</button>}

      {loading && !["persistir", "pacote", "adversarial"].includes(loading) && <div className="flex items-center gap-2 rounded-xl bg-primary-50 p-3 text-sm text-primary-800"><Loader2 className="h-4 w-4 animate-spin" /> Processando…</div>}

      {saida && (
        <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">
          {JSON.stringify(saida, null, 2)}
        </pre>
      )}
    </section>
  );
}
