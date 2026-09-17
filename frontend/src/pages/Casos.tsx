import { toast } from "../components/Toast";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { FileUp, LayoutGrid, List, PenLine } from "lucide-react";
import api, { aplicarExtracao, vincularLoteAoCaso } from "../lib/api";
import { asList } from "../lib/list";
import { useAreas } from "../lib/areas";
import { caseJourneyPath } from "../lib/caseContext";
import type { AplicarExtracaoResult, ExtracaoPayload } from "../lib/api";
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
  ConfirmModal,
  FieldLabel,
  PageHeader,
  Textarea,
  Button,
} from "../components/UI";
import { useAuth } from "../stores/auth";
import { CasosStats } from "../components/Dashboards";
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
import CasosFiltros from "./casos/CasosFiltros";
import CasosTabela from "./casos/CasosTabela";
import NovoCasoDocumentoModal from "./casos/NovoCasoDocumentoModal";
import RevisaoCriacaoModal from "./casos/RevisaoCriacaoModal";
import PreviewExtracaoModal, {
  type PreviewExtracao,
} from "./casos/PreviewExtracaoModal";
import {
  anexarDocumento,
  avisarConflitosDeVinculo,
  classificarErroCriacao,
  montarResumoRevisao,
  type ResumoRevisao,
} from "./casos/casosIntake";

// Página de Casos (auditoria §2.6 #10): orquestração de estado e regras do
// fluxograma documental. Catálogos vivem em casos/casosCatalogo.ts, helpers
// do intake em casos/casosIntake.ts e os blocos de UI (filtros, tabela e
// modais) em casos/*.tsx — esta página não tem mais a marcação deles.

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
  // V2-1.3 — filtro por status EXATO (independente de `arquivoF`, que só
  // distingue ativos/arquivados/todos). "" = sem filtro ("Todos os status"),
  // nunca um valor sentinela: só os seis valores de CASE_STATUS chegam à API,
  // que já valida e devolve 422 para qualquer outro (nunca 500).
  const [statusF, setStatusF] = useState("");
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
  const [preview, setPreview] = useState<PreviewExtracao | null>(null);
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
          status: statusF || undefined,
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
  }, [search, areaF, statusF, advogadoF, arquivoF]);

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
          <CasosFiltros
            search={search}
            setSearch={setSearch}
            areas={areas}
            areaF={areaF}
            setAreaF={setAreaF}
            advogados={advogados}
            advogadoF={advogadoF}
            setAdvogadoF={setAdvogadoF}
            user={user ?? undefined}
            statusF={statusF}
            setStatusF={setStatusF}
            tipoF={tipoF}
            setTipoF={setTipoF}
            arquivoF={arquivoF}
            setArquivoF={setArquivoF}
          />

          <CasosTabela
            erro={erro}
            data={data}
            arquivoF={arquivoF}
            tipoF={tipoF}
            podeExcluir={podeExcluir}
            desarquivandoId={desarquivandoId}
            onRecarregar={load}
            onDesarquivar={desarquivar}
            onPedirExclusao={(caso) => {
              setDelMotivo("");
              setDelCaso(caso);
            }}
          />
        </>
      )}

      <NovoCasoWizard
        open={wizardAberto}
        onClose={() => nav("/casos")}
        onCadastroCompleto={() => nav(NOVO_CASO_DOCUMENTO_PATH)}
      />

      <NovoCasoDocumentoModal
        open={modal}
        onClose={fecharCadastroCompleto}
        onIrCadastroManual={() => nav(NOVO_CASO_MANUAL_PATH)}
        form={form}
        setForm={setForm}
        areas={areas}
        clientes={clientes}
        advogados={advogados}
        pendencia={pendencia}
        rascunhoSalvo={rascunhoSalvo}
        salvando={salvando}
        reanexando={reanexando}
        onReanexar={reanexarDocumento}
        onConcluirSemDocumento={concluirSemDocumento}
        onDescartarRascunho={descartarRascunho}
        onAbrirRevisao={abrirRevisao}
      />

      <RevisaoCriacaoModal
        revisao={revisao}
        salvando={salvando}
        onFechar={() => setRevisao(null)}
        onConfirmar={() => {
          setRevisao(null);
          salvar();
        }}
      />

      <PreviewExtracaoModal
        preview={preview}
        aplicando={aplicando}
        onFechar={fecharPreviewSemDecidir}
        onAplicar={aplicarPreviewNoCaso}
        onAbrirSemAplicar={abrirJornadaSemAplicar}
      />

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
