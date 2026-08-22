import { toast } from "../components/Toast";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import {
  Plus,
  Search,
  LayoutGrid,
  Gavel,
  Handshake,
  FileSignature,
  FileUp,
  PenLine,
  Archive,
  ArchiveRestore,
  Trash2,
  AlertTriangle,
  RotateCw,
} from "lucide-react";
import api, { aplicarExtracao, vincularLoteAoCaso } from "../lib/api";
import { asList } from "../lib/list";
import { areaLabel, useAreas } from "../lib/areas";
import { caseJourneyPath } from "../lib/caseContext";
import type {
  AplicarExtracaoResult,
  ExtracaoPayload,
  VincularLoteResult,
} from "../lib/api";

/**
 * O vínculo de lote pode retornar 200 com `conflitos` (itens que apontam para
 * documento de outro caso sem arquivo clonável — ex.: ausente/externo). Isso
 * NÃO é sucesso pleno: avisa o usuário quais documentos ficaram de fora e onde
 * resolvê-los, em vez de seguir em silêncio.
 */
function avisarConflitosDeVinculo(vinc: VincularLoteResult) {
  const conflitos = vinc?.conflitos ?? [];
  if (conflitos.length === 0) return;
  const nomes = conflitos
    .slice(0, 3)
    .map((c) => c.filename)
    .join(", ");
  const extra = conflitos.length > 3 ? ` e mais ${conflitos.length - 3}` : "";
  toast.error(
    `${conflitos.length} documento(s) do lote não puderam ser vinculados ao caso ` +
      `(${nomes}${extra}). Eles permanecem na Entrada Universal/GED de origem — ` +
      `verifique e anexe manualmente pelo caso.`,
  );
}
import {
  carregarRascunho,
  salvarRascunho,
  atualizarRascunho,
  limparRascunho,
  snapshotForm,
  pendenciaDeRascunho,
  type IntakeRascunho,
  type IntakePendencia,
} from "../lib/intakeRascunho";
import type { Case, Client, Paged, User } from "../types";
import {
  PageHeader,
  StatusBadge,
  Modal,
  ConfirmModal,
  FieldLabel,
  Textarea,
  Empty,
  EmptyState,
  SkeletonTable,
  Button,
  fmtDate,
  SigiloReforcadoField,
} from "../components/UI";
import { useAuth } from "../stores/auth";
import { CasosStats } from "../components/Dashboards";
import ImportarDocumento from "../components/ImportarDocumento";
import NovoCasoWizard from "../components/NovoCasoWizard";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
  resolverModoNovoCaso,
} from "../lib/novoCaso";
import {
  rascunhoCobreRevisao,
  urlRevisaoPendente,
  urlSemParamRevisao,
} from "../lib/revisaoExtracao";
import Kanban from "./Kanban";
import { List } from "lucide-react";

// Taxonomia canônica de áreas: GET /areas via useAreas(), com fallback
// completo do enum CaseArea (25 áreas) em lib/areas.ts.

const CASE_TYPES = [
  { k: "judicial", l: "Judicial", icon: Gavel },
  { k: "extrajudicial", l: "Extrajudicial", icon: Handshake },
  { k: "consultoria", l: "Consultoria", icon: FileSignature },
];
const CASE_TYPE_LABEL: Record<string, string> = {
  judicial: "Judicial",
  extrajudicial: "Extrajudicial",
  consultoria: "Consultoria",
};
const CASE_TYPE_COLOR: Record<string, string> = {
  judicial: "bg-primary-100 text-primary-700",
  extrajudicial: "bg-warn-100 text-warn-700",
  consultoria: "bg-ai-100 text-ai-700",
};
const EXTRAJ_TYPES = [
  { k: "notificacao", l: "Notificação" },
  { k: "acordo", l: "Acordo" },
  { k: "contrato", l: "Contrato" },
  { k: "parecer", l: "Parecer" },
  { k: "due_diligence", l: "Due Diligence" },
  { k: "negociacao", l: "Negociação" },
];

// Catálogo de prescrição/decadência — espelha app/services/calc/prescricao.py.
// As chaves (k) DEVEM ser idênticas às do backend: ele recusa qualquer outra.
// Enviando { tipo_acao_prescricao: k, data_fato_prescricao } o backend calcula data_prescricao.
const PRESCRICAO: {
  grupo: string;
  itens: { k: string; nm: string; base: string }[];
}[] = [
  {
    grupo: "Cível (Código Civil)",
    itens: [
      {
        k: "civel_geral",
        nm: "Prescrição geral — pretensões pessoais (10 anos)",
        base: "CC art. 205",
      },
      {
        k: "reparacao_civil",
        nm: "Reparação civil extracontratual (3 anos)",
        base: "CC art. 206 §3º V",
      },
      {
        k: "cobranca_liquida",
        nm: "Cobrança de dívida líquida (5 anos)",
        base: "CC art. 206 §5º I",
      },
      {
        k: "honorarios_profissionais",
        nm: "Honorários de profissional liberal (5 anos)",
        base: "CC art. 206 §5º II",
      },
      {
        k: "enriquecimento_sem_causa",
        nm: "Enriquecimento sem causa (3 anos)",
        base: "CC art. 206 §3º IV",
      },
      {
        k: "seguro",
        nm: "Segurado × segurador (1 ano)",
        base: "CC art. 206 §1º II",
      },
      {
        k: "alugueis",
        nm: "Cobrança de aluguéis (3 anos)",
        base: "CC art. 206 §3º I",
      },
    ],
  },
  {
    grupo: "Consumidor (CDC)",
    itens: [
      {
        k: "cdc_reparacao_fato",
        nm: "Acidente de consumo / fato do produto (5 anos)",
        base: "CDC art. 27",
      },
      {
        k: "cdc_vicio_nao_duravel",
        nm: "Vício — produto NÃO durável (30 dias · decadência)",
        base: "CDC art. 26 I",
      },
      {
        k: "cdc_vicio_duravel",
        nm: "Vício — produto durável (90 dias · decadência)",
        base: "CDC art. 26 II",
      },
    ],
  },
  {
    grupo: "Trabalhista (CF/CLT)",
    itens: [
      {
        k: "trabalhista_quinquenal",
        nm: "Créditos trabalhistas — quinquenal (5 anos)",
        base: "CF art. 7º XXIX",
      },
      {
        k: "trabalhista_bienal",
        nm: "Créditos trabalhistas — bienal pós-contrato (2 anos)",
        base: "CLT art. 11",
      },
    ],
  },
  {
    grupo: "Tributário (CTN)",
    itens: [
      {
        k: "tributario_decadencia",
        nm: "Decadência do lançamento (5 anos · decadência)",
        base: "CTN art. 173 I",
      },
      {
        k: "tributario_prescricao",
        nm: "Prescrição da cobrança (5 anos)",
        base: "CTN art. 174",
      },
    ],
  },
];

// Upload do documento importado para a GED, vinculado ao caso. Reutilizado no
// fluxo normal de criação e no retry de recuperação (reanexar) — sem recriar.
async function anexarDocumento(
  caseId: string,
  clientId: string | undefined,
  arquivo: File,
  tituloDoc: string,
  tipoDoc?: string,
): Promise<void> {
  const fd = new FormData();
  fd.append("file", arquivo);
  fd.append("titulo", tituloDoc);
  if (tipoDoc) fd.append("tipo", tipoDoc);
  fd.append("case_id", caseId);
  if (clientId) fd.append("client_id", clientId);
  await api.post("/documents/upload", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

interface ResumoRevisao {
  principais: { label: string; valor: string }[];
  aplicar: { label: string; valor: string }[];
  ausentes: string[];
  alertas: string[];
}

const txtResumo = (v: unknown): string => (v == null ? "" : String(v).trim());

// Resumo de revisão 100% client-side (form + _extracao) — NÃO chama o backend.
// Alimenta o passo "Revisar dados" ANTES de confirmar a criação do caso, para
// que nada seja gravado sem a conferência do advogado (fluxograma documental).
function montarResumoRevisao(
  form: Record<string, any>,
  clienteLabel: string,
): ResumoRevisao {
  const ex = (form?._extracao || {}) as Record<string, any>;
  const partes = (ex.partes || {}) as Record<string, any>;
  const classificacao = (ex.classificacao || {}) as Record<string, any>;

  const principais = [
    { label: "Título", valor: txtResumo(form?.titulo) || "—" },
    { label: "Cliente", valor: clienteLabel || "—" },
    {
      label: "Área",
      valor: areaLabel(form?.area) || txtResumo(form?.area) || "—",
    },
    { label: "Tipo", valor: CASE_TYPE_LABEL[form?.case_type] || "—" },
    { label: "Nº do processo", valor: txtResumo(form?.numero_processo) || "—" },
  ];

  const aplicar: { label: string; valor: string }[] = [];
  const push = (label: string, valor: unknown) => {
    const s = txtResumo(valor);
    if (s) aplicar.push({ label, valor: s });
  };
  push("Autor (parte)", partes.autor);
  push("Réu / parte contrária", partes.reu || form?.parte_contraria);
  push("Subárea", classificacao.subarea);
  push("Rito", classificacao.rito);
  push("Fase", classificacao.fase);
  push("Tribunal", form?.tribunal);
  push("Comarca", form?.comarca);
  push("Vara", form?.vara);
  if (txtResumo(form?.valor_causa))
    push("Valor da causa", `R$ ${form.valor_causa}`);

  const ausentes: string[] = [];
  if (!txtResumo(form?.titulo)) ausentes.push("Título");
  if (!txtResumo(form?.numero_processo)) ausentes.push("Número do processo");
  if (!txtResumo(form?.parte_contraria) && !txtResumo(partes.reu))
    ausentes.push("Parte contrária");
  if (!txtResumo(form?.valor_causa)) ausentes.push("Valor da causa");

  const alertas: string[] = [];
  if (
    txtResumo(form?.tipo_acao_prescricao) &&
    txtResumo(form?.data_fato_prescricao)
  ) {
    alertas.push(
      "Prazo prescricional/decadencial será calculado na criação — confira suspensões e interrupções (CC arts. 197–204).",
    );
  }
  const etapas = classificacao?.jornada?.proximas_etapas;
  if (Array.isArray(etapas) && etapas.length) {
    alertas.push(`Próximas etapas sugeridas pela IA: ${etapas.join(" → ")}.`);
  }
  return { principais, aplicar, ausentes, alertas };
}

export default function Casos() {
  const areas = useAreas();
  const [data, setData] = useState<Paged<Case> | null>(null);
  const [clientes, setClientes] = useState<Client[]>([]);
  const [advogados, setAdvogados] = useState<User[]>([]);
  const [search, setSearch] = useState("");
  const [areaF, setAreaF] = useState("");
  const [tipoF, setTipoF] = useState("");
  // Filtro por advogado responsável/auxiliar (query param advogado_id)
  const [advogadoF, setAdvogadoF] = useState("");
  // R2 — filtro ativos/arquivados/todos + ação de desarquivar por linha
  const [arquivoF, setArquivoF] = useState<"ativos" | "arquivados" | "todos">(
    "ativos",
  );
  const [desarquivandoId, setDesarquivandoId] = useState<string | null>(null);
  // Exclusão (soft delete → Lixeira) restrita a administração/sócios
  const { user } = useAuth();
  const podeExcluir = ["superadmin", "admin", "socio"].includes(
    user?.role || "",
  );
  const [delCaso, setDelCaso] = useState<Case | null>(null);
  const [delMotivo, setDelMotivo] = useState("");
  const [delLoading, setDelLoading] = useState(false);
  const [view, setView] = useState<"lista" | "kanban">("lista");
  const [modal, setModal] = useState(false);
  // A mesma rota mantém dois caminhos explícitos, sem criar módulo paralelo:
  // documento (IA + revisão) ou cadastro rápido manual (sem IA).
  const location = useLocation();
  const nav = useNavigate();
  const novoCasoModo = resolverModoNovoCaso(location.pathname, location.search);
  const wizardAberto = novoCasoModo === "manual";
  const [form, setForm] = useState<any>({
    area: "civil",
    prioridade: "media",
    case_type: "judicial",
  });
  const [salvando, setSalvando] = useState(false);
  // Preview da materialização da extração de IA (dry_run) antes de aplicar.
  const [preview, setPreview] = useState<{
    caseId: string;
    caseTitulo: string;
    extracao: ExtracaoPayload;
    result: AplicarExtracaoResult;
  } | null>(null);
  const [aplicando, setAplicando] = useState(false);
  // Rascunho recuperável do intake documental (localStorage): banner de retomada
  // ao reabrir, e recuperação SEM recriar quando o caso já foi criado mas o
  // anexo do documento falhou.
  const [rascunhoSalvo, setRascunhoSalvo] = useState<IntakeRascunho | null>(
    null,
  );
  const [pendencia, setPendencia] = useState<IntakePendencia | null>(null);
  const [reanexando, setReanexando] = useState(false);
  // Passo de revisão (client-side) antes de confirmar a criação do caso.
  const [revisao, setRevisao] = useState<ResumoRevisao | null>(null);
  const [erro, setErro] = useState(false);
  // Guarda de sequência: só a resposta mais recente aplica setData (evita que
  // a resposta antiga de uma busca/filtro com debounce sobrescreva a nova).
  const seq = useRef(0);

  useEffect(() => {
    if (novoCasoModo === "documento") {
      setModal(true);
      // Ao (re)abrir o intake, oferece retomar um cadastro por documento não
      // finalizado. Se o rascunho já traz `caseId`, o caso EXISTE: reconstrói a
      // pendência para que a retomada passe pelo retry de vínculo/anexo (que
      // nunca recria o caso) em vez de um novo POST /cases/ — evita duplicata.
      const rascunho = carregarRascunho();
      setRascunhoSalvo(rascunho);
      setPendencia(pendenciaDeRascunho(rascunho));
    }
  }, [novoCasoModo]);

  // FLX-048 — recuperação pós-refresh da revisão da extração: se a URL marca
  // ?revisao=<caseId> e o rascunho persistido cobre esse caso, refaz o preview
  // (dry-run) e reabre o modal de decisão. Sem rascunho compatível, remove o
  // param silenciosamente (não há o que recuperar).
  useEffect(() => {
    const revisaoCaseId = new URLSearchParams(location.search).get("revisao");
    if (!revisaoCaseId || preview) return;
    const rascunho = carregarRascunho();
    if (!rascunhoCobreRevisao(rascunho, revisaoCaseId)) {
      nav(urlSemParamRevisao(location.pathname, location.search), {
        replace: true,
      });
      return;
    }
    let cancelado = false;
    (async () => {
      try {
        const result = await aplicarExtracao(revisaoCaseId, rascunho.extracao, {
          dryRun: true,
        });
        if (cancelado) return;
        setPreview({
          caseId: revisaoCaseId,
          caseTitulo: (rascunho.form.titulo as string) || "caso",
          extracao: rascunho.extracao,
          result,
        });
      } catch {
        if (!cancelado)
          toast.error(
            "Não foi possível recuperar a revisão dos dados extraídos. " +
              "Abra o caso pela lista para continuar — o rascunho segue salvo.",
          );
      }
    })();
    return () => {
      cancelado = true;
    };
    // `preview` fica fora das deps de propósito: o guard acima já impede
    // reexecução com o modal aberto, e o objetivo é rodar só quando a URL muda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search]);

  const fecharCadastroCompleto = () => {
    setModal(false);
    if (location.pathname === "/casos/novo") {
      nav("/casos", { replace: true });
    }
  };

  const load = () => {
    const my = ++seq.current;
    setErro(false);
    return api
      .get("/cases/", {
        params: {
          search: search || undefined,
          area: areaF || undefined,
          advogado_id: advogadoF || undefined,
          arquivo: arquivoF,
          page_size: 50,
        },
      })
      .then((r) => {
        if (my === seq.current) setData(r.data);
      })
      .catch(() => {
        if (my !== seq.current) return;
        setErro(true);
        toast.error("Falha ao carregar casos");
      });
  };

  const desarquivar = async (id: string) => {
    setDesarquivandoId(id);
    try {
      await api.post(`/cases/${id}/desarquivar`);
      toast.success("Caso desarquivado.");
      await load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === "string" ? detail : "Falha ao desarquivar o caso",
      );
    } finally {
      setDesarquivandoId(null);
    }
  };

  const excluir = async () => {
    if (!delCaso) return;
    const motivo = delMotivo.trim();
    // Backend (DELETE /cases/{id}) exige motivo com no mínimo 5 caracteres
    if (motivo.length < 5) {
      toast.error("Informe o motivo da exclusão (mínimo 5 caracteres).");
      return;
    }
    setDelLoading(true);
    try {
      await api.delete(`/cases/${delCaso.id}`, { data: { motivo } });
      toast.success("Caso excluído — reversível pela Lixeira.");
      setDelCaso(null);
      setDelMotivo("");
      await load();
    } catch (e: any) {
      if (e?.response?.status === 403) {
        toast.error("Sem permissão para excluir casos (apenas admin/sócio).");
      } else {
        const detail = e?.response?.data?.detail;
        toast.error(
          typeof detail === "string"
            ? detail
            : detail?.mensagem || "Falha ao excluir o caso",
        );
      }
    } finally {
      setDelLoading(false);
    }
  };

  useEffect(() => {
    // load() inicial fica a cargo do effect de [arquivoF] abaixo
    // clientes p/ filtro/seletor — falha silenciosa se o perfil (ex.: financeiro)
    // não puder listar clientes (403); o restante de /casos segue funcionando.
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => setClientes(asList<Client>(r.data)))
      .catch(() => setClientes([]));
    // advogados p/ o seletor de responsável — falha silenciosa se o perfil não puder listar usuários
    api
      .get("/users/")
      .then((r) => setAdvogados(asList<User>(r.data)))
      .catch(() => setAdvogados([]));
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [search, areaF, advogadoF, arquivoF]);

  // Passo 3 do fluxograma documental: abre a REVISÃO antes de qualquer escrita.
  // Só depois de "Confirmar criação" é que salvar() cria o caso e anexa o doc.
  const abrirRevisao = () => {
    if (!form._arquivo_original) {
      toast.error(
        "Envie e analise o documento do cliente antes de criar o caso.",
      );
      return;
    }
    const cand = form._cliente_candidato;
    const temCandidato = !!(cand && (cand.nome || cand.cpf || cand.cnpj));
    if (!form.titulo || (!form.client_id && !temCandidato)) {
      toast.error(
        "Título e cliente são obrigatórios (ou importe um documento).",
      );
      return;
    }
    if (!form.proxima_acao?.trim()) {
      toast.error("Informe a próxima ação — é obrigatória para casos ativos.");
      return;
    }
    const selecionado = clientes.find((c) => c.id === form.client_id);
    const clienteLabel =
      selecionado?.nome ||
      (selecionado as any)?.razao_social ||
      cand?.nome ||
      "";
    setRevisao(montarResumoRevisao(form, clienteLabel));
  };

  const salvar = async () => {
    if (novoCasoModo === "documento" && !form._arquivo_original) {
      toast.error(
        "Envie e analise o documento do cliente antes de criar o caso.",
      );
      return;
    }
    const cand = form._cliente_candidato;
    const temCandidato = !!(cand && (cand.nome || cand.cpf || cand.cnpj));
    if (!form.titulo || (!form.client_id && !temCandidato)) {
      toast.error(
        "Título e cliente são obrigatórios (ou importe um documento)",
      );
      return;
    }
    if (!form.proxima_acao?.trim()) {
      toast.error("Informe a próxima ação — é obrigatória para casos ativos.");
      return;
    }
    setSalvando(true);
    // Metadados do intake documental capturados ANTES de qualquer escrita.
    const extracao = form._extracao as ExtracaoPayload | undefined;
    const arquivoOriginal = form._arquivo_original as File | undefined;
    const tipoDoc = form._tipo_documento as string | undefined;
    // Lote da Entrada Universal: quando presente, TODOS os arquivos já estão no
    // GED (órfãos) e o vínculo em lote substitui o re-upload do 1º arquivo.
    const batchIdForm =
      (form._entrada_universal_batch_id as string | undefined) ||
      (typeof extracao?.batch_id === "string" ? extracao.batch_id : undefined);
    // RETOMADA (arquivo único e lote): havendo pendência — inclusive a
    // reconstruída do rascunho após um reload — o caso JÁ foi criado. Nesse
    // estado salvar() NUNCA emite POST /cases/: reaproveita o caso existente e
    // segue direto para o vínculo/anexo, senão a retomada duplicaria o caso.
    const casoExistente = pendencia;
    const batchId = batchIdForm ?? casoExistente?.batchId;
    // Rascunho recuperável: persistido ANTES de criar. Se qualquer passo falhar
    // (ou a aba fechar), o trabalho analisado não se perde. Limpo só no sucesso.
    // Cobre TAMBÉM o fluxo de lote (batchId sem File local) e a extração avulsa
    // — sem isso, o F5 durante a revisão (?revisao=) perdia tudo em silêncio.
    const intakeDocumental = !!(
      arquivoOriginal ||
      batchId ||
      extracao ||
      casoExistente
    );
    if (intakeDocumental) {
      salvarRascunho({
        form: snapshotForm(form),
        extracao: extracao ?? null,
        arquivoNome: arquivoOriginal?.name ?? null,
        batchId: batchId ?? null,
        arquivoTipo: tipoDoc ?? null,
        clientId: form.client_id || casoExistente?.clientId || null,
        // Preserva o caso já criado: o rascunho não pode "esquecer" o caseId,
        // sob pena de a próxima retomada recriar o caso.
        caseId: casoExistente?.caseId ?? null,
        uploadFeito: false,
      });
    }
    try {
      let previewPreparado = false;
      let clientId = form.client_id || casoExistente?.clientId;
      // Importação inteligente: cria/vincula cliente por CPF/CNPJ (dedup no backend)
      if (!clientId && temCandidato) {
        const { data: cli } = await api.post("/clients/resolver", cand);
        clientId = cli.id;
      }
      // Remove campos vazios e auxiliares (_extracao/_cliente_candidato não são campos do caso)
      const payload: Record<string, any> = {};
      for (const [k, v] of Object.entries(form)) {
        if (k.startsWith("_")) continue;
        if (v !== "" && v !== null && v !== undefined) payload[k] = v;
      }
      payload.client_id = clientId;
      // Caso já criado (retomada) → reaproveita; caso novo → cria.
      const novo = casoExistente
        ? { id: casoExistente.caseId, titulo: casoExistente.caseTitulo }
        : (await api.post("/cases/", payload)).data;
      const tituloDoc =
        (payload.titulo as string) || novo?.titulo || "Documento importado";
      if (intakeDocumental)
        atualizarRascunho({ caseId: novo?.id ?? null, clientId });

      // VINCULA/ANEXA os documentos ANTES de navegar: uma falha não deixa mais
      // o usuário numa lista com um caso órfão dos seus documentos de origem.
      if ((batchId || arquivoOriginal) && novo?.id) {
        try {
          if (batchId) {
            // Entrada Universal: vincula TODOS os arquivos do lote ao caso (e
            // ao cliente) de uma vez — sem re-upload nem duplicata do 1º arquivo.
            const vinc = await vincularLoteAoCaso(batchId, novo.id);
            avisarConflitosDeVinculo(vinc);
          } else if (arquivoOriginal) {
            await anexarDocumento(
              novo.id,
              clientId,
              arquivoOriginal,
              tituloDoc,
              tipoDoc,
            );
          }
          atualizarRascunho({ uploadFeito: true });
        } catch (e: any) {
          // Caso criado, vínculo/anexo falhou: NÃO navega nem silencia. Oferece
          // retomada (retry) sem recriar o caso (ele permanece em triagem).
          setPendencia({
            caseId: novo.id,
            caseTitulo: novo.titulo || tituloDoc,
            arquivo: arquivoOriginal,
            tituloDoc,
            tipoDoc,
            clientId,
            batchId,
          });
          toast.error(
            e.response?.data?.detail ||
              (batchId
                ? "O caso foi criado, mas os documentos importados não foram vinculados. Tente novamente abaixo — o caso não será duplicado."
                : "O caso foi criado, mas o documento não foi anexado. Tente novamente abaixo — o caso não será duplicado."),
          );
          return;
        }
      }

      // Materialização EXPLÍCITA (preview dry_run) — agora DEPOIS do anexo.
      // O usuário confirma ("Aplicar ao caso") ou pula; erros são visíveis.
      if (extracao && novo?.id) {
        try {
          const result = await aplicarExtracao(novo.id, extracao, {
            dryRun: true,
          });
          setPreview({
            caseId: novo.id,
            caseTitulo: novo.titulo || payload.titulo || "caso",
            extracao,
            result,
          });
          previewPreparado = true;
        } catch (e: any) {
          toast.error(
            e.response?.data?.detail ||
              "Caso criado, mas não foi possível pré-visualizar os dados extraídos pela IA.",
          );
        }
      }

      // Sucesso: segue direto para a jornada. Quando há preview de extração,
      // mantém o modal de confirmação e — FLX-048 — PRESERVA o rascunho e
      // marca ?revisao=<caseId> na URL: um refresh nesse momento recupera a
      // decisão pendente. O rascunho só é limpo nos desfechos da decisão
      // (aplicar ou pular), em aplicarPreviewNoCaso/abrirJornadaSemAplicar.
      setPendencia(null);
      setRascunhoSalvo(null);
      setModal(false);
      if (previewPreparado && novo?.id) {
        nav(urlRevisaoPendente(novo.id), { replace: true });
      } else {
        limparRascunho();
        if (novo?.id) nav(caseJourneyPath(novo.id), { replace: true });
        else nav("/casos", { replace: true });
      }
      setForm({ area: "civil", prioridade: "media", case_type: "judicial" });
      load();
    } catch (e: any) {
      // Falha antes/na criação do caso: o caso NÃO foi criado; o rascunho (se
      // documental) permanece para retomada.
      // E02 (auditoria funcional): 422 do Pydantic nomeia o campo exato para
      // correção, em vez de mostrar a string bruta do validador.
      toast.error(classificarErroCriacao(e));
    } finally {
      setSalvando(false);
    }
  };

  // E02 (auditoria funcional): erros 422 do FastAPI/Pydantic chegam como
  // {detail: [{loc, msg}]} — extrair o nome do campo para o usuário corrigir
  // exatamente o ponto em vez de receber a string bruta do validador.
  const classificarErroCriacao = (e: any): string => {
    const resp = e?.response?.data;
    const status = e?.response?.status;
    const detail = resp?.detail;
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((d: any) => {
          const loc = Array.isArray(d?.loc) ? d.loc : [];
          const campo = loc.length ? String(loc[loc.length - 1]) : null;
          const rotulo = campo ? campo.replace(/_/g, " ") : null;
          return rotulo
            ? `${rotulo}: ${String(d.msg ?? d)}`
            : String(d.msg ?? d);
        })
        .join("; ");
    }
    if (typeof detail === "string" && detail) return detail;
    if (status === 422 || status === 400)
      return "Algum campo está em formato inválido ou ausente. Revise os campos destacados e tente novamente.";
    return e?.response?.data?.detail || "Erro ao salvar";
  };

  // Retry do vínculo/anexo quando o caso JÁ existe (pendência) — nunca recria o caso.
  const reanexarDocumento = async () => {
    if (!pendencia) return;
    setReanexando(true);
    try {
      if (pendencia.batchId) {
        // Vínculo em lote (idempotente): religa TODOS os arquivos ao caso.
        const vinc = await vincularLoteAoCaso(
          pendencia.batchId,
          pendencia.caseId,
        );
        avisarConflitosDeVinculo(vinc);
      } else if (pendencia.arquivo) {
        await anexarDocumento(
          pendencia.caseId,
          pendencia.clientId,
          pendencia.arquivo,
          pendencia.tituloDoc,
          pendencia.tipoDoc,
        );
      } else {
        toast.error(
          "O arquivo original não está mais disponível nesta sessão. Anexe-o pelo caso na GED.",
        );
        return;
      }
      atualizarRascunho({ uploadFeito: true });
      limparRascunho();
      toast.success(
        pendencia.batchId
          ? "Documentos importados vinculados ao caso."
          : "Documento anexado ao caso.",
      );
      setPendencia(null);
      setRascunhoSalvo(null);
      setModal(false);
      nav(caseJourneyPath(pendencia.caseId), { replace: true });
      setForm({ area: "civil", prioridade: "media", case_type: "judicial" });
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Ainda não foi possível anexar. Tente de novo ou conclua sem o documento.",
      );
    } finally {
      setReanexando(false);
    }
  };

  // Conclui deixando o caso sem o documento (escolha EXPLÍCITA do usuário).
  const concluirSemDocumento = () => {
    const caseId = pendencia?.caseId;
    limparRascunho();
    setPendencia(null);
    setRascunhoSalvo(null);
    setModal(false);
    if (caseId) nav(caseJourneyPath(caseId), { replace: true });
    else nav("/casos", { replace: true });
    setForm({ area: "civil", prioridade: "media", case_type: "judicial" });
    load();
  };

  // Descarta o rascunho de retomada (banner) sem afetar nenhum caso.
  const descartarRascunho = () => {
    limparRascunho();
    setRascunhoSalvo(null);
  };

  // Aplica de fato (dry_run=false) o que foi mostrado no preview.
  const aplicarPreviewNoCaso = async () => {
    if (!preview) return;
    const caseId = preview.caseId;
    setAplicando(true);
    try {
      const r = await aplicarExtracao(caseId, preview.extracao, {
        dryRun: false,
      });
      const campos = r.campos_preenchidos.length
        ? `, campos: ${r.campos_preenchidos.join(", ")}`
        : "";
      const prazos = r.prazos_criados
        ? `, ${r.prazos_criados} prazo(s) criado(s) como rascunho a confirmar`
        : "";
      toast.success(
        `Dados aplicados ao caso: ${r.partes_criadas} parte(s), ${r.areas_criadas} área(s)${campos}${prazos}.`,
      );
      // Desfecho da decisão (FLX-048): agora sim o rascunho pode ser limpo; a
      // navegação com replace tira o marcador ?revisao da URL/histórico.
      limparRascunho();
      setRascunhoSalvo(null);
      setPreview(null);
      load();
      nav(caseJourneyPath(caseId), { replace: true });
    } catch (e: any) {
      // Falha ao aplicar: rascunho e ?revisao permanecem — segue recuperável.
      toast.error(
        e.response?.data?.detail || "Erro ao aplicar os dados ao caso.",
      );
    } finally {
      setAplicando(false);
    }
  };

  const abrirJornadaSemAplicar = () => {
    if (!preview) return;
    const caseId = preview.caseId;
    // Desfecho explícito ("pular") — FLX-048: limpa o rascunho e sai do
    // estado de revisão (o replace remove ?revisao da URL/histórico).
    limparRascunho();
    setRascunhoSalvo(null);
    setPreview(null);
    nav(caseJourneyPath(caseId), { replace: true });
  };

  // Fechar o modal SEM decidir (X/backdrop) — FLX-048: mantém o rascunho e o
  // ?revisao na URL; a revisão continua recuperável (um F5 reabre o preview).
  // Os desfechos reais são aplicarPreviewNoCaso e abrirJornadaSemAplicar.
  const fecharPreviewSemDecidir = () => {
    setPreview(null);
  };

  return (
    <div>
      <PageHeader
        title="Casos e Processos"
        subtitle={`${data?.total ?? 0} casos`}
        actions={
          <div className="flex flex-wrap gap-2 items-center">
            <div className="flex rounded-lg overflow-hidden bg-slate-900/[0.05] dark:bg-white/[0.07]">
              <button
                onClick={() => setView("lista")}
                className={`flex items-center gap-1 px-3 py-1.5 transition-colors duration-150 text-sm ${view === "lista" ? "bg-primary-900 text-white" : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"}`}
              >
                <List size={15} /> Lista
              </button>
              <button
                onClick={() => setView("kanban")}
                className={`flex items-center gap-1 px-3 py-1.5 transition-colors duration-150 text-sm ${view === "kanban" ? "bg-primary-900 text-white" : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"}`}
              >
                <LayoutGrid size={15} /> Quadro
              </button>
            </div>
            <Button
              variant="secondary"
              icon={<PenLine size={16} />}
              onClick={() => nav(NOVO_CASO_MANUAL_PATH)}
            >
              Cadastro manual
            </Button>
            <button
              className="btn-gold"
              onClick={() => nav(NOVO_CASO_DOCUMENTO_PATH)}
            >
              <FileUp size={16} /> Novo caso por documento
            </button>
          </div>
        }
      />

      {view === "lista" && <CasosStats />}

      {view === "kanban" && (
        <div className="-mx-2">
          <Kanban />
        </div>
      )}
      {view === "lista" && (
        <>
          <div className="flex flex-wrap gap-3 mb-4">
            <div className="relative flex-1 min-w-[220px] max-w-md">
              <Search
                size={16}
                className="absolute left-3 top-2.5 text-slate-400"
              />
              <input
                className="input pl-9"
                placeholder="Buscar título, processo, parte..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {/* Sem rótulo acessível, este filtro era anunciado apenas pela
                opção selecionada ("Todas as áreas") — o leitor de tela dizia o
                VALOR sem dizer do que ele é valor. Medido em 22/08/2026. */}
            <select
              className="input w-44"
              aria-label="Filtrar por área do Direito"
              value={areaF}
              onChange={(e) => setAreaF(e.target.value)}
            >
              <option value="">Todas as áreas</option>
              {areas.map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.nome}
                </option>
              ))}
            </select>
            {user?.id && (
              <button
                onClick={() =>
                  setAdvogadoF((prev) => (prev === user.id ? "" : user.id))
                }
                title="Ver somente os casos em que você é responsável ou auxiliar"
                className={`px-3 py-1.5 transition-colors duration-150 rounded-lg text-sm font-medium whitespace-nowrap ${
                  advogadoF === user.id
                    ? "bg-primary-600 text-white"
                    : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"
                }`}
              >
                Meus casos
              </button>
            )}
            {/* `title` sozinho é nome acessível fraco — vira tooltip e nem
                todo leitor de tela o anuncia. `aria-label` é o mecanismo
                próprio; o `title` fica para o usuário de mouse. */}
            <select
              className="input w-52"
              value={advogadoF}
              onChange={(e) => setAdvogadoF(e.target.value)}
              aria-label="Filtrar por advogado responsável ou auxiliar"
              title="Filtrar por advogado responsável ou auxiliar"
            >
              <option value="">Todos os advogados</option>
              {advogados.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.email}
                </option>
              ))}
            </select>
            <div className="flex gap-1">
              <button
                onClick={() => setTipoF("")}
                className={`px-3 py-1.5 transition-colors duration-150 rounded-lg text-sm font-medium ${tipoF === "" ? "bg-primary-900 text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
              >
                Todos
              </button>
              {CASE_TYPES.map((t) => (
                <button
                  key={t.k}
                  onClick={() => setTipoF(t.k)}
                  className={`flex items-center gap-1 px-3 py-1.5 transition-colors duration-150 rounded-lg text-sm font-medium ${tipoF === t.k ? "bg-primary-900 text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
                >
                  <t.icon size={13} /> {t.l}
                </button>
              ))}
            </div>
            {/* R2 — alterna entre casos ativos/arquivados/todos */}
            <div className="flex rounded-lg overflow-hidden bg-slate-900/[0.05] dark:bg-white/[0.07]">
              {[
                ["ativos", "Ativos", List],
                ["arquivados", "Arquivados", Archive],
                ["todos", "Todos", ArchiveRestore],
              ].map(([k, label, Icon]: any) => (
                <button
                  key={k}
                  onClick={() => setArquivoF(k)}
                  className={`flex items-center gap-1 px-3 py-1.5 transition-colors duration-150 text-sm font-medium ${arquivoF === k ? "bg-primary-900 text-white" : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"}`}
                >
                  <Icon size={13} /> {label}
                </button>
              ))}
            </div>
          </div>

          {erro && !data ? (
            <EmptyState
              title="Falha ao carregar casos"
              message="Não foi possível carregar a lista. Verifique sua conexão e tente novamente."
              action={
                <Button variant="primary" onClick={load}>
                  Tentar novamente
                </Button>
              }
            />
          ) : !data ? (
            <SkeletonTable
              rows={6}
              cols={arquivoF === "arquivados" || podeExcluir ? 8 : 7}
            />
          ) : data.data.length === 0 ? (
            arquivoF === "arquivados" ? (
              <Empty
                titulo="Nenhum caso arquivado"
                descricao="Casos que você arquivar ficam guardados aqui — nenhum foi arquivado ainda."
              />
            ) : (
              <Empty
                titulo="Nenhum caso por aqui ainda"
                descricao="Os casos são o centro do EJC: cada um reúne prazos, documentos, peças e honorários. Comece abrindo o primeiro pelo cadastro guiado."
                acao={
                  <Link to="/casos/novo">
                    <Button
                      variant="primary"
                      icon={<Plus className="h-4 w-4" />}
                    >
                      Criar seu primeiro caso
                    </Button>
                  </Link>
                }
              />
            )
          ) : (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-primary-50/60 text-left dark:bg-white/[0.04]">
                  <tr>
                    <th className="px-4 py-2.5 label-caps">Nº interno</th>
                    <th className="px-4 py-2.5 label-caps">Título</th>
                    <th className="px-4 py-2.5 label-caps">Área</th>
                    <th className="px-4 py-2.5 label-caps">Tipo</th>
                    <th className="px-4 py-2.5 label-caps">Status</th>
                    <th className="px-4 py-2.5 label-caps">Parte contrária</th>
                    <th className="px-4 py-2.5 label-caps">Aberto em</th>
                    {(arquivoF === "arquivados" || podeExcluir) && (
                      <th className="px-4 py-2.5 label-caps">Ações</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/[0.06]">
                  {(tipoF
                    ? data.data.filter(
                        (c: any) => (c.case_type || "judicial") === tipoF,
                      )
                    : data.data
                  ).map((c) => (
                    <tr
                      key={c.id}
                      className="transition-colors duration-150 hover:bg-primary-50/40 dark:hover:bg-white/[0.03]"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-bronze-deep font-medium tracking-tight">
                        <Link to={`/casos/${c.id}`}>{c.numero_interno}</Link>
                      </td>
                      <td
                        className="px-4 py-3 text-navy-800"
                        style={{ fontWeight: 400 }}
                      >
                        <Link to={`/casos/${c.id}`} className="hover:underline">
                          {c.titulo}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500 capitalize">
                        {areaLabel((c as any).area) || c.area}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${CASE_TYPE_COLOR[(c as any).case_type || "judicial"]}`}
                        >
                          {CASE_TYPE_LABEL[(c as any).case_type || "judicial"]}
                          {(c as any).extrajudicial_type
                            ? ` · ${EXTRAJ_TYPES.find((e) => e.k === (c as any).extrajudicial_type)?.l || ""}`
                            : ""}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={c.status} />
                      </td>
                      <td className="px-4 py-3 text-slate-500">
                        {c.parte_contraria || "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {fmtDate(c.created_at)}
                      </td>
                      {(arquivoF === "arquivados" || podeExcluir) && (
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            {arquivoF === "arquivados" && (
                              <button
                                onClick={() => desarquivar(c.id)}
                                disabled={desarquivandoId === c.id}
                                className="flex items-center gap-1 text-xs font-medium text-primary-700 hover:underline disabled:opacity-50"
                              >
                                <ArchiveRestore size={13} />
                                {desarquivandoId === c.id
                                  ? "Desarquivando..."
                                  : "Desarquivar"}
                              </button>
                            )}
                            {podeExcluir && (
                              <button
                                onClick={() => {
                                  setDelMotivo("");
                                  setDelCaso(c);
                                }}
                                title="Excluir caso (reversível pela Lixeira)"
                                className="flex min-h-[24px] items-center gap-1 text-xs font-medium text-danger-600 hover:underline"
                              >
                                <Trash2 size={13} /> Excluir
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <NovoCasoWizard
        open={wizardAberto}
        onClose={() => nav("/casos")}
        onCadastroCompleto={() => nav(NOVO_CASO_DOCUMENTO_PATH)}
      />

      <Modal
        open={modal}
        onClose={fecharCadastroCompleto}
        title="Novo caso por documento — IA assistida"
        wide
      >
        <div className="mb-5 flex flex-col gap-3 rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-primary-800">
              1. Analise o documento · 2. Revise os dados · 3. Confirme a
              jornada
            </p>
            <p className="mt-1 text-xs leading-5 text-primary-700">
              Nada é gravado silenciosamente: cliente, caso, partes, área e
              prazos só são aplicados após sua conferência.
            </p>
          </div>
          <Button
            size="sm"
            variant="secondary"
            icon={<PenLine className="h-3.5 w-3.5" />}
            onClick={() => nav(NOVO_CASO_MANUAL_PATH)}
          >
            Prefiro cadastrar sem IA
          </Button>
        </div>
        {pendencia && (
          <div className="mb-5 rounded-xl border border-warn-200 bg-warn-100 px-4 py-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-700" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-warn-800">
                  O caso “{pendencia.caseTitulo}” foi criado, mas{" "}
                  {pendencia.batchId
                    ? "os documentos importados não foram vinculados."
                    : "o documento não foi anexado."}
                </p>
                <p className="mt-1 text-xs leading-5 text-warn-700">
                  Nada foi perdido: o caso está salvo (em triagem)
                  {pendencia.batchId
                    ? " e os arquivos do lote importado continuam no servidor. Tente vincular de novo — nenhum arquivo será duplicado."
                    : pendencia.arquivo
                      ? ` e o documento “${pendencia.arquivo.name}” continua aqui. Tente anexar de novo — o caso não será duplicado.`
                      : ` — só falta o documento “${pendencia.tituloDoc}”, que não sobreviveu ao recarregamento da página. Reenvie-o abaixo (o caso não será duplicado) ou anexe-o pela GED do caso.`}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(pendencia.batchId || pendencia.arquivo) && (
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<RotateCw className="h-3.5 w-3.5" />}
                      onClick={reanexarDocumento}
                      disabled={reanexando}
                    >
                      {reanexando
                        ? pendencia.batchId
                          ? "Vinculando..."
                          : "Anexando..."
                        : pendencia.batchId
                          ? "Tentar vincular novamente"
                          : "Tentar anexar novamente"}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={concluirSemDocumento}
                    disabled={reanexando}
                  >
                    Concluir sem o documento
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
        {!pendencia && rascunhoSalvo && (
          <div className="mb-5 rounded-xl border border-primary-200 bg-primary-50 px-4 py-3">
            <div className="flex items-start gap-2">
              <FileUp className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-primary-800">
                  Cadastro por documento não finalizado
                </p>
                <p className="mt-1 text-xs leading-5 text-primary-700">
                  {rascunhoSalvo.arquivoNome
                    ? `Havia um cadastro em andamento com o documento “${rascunhoSalvo.arquivoNome}”. `
                    : "Havia um cadastro por documento em andamento. "}
                  Reenvie o documento abaixo para retomar, ou descarte este
                  rascunho.
                </p>
                <div className="mt-3">
                  <Button size="sm" variant="ghost" onClick={descartarRascunho}>
                    Descartar rascunho
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
        <ImportarDocumento
          onPrefill={(p) => setForm((f: any) => ({ ...f, ...p }))}
        />
        {/* ── Cliente & responsável ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Cliente & responsável
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <div>
            <label className="label">Cliente *</label>
            <select
              className="input"
              value={form.client_id || ""}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            >
              <option value="">Selecione...</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome || c.razao_social}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Advogado responsável</label>
            <select
              className="input"
              value={form.advogado_responsavel_id || ""}
              onChange={(e) =>
                setForm({ ...form, advogado_responsavel_id: e.target.value })
              }
            >
              <option value="">Eu mesmo (padrão)</option>
              {advogados.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                  {u.oab_number ? ` — OAB ${u.oab_number}` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* ── Classificação ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Classificação
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <div className="sm:col-span-2">
            <label className="label">Título *</label>
            <input
              className="input"
              value={form.titulo || ""}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Área *</label>
            <select
              className="input"
              value={form.area}
              onChange={(e) => setForm({ ...form, area: e.target.value })}
            >
              {areas.map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.nome}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Prioridade</label>
            <select
              className="input"
              value={form.prioridade}
              onChange={(e) => setForm({ ...form, prioridade: e.target.value })}
            >
              <option value="baixa">Baixa</option>
              <option value="media">Média</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </select>
          </div>
          <SigiloReforcadoField
            checked={!!form.sigilo_reforcado}
            onChange={(v) => setForm({ ...form, sigilo_reforcado: v })}
          />
          <div>
            <label className="label">Tipo de caso</label>
            <select
              className="input"
              value={form.case_type}
              onChange={(e) =>
                setForm({
                  ...form,
                  case_type: e.target.value,
                  extrajudicial_type:
                    e.target.value === "extrajudicial"
                      ? form.extrajudicial_type
                      : undefined,
                })
              }
            >
              {CASE_TYPES.map((t) => (
                <option key={t.k} value={t.k}>
                  {t.l}
                </option>
              ))}
            </select>
          </div>
          {form.case_type === "extrajudicial" && (
            <div>
              <label className="label">Subtipo extrajudicial</label>
              <select
                className="input"
                value={form.extrajudicial_type || ""}
                onChange={(e) =>
                  setForm({ ...form, extrajudicial_type: e.target.value })
                }
              >
                <option value="">Selecione...</option>
                {EXTRAJ_TYPES.map((t) => (
                  <option key={t.k} value={t.k}>
                    {t.l}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* ── Localização processual ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Localização processual
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <div>
            <label className="label">Nº do processo (se houver)</label>
            <input
              className="input"
              value={form.numero_processo || ""}
              onChange={(e) =>
                setForm({ ...form, numero_processo: e.target.value })
              }
              placeholder="0000000-00.0000.0.00.0000"
            />
          </div>
          <div>
            <label className="label">Tribunal</label>
            <input
              className="input"
              value={form.tribunal || ""}
              onChange={(e) => setForm({ ...form, tribunal: e.target.value })}
              placeholder="TJMG, TRT-3, STJ..."
            />
          </div>
          <div>
            <label className="label">Comarca</label>
            <input
              className="input"
              value={form.comarca || ""}
              onChange={(e) => setForm({ ...form, comarca: e.target.value })}
              placeholder="Betim/MG"
            />
          </div>
          <div>
            <label className="label">Vara</label>
            <input
              className="input"
              value={form.vara || ""}
              onChange={(e) => setForm({ ...form, vara: e.target.value })}
              placeholder="5ª Vara Cível"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Parte contrária</label>
            <input
              className="input"
              value={form.parte_contraria || ""}
              onChange={(e) =>
                setForm({ ...form, parte_contraria: e.target.value })
              }
            />
          </div>
        </div>

        {/* ── Prazo prescricional / decadencial ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Prazo prescricional / decadencial
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-2">
          <div>
            <label className="label">Tipo de pretensão</label>
            <select
              className="input"
              value={form.tipo_acao_prescricao || ""}
              onChange={(e) =>
                setForm({ ...form, tipo_acao_prescricao: e.target.value })
              }
            >
              <option value="">Não calcular agora</option>
              {PRESCRICAO.map((g) => (
                <optgroup key={g.grupo} label={g.grupo}>
                  {g.itens.map((i) => (
                    <option key={i.k} value={i.k}>
                      {i.nm} · {i.base}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className="label">
              Termo inicial (fato / violação / ciência)
            </label>
            <input
              className="input"
              type="date"
              value={form.data_fato_prescricao || ""}
              onChange={(e) =>
                setForm({ ...form, data_fato_prescricao: e.target.value })
              }
            />
          </div>
        </div>
        <p className="text-[11px] text-warn-800 bg-warn-50 border border-warn-200 rounded-md px-3 py-2 mb-5">
          Minuta automática (revisão obrigatória): informando o tipo + termo
          inicial, o sistema calcula a data-limite na abertura do caso.
          Suspensões e interrupções (CC arts. 197–204) e particularidades do
          caso devem ser conferidas pelo advogado.
        </p>

        {/* ── Valor & fatos ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Valor & fatos
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Valor da causa (R$)</label>
            <input
              className="input"
              type="number"
              value={form.valor_causa || ""}
              onChange={(e) =>
                setForm({ ...form, valor_causa: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">
              Descrição dos fatos (usada pela IA p/ sugerir teses)
            </label>
            <textarea
              className="input min-h-[100px]"
              value={form.descricao_fatos || ""}
              onChange={(e) =>
                setForm({ ...form, descricao_fatos: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Próxima ação *</label>
            <input
              className="input"
              placeholder="Ex.: Protocolar contestação, Agendar reunião"
              value={form.proxima_acao || ""}
              onChange={(e) =>
                setForm({ ...form, proxima_acao: e.target.value })
              }
            />
            <p className="mt-1 text-xs text-slate-400">
              O que precisa ser feito agora neste caso? Obrigatório para casos
              ativos.
            </p>
          </div>
        </div>
        <div className="flex justify-end mt-5">
          <button
            className="btn-primary"
            disabled={salvando}
            onClick={abrirRevisao}
          >
            {salvando ? "Criando caso..." : "Revisar e criar o caso"}
          </button>
        </div>
      </Modal>

      {/* Passo de REVISÃO — o que será criado/aplicado, antes de qualquer
          escrita no backend. "Confirmar" dispara a criação (salvar). */}
      <Modal
        open={!!revisao}
        onClose={() => setRevisao(null)}
        title="Revisar antes de criar o caso"
        footer={
          <>
            <button
              className="btn-ghost"
              disabled={salvando}
              onClick={() => setRevisao(null)}
            >
              Voltar e editar
            </button>
            <button
              className="btn-primary"
              disabled={salvando}
              onClick={() => {
                setRevisao(null);
                salvar();
              }}
            >
              {salvando ? "Criando caso..." : "Confirmar criação"}
            </button>
          </>
        }
      >
        {revisao && (
          <div className="space-y-5 text-sm">
            <p className="text-xs leading-5 text-slate-500">
              Confira o que será criado. Nada é gravado até você confirmar — ao
              confirmar, o caso é criado, o documento é anexado e os dados
              extraídos abaixo são aplicados.
            </p>
            <section>
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">
                Caso
              </p>
              <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
                {revisao.principais.map((it) => (
                  <div
                    key={it.label}
                    className="flex justify-between gap-3 border-b border-slate-100 py-1"
                  >
                    <dt className="text-slate-500">{it.label}</dt>
                    <dd className="text-right font-medium text-slate-800">
                      {it.valor}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
            {revisao.aplicar.length > 0 && (
              <section>
                <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">
                  Dados extraídos que serão aplicados
                </p>
                <ul className="space-y-1">
                  {revisao.aplicar.map((it) => (
                    <li
                      key={it.label}
                      className="flex justify-between gap-3 border-b border-slate-100 py-1"
                    >
                      <span className="text-slate-500">{it.label}</span>
                      <span className="text-right font-medium text-slate-800">
                        {it.valor}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {revisao.ausentes.length > 0 && (
              <section className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold text-slate-700">
                  Informação ausente — você pode completar agora ou depois
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {revisao.ausentes.join(" · ")}
                </p>
              </section>
            )}
            {revisao.alertas.length > 0 && (
              <section className="rounded-xl border border-warn-200 bg-warn-100 px-4 py-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-700" />
                  <div className="space-y-1">
                    {revisao.alertas.map((a, i) => (
                      <p key={i} className="text-xs leading-5 text-warn-800">
                        {a}
                      </p>
                    ))}
                  </div>
                </div>
              </section>
            )}
          </div>
        )}
      </Modal>

      {/* Preview EXPLÍCITO da materialização da extração de IA (dry_run).
          O usuário vê o que SERÁ aplicado e confirma ou pula. */}
      <Modal
        open={!!preview}
        onClose={fecharPreviewSemDecidir}
        title="Aplicar dados extraídos ao caso"
        footer={
          <>
            <button
              className="btn-ghost"
              disabled={aplicando}
              onClick={abrirJornadaSemAplicar}
            >
              Abrir jornada sem aplicar
            </button>
            <button
              className="btn-primary"
              disabled={
                aplicando ||
                (preview
                  ? preview.result.partes_criadas +
                      preview.result.areas_criadas +
                      preview.result.prazos_criados +
                      preview.result.campos_preenchidos.length ===
                    0
                  : true)
              }
              onClick={aplicarPreviewNoCaso}
            >
              {aplicando
                ? "Preenchendo jornada..."
                : "Confirmar e preencher jornada"}
            </button>
          </>
        }
      >
        {preview && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              A IA extraiu dados do documento importado para o caso{" "}
              <span className="font-medium text-slate-900">
                {preview.caseTitulo}
              </span>
              . Confira o que será aplicado:
            </p>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <span className="text-slate-600">Partes a criar</span>
                <span className="font-semibold text-slate-900">
                  {preview.result.partes_criadas}
                </span>
              </li>
              <li className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <span className="text-slate-600">Áreas a criar</span>
                <span className="font-semibold text-slate-900">
                  {preview.result.areas_criadas}
                </span>
              </li>
              <li className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Campos a preencher</span>
                  <span className="font-semibold text-slate-900">
                    {preview.result.campos_preenchidos.length}
                  </span>
                </div>
                {preview.result.campos_preenchidos.length > 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    {preview.result.campos_preenchidos.join(", ")}
                  </p>
                )}
              </li>
              <li className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-amber-800">
                    Prazos a criar (rascunho, a confirmar)
                  </span>
                  <span className="font-semibold text-amber-900">
                    {preview.result.prazos_criados}
                  </span>
                </div>
                {preview.result.prazos_criados > 0 && (
                  <p className="mt-1 text-xs text-amber-700">
                    {preview.result.prazos_criados} prazo(s) serão criados como
                    rascunho e já passam a alertar — confira e confirme cada um
                    na tela de Prazos.
                  </p>
                )}
              </li>
            </ul>
            {preview.result.partes_criadas +
              preview.result.areas_criadas +
              preview.result.prazos_criados +
              preview.result.campos_preenchidos.length ===
              0 && (
              <p className="text-xs text-slate-500">
                Nada novo a aplicar — as partes/área/campos já estão preenchidos
                no caso.
              </p>
            )}
            {preview.result.aviso && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                {preview.result.aviso}
              </p>
            )}
          </div>
        )}
      </Modal>

      {/* Exclusão de caso (soft delete): motivo obrigatório no backend (≥ 5 chars) */}
      <ConfirmModal
        open={!!delCaso}
        onClose={() => setDelCaso(null)}
        onConfirm={excluir}
        variant="danger"
        title="Excluir caso"
        message={`O caso "${delCaso?.titulo ?? ""}" será enviado para a Lixeira — a exclusão é reversível pela lixeira. A ação fica registrada na Auditoria com o motivo informado.`}
        confirmLabel="Excluir caso"
        loading={delLoading}
      >
        <div className="mt-3">
          <FieldLabel required>
            Motivo da exclusão (mínimo 5 caracteres)
          </FieldLabel>
          <Textarea
            value={delMotivo}
            onChange={(e) => setDelMotivo(e.target.value)}
            rows={3}
            placeholder="Ex.: caso duplicado, cadastro de teste..."
          />
        </div>
      </ConfirmModal>
    </div>
  );
}
