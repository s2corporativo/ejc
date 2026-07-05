// ── src/components/ImportarDocumento.tsx ─────────────────────────────────────
// Importação inteligente de documento no intake de Casos. Upload PDF/DOCX/imagem/
// XML (NF-e) → /api/documentos-ia/analisar (OCR + extração + diagnóstico) →
// pré-preenche o formulário do caso e exibe a análise. Evoluções R3/R4:
//  • seletor de tipo (GET /documents/tipos, fallback estático — 14 tipos);
//  • sugestão de tipo por IA (POST /documents/sugerir-tipo) com confirmação
//    humana obrigatória — nunca aplicada automaticamente;
//  • revisão da extração campo a campo (campos_v2: valor editável + confiança
//    + trecho de origem). Tudo é MINUTA (revisão obrigatória OAB Prov. 205/2021).
import { Fragment, useEffect, useRef, useState } from "react";
import {
  UploadCloud,
  FileSearch,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ScrollText,
  Sparkles,
} from "lucide-react";
import api from "../lib/api";
import {
  Alert,
  Badge,
  Button,
  FieldLabel,
  Select,
  Input,
  Table,
  THead,
  TR,
  TH,
  TD,
} from "./UI";

type Patch = Record<string, any>;

// ── Tipos de documento (contrato GET /documents/tipos) ───────────────────────
interface TipoDocumento {
  tipo_key: string;
  nome: string;
  categoria: string;
  campos_extracao?: string[] | null;
  extensoes_aceitas?: string[] | null;
}

interface SugestaoTipo {
  tipo_sugerido: string;
  confianca: "alta" | "media" | "baixa" | string;
  justificativa?: string | null;
}

// Linha normalizada de campos_v2 (contrato: {valor, trecho_origem, confianca 0-1,
// origem_verificada}).
interface CampoRevisao {
  campo: string;
  valorOriginal: string;
  valor: string;
  trecho: string;
  confianca: number | null;
  verificada: boolean;
}

// Fallback estático (espelha document_types_master / redesign_seed.py — 14 tipos)
// usado apenas se GET /documents/tipos falhar.
const FALLBACK_TIPOS: TipoDocumento[] = [
  { tipo_key: "contrato", nome: "Contrato", categoria: "juridico" },
  { tipo_key: "peticao", nome: "Petição", categoria: "juridico" },
  { tipo_key: "procuracao", nome: "Procuração", categoria: "juridico" },
  {
    tipo_key: "denuncia",
    nome: "Denúncia / Queixa-crime",
    categoria: "juridico",
  },
  {
    tipo_key: "boletim_ocorrencia",
    nome: "Boletim de Ocorrência",
    categoria: "juridico",
  },
  {
    tipo_key: "laudo_tecnico",
    nome: "Laudo Técnico / Perícia",
    categoria: "juridico",
  },
  {
    tipo_key: "multa_transito",
    nome: "Multa de Trânsito",
    categoria: "administrativo",
  },
  {
    tipo_key: "multa_ambiental",
    nome: "Multa Ambiental",
    categoria: "administrativo",
  },
  {
    tipo_key: "auto_infracao",
    nome: "Auto de Infração (geral)",
    categoria: "administrativo",
  },
  {
    tipo_key: "edital_licitacao",
    nome: "Edital de Licitação",
    categoria: "administrativo",
  },
  {
    tipo_key: "nfe_xml",
    nome: "Nota Fiscal Eletrônica (XML)",
    categoria: "fiscal",
  },
  {
    tipo_key: "doc_identificacao",
    nome: "Documento de Identificação",
    categoria: "pessoal",
  },
  {
    tipo_key: "comprovante_residencia",
    nome: "Comprovante de Residência",
    categoria: "pessoal",
  },
  { tipo_key: "outro", nome: "Outro Documento", categoria: "outro" },
];

const CATEGORIA_LABEL: Record<string, string> = {
  juridico: "Jurídico",
  administrativo: "Administrativo",
  fiscal: "Fiscal",
  pessoal: "Pessoal",
  outro: "Outros",
};

// Campos de campos_v2 que, quando editados, sobrescrevem o patch do formulário.
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

const CONF_SUGESTAO_TONE: Record<string, "green" | "amber" | "red"> = {
  alta: "green",
  media: "amber",
  baixa: "red",
};

function rotuloCampo(campo: string) {
  const s = campo.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Badge de confiança por campo (0-1): ≥0.8 alta/verde · 0.5–0.8 média/âmbar ·
// <0.5 baixa/vermelho.
function BadgeConfiancaCampo({ score }: { score: number | null }) {
  if (score == null) return <Badge tone="slate">sem score</Badge>;
  const tone = score >= 0.8 ? "green" : score >= 0.5 ? "amber" : "red";
  const label = score >= 0.8 ? "alta" : score >= 0.5 ? "média" : "baixa";
  return (
    <Badge tone={tone}>
      {label} · {Math.round(score * 100)}%
    </Badge>
  );
}

function normalizarCamposV2(cv: unknown): CampoRevisao[] {
  if (!cv || typeof cv !== "object" || Array.isArray(cv)) return [];
  return Object.entries(cv as Record<string, unknown>).map(([campo, raw]) => {
    const o = (raw && typeof raw === "object" ? raw : { valor: raw }) as Record<
      string,
      unknown
    >;
    const valor = o.valor == null ? "" : String(o.valor);
    return {
      campo,
      valorOriginal: valor,
      valor,
      trecho: typeof o.trecho_origem === "string" ? o.trecho_origem : "",
      confianca: typeof o.confianca === "number" ? o.confianca : null,
      verificada: o.origem_verificada !== false,
    };
  });
}

function Bloco({ titulo, itens }: { titulo: string; itens?: string[] }) {
  if (!itens || itens.length === 0) return null;
  return (
    <div>
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
        {titulo}
      </p>
      <ul className="list-disc list-inside text-xs text-slate-700 space-y-0.5">
        {itens.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ImportarDocumento({
  onPrefill,
}: {
  onPrefill: (p: Patch) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [d, setD] = useState<any>(null);

  // Tipos de documento + seleção do usuário
  const [tipos, setTipos] = useState<TipoDocumento[]>(FALLBACK_TIPOS);
  const [tipoSelecionado, setTipoSelecionado] = useState("");

  // Sugestão de tipo por IA (nunca aplicada automaticamente)
  const [sugestao, setSugestao] = useState<SugestaoTipo | null>(null);

  // Revisão campo a campo (campos_v2)
  const [camposRevisao, setCamposRevisao] = useState<CampoRevisao[]>([]);
  const [trechoAberto, setTrechoAberto] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    api
      .get<TipoDocumento[]>("/documents/tipos")
      .then(({ data }) => {
        if (ativo && Array.isArray(data) && data.length > 0) setTipos(data);
      })
      .catch(() => {
        // Mantém o fallback estático dos 14 tipos.
      });
    return () => {
      ativo = false;
    };
  }, []);

  const categorias = Array.from(new Set(tipos.map((t) => t.categoria)));

  const analisar = async (file: File) => {
    setLoading(true);
    setErro("");
    setD(null);
    setSugestao(null);
    setCamposRevisao([]);
    setTrechoAberto(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (tipoSelecionado) fd.append("tipo_documento", tipoSelecionado);
      const { data } = await api.post("/documentos-ia/analisar", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setD(data);
      // Revisão campo a campo (R4) — só quando o backend retornar campos_v2.
      setCamposRevisao(normalizarCamposV2(data?.campos_v2));
      // Pré-preenche o formulário do caso com o que foi extraído
      const ip = data.identificacao_processual || {};
      const pa = data.partes || {};
      const cl = data.classificacao || {};
      const re = data.resumo_executivo || {};
      const AREA_OK = [
        "civil",
        "trabalhista",
        "consumidor",
        "familia",
        "ambiental",
        "criminal",
        "previdenciario",
        "empresarial",
        "tributario",
      ];
      // Extração determinística local (regex, sem IA) — presente mesmo quando
      // a interpretação por LLM está indisponível (analise_llm_indisponivel).
      const de = data.dados_estruturados || {};
      const primeiro = (lista?: { valor: string }[]) => lista?.[0]?.valor || "";
      const patch: Patch = {};
      const titulo = cl.materia || re.fatos?.slice(0, 70);
      if (titulo) patch.titulo = titulo;
      if (cl.area && AREA_OK.includes(cl.area)) patch.area = cl.area;
      if (ip.numero_processo) patch.numero_processo = ip.numero_processo;
      else if (primeiro(de.processos_cnj))
        patch.numero_processo = primeiro(de.processos_cnj);
      if (ip.tribunal) patch.tribunal = ip.tribunal;
      if (ip.comarca) patch.comarca = ip.comarca;
      if (ip.vara) patch.vara = ip.vara;
      if (pa.reu) patch.parte_contraria = pa.reu;
      if (data.valor_causa_estimado)
        patch.valor_causa = data.valor_causa_estimado;
      if (re.fatos) patch.descricao_fatos = re.fatos;
      if (cl.complexidade)
        patch.prioridade =
          cl.complexidade === "alta"
            ? "alta"
            : cl.complexidade === "baixa"
              ? "baixa"
              : "media";
      const dp2 = data.dados_pessoais || {};
      patch._extracao = {
        identificacao_processual: ip,
        partes: pa,
        classificacao: cl,
        dados_pessoais: dp2,
      };
      patch._cliente_candidato = {
        nome: pa.autor || "",
        cpf: dp2.cpf || primeiro(de.cpfs),
        cnpj: dp2.cnpj || primeiro(de.cnpjs),
      };
      if (tipoSelecionado) patch._tipo_documento = tipoSelecionado;
      onPrefill(patch);
      // Sugestão de tipo por IA — best-effort; falha não interrompe o fluxo.
      try {
        const { data: sug } = await api.post<SugestaoTipo>(
          "/documents/sugerir-tipo",
          { nome_arquivo: file.name, analise: data },
        );
        if (sug?.tipo_sugerido) setSugestao(sug);
      } catch {
        // Sem sugestão — usuário escolhe manualmente no select.
      }
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha ao analisar o documento.");
    } finally {
      setLoading(false);
    }
  };

  // Valores revisados pelo usuário seguem no fluxo: sobrescrevem o patch do
  // formulário (campos mapeados) e viajam completos em _campos_revisados.
  const emitirRevisao = (linhas: CampoRevisao[]) => {
    const patch: Patch = {
      _campos_revisados: Object.fromEntries(
        linhas.map((l) => [l.campo, l.valor]),
      ),
    };
    for (const l of linhas) {
      const chave = CAMPO_PARA_PATCH[l.campo];
      if (chave && l.valor && l.valor !== l.valorOriginal)
        patch[chave] = l.valor;
    }
    onPrefill(patch);
  };

  const editarCampo = (campo: string, valor: string) => {
    setCamposRevisao((prev) =>
      prev.map((l) => (l.campo === campo ? { ...l, valor } : l)),
    );
  };

  const selecionarTipo = (key: string) => {
    setTipoSelecionado(key);
    if (d) onPrefill({ _tipo_documento: key });
  };

  const tipoSugeridoInfo = sugestao
    ? tipos.find((t) => t.tipo_key === sugestao.tipo_sugerido)
    : undefined;

  const confirmarSugestao = () => {
    if (!sugestao) return;
    selecionarTipo(sugestao.tipo_sugerido);
    setSugestao(null);
  };

  const escolherOutro = () => {
    setSugestao(null);
    document.getElementById("importar-doc-tipo")?.focus();
  };

  const ip = d?.identificacao_processual || {};
  const pa = d?.partes || {};
  const dp = d?.dados_pessoais || {};
  const cl = d?.classificacao || {};
  const re = d?.resumo_executivo || {};
  const di = d?.diagnostico || {};
  const br = d?.brechas_processuais || {};
  const es = d?.estrategia || {};
  const ho = d?.honorarios_sugeridos || {};

  return (
    <div className="card p-4 mb-5 border-l-4 border-bronze bg-bronze-50/20">
      <div className="flex items-center gap-2 mb-1">
        <FileSearch size={16} className="text-bronze" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          Importação inteligente (IA)
        </h3>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Envie a petição, sentença, contrato, multa, NF-e (XML) ou processo
        digitalizado. A IA lê (OCR), extrai partes, número, área e produz um
        diagnóstico — e pré-preenche o caso. Tudo é minuta: revise.
      </p>

      {/* Seletor de tipo de documento (agrupado por categoria) */}
      <div className="mb-3 max-w-sm">
        <FieldLabel>Tipo de documento</FieldLabel>
        <Select
          id="importar-doc-tipo"
          value={tipoSelecionado}
          onChange={(e) => selecionarTipo(e.target.value)}
          disabled={loading}
        >
          <option value="">Detectar automaticamente (IA sugere)</option>
          {categorias.map((cat) => (
            <optgroup key={cat} label={CATEGORIA_LABEL[cat] || cat}>
              {tipos
                .filter((t) => t.categoria === cat)
                .map((t) => (
                  <option key={t.tipo_key} value={t.tipo_key}>
                    {t.nome}
                  </option>
                ))}
            </optgroup>
          ))}
        </Select>
      </div>

      <input
        ref={ref}
        type="file"
        accept=".pdf,.docx,.png,.jpg,.jpeg,.tiff,.webp,.xml,application/pdf,image/*,text/xml,application/xml"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) analisar(f);
          e.target.value = "";
        }}
      />
      <button
        onClick={() => ref.current?.click()}
        disabled={loading}
        className="btn-gold text-sm"
      >
        <UploadCloud size={15} />{" "}
        {loading ? "Analisando documento…" : "Enviar documento"}
      </button>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {d && (
        <div className="mt-4 space-y-3 text-sm">
          {/* Aviso permanente — OAB Prov. 205/2021 */}
          <Alert variant="info">
            Dados extraídos por IA — revisão humana obrigatória antes de gravar
            (OAB Prov. 205/2021).
          </Alert>

          {/* Interpretação por LLM indisponível — a extração determinística
              local (regex, sem IA) segue válida e pré-preenche o caso. */}
          {d.analise_llm_indisponivel && (
            <Alert variant="warning" title="Interpretação por IA indisponível">
              {d.aviso_llm ||
                "A interpretação por IA está indisponível no momento. Os dados abaixo foram extraídos localmente (sem IA) — revise e complete o caso manualmente."}
            </Alert>
          )}

          {/* Sugestão de tipo por IA — exige confirmação humana explícita */}
          {sugestao && (
            <div className="rounded-xl border border-ai-200 bg-ai-50 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Sparkles className="h-4 w-4 shrink-0 text-ai-600" />
                <p className="text-xs text-ai-800">
                  Tipo detectado:{" "}
                  <b>{tipoSugeridoInfo?.nome || sugestao.tipo_sugerido}</b>
                </p>
                <Badge
                  tone={
                    CONF_SUGESTAO_TONE[
                      String(sugestao.confianca).toLowerCase()
                    ] || "slate"
                  }
                >
                  confiança {sugestao.confianca}
                </Badge>
              </div>
              {sugestao.justificativa && (
                <p className="mt-1 text-[11px] text-ai-800/80">
                  {sugestao.justificativa}
                </p>
              )}
              <p className="mt-1 text-[11px] text-ai-700">
                Sugestão de IA — nada é aplicado sem a sua confirmação.
              </p>
              <div className="mt-2 flex gap-2">
                {tipoSugeridoInfo && (
                  <Button
                    type="button"
                    variant="ai"
                    size="sm"
                    icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                    onClick={confirmarSugestao}
                  >
                    Confirmar
                  </Button>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={escolherOutro}
                >
                  Escolher outro
                </Button>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 text-success-700 text-xs">
            <CheckCircle2 size={14} /> Campos do caso pré-preenchidos — confira
            abaixo e ajuste.
          </div>

          {/* Revisão da extração campo a campo (R4 — campos_v2) */}
          {camposRevisao.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
                Revisão da extração — edite os valores antes de gravar
              </p>
              <Table>
                <THead>
                  <TR zebra={false}>
                    <TH>Campo</TH>
                    <TH>Valor (editável)</TH>
                    <TH>Confiança</TH>
                    <TH>Origem</TH>
                  </TR>
                </THead>
                <tbody>
                  {camposRevisao.map((l) => (
                    <Fragment key={l.campo}>
                      <TR>
                        <TD className="text-xs font-medium text-slate-700 whitespace-nowrap">
                          {rotuloCampo(l.campo)}
                        </TD>
                        <TD className="min-w-48">
                          <Input
                            value={l.valor}
                            onChange={(e) =>
                              editarCampo(l.campo, e.target.value)
                            }
                            onBlur={() => emitirRevisao(camposRevisao)}
                            className="h-8 text-xs"
                            aria-label={`Valor extraído de ${rotuloCampo(l.campo)}`}
                          />
                        </TD>
                        <TD>
                          <BadgeConfiancaCampo score={l.confianca} />
                        </TD>
                        <TD>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() =>
                                setTrechoAberto(
                                  trechoAberto === l.campo ? null : l.campo,
                                )
                              }
                              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
                            >
                              {trechoAberto === l.campo ? (
                                <ChevronDown className="h-3.5 w-3.5" />
                              ) : (
                                <ChevronRight className="h-3.5 w-3.5" />
                              )}
                              trecho
                            </button>
                            {!l.verificada && (
                              <span title="Trecho não localizado no documento — confira">
                                <AlertTriangle className="h-3.5 w-3.5 text-warn-600" />
                              </span>
                            )}
                          </div>
                        </TD>
                      </TR>
                      {trechoAberto === l.campo && (
                        <TR zebra={false}>
                          <TD colSpan={4} className="bg-slate-50/70">
                            {l.trecho ? (
                              <blockquote className="border-l-2 border-slate-300 pl-3 text-xs italic text-slate-600">
                                “{l.trecho}”
                              </blockquote>
                            ) : (
                              <p className="text-xs text-slate-400">
                                Sem trecho de origem para este campo.
                              </p>
                            )}
                            {!l.verificada && (
                              <p className="mt-1.5 flex items-center gap-1.5 text-xs text-warn-700">
                                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                Trecho não localizado no documento — confira o
                                original antes de gravar.
                              </p>
                            )}
                          </TD>
                        </TR>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </Table>
            </div>
          )}

          {/* Dados extraídos localmente (determinístico, sem IA) — exibidos
              quando a interpretação por LLM não está disponível. */}
          {d.analise_llm_indisponivel && d.dados_estruturados && (
            <div className="grid sm:grid-cols-2 gap-2 text-xs">
              {(d.dados_estruturados.processos_cnj || [])
                .slice(0, 3)
                .map((o: { valor: string }, i: number) => (
                  <p key={`cnj-${i}`}>
                    <b>Processo:</b> {o.valor}
                  </p>
                ))}
              {(d.dados_estruturados.cpfs || [])
                .slice(0, 3)
                .map((o: { valor: string }, i: number) => (
                  <p key={`cpf-${i}`}>
                    <b>CPF:</b> {o.valor}
                  </p>
                ))}
              {(d.dados_estruturados.cnpjs || [])
                .slice(0, 3)
                .map((o: { valor: string }, i: number) => (
                  <p key={`cnpj-${i}`}>
                    <b>CNPJ:</b> {o.valor}
                  </p>
                ))}
              {(d.dados_estruturados.valores || [])
                .slice(0, 3)
                .map((o: { valor: string }, i: number) => (
                  <p key={`val-${i}`}>
                    <b>Valor:</b> {o.valor}
                  </p>
                ))}
            </div>
          )}

          {/* Identificação + partes */}
          <div className="grid sm:grid-cols-2 gap-2 text-xs">
            {ip.numero_processo && (
              <p>
                <b>Processo:</b> {ip.numero_processo}
              </p>
            )}
            {ip.tribunal && (
              <p>
                <b>Tribunal:</b> {ip.tribunal}
              </p>
            )}
            {ip.comarca && (
              <p>
                <b>Comarca:</b> {ip.comarca}
              </p>
            )}
            {ip.vara && (
              <p>
                <b>Vara:</b> {ip.vara}
              </p>
            )}
            {pa.autor && (
              <p>
                <b>Autor:</b> {pa.autor}
              </p>
            )}
            {pa.reu && (
              <p>
                <b>Réu:</b> {pa.reu}
              </p>
            )}
            {cl.area && (
              <p>
                <b>Área:</b> {cl.area}
                {cl.subarea ? ` · ${cl.subarea}` : ""}
              </p>
            )}
            {cl.complexidade && (
              <p>
                <b>Complexidade:</b> {cl.complexidade}
              </p>
            )}
            {(dp.cpf || dp.cnpj) && (
              <p>
                <b>Doc:</b> {dp.cpf || dp.cnpj}
              </p>
            )}
          </div>

          {re.fatos && (
            <div className="bg-white rounded-lg p-3 border border-bronze-pale">
              <p className="text-[11px] font-semibold text-slate-500 uppercase mb-1 flex items-center gap-1">
                <ScrollText size={12} /> Resumo executivo
              </p>
              <p className="text-xs text-slate-700">{re.fatos}</p>
              {re.pedidos && (
                <p className="text-xs text-slate-600 mt-1">
                  <b>Pedidos:</b> {re.pedidos}
                </p>
              )}
              {re.situacao_processual && (
                <p className="text-xs text-slate-600 mt-1">
                  <b>Situação:</b> {re.situacao_processual}
                </p>
              )}
            </div>
          )}

          <div className="grid sm:grid-cols-2 gap-3">
            <Bloco titulo="Pontos fortes" itens={di.pontos_fortes} />
            <Bloco
              titulo="Pontos fracos / riscos"
              itens={[...(di.pontos_fracos || []), ...(di.riscos || [])]}
            />
          </div>

          {/* Brechas processuais */}
          {br.nulidades?.length ||
          br.teses_defensivas?.length ||
          br.prescricao ||
          br.falhas_documentais?.length ? (
            <div className="bg-warn-50/60 rounded-lg p-3 border border-warn-200">
              <p className="text-[11px] font-semibold text-warn-800 uppercase mb-1 flex items-center gap-1">
                <AlertTriangle size={12} /> Brechas processuais (verificar)
              </p>
              {br.prescricao && (
                <p className="text-xs text-slate-700">
                  <b>Prescrição:</b> {br.prescricao}
                </p>
              )}
              {br.decadencia && (
                <p className="text-xs text-slate-700">
                  <b>Decadência:</b> {br.decadencia}
                </p>
              )}
              <Bloco titulo="Nulidades" itens={br.nulidades} />
              <Bloco
                titulo="Falhas documentais"
                itens={br.falhas_documentais}
              />
              <Bloco titulo="Teses defensivas" itens={br.teses_defensivas} />
            </div>
          ) : null}

          <div className="grid sm:grid-cols-2 gap-3">
            <Bloco
              titulo="Medidas / ações cabíveis"
              itens={[...(es.medidas_cabiveis || []), ...(es.acoes || [])]}
            />
            <Bloco titulo="Provas a produzir" itens={es.producao_de_provas} />
          </div>

          {(ho.recomendado || ho.minimo) && (
            <div className="bg-white rounded-lg p-3 border border-bronze-pale text-xs">
              <p className="text-[11px] font-semibold text-slate-500 uppercase mb-1">
                Honorários sugeridos (tabela OAB — referência)
              </p>
              <div className="grid grid-cols-3 gap-2">
                <p>
                  <b>Mínimo:</b>
                  <br />
                  {ho.minimo || "—"}
                </p>
                <p>
                  <b>Recomendado:</b>
                  <br />
                  {ho.recomendado || "—"}
                </p>
                <p>
                  <b>Estratégico:</b>
                  <br />
                  {ho.estrategico || "—"}
                </p>
              </div>
              {ho.contrato_sugerido && (
                <p className="mt-1">
                  <b>Contrato:</b> {ho.contrato_sugerido}
                </p>
              )}
            </div>
          )}

          {d._aviso && (
            <p className="text-[11px] text-warn-700 border-t border-warn-100 pt-2">
              ⚠ {d._aviso}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
