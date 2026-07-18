import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  Car,
  FileText,
  Gavel,
  Leaf,
  Loader2,
  Save,
  Scale,
  ShieldCheck,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import DefesasRevisoesComplementos from "./DefesasRevisoesComplementos";
import EntradaUniversalDocumentos, { EntradaUniversalResultado } from "./EntradaUniversalDocumentos";
import { toast } from "./Toast";

type Modalidade = {
  codigo: string;
  titulo: string;
  area: string;
  descricao: string;
  pecas: string[];
  documentos: string[];
};
type CasoResumo = { id: string; numero_interno?: string; titulo: string };

const ICONES: Record<string, typeof Gavel> = {
  multa_transito: Car,
  multa_ambiental: Leaf,
  multa_administrativa: Gavel,
  revisao_contratual: FileText,
  revisao_bancaria: Banknote,
};
const ROLES_MOTOR = ["superadmin", "admin", "socio", "advogado"];

const arraySeguro = (valor: unknown): any[] => (Array.isArray(valor) ? valor : []);
const riscoClasse = (risco?: string) =>
  risco === "alto"
    ? "bg-danger-50 text-danger-700 ring-danger-200"
    : risco === "medio"
      ? "bg-warn-50 text-warn-700 ring-warn-200"
      : "bg-slate-100 text-slate-600 ring-slate-200";

function Lista({ titulo, itens }: { titulo: string; itens?: unknown }) {
  const lista = arraySeguro(itens);
  if (!lista.length) return null;
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <h4 className="mb-3 text-sm font-semibold text-slate-950 dark:text-slate-50">{titulo}</h4>
      <div className="space-y-2">
        {lista.map((item: any, index) => (
          <div key={index} className="rounded-xl bg-slate-50 p-3 text-sm dark:bg-white/[0.04]">
            {typeof item === "string" ? (
              <p className="text-slate-700 dark:text-slate-200">{item}</p>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-medium text-slate-900 dark:text-slate-50">
                    {item?.titulo || item?.item || item?.evento || item?.vicio_ou_tese || "Item de análise"}
                  </p>
                  {item?.risco && <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${riscoClasse(item.risco)}`}>{item.risco}</span>}
                  {item?.status && <span className="rounded-full bg-primary-50 px-2 py-0.5 text-[11px] font-semibold text-primary-700 ring-1 ring-primary-100">{item.status}</span>}
                </div>
                {item?.analise && <p className="mt-1 text-slate-600 dark:text-slate-300">{item.analise}</p>}
                {item?.fato && <p className="mt-1 text-xs text-slate-500">Fato: {item.fato}</p>}
                {item?.prova && <p className="mt-1 text-xs text-slate-500">Prova: {item.prova}</p>}
                {item?.fundamento && <p className="mt-1 text-xs text-slate-500">Fundamento: {item.fundamento}</p>}
                {item?.data && <p className="mt-1 text-xs text-slate-500">Data: {item.data}</p>}
                {(item?.origem_literal || item?.trecho_literal) && <p className="mt-1 text-xs italic text-slate-500">“{item.origem_literal || item.trecho_literal}”</p>}
                {item?.fonte && <p className="mt-1 text-xs text-slate-500">Fonte: {item.fonte}</p>}
                {arraySeguro(item?.fatos).length > 0 && <p className="mt-1 text-xs text-slate-500">Fatos: {arraySeguro(item.fatos).join("; ")}</p>}
                {arraySeguro(item?.provas).length > 0 && <p className="mt-1 text-xs text-slate-500">Provas: {arraySeguro(item.provas).join("; ")}</p>}
              </>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DefesasRevisoesPanel() {
  const user = useAuth((state) => state.user);
  const [modalidades, setModalidades] = useState<Modalidade[]>([]);
  const [modalidade, setModalidade] = useState("");
  const [casos, setCasos] = useState<CasoResumo[]>([]);
  const [caseId, setCaseId] = useState("");
  const [resultadoEntrada, setResultadoEntrada] = useState<EntradaUniversalResultado | null>(null);
  const [resultado, setResultado] = useState<any>(null);
  const [analisando, setAnalisando] = useState(false);
  const [encaminhando, setEncaminhando] = useState(false);
  const [salvando, setSalvando] = useState(false);

  const podeMotor = ROLES_MOTOR.includes(user?.role || "");

  useEffect(() => {
    Promise.all([
      api.get("/defesas-revisoes/meta"),
      api.get("/cases/", { params: { page_size: 100 } }),
    ])
      .then(([meta, casosResp]) => {
        const lista = arraySeguro(meta.data?.modalidades) as Modalidade[];
        setModalidades(lista);
        setModalidade((atual) => atual || lista[0]?.codigo || "");
        setCasos(arraySeguro(casosResp.data?.data) as CasoResumo[]);
      })
      .catch(() => toast.error("Não foi possível carregar o módulo de Defesas e Revisões."));
  }, []);

  const selecionada = useMemo(
    () => modalidades.find((item) => item.codigo === modalidade),
    [modalidade, modalidades],
  );

  const analisarLote = async (entrada: EntradaUniversalResultado) => {
    setResultadoEntrada(entrada);
    setResultado(null);
    setAnalisando(true);
    const form = new FormData();
    form.append("modalidade", modalidade);
    form.append("batch_id", entrada.batch_id);
    if (caseId) form.append("case_id", caseId);
    try {
      const { data } = await api.post("/defesas-revisoes/analisar", form);
      setResultado(data);
      toast.success("Pacote documental transformado em estratégia jurídica revisável.");
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Falha ao montar a estratégia jurídica.");
    } finally {
      setAnalisando(false);
    }
  };

  const resumoParaMotor = () => {
    if (!resultado) return "";
    const teses = arraySeguro(resultado.teses || resultado.matriz_vicios_teses)
      .slice(0, 12)
      .map((item: any) => `- ${item?.titulo || item?.vicio_ou_tese || "Tese"}: ${item?.fundamento || "verificar"}`)
      .join("\n");
    const pendencias = arraySeguro(resultado.documentos_faltantes).map((item) => `- ${item}`).join("\n");
    return [
      `DEFESAS E REVISÕES — ${selecionada?.titulo || modalidade}`,
      `Lote universal: ${resultadoEntrada?.batch_id || resultado.batch_id || "não informado"}`,
      `Prontidão: ${resultado.nivel_prontidao || resultadoEntrada?.nivel_prontidao || "a confirmar"}`,
      resultado.resumo || resultado.resumo_executivo?.fatos || "",
      `Peça sugerida: ${resultado.peca_recomendada?.nome || resultado.peca_recomendada?.codigo || "a confirmar"}`,
      resultado.peca_recomendada?.justificativa || "",
      teses ? `Teses:\n${teses}` : "",
      pendencias ? `Documentos pendentes:\n${pendencias}` : "",
      "Rascunho gerado por IA — revisão jurídica obrigatória.",
    ].filter(Boolean).join("\n\n");
  };

  const salvarNoCaso = async () => {
    if (!caseId) return toast.error("Selecione o caso para salvar a análise.");
    setSalvando(true);
    try {
      await api.post("/defesas-revisoes/avancado/persistir", {
        case_id: caseId,
        modalidade,
        resultado,
      });
      if (resultadoEntrada?.batch_id) {
        await api.post(`/entrada-universal/${resultadoEntrada.batch_id}/preparar-pacote`, { salvar_no_caso: true });
      }
      toast.success("Dossiê, checklist, tarefas e pacote registrados no caso.");
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Falha ao persistir a jornada.");
    } finally {
      setSalvando(false);
    }
  };

  const encaminharMotor = async () => {
    if (!podeMotor) return toast.error("A geração da peça exige advogado ou gestor jurídico.");
    if (!caseId) return toast.error("Vincule a análise a um caso.");
    const codigo = resultado?.motor_peca_codigo;
    if (!codigo) return toast.error("Resolva as pendências impeditivas ou use o gerador geral de peças.");
    setEncaminhando(true);
    try {
      const { data } = await api.post(`/cases/${caseId}/motor-peca/analisar`, {
        texto: resumoParaMotor(),
        tipo_documento: resultado.tipo_documento,
        fase: resultado.fase,
        peca_codigo: codigo,
        incluir_motivacao_ia: true,
      });
      setResultado((atual: any) => ({ ...atual, motor_peca: data }));
      toast.success("Motor de Peça executado. Revise checklist, documentos e prazo.");
    } catch (error: any) {
      const detalhe = error.response?.data?.detail;
      toast.error(detalhe?.mensagem || (typeof detalhe === "string" ? detalhe : "Falha no Motor de Peça."));
    } finally {
      setEncaminhando(false);
    }
  };

  return (
    <section id="defesas-revisoes" className="space-y-5 rounded-[2rem] border border-primary-100 bg-gradient-to-br from-white via-white to-primary-50/60 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.10)] dark:border-white/10 dark:from-white/[0.05] dark:via-white/[0.03] dark:to-primary-950/20">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="max-w-3xl">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary-700"><ShieldCheck className="h-4 w-4" /> Módulo jurídico integrado</div>
          <h2 className="text-2xl font-semibold text-slate-950 dark:text-white">Defesas e Revisões</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">Importe o pacote completo, organize documentos, confira a prontidão e produza a estratégia para trânsito, ambiental, administrativo, contratos e bancos.</p>
        </div>
        <div className="rounded-2xl bg-warn-50 p-3 text-xs text-warn-800 ring-1 ring-warn-200"><div className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span>Prazos, abusividade, classificação e cabimento nunca são confirmados automaticamente.</span></div></div>
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        {modalidades.map((item) => {
          const Icon = ICONES[item.codigo] || Scale;
          const ativo = item.codigo === modalidade;
          return (
            <button key={item.codigo} type="button" onClick={() => { setModalidade(item.codigo); setResultado(null); setResultadoEntrada(null); }} className={`rounded-2xl border p-3 text-left transition ${ativo ? "border-primary-400 bg-primary-50 ring-2 ring-primary-100 dark:bg-primary-950/30" : "border-slate-200 bg-white hover:-translate-y-0.5 hover:border-primary-200 dark:border-white/10 dark:bg-white/[0.03]"}`}>
              <Icon className={`mb-2 h-5 w-5 ${ativo ? "text-primary-700" : "text-slate-500"}`} />
              <div className="text-sm font-semibold text-slate-900 dark:text-white">{item.titulo}</div>
              <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-300">{item.descricao}</div>
            </button>
          );
        })}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
        <label className="label">Caso vinculado (recomendado)</label>
        <select className="input w-full" value={caseId} onChange={(event) => { setCaseId(event.target.value); setResultado(null); setResultadoEntrada(null); }}>
          <option value="">Analisar sem vincular a caso</option>
          {casos.map((caso) => <option key={caso.id} value={caso.id}>{caso.numero_interno ? `${caso.numero_interno} — ` : ""}{caso.titulo}</option>)}
        </select>
      </div>

      {modalidade && (
        <EntradaUniversalDocumentos
          key={`${modalidade}:${caseId}`}
          modalidade={modalidade}
          caseId={caseId || undefined}
          onProcessado={analisarLote}
          processarLabel="Importar pacote e montar estratégia"
          titulo={`Documentos para ${selecionada?.titulo || "defesa ou revisão"}`}
          descricao="Envie o documento inicial e os complementos. O sistema preservará os originais, organizará as páginas, apontará ausências e só liberará a redação quando o conjunto estiver apto."
        />
      )}

      {analisando && <div className="flex items-center justify-center gap-2 rounded-2xl border border-primary-100 bg-primary-50 p-5 text-sm font-medium text-primary-800"><Loader2 className="h-5 w-5 animate-spin" /> Aplicando o motor jurídico especializado ao pacote documental…</div>}

      {resultado && (
        <div className="space-y-4 border-t border-slate-200 pt-5 dark:border-white/10">
          <div className="grid gap-3 lg:grid-cols-3">
            <div className="rounded-2xl bg-slate-950 p-4 text-white lg:col-span-2">
              <p className="text-xs uppercase tracking-wider text-slate-300">Diagnóstico</p>
              <h3 className="mt-1 text-lg font-semibold">{resultado.peca_recomendada?.nome || "Providência a confirmar"}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-200">{resultado.resumo}</p>
              {resultado.peca_recomendada?.justificativa && <p className="mt-2 text-xs text-slate-300">{resultado.peca_recomendada.justificativa}</p>}
            </div>
            <div className="rounded-2xl bg-warn-50 p-4 text-warn-900 ring-1 ring-warn-200">
              <p className="text-xs font-semibold uppercase tracking-wider">Prazo</p>
              <p className="mt-2 text-sm font-medium">{resultado.prazo?.data_expressa_no_documento || resultado.prazo?.data_expressa || "Sem data final confirmada"}</p>
              <p className="mt-1 text-xs leading-5">{resultado.prazo?.regra || "Verificar regra e termo inicial."}</p>
              <p className="mt-2 text-[11px] font-semibold">Confirmação humana obrigatória</p>
            </div>
          </div>

          {resultado.juros_taxas && modalidade === "revisao_bancaria" && (
            <section className="rounded-2xl border border-primary-200 bg-primary-50 p-4 dark:bg-primary-950/20">
              <h4 className="flex items-center gap-2 text-sm font-semibold text-primary-950 dark:text-primary-100"><Banknote className="h-4 w-4" /> Juros, CET e encargos identificados</h4>
              <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div><span className="block text-xs text-slate-500">Taxa mensal</span><b>{resultado.juros_taxas.taxa_mensal ?? "não identificada"}</b></div>
                <div><span className="block text-xs text-slate-500">Taxa anual</span><b>{resultado.juros_taxas.taxa_anual ?? "não identificada"}</b></div>
                <div><span className="block text-xs text-slate-500">CET</span><b>{resultado.juros_taxas.cet ?? "não identificado"}</b></div>
                <div><span className="block text-xs text-slate-500">Capitalização</span><b>{resultado.juros_taxas.capitalizacao ?? "indefinido"}</b></div>
              </div>
            </section>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <Lista titulo="Datas e eventos encontrados" itens={resultado.datas_eventos} />
            <Lista titulo="Vícios formais" itens={resultado.vicios_formais} />
            <Lista titulo="Questões de mérito" itens={resultado.questoes_de_merito} />
            <Lista titulo="Matriz de teses" itens={resultado.teses || resultado.matriz_vicios_teses} />
            <Lista titulo="Checklist obrigatório" itens={resultado.checklist_obrigatorio} />
            <Lista titulo="Documentos faltantes" itens={resultado.documentos_faltantes} />
          </div>

          {resultado.motor_peca && <section className="rounded-2xl border border-success-200 bg-success-50 p-4"><h4 className="text-sm font-semibold text-success-900">Motor de Peça concluído</h4><p className="mt-1 text-sm text-success-800">Peça principal: {resultado.motor_peca.peca_principal || "a confirmar"}. Checklist: {resultado.motor_peca.checklist?.pronto ? "pronto" : "possui pendências"}.</p></section>}

          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary flex items-center gap-2" onClick={salvarNoCaso} disabled={!caseId || salvando}>{salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Persistir jornada no caso</button>
            {resultado.motor_peca_codigo && podeMotor && <button className="btn-gold flex items-center gap-2" onClick={encaminharMotor} disabled={encaminhando || !caseId}>{encaminhando ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} Encaminhar ao Motor de Peça</button>}
            {!resultado.motor_peca_codigo && podeMotor && <Link to={`/pecas${caseId ? `?case_id=${caseId}` : ""}`} className="btn-gold flex items-center gap-2"><ArrowRight className="h-4 w-4" /> Abrir gerador de peças</Link>}
            {caseId && <Link to={`/casos/${caseId}/jornada`} className="btn-ghost">Abrir Jornada do Caso</Link>}
          </div>

          <DefesasRevisoesComplementos modalidade={modalidade} caseId={caseId} resultado={resultado} />

          {arraySeguro(resultado.fontes).length > 0 && <section className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]"><h4 className="text-sm font-semibold text-slate-900 dark:text-white">Fontes recuperadas pela IA</h4><ul className="mt-2 space-y-1 text-xs text-slate-500">{arraySeguro(resultado.fontes).map((fonte: any, index: number) => <li key={index}>• {fonte?.titulo || fonte?.fonte || "Fonte interna"}{fonte?.categoria ? ` — ${fonte.categoria}` : ""}</li>)}</ul></section>}
          <p className="text-xs text-warn-700">{resultado.aviso}</p>
        </div>
      )}
    </section>
  );
}
