import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileSearch,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import api from "../lib/api";
import {
  Alert,
  Badge,
  Button,
  FieldLabel,
  Input,
  Select,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "./UI";

type Patch = Record<string, any>;

type TipoDocumento = {
  tipo_key: string;
  nome: string;
  categoria: string;
  campos_extracao?: string[] | null;
};

type Area = { slug: string; nome: string; ativo?: boolean };

type SugestaoTipo = {
  tipo_sugerido: string;
  confianca: "alta" | "media" | "baixa" | string;
  justificativa?: string | null;
};

type CampoRevisao = {
  campo: string;
  valorOriginal: string;
  valor: string;
  trecho: string;
  confianca: number | null;
  verificada: boolean;
};

const FALLBACK_TIPOS: TipoDocumento[] = [
  { tipo_key: "contrato", nome: "Contrato", categoria: "juridico" },
  { tipo_key: "peticao", nome: "Petição", categoria: "juridico" },
  { tipo_key: "procuracao", nome: "Procuração", categoria: "juridico" },
  { tipo_key: "denuncia", nome: "Denúncia / Queixa-crime", categoria: "juridico" },
  { tipo_key: "boletim_ocorrencia", nome: "Boletim de Ocorrência", categoria: "juridico" },
  { tipo_key: "laudo_tecnico", nome: "Laudo Técnico / Perícia", categoria: "juridico" },
  { tipo_key: "sentenca_acordao", nome: "Sentença / Acórdão", categoria: "juridico" },
  { tipo_key: "multa_transito", nome: "Multa de Trânsito", categoria: "administrativo" },
  { tipo_key: "multa_ambiental", nome: "Multa Ambiental", categoria: "administrativo" },
  { tipo_key: "auto_infracao", nome: "Auto de Infração", categoria: "administrativo" },
  { tipo_key: "licitacao_contrato_administrativo", nome: "Licitação / Contrato Administrativo", categoria: "administrativo" },
  { tipo_key: "contrato_bancario", nome: "Contrato Bancário", categoria: "financeiro" },
  { tipo_key: "indeferimento_inss", nome: "Decisão / Indeferimento do INSS", categoria: "previdenciario" },
  { tipo_key: "plano_saude_negativa", nome: "Negativa de Plano de Saúde", categoria: "saude" },
  { tipo_key: "inventario_sucessoes", nome: "Inventário / Sucessões", categoria: "familia" },
  { tipo_key: "nfe_xml", nome: "Nota Fiscal Eletrônica (XML)", categoria: "fiscal" },
  { tipo_key: "doc_identificacao", nome: "Documento de Identificação", categoria: "pessoal" },
  { tipo_key: "comprovante_residencia", nome: "Comprovante de Residência", categoria: "pessoal" },
  { tipo_key: "outro", nome: "Outro Documento", categoria: "outro" },
];

const FALLBACK_AREAS = new Set([
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "ambiental",
  "criminal",
  "previdenciario",
  "empresarial",
  "tributario",
  "administrativo",
  "bancario",
  "imobiliario",
  "sucessoes",
  "constitucional",
  "digital_lgpd",
  "transito",
  "saude",
  "medico",
  "agrario",
  "agronegocio",
  "eleitoral",
  "internacional",
  "contratual",
  "societario",
  "licitacoes",
]);

const CATEGORIA_LABEL: Record<string, string> = {
  juridico: "Jurídico",
  administrativo: "Administrativo",
  financeiro: "Financeiro",
  previdenciario: "Previdenciário",
  saude: "Saúde",
  familia: "Família e Sucessões",
  fiscal: "Fiscal",
  pessoal: "Pessoal",
  outro: "Outros",
};

const CAMPO_PARA_PATCH: Record<string, string> = {
  numero_processo: "numero_processo",
  tribunal: "tribunal",
  comarca: "comarca",
  vara: "vara",
  valor: "valor_causa",
  valor_causa: "valor_causa",
  valor_total: "valor_causa",
  reu: "parte_contraria",
  denunciado: "parte_contraria",
};

const TIPO_PARA_AREA: Record<string, string> = {
  multa_transito: "transito",
  suspensao_cnh: "transito",
  multa_ambiental: "ambiental",
  auto_infracao_ambiental: "ambiental",
  auto_infracao: "administrativo",
  licitacao_contrato_administrativo: "licitacoes",
  contrato_bancario: "bancario",
  cnis: "previdenciario",
  ppp: "previdenciario",
  indeferimento_inss: "previdenciario",
  plano_saude_negativa: "saude",
  inventario_sucessoes: "sucessoes",
  denuncia: "criminal",
  boletim_ocorrencia: "criminal",
};

const rotuloCampo = (campo: string) => {
  const text = campo.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

const primeiro = (items?: Array<{ valor?: string }>) => items?.[0]?.valor || "";

function normalizarCamposV2(value: unknown): CampoRevisao[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value as Record<string, unknown>).map(([campo, raw]) => {
    const item = (raw && typeof raw === "object" ? raw : { valor: raw }) as Record<string, unknown>;
    const normalized = item.valor == null ? "" : String(item.valor);
    return {
      campo,
      valorOriginal: normalized,
      valor: normalized,
      trecho: typeof item.trecho_origem === "string" ? item.trecho_origem : "",
      confianca: typeof item.confianca === "number" ? item.confianca : null,
      verificada: item.origem_verificada !== false,
    };
  });
}

function BadgeConfianca({ score }: { score: number | null }) {
  if (score == null) return <Badge tone="slate">sem score</Badge>;
  const tone: "green" | "amber" | "red" = score >= 0.8 ? "green" : score >= 0.5 ? "amber" : "red";
  return <Badge tone={tone}>{score >= 0.8 ? "alta" : score >= 0.5 ? "média" : "baixa"} · {Math.round(score * 100)}%</Badge>;
}

function Bloco({ titulo, itens }: { titulo: string; itens?: unknown[] }) {
  if (!itens?.length) return null;
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{titulo}</p>
      <ul className="space-y-1 text-xs text-slate-700">
        {itens.map((item, index) => (
          <li key={index} className="rounded-lg bg-white/70 px-3 py-2 dark:bg-white/[0.04]">
            {typeof item === "string" ? item : JSON.stringify(item)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ImportarDocumento({ onPrefill }: { onPrefill: (patch: Patch) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [resultado, setResultado] = useState<any>(null);
  const [tipos, setTipos] = useState<TipoDocumento[]>(FALLBACK_TIPOS);
  const [areasPermitidas, setAreasPermitidas] = useState<Set<string>>(FALLBACK_AREAS);
  const [tipoSelecionado, setTipoSelecionado] = useState("");
  const [sugestao, setSugestao] = useState<SugestaoTipo | null>(null);
  const [campos, setCampos] = useState<CampoRevisao[]>([]);
  const [trechoAberto, setTrechoAberto] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([api.get("/documents/tipos"), api.get("/areas")]).then(([typesResult, areasResult]) => {
      if (!active) return;
      if (typesResult.status === "fulfilled" && Array.isArray(typesResult.value.data) && typesResult.value.data.length) {
        setTipos(typesResult.value.data);
      }
      if (areasResult.status === "fulfilled") {
        const raw = Array.isArray(areasResult.value.data) ? areasResult.value.data : areasResult.value.data?.areas;
        if (Array.isArray(raw) && raw.length) {
          setAreasPermitidas(new Set(raw.filter((area: Area) => area.ativo !== false).map((area: Area) => area.slug)));
        }
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const categorias = useMemo(() => Array.from(new Set(tipos.map((tipo) => tipo.categoria))), [tipos]);

  const emitirRevisao = (linhas: CampoRevisao[]) => {
    const patch: Patch = {
      _campos_revisados: Object.fromEntries(linhas.map((linha) => [linha.campo, linha.valor])),
    };
    for (const linha of linhas) {
      const target = CAMPO_PARA_PATCH[linha.campo];
      if (target && linha.valor && linha.valor !== linha.valorOriginal) patch[target] = linha.valor;
    }
    onPrefill(patch);
  };

  const selecionarTipo = (key: string) => {
    setTipoSelecionado(key);
    const area = TIPO_PARA_AREA[key];
    onPrefill({
      _tipo_documento: key || undefined,
      ...(area && areasPermitidas.has(area) ? { area } : {}),
    });
  };

  const analisar = async (file: File) => {
    setLoading(true);
    setErro("");
    setResultado(null);
    setSugestao(null);
    setCampos([]);
    setTrechoAberto(null);
    try {
      const body = new FormData();
      body.append("file", file);
      if (tipoSelecionado) body.append("tipo_documento", tipoSelecionado);
      const { data } = await api.post("/documentos-ia/analisar", body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResultado(data);
      setCampos(normalizarCamposV2(data?.campos_v2));

      const identification = data.identificacao_processual || {};
      const parties = data.partes || {};
      const classification = data.classificacao || {};
      const contextual = data.classificacao_contextual || {};
      const summary = data.resumo_executivo || {};
      const structured = data.dados_estruturados || {};
      const personal = data.dados_pessoais || {};
      const areaDetected = contextual.area_sugerida || classification.area;
      const patch: Patch = {};
      const title = classification.materia || contextual.subarea_sugerida || summary.fatos?.slice(0, 70);
      if (title) patch.titulo = title;
      if (areaDetected && areasPermitidas.has(areaDetected)) patch.area = areaDetected;
      if (identification.numero_processo || primeiro(structured.processos_cnj)) patch.numero_processo = identification.numero_processo || primeiro(structured.processos_cnj);
      if (identification.tribunal) patch.tribunal = identification.tribunal;
      if (identification.comarca) patch.comarca = identification.comarca;
      if (identification.vara) patch.vara = identification.vara;
      if (parties.reu) patch.parte_contraria = parties.reu;
      if (data.valor_causa_estimado) patch.valor_causa = data.valor_causa_estimado;
      if (summary.fatos) patch.descricao_fatos = summary.fatos;
      if (classification.complexidade) {
        patch.prioridade = classification.complexidade === "alta" ? "alta" : classification.complexidade === "baixa" ? "baixa" : "media";
      }
      patch._extracao = {
        identificacao_processual: identification,
        partes: parties,
        classificacao: {
          ...classification,
          area: areaDetected || classification.area,
          subarea: contextual.subarea_sugerida || classification.subarea,
          rito: contextual.rito_sugerido || classification.rito,
          fase: contextual.fase_sugerida || classification.fase,
          jornada: contextual.jornada_sugerida,
          classificacao_contextual: contextual,
        },
        dados_pessoais: personal,
      };
      patch._cliente_candidato = {
        nome: parties.autor || "",
        cpf: personal.cpf || primeiro(structured.cpfs),
        cnpj: personal.cnpj || primeiro(structured.cnpjs),
      };
      patch._arquivo_original = file;
      if (tipoSelecionado) patch._tipo_documento = tipoSelecionado;
      onPrefill(patch);

      try {
        const { data: suggestion } = await api.post<SugestaoTipo>("/documents/sugerir-tipo", {
          nome_arquivo: file.name,
          analise: data,
        });
        if (suggestion?.tipo_sugerido) setSugestao(suggestion);
      } catch {
        // A classificação contextual local continua válida sem esta sugestão.
      }
    } catch (error: any) {
      setErro(error?.response?.data?.detail || "Falha ao analisar o documento.");
    } finally {
      setLoading(false);
    }
  };

  const contextual = resultado?.classificacao_contextual || {};
  const classification = resultado?.classificacao || {};
  const summary = resultado?.resumo_executivo || {};
  const diagnosis = resultado?.diagnostico || {};
  const strategy = resultado?.estrategia || {};
  const typeInfo = sugestao ? tipos.find((tipo) => tipo.tipo_key === sugestao.tipo_sugerido) : undefined;

  return (
    <div className="card mb-5 border-l-4 border-bronze bg-bronze-50/20 p-4">
      <div className="mb-1 flex items-center gap-2">
        <FileSearch size={16} className="text-bronze" />
        <h3 className="font-serif text-sm font-semibold text-navy">Importação inteligente</h3>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Envie petição, sentença, contrato, multa, documento administrativo ou processo digitalizado. O sistema reconhece área, rito e fase e pré-preenche o caso; tudo permanece sujeito à revisão.
      </p>

      <div className="mb-3 max-w-sm">
        <FieldLabel>Tipo de documento</FieldLabel>
        <Select id="importar-doc-tipo" value={tipoSelecionado} onChange={(event) => selecionarTipo(event.target.value)} disabled={loading}>
          <option value="">Detectar automaticamente</option>
          {categorias.map((category) => (
            <optgroup key={category} label={CATEGORIA_LABEL[category] || category}>
              {tipos.filter((tipo) => tipo.categoria === category).map((tipo) => (
                <option key={tipo.tipo_key} value={tipo.tipo_key}>{tipo.nome}</option>
              ))}
            </optgroup>
          ))}
        </Select>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff,.webp,.xml,application/pdf,image/*,text/xml,application/xml"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void analisar(file);
          event.target.value = "";
        }}
      />
      <button onClick={() => inputRef.current?.click()} disabled={loading} className="btn-gold text-sm">
        <UploadCloud size={15} /> {loading ? "Analisando documento…" : "Enviar documento"}
      </button>
      {erro && <p className="mt-2 text-xs text-danger-600">{erro}</p>}

      {resultado && (
        <div className="mt-4 space-y-3 text-sm">
          <Alert variant="info">Dados extraídos automaticamente — revisão humana obrigatória antes de gravar ou utilizar externamente.</Alert>
          {resultado.analise_llm_indisponivel && (
            <Alert variant="warning" title="Interpretação por IA indisponível">
              {resultado.aviso_llm || "Os dados estruturados foram extraídos localmente. Complete e confira o caso manualmente."}
            </Alert>
          )}

          {contextual.tipo && (
            <div className="rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 text-xs text-primary-900">
              <div className="flex flex-wrap items-center gap-2">
                <FileSearch className="h-4 w-4" />
                <b>Reconhecimento contextual:</b>
                <span>{String(contextual.tipo).replace(/_/g, " ")}</span>
                {contextual.area_sugerida && <Badge tone="blue">{contextual.area_sugerida}</Badge>}
                {typeof contextual.confianca === "number" && <Badge tone={contextual.confianca >= 0.8 ? "green" : "amber"}>confiança {Math.round(contextual.confianca * 100)}%</Badge>}
              </div>
              <p className="mt-2">
                {contextual.subarea_sugerida && <>Subárea: {contextual.subarea_sugerida}. </>}
                {contextual.rito_sugerido && <>Rito: {contextual.rito_sugerido}. </>}
                {contextual.fase_sugerida && <>Fase: {contextual.fase_sugerida}.</>}
              </p>
              {Array.isArray(contextual.jornada_sugerida?.proximas_etapas) && (
                <p className="mt-1 text-primary-700">Próximas etapas sugeridas: {contextual.jornada_sugerida.proximas_etapas.join(" → ")}.</p>
              )}
            </div>
          )}

          {sugestao && (
            <div className="rounded-xl border border-ai-200 bg-ai-50 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Sparkles className="h-4 w-4 text-ai-600" />
                <span className="text-xs text-ai-800">Tipo sugerido: <b>{typeInfo?.nome || sugestao.tipo_sugerido}</b></span>
                <Badge tone={String(sugestao.confianca).toLowerCase() === "alta" ? "green" : String(sugestao.confianca).toLowerCase() === "baixa" ? "red" : "amber"}>{sugestao.confianca}</Badge>
              </div>
              {sugestao.justificativa && <p className="mt-1 text-[11px] text-ai-800/80">{sugestao.justificativa}</p>}
              <div className="mt-2 flex gap-2">
                <Button type="button" variant="ai" size="sm" onClick={() => { selecionarTipo(sugestao.tipo_sugerido); setSugestao(null); }}><CheckCircle2 className="h-3.5 w-3.5" /> Confirmar</Button>
                <Button type="button" variant="secondary" size="sm" onClick={() => setSugestao(null)}>Escolher outro</Button>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 text-xs text-success-700"><CheckCircle2 size={14} /> Campos pré-preenchidos; confira todos antes de criar o caso.</div>

          {campos.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Revisão da extração</p>
              <Table>
                <THead><TR zebra={false}><TH>Campo</TH><TH>Valor editável</TH><TH>Confiança</TH><TH>Origem</TH></TR></THead>
                <tbody>
                  {campos.map((linha) => (
                    <Fragment key={linha.campo}>
                      <TR>
                        <TD className="whitespace-nowrap text-xs font-medium">{rotuloCampo(linha.campo)}</TD>
                        <TD className="min-w-48"><Input value={linha.valor} onChange={(event) => setCampos((current) => current.map((item) => item.campo === linha.campo ? { ...item, valor: event.target.value } : item))} onBlur={() => emitirRevisao(campos)} className="h-8 text-xs" /></TD>
                        <TD><BadgeConfianca score={linha.confianca} /></TD>
                        <TD>
                          {linha.trecho ? (
                            <button type="button" onClick={() => setTrechoAberto((current) => current === linha.campo ? null : linha.campo)} className="inline-flex items-center gap-1 text-xs text-primary-700">
                              {trechoAberto === linha.campo ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Ver trecho
                            </button>
                          ) : linha.verificada ? <Badge tone="green">verificada</Badge> : <Badge tone="amber">conferir</Badge>}
                        </TD>
                      </TR>
                      {trechoAberto === linha.campo && linha.trecho && (
                        <TR><TD colSpan={4}><div className="rounded-lg bg-slate-50 p-3 text-xs italic text-slate-600">“{linha.trecho}”</div></TD></TR>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </Table>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <Bloco titulo="Fatos" itens={summary.fatos ? [summary.fatos] : []} />
            <Bloco titulo="Pedidos" itens={resultado.pedidos || []} />
            <Bloco titulo="Riscos" itens={diagnosis.riscos || resultado.riscos || []} />
            <Bloco titulo="Próximos passos" itens={strategy.proximos_passos || resultado.acoes_contextuais_sugeridas || []} />
          </div>

          {!areasPermitidas.has(contextual.area_sugerida) && contextual.area_sugerida && (
            <Alert variant="warning" title="Área ainda não disponível">
              A área detectada “{contextual.area_sugerida}” não consta na taxonomia ativa. Selecione uma área manualmente antes de criar o caso.
            </Alert>
          )}

          {classification.requer_confirmacao_humana !== false && (
            <div className="flex gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800"><AlertTriangle size={15} className="shrink-0" /> Área, rito, fase, partes, valores e prazos devem ser confirmados pelo advogado.</div>
          )}
        </div>
      )}
    </div>
  );
}
