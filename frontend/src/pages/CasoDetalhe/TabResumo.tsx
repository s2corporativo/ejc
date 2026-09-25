import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Sparkles, RefreshCw, ArchiveRestore } from "lucide-react";
import { toast } from "../../components/Toast";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { areaLabel, useAreas } from "../../lib/areas";
import { mensagemErroIA, ROTULO_IA_NAO_ATIVADA } from "../../lib/iaErro";
import { useIaStatus } from "../../lib/iaStatus";
import IntakeAnalise from "../../components/IntakeAnalise";
import ConversaoChecklist from "../../components/ConversaoChecklist";
import type { Case } from "../../types";
import {
  StatusBadge,
  PriorityBadge,
  RiskBadge,
  Spinner,
  fmtDate,
  fmtMoney,
  Modal,
  ConfirmModal,
  Alert,
  Textarea,
  FieldLabel,
} from "../../components/UI";
import { useAuth } from "../../stores/auth";

interface PendenciaExclusao {
  tipo: string;
  id: string | number;
  descricao: string;
}

// Fechamento inteligente (GET /cases/{id}/encerrar/diagnostico): prazo ativo
// bloqueia; tarefas/financeiro/peças/processo ativo/próxima ação são alertas
// que o operador confirma. Gestão (sócio+) pode justificar o bloqueio.
interface PendenciaFechamento {
  codigo: string;
  tipo: string;
  id: string | number;
  titulo: string;
  descricao: string;
  destino?: string;
}
interface DiagnosticoFechamento {
  pode_encerrar: boolean;
  requer_confirmacao_alertas: boolean;
  bloqueios: PendenciaFechamento[];
  alertas: PendenciaFechamento[];
  processo?: {
    numero_processo: string | null;
    processos_ativos: number;
    pode_sincronizar: boolean;
    ultima_sincronizacao: string | null;
    erro_sincronizacao: string | null;
  };
}

function detalheErro(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  if (typeof detail === "string") return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return fallback;
}

function ExtratoCaso({ caso }: { caso: Case }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [erro, setErro] = useState("");
  const fmt = (v: number) =>
    (v ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const abrir = async () => {
    setOpen(true);
    if (!data) {
      setErro("");
      try {
        const r = await api.get(`/extratos/detalhado/${caso.id}`);
        setData(r.data);
      } catch (e: any) {
        setErro(
          e?.response?.data?.detail || "Falha ao carregar o extrato do caso.",
        );
      }
    }
  };
  if (
    !["superadmin", "admin", "socio", "advogado"].includes(user?.role || "")
  ) {
    return null;
  }

  return (
    <>
      <button onClick={abrir} className="btn-secondary flex items-center gap-1">
        📊 Extrato do caso
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Extrato financeiro do caso"
      >
        {erro ? (
          <div className="py-8 text-center text-danger-600 text-sm">{erro}</div>
        ) : !data ? (
          <Spinner />
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              {[
                ["Entradas", data.resumo?.entradas, "text-success-600"],
                ["A receber", data.resumo?.a_receber, "text-warn-600"],
                ["Saídas (custos)", data.resumo?.saidas, "text-danger-600"],
                [
                  "Saldo",
                  data.resumo?.saldo,
                  (data.resumo?.saldo ?? 0) >= 0
                    ? "text-success-700"
                    : "text-danger-700",
                ],
              ].map(([l, v, cls]: any) => (
                <div key={l} className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">{l}</p>
                  <p className={`text-base font-bold ${cls}`}>
                    {fmt(Number(v))}
                  </p>
                </div>
              ))}
            </div>
            {(data.honorarios ?? []).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                  Honorários
                </p>
                <div className="max-h-40 overflow-y-auto divide-y divide-slate-100">
                  {data.honorarios.map((h: any, i: number) => (
                    <div
                      key={i}
                      className="flex justify-between text-xs py-1.5"
                    >
                      <span className="text-slate-600 capitalize">
                        {h.tipo?.replace(/_/g, " ")} · {h.status}
                      </span>
                      <span className="font-medium">{fmt(h.valor)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

function AreasCaso({ caso }: { caso: Case }) {
  const catalogoAreas = useAreas();
  const [areas, setAreas] = useState<any[]>([]);
  const [add, setAdd] = useState("");
  const load = () =>
    api
      .get(`/cases/${caso.id}/areas`)
      .then((r) => setAreas(r.data?.areas ?? []))
      .catch(() => {});
  useEffect(() => {
    load(); /* eslint-disable-next-line */
  }, [caso.id]);
  const adicionar = async () => {
    if (!add) return;
    await api.post(`/cases/${caso.id}/areas`, { area: add });
    setAdd("");
    load();
  };
  const remover = async (a: string) => {
    if (!confirm("Remover esta área do caso?")) return;
    try {
      await api.delete(`/cases/${caso.id}/areas/${a}`);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover área");
    }
  };
  const disponiveis = catalogoAreas.filter(
    (item) => !areas.some((a) => a.area === item.slug),
  );
  return (
    <div className="card p-4">
      <h3 className="font-semibold mb-2 text-sm text-slate-500 uppercase tracking-wide">
        Áreas do caso
      </h3>
      <div className="flex flex-wrap gap-2 items-center">
        {areas.map((a) => (
          <span
            key={a.area}
            className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full ${a.principal ? "bg-navy text-white" : "bg-slate-100 text-slate-600"}`}
          >
            {a.principal && "★ "}
            {areaLabel(a.area)}
            {!a.principal && (
              <button
                onClick={() => remover(a.area)}
                className="ml-1 opacity-60 hover:opacity-100"
              >
                ×
              </button>
            )}
          </span>
        ))}
        {disponiveis.length > 0 && (
          <span className="inline-flex items-center gap-1">
            <select
              value={add}
              onChange={(e) => setAdd(e.target.value)}
              className="input text-xs px-2 py-1"
            >
              <option value="">+ área relacionada</option>
              {disponiveis.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.nome}
                </option>
              ))}
            </select>
            {add && (
              <button
                onClick={adicionar}
                className="text-xs bg-bronze text-white px-2 py-1 rounded-lg"
              >
                Add
              </button>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

// Aviso + controle de reabertura de caso encerrado/arquivado. Exportado para a
// Visão do caso (CasoDetalhe) exibi-lo em destaque no topo — acima do painel do
// orquestrador — mesmo com a linha "Dados do caso" recolhida (review PR #483).
export function AvisoCasoEncerrado({ caso }: { caso: Case }) {
  const [reabrindo, setReabrindo] = useState(false);

  const reabrir = async () => {
    setReabrindo(true);
    try {
      if (caso.status === "arquivado") {
        await api.post(`/cases/${caso.id}/desarquivar`);
        toast.success("Caso desarquivado.");
      } else {
        // V2-B3 (plano-mestre): endpoint dedicado restaura o estágio real de
        // trabalho anterior (em_instrucao/em_producao/protocolado) em vez de
        // sempre forçar "aberto" via PATCH cru.
        await api.post(`/cases/${caso.id}/reabrir`);
        toast.success("Caso reaberto.");
      }
      window.location.reload();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao reabrir caso");
    } finally {
      setReabrindo(false);
    }
  };

  if (caso.status !== "encerrado" && caso.status !== "arquivado") return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <p className="text-sm text-amber-800">
        Este caso está{" "}
        <strong>
          {caso.status === "arquivado" ? "arquivado" : "encerrado"}
        </strong>
        . Edições e novos lançamentos estão bloqueados enquanto ele não for
        reaberto.
      </p>
      <button
        onClick={reabrir}
        disabled={reabrindo}
        className="btn-secondary flex items-center gap-1 whitespace-nowrap border-amber-300 text-amber-800"
      >
        {caso.status === "arquivado" ? (
          <ArchiveRestore
            size={14}
            className={reabrindo ? "animate-spin" : ""}
          />
        ) : (
          <RefreshCw size={14} className={reabrindo ? "animate-spin" : ""} />
        )}
        {reabrindo
          ? "Reabrindo..."
          : caso.status === "arquivado"
            ? "Desarquivar caso"
            : "Reabrir caso"}
      </button>
    </div>
  );
}

export default function TabResumo({
  caso,
  ocultarAvisoEncerramento = false,
}: {
  caso: Case;
  // A Visão já mostra o AvisoCasoEncerrado no topo; evita o banner duplicado
  // quando a linha "Dados do caso" está expandida.
  ocultarAvisoEncerramento?: boolean;
}) {
  const { disponivel: iaDisponivel } = useIaStatus();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [iaModal, setIaModal] = useState(false);
  const [iaResp, setIaResp] = useState<any>(null);
  const [iaLoading, setIaLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [movs, setMovs] = useState<any[]>([]);
  const [novoMov, setNovoMov] = useState("");
  const [encModal, setEncModal] = useState(false);
  const [encLoading, setEncLoading] = useState(false);
  const [encSimplesModal, setEncSimplesModal] = useState(false);
  const [encSimplesLoading, setEncSimplesLoading] = useState(false);
  const [encSimples, setEncSimples] = useState({
    cliente_nome: "",
    valor_recebido: "",
  });
  const [sigiloSalvando, setSigiloSalvando] = useState(false);
  const [enc, setEnc] = useState({
    // Vocabulário CANÔNICO do backend (EncerrarCasoReq) — é o mesmo que a
    // jurimetria consome. "exito_total"/"improcedente" não existem lá e o
    // encerramento voltava 422 já no valor default do formulário.
    resultado: "exito",
    motivo_resultado: "",
    provas_determinantes: "",
    licoes_aprendidas: "",
    alimentar_rag: true,
    // Puxa a movimentação final do tribunal (MNI/PJe) ao encerrar, para o
    // acervo do caso fechar completo. Opt-in.
    sincronizar_processo_eletronico: false,
    confirmar_alertas: false,
    justificativa_bloqueio: "",
  });
  const [encDiag, setEncDiag] = useState<DiagnosticoFechamento | null>(null);
  const [encDiagLoading, setEncDiagLoading] = useState(false);
  const [gerando, setGerando] = useState(false);
  const [honModal, setHonModal] = useState(false);
  const [honLoading, setHonLoading] = useState(false);
  const [honDesc, setHonDesc] = useState("");
  const [honResp, setHonResp] = useState<any>(null);
  // R2 — arquivar / excluir
  const [arqModal, setArqModal] = useState(false);
  const [arqLoading, setArqLoading] = useState(false);
  const [delModal, setDelModal] = useState(false);
  const [delLoading, setDelLoading] = useState(false);
  const [delMotivo, setDelMotivo] = useState("");
  const [pendencias, setPendencias] = useState<PendenciaExclusao[] | null>(
    null,
  );
  // Exclusão restrita a administração/sócios (soft delete → Lixeira)
  const podeExcluir = ["superadmin", "admin", "socio"].includes(
    user?.role || "",
  );

  const arquivar = async () => {
    setArqLoading(true);
    try {
      await api.post(`/cases/${caso.id}/arquivar`);
      toast.success("Caso arquivado.");
      window.location.reload();
    } catch (e) {
      toast.error(detalheErro(e, "Falha ao arquivar o caso"));
      setArqLoading(false);
    }
  };

  const desarquivar = async () => {
    setArqLoading(true);
    try {
      await api.post(`/cases/${caso.id}/desarquivar`);
      toast.success("Caso desarquivado.");
      window.location.reload();
    } catch (e) {
      toast.error(detalheErro(e, "Falha ao desarquivar o caso"));
      setArqLoading(false);
    }
  };

  const excluir = async () => {
    const motivo = delMotivo.trim();
    if (motivo.length < 5) {
      toast.error("Informe o motivo da exclusão (mínimo 5 caracteres).");
      return;
    }
    setDelLoading(true);
    setPendencias(null);
    try {
      await api.delete(`/cases/${caso.id}`, { data: { motivo } });
      toast.success("Caso excluído — enviado para a Lixeira.");
      navigate("/casos");
    } catch (e: any) {
      const detail =
        e?.response?.status === 422 ? e?.response?.data?.detail : null;
      if (
        detail &&
        Array.isArray(detail.pendencias) &&
        detail.pendencias.length
      ) {
        setPendencias(detail.pendencias as PendenciaExclusao[]);
      } else {
        toast.error(detalheErro(e, "Falha ao excluir o caso"));
      }
    } finally {
      setDelLoading(false);
    }
  };

  useEffect(() => {
    api
      .get(`/cases/${caso.id}/movimentos`)
      .then((r) => setMovs(asList(r.data)))
      .catch(() => {});
  }, [caso.id]);

  const encerrarSimples = async () => {
    const valor = Number(encSimples.valor_recebido || 0);
    if (!encSimples.cliente_nome.trim()) {
      toast.error("Informe o nome do cliente.");
      return;
    }
    if (!Number.isFinite(valor) || valor < 0) {
      toast.error("Informe um valor válido.");
      return;
    }
    setEncSimplesLoading(true);
    try {
      const { data } = await api.post(`/cases/${caso.id}/encerrar-simples`, {
        cliente_nome: encSimples.cliente_nome.trim(),
        valor_recebido: valor,
      });
      setEncSimplesModal(false);
      const regra = data?.rateio?.regra;
      toast.success(
        regra === "civil_integral_escritorio"
          ? "Caso encerrado. Valor lançado integralmente para o escritório."
          : regra === "rateio_50_50"
            ? "Caso encerrado. Valor lançado com rateio 50% responsável / 50% escritório."
            : "Caso encerrado.",
      );
      window.location.reload();
    } catch (e: any) {
      toast.error(detalheErro(e, "Falha ao encerrar o caso"));
    } finally {
      setEncSimplesLoading(false);
    }
  };

  // Diagnóstico ao abrir o modal: o operador vê prazos/tarefas/financeiro/
  // processo ativo ANTES de confirmar, e "sincronizar antes de encerrar" já
  // vem marcado quando há processo vinculado.
  const abrirEncerrar = async () => {
    setEncModal(true);
    setEncDiag(null);
    setEncDiagLoading(true);
    try {
      const { data } = await api.get<DiagnosticoFechamento>(
        `/cases/${caso.id}/encerrar/diagnostico`,
      );
      setEncDiag(data);
      setEnc((prev) => ({
        ...prev,
        confirmar_alertas: false,
        justificativa_bloqueio: "",
        sincronizar_processo_eletronico: Boolean(
          data.processo?.pode_sincronizar && data.processo?.processos_ativos,
        ),
      }));
    } catch (e: any) {
      toast.error(
        detalheErro(e, "Não foi possível verificar as pendências do caso."),
      );
    } finally {
      setEncDiagLoading(false);
    }
  };

  const podeJustificarBloqueio = ["superadmin", "admin", "socio"].includes(
    user?.role || "",
  );
  const encBloqueado =
    Boolean(encDiag?.bloqueios.length) &&
    !(podeJustificarBloqueio && enc.justificativa_bloqueio.trim().length >= 20);
  const encPrecisaConfirmar =
    Boolean(encDiag?.alertas.length) &&
    !enc.confirmar_alertas &&
    !(podeJustificarBloqueio && enc.justificativa_bloqueio.trim().length >= 20);

  const encerrar = async () => {
    setEncLoading(true);
    try {
      const payload = {
        ...enc,
        justificativa_bloqueio: enc.justificativa_bloqueio.trim() || null,
      };
      const { data } = await api.post(`/cases/${caso.id}/encerrar`, payload);
      setEncModal(false);
      toast.success(data?.detail || "Caso encerrado.");
      const memoria = data?.memoria_institucional;
      const falhaPrecedenteRag =
        memoria?.precedente_rag === "falha_acessoria";
      if (falhaPrecedenteRag) {
        toast.error(
          "Caso encerrado, mas o precedente não pôde ser registrado no RAG. O encerramento foi preservado.",
        );
      }
      // A sincronização é assíncrona e degrada graciosamente no backend: o
      // encerramento vale mesmo quando ela não sai. Reporta o que de fato
      // aconteceu, em vez de prometer o que foi apenas pedido.
      const sinc = data?.sincronizacao_processo_eletronico;
      if (sinc?.solicitada && sinc.status !== "enfileirado") {
        // O caso ESTÁ encerrado; só a sincronização falhou. Recarregar aqui
        // apagaria o toast antes de ele renderizar e o operador acharia que o
        // tribunal foi consultado. Mantém a página e fixa o motivo na tela.
        setSincFalhou(
          sinc.detalhe || "Não foi possível sincronizar com o tribunal.",
        );
        toast.error(sinc.detalhe || "Não foi possível sincronizar com o tribunal.");
        return;
      }
      if (sinc?.solicitada) {
        toast.success(
          "Sincronização com o tribunal enfileirada — acompanhe em Processo Eletrônico.",
        );
      }
      // Em falha acessória do RAG, não recarrega imediatamente: o toast é
      // estado React e seria descartado antes de o operador conseguir lê-lo.
      // O caso já está encerrado no backend; manter a página é fail-safe e
      // preserva a informação operacional sem alterar o resultado jurídico.
      if (falhaPrecedenteRag) return;
      window.location.reload();
    } catch (e: any) {
      // 422 do fechamento inteligente traz a lista atualizada de pendências.
      const detail = e.response?.data?.detail;
      if (detail && typeof detail === "object" && Array.isArray(detail.alertas)) {
        setEncDiag((prev) => ({
          pode_encerrar: !detail.bloqueios?.length,
          requer_confirmacao_alertas: detail.alertas.length > 0,
          bloqueios: detail.bloqueios || [],
          alertas: detail.alertas,
          processo: detail.processo ?? prev?.processo,
        }));
        toast.error(detail.mensagem || "Caso com pendências");
      } else {
        toast.error(detalheErro(e, "Falha ao encerrar"));
      }
    } finally {
      setEncLoading(false);
    }
  };

  const gerarDocs = async () => {
    setGerando(true);
    try {
      const { data } = await api.post(`/cases/${caso.id}/gerar-documentos`);
      toast.success(
        `${data.gerados?.length || 0} minuta(s) gerada(s): Procuração, Contrato de Honorários e Relatório Inicial. Veja na aba Documentos do caso.`,
      );
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao gerar documentos");
    } finally {
      setGerando(false);
    }
  };
  const sugerirHonorarios = async () => {
    setHonLoading(true);
    setHonResp(null);
    try {
      const { data } = await api.post("/ai/sugestao-honorarios", {
        area: caso.area,
        descricao: honDesc || caso.titulo,
        valor_causa: caso.valor_causa || undefined,
      });
      setHonResp(data);
    } catch (e: any) {
      setHonResp({
        erro: mensagemErroIA(e, "Não foi possível sugerir honorários."),
      });
    } finally {
      setHonLoading(false);
    }
  };

  const analisarIA = async () => {
    setIaModal(true);
    setIaLoading(true);
    setIaResp(null);
    try {
      const { data } = await api.post("/ai/analisar-caso", {
        descricao_fatos: caso.descricao_fatos,
        area: caso.area,
        case_id: caso.id,
        nomes_proteger: [caso.parte_contraria].filter(Boolean),
      });
      setIaResp(data);
    } catch (e: any) {
      setIaResp({
        erro: mensagemErroIA(e, "Não foi possível gerar a análise."),
      });
    } finally {
      setIaLoading(false);
    }
  };

  const addMov = async () => {
    if (!novoMov.trim()) return;
    await api.post(`/cases/${caso.id}/movimentos`, {
      tipo: "nota",
      descricao: novoMov,
    });
    setNovoMov("");
    api
      .get(`/cases/${caso.id}/movimentos`)
      .then((r) => setMovs(asList(r.data)))
      .catch(() => {});
  };

  // Sigilo reforçado de IA (Issue #1194): único jeito de o piso LOCAL_COMPLETO
  // da sanitization_policy alcançar um caso real de crime sexual/menor — área
  // do caso não tem granularidade para isso. PATCH direto + reload, mesmo
  // padrão de AvisoCasoEncerrado.reabrir().
  const toggleSigilo = async (marcar: boolean) => {
    setSigiloSalvando(true);
    try {
      await api.patch(`/cases/${caso.id}`, { sigilo_reforcado: marcar });
      toast.success(
        marcar
          ? "Sigilo reforçado ativado — a IA deste caso passa a exigir provedor local."
          : "Sigilo reforçado desativado.",
      );
      window.location.reload();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha ao atualizar sigilo reforçado",
      );
      setSigiloSalvando(false);
    }
  };

  const syncDataJud = async () => {
    if (!caso.processo_principal?.numero_cnj) {
      toast.error("Adicione um processo com número CNJ antes de sincronizar.");
      return;
    }
    setSyncing(true);
    try {
      const { data } = await api.post(`/cases/${caso.id}/sincronizar-processo`);
      toast.success(data.detail || "Dados sincronizados com DataJud.");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao sincronizar");
    } finally {
      setSyncing(false);
    }
  };

  // #R8 — conversão em judicial passa pelo checklist bloqueante (ConversaoChecklist)
  const [convModal, setConvModal] = useState(false);
  // Motivo pelo qual a sincronização pedida no encerramento não saiu. Fica na
  // tela porque é a ÚNICA indicação de que o tribunal não foi consultado — um
  // toast morreria no reload que segue o encerramento.
  const [sincFalhou, setSincFalhou] = useState<string | null>(null);

  const casoEncerrado =
    caso.status === "encerrado" || caso.status === "arquivado";

  return (
    <div className="space-y-5">
      {casoEncerrado && !ocultarAvisoEncerramento && (
        <AvisoCasoEncerrado caso={caso} />
      )}
      {sincFalhou && (
        <Alert variant="warning" title="Caso encerrado, sem sincronização">
          <p>{sincFalhou}</p>
          <button
            className="mt-2 underline hover:no-underline"
            onClick={() => window.location.reload()}
          >
            Atualizar a página
          </button>
        </Alert>
      )}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={analisarIA}
          disabled={!iaDisponivel}
          title={iaDisponivel ? undefined : ROTULO_IA_NAO_ATIVADA}
          className="btn-primary flex items-center gap-1 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles size={14} />{" "}
          {iaDisponivel ? "Análise IA" : "IA não ativada"}
        </button>
        <button
          onClick={syncDataJud}
          disabled={syncing}
          className="btn-secondary flex items-center gap-1"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Consultando..." : "Sincronizar DataJud"}
        </button>
        <button
          onClick={gerarDocs}
          disabled={gerando}
          className="btn-secondary flex items-center gap-1"
        >
          📄 {gerando ? "Gerando..." : "Gerar documentos"}
        </button>
        <button
          onClick={() => {
            setHonDesc(caso.titulo);
            setHonResp(null);
            setHonModal(true);
          }}
          className="btn-secondary flex items-center gap-1"
        >
          💰 Honorários (OAB)
        </button>
        <Link
          to={`/raio-x?case_id=${caso.id}`}
          className="btn-secondary flex items-center gap-1 text-primary-700"
        >
          🔎 Raio-X do processo
        </Link>
        {/* Fase 1: o botão "Jornada do caso" saiu daqui — a jornada agora vive
            embutida na própria Visão (painel do orquestrador acima). */}
        <button
          onClick={() => navigate(`/casos/${caso.id}/entrevista`)}
          className="btn-secondary flex items-center gap-1"
        >
          🎤 Entrevista inteligente
        </button>
        <Link
          to={`/pecas?caso=${caso.id}`}
          className="btn-secondary flex items-center gap-1"
        >
          📝 Peças do caso
        </Link>
        <ExtratoCaso caso={caso} />
        {/* Ajuizamento: mesma entidade Caso, sem redigitação — o wizard lê
            cliente, partes, documentos e peças deste caso. */}
        <Link
          to={`/ajuizamento?caso=${caso.id}`}
          className="btn-secondary flex items-center gap-1"
        >
          ⚖️ Ajuizar ação
        </Link>
        {(caso as any).case_type === "extrajudicial" &&
          !(caso as any).linked_judicial_case_id && (
            <button
              onClick={() => setConvModal(true)}
              className="btn-secondary flex items-center gap-1 text-primary-700 border-primary-200"
            >
              ⚖️ Converter em processo judicial
            </button>
          )}
        {(caso as any).linked_judicial_case_id && (
          <button
            onClick={() =>
              navigate(`/casos/${(caso as any).linked_judicial_case_id}`)
            }
            className="btn-secondary flex items-center gap-1 text-primary-700 border-primary-200"
          >
            🔗 Ver caso vinculado
          </button>
        )}
        <div
          className="basis-full mt-2 rounded-xl border border-slate-200 bg-slate-50 p-3"
          aria-label="Encerramento e administração do caso"
        >
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Encerramento e administração
          </div>
          <div className="flex flex-wrap gap-2">
            {caso.status !== "encerrado" && caso.status !== "arquivado" && (
              <>
                <button
                  onClick={() => {
                    setEncSimples({ cliente_nome: "", valor_recebido: "" });
                    setEncSimplesModal(true);
                  }}
                  className="btn-primary flex items-center gap-1"
                >
                  ✓ Encerrar caso
                </button>
                <button
                  onClick={abrirEncerrar}
                  className="btn-secondary flex items-center gap-1"
                  title="Encerramento com resultado, provas, lições e diagnóstico de pendências"
                >
                  Pós-mortem detalhado
                </button>
              </>
            )}
            {caso.status !== "arquivado" ? (
              <button
                onClick={() => setArqModal(true)}
                className="btn-secondary flex items-center gap-1"
              >
                🗄️ Arquivar
              </button>
            ) : (
              <button
                onClick={desarquivar}
                disabled={arqLoading}
                className="btn-secondary flex items-center gap-1"
              >
                🗄️ {arqLoading ? "Desarquivando..." : "Desarquivar"}
              </button>
            )}
            {podeExcluir && (
              <button
                onClick={() => {
                  setDelMotivo("");
                  setPendencias(null);
                  setDelModal(true);
                }}
                className="btn-secondary flex items-center gap-1 text-danger-600 border-danger-200 hover:bg-danger-50"
              >
                🗑️ Excluir
              </button>
            )}
          </div>
        </div>
      </div>

      <AreasCaso caso={caso} />

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-5">
          <h3 className="font-semibold mb-3 text-sm text-slate-500 uppercase tracking-wide">
            Dados do Processo
          </h3>
          <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-sm">
            <div>
              <span className="text-slate-400">Área:</span>{" "}
              <span className="capitalize ml-1">{caso.area}</span>
            </div>
            <div>
              <span className="text-slate-400">Status:</span>{" "}
              <StatusBadge value={caso.status} />
            </div>
            <div>
              <span className="text-slate-400">Fase:</span>{" "}
              <span className="capitalize ml-1">
                {caso.fase?.replace(/_/g, " ")}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">Prioridade:</span>{" "}
              <PriorityBadge value={caso.prioridade} />
            </div>
            {(caso.risco_nivel || caso.risco) && (
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400">Risco:</span>{" "}
                <RiskBadge value={caso.risco_nivel || caso.risco} />
              </div>
            )}
            {["superadmin", "admin", "socio", "advogado"].includes(
              user?.role || "",
            ) ? (
              <div className="col-span-2 flex items-center gap-1.5">
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={!!caso.sigilo_reforcado}
                    disabled={sigiloSalvando}
                    onChange={(e) => toggleSigilo(e.target.checked)}
                  />
                  <span className="text-slate-400">
                    Sigilo reforçado (crime sexual/menor) — IA só via provedor
                    local
                  </span>
                </label>
              </div>
            ) : (
              caso.sigilo_reforcado && (
                <div className="col-span-2">
                  <span className="badge bg-danger-50 text-danger-700 border border-danger-200">
                    🔒 Sigilo reforçado — IA restrita a provedor local
                  </span>
                </div>
              )
            )}
            <div>
              <span className="text-slate-400">Parte contrária:</span>{" "}
              <span className="ml-1">{caso.parte_contraria || "—"}</span>
            </div>
            {["superadmin", "admin", "socio", "advogado"].includes(
              user?.role || "",
            ) && (
              <div>
                <span className="text-slate-400">Valor:</span>{" "}
                <span className="ml-1">{fmtMoney(caso.valor_causa)}</span>
              </div>
            )}
            {caso.comarca && (
              <div>
                <span className="text-slate-400">Comarca/Vara:</span>{" "}
                <span className="ml-1">
                  {caso.comarca} {caso.vara && `· ${caso.vara}`}
                </span>
              </div>
            )}
            {caso.data_prescricao && (
              <div className="text-danger-700 font-medium">
                <span className="text-slate-400">Prescrição:</span>{" "}
                <span className="ml-1">{fmtDate(caso.data_prescricao)}</span>
              </div>
            )}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-semibold mb-3 text-sm text-slate-500 uppercase tracking-wide">
            Timeline Recente
          </h3>
          <div className="text-sm text-slate-400 mb-2">
            <input
              value={novoMov}
              onChange={(e) => setNovoMov(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addMov()}
              placeholder="Nova anotação... (Enter para salvar)"
              className="input w-full text-xs"
            />
          </div>
          <div className="max-h-40 overflow-auto divide-y divide-slate-100">
            {movs.map((e) => (
              <div key={e.id} className="py-1.5 flex justify-between text-xs">
                <span className="text-slate-600">{e.descricao}</span>
                <span className="text-slate-400 ml-2 shrink-0">
                  {fmtDate(e.created_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {caso.descricao_fatos && (
        <div className="card p-5">
          <h3 className="font-semibold mb-2 text-sm text-slate-500">
            Descrição dos Fatos
          </h3>
          <p className="text-sm text-slate-700 leading-relaxed">
            {caso.descricao_fatos}
          </p>
        </div>
      )}

      {caso.proxima_acao && (
        <div className="card p-5 border-l-4 border-primary-400">
          <h3 className="font-semibold mb-2 text-sm text-primary-600">
            Próxima Ação
          </h3>
          <p className="text-sm text-slate-700 leading-relaxed">
            {caso.proxima_acao}
          </p>
          {caso.proxima_acao_prazo && (
            <p className="mt-1 text-xs text-slate-500">
              Prazo: {fmtDate(caso.proxima_acao_prazo)}
            </p>
          )}
        </div>
      )}

      {/* Intake — Análise Completa (IA): área, teses, estratégia, honorários e módulos */}
      <IntakeAnalise caseId={caso.id} />

      {(caso as any).tese_principal && (
        <div className="grid lg:grid-cols-2 gap-5">
          {(caso as any).tese_principal && (
            <div className="card p-5">
              <h3 className="font-semibold mb-2 text-sm text-green-600">
                Pontos Fortes
              </h3>
              <p className="text-sm text-slate-700">
                {(caso as any).pontos_fortes}
              </p>
            </div>
          )}
          {(caso as any).pontos_fracos && (
            <div className="card p-5">
              <h3 className="font-semibold mb-2 text-sm text-danger-600">
                Pontos de Atenção
              </h3>
              <p className="text-sm text-slate-700">
                {(caso as any).pontos_fracos}
              </p>
            </div>
          )}
        </div>
      )}

      {iaModal && (
        <Modal
          open={iaModal}
          onClose={() => setIaModal(false)}
          title="Análise de IA — EJC Núcleo Cognitivo"
        >
          {iaLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : iaResp?.erro ? (
            <p className="text-danger-600">{iaResp.erro}</p>
          ) : (
            <div className="space-y-3 text-sm">
              {iaResp?.analise && (
                <p className="text-slate-700 leading-relaxed">
                  {iaResp.analise}
                </p>
              )}
              {iaResp?.pontos_fortes?.length > 0 && (
                <div>
                  <p className="font-semibold text-green-700 mb-1">
                    Pontos Fortes
                  </p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {iaResp.pontos_fortes.map((p: string, i: number) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              {iaResp?.pontos_fracos?.length > 0 && (
                <div>
                  <p className="font-semibold text-danger-700 mb-1">
                    Pontos de Atenção
                  </p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {iaResp.pontos_fracos.map((p: string, i: number) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-warn-600 border-t pt-2">
                ⚠️ Rascunho gerado por IA — revisão humana obrigatória (OAB)
              </p>
            </div>
          )}
        </Modal>
      )}

      {encSimplesModal && (
        <Modal
          open={encSimplesModal}
          onClose={() => setEncSimplesModal(false)}
          title="Encerrar caso"
        >
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              Encerramento direto. O EJC preservará documentos, prazos, histórico e
              pendências existentes; nenhuma etapa será apagada.
            </p>
            <div>
              <label className="label">Nome do cliente</label>
              <input
                className="input w-full"
                autoComplete="off"
                value={encSimples.cliente_nome}
                onChange={(e) =>
                  setEncSimples({ ...encSimples, cliente_nome: e.target.value })
                }
                placeholder="Digite o nome do cliente para confirmar"
              />
            </div>
            <div>
              <label className="label">Valor total recebido pelo escritório (R$)</label>
              <input
                type="number"
                min="0"
                step="0.01"
                className="input w-full"
                value={encSimples.valor_recebido}
                onChange={(e) =>
                  setEncSimples({ ...encSimples, valor_recebido: e.target.value })
                }
                placeholder="0,00"
              />
              <p className="mt-1 text-xs text-slate-500">
                Informe o total de honorários efetivamente recebidos pelo escritório neste caso. O EJC lançará apenas a diferença ainda não registrada. Não inclua valores do principal pertencentes ao cliente.
              </p>
            </div>
            <button
              onClick={encerrarSimples}
              disabled={encSimplesLoading}
              className="btn-primary w-full"
            >
              {encSimplesLoading ? "Encerrando..." : "Confirmar encerramento"}
            </button>
          </div>
        </Modal>
      )}

      {encModal && (
        <Modal
          open={encModal}
          onClose={() => setEncModal(false)}
          title="Encerrar caso — Pós-Mortem"
        >
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              Ao encerrar, o conhecimento do caso vira ativo institucional:{" "}
              <b>precedente na base de conhecimento</b> +{" "}
              <b>memória institucional</b> + <b>tese no banco</b>. Tudo como
              rascunho revisável (OAB).
            </p>
            {encDiagLoading && (
              <p className="text-xs text-slate-400">Verificando pendências…</p>
            )}
            {encDiag && encDiag.bloqueios.length > 0 && (
              <Alert variant="error" title="Encerramento bloqueado">
                <ul className="list-disc pl-4 text-xs">
                  {encDiag.bloqueios.map((b) => (
                    <li key={`${b.codigo}-${b.id}`}>
                      <b>{b.titulo}</b> — {b.descricao}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs">
                  Conclua ou cancele os prazos antes de encerrar
                  {podeJustificarBloqueio
                    ? ", ou registre abaixo uma justificativa (mínimo 20 caracteres) — ela fica na auditoria."
                    : ". Somente sócio/administração pode encerrar com justificativa."}
                </p>
              </Alert>
            )}
            {encDiag && encDiag.alertas.length > 0 && (
              <Alert variant="warning" title="Pendências do caso">
                <ul className="list-disc pl-4 text-xs">
                  {encDiag.alertas.map((a) => (
                    <li key={`${a.codigo}-${a.id}`}>
                      <b>{a.titulo}</b> — {a.descricao}
                    </li>
                  ))}
                </ul>
              </Alert>
            )}
            {encDiag && !encDiag.bloqueios.length && !encDiag.alertas.length && (
              <Alert variant="success" title="Sem pendências">
                Nenhum prazo, tarefa, honorário, peça ou processo em aberto.
              </Alert>
            )}
            {encDiag && encDiag.bloqueios.length > 0 && podeJustificarBloqueio && (
              <div>
                <label className="label">Justificativa para encerrar com prazo aberto</label>
                <textarea
                  rows={2}
                  className="input w-full"
                  value={enc.justificativa_bloqueio}
                  onChange={(e) =>
                    setEnc({ ...enc, justificativa_bloqueio: e.target.value })
                  }
                />
              </div>
            )}
            <div>
              <label className="label">Resultado</label>
              <select
                className="input w-full"
                value={enc.resultado}
                onChange={(e) => setEnc({ ...enc, resultado: e.target.value })}
              >
                <option value="exito">Êxito</option>
                <option value="exito_parcial">Êxito parcial</option>
                <option value="acordo">Acordo</option>
                <option value="derrota">Derrota</option>
                <option value="desistencia">Desistência</option>
                <option value="arquivado">Arquivado</option>
              </select>
            </div>
            <div>
              <label className="label">Motivo do resultado</label>
              <textarea
                rows={2}
                className="input w-full"
                value={enc.motivo_resultado}
                onChange={(e) =>
                  setEnc({ ...enc, motivo_resultado: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Provas determinantes</label>
              <textarea
                rows={2}
                className="input w-full"
                value={enc.provas_determinantes}
                onChange={(e) =>
                  setEnc({ ...enc, provas_determinantes: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Lições aprendidas</label>
              <textarea
                rows={2}
                className="input w-full"
                value={enc.licoes_aprendidas}
                onChange={(e) =>
                  setEnc({ ...enc, licoes_aprendidas: e.target.value })
                }
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={enc.alimentar_rag}
                onChange={(e) =>
                  setEnc({ ...enc, alimentar_rag: e.target.checked })
                }
              />
              Alimentar a base de conhecimento
            </label>
            {encDiag && encDiag.alertas.length > 0 && (
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={enc.confirmar_alertas}
                  onChange={(e) =>
                    setEnc({ ...enc, confirmar_alertas: e.target.checked })
                  }
                />
                Estou ciente das pendências acima e desejo encerrar mesmo assim
              </label>
            )}
            <label className="flex items-start gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                className="mt-1"
                checked={enc.sincronizar_processo_eletronico}
                onChange={(e) =>
                  setEnc({
                    ...enc,
                    sincronizar_processo_eletronico: e.target.checked,
                  })
                }
              />
              <span>
                Sincronizar com o tribunal (PJe/MNI) antes de arquivar
                {caso.numero_processo ? (
                  <span className="block text-xs text-slate-400">
                    Processo {caso.numero_processo} — puxa a movimentação e os
                    documentos finais para o acervo do caso.
                  </span>
                ) : (
                  <span className="block text-xs text-amber-600">
                    Caso sem número de processo cadastrado — não há o que
                    sincronizar.
                  </span>
                )}
              </span>
            </label>
            <button
              onClick={encerrar}
              disabled={encLoading || encDiagLoading || encBloqueado || encPrecisaConfirmar}
              className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
            >
              {encLoading ? "Encerrando..." : "Confirmar encerramento"}
            </button>
          </div>
        </Modal>
      )}

      {honModal && (
        <Modal
          open={honModal}
          onClose={() => setHonModal(false)}
          title="Sugestão de honorários — Tabela OAB/MG"
        >
          <div className="space-y-3">
            <div>
              <label className="label">Serviço / ato</label>
              <input
                className="input w-full"
                value={honDesc}
                onChange={(e) => setHonDesc(e.target.value)}
              />
            </div>
            <p className="text-xs text-slate-400">
              Área: <span className="capitalize">{caso.area}</span> · Valor da
              causa: {fmtMoney(caso.valor_causa)}
            </p>
            <button
              onClick={sugerirHonorarios}
              disabled={honLoading}
              className="btn-primary w-full"
            >
              {honLoading ? "Consultando a tabela…" : "Sugerir honorários"}
            </button>
            {honResp?.erro && (
              <p className="text-sm text-danger-600">{honResp.erro}</p>
            )}
            {honResp?.sugestao && (
              <div className="text-sm space-y-1.5 border-t border-bronze-pale pt-3">
                <div>
                  <span className="text-slate-400">Mínimo OAB:</span>{" "}
                  <b className="text-navy">
                    {honResp.sugestao.honorario_minimo_oab}
                  </b>
                </div>
                <div>
                  <span className="text-slate-400">Recomendado:</span>{" "}
                  <b className="text-navy">
                    {honResp.sugestao.honorario_recomendado}
                  </b>
                </div>
                <div>
                  <span className="text-slate-400">Êxito:</span>{" "}
                  <b className="text-navy">
                    {honResp.sugestao.percentual_exito}
                  </b>
                </div>
                {honResp.sugestao.fundamento && (
                  <p className="text-xs text-slate-500">
                    {honResp.sugestao.fundamento}
                  </p>
                )}
                <p className="text-xs text-warn-600">{honResp.aviso}</p>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* R2 — Arquivar (confirmação simples) */}
      <ConfirmModal
        open={arqModal}
        onClose={() => setArqModal(false)}
        onConfirm={arquivar}
        variant="primary"
        title="Arquivar caso"
        message="O caso sai das listagens ativas, mas nada é apagado. Ele fica disponível na aba Arquivados e pode ser desarquivado a qualquer momento."
        confirmLabel="Arquivar"
        loading={arqLoading}
      />

      {/* R2 — Excluir (confirmação forte: digitar EXCLUIR + motivo ≥ 5 chars) */}
      <ConfirmModal
        open={delModal}
        onClose={() => {
          setDelModal(false);
          setPendencias(null);
        }}
        onConfirm={excluir}
        variant="danger"
        title="Excluir caso"
        message={`Esta ação envia o caso "${caso.titulo}" para a Lixeira e fica registrada na Auditoria com o motivo informado.`}
        typeToConfirm="EXCLUIR"
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
        {pendencias && pendencias.length > 0 && (
          <Alert
            variant="danger"
            title="Pendências impedem a exclusão"
            className="mt-3"
          >
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {pendencias.map((p, i) => (
                <li key={`${p.tipo}-${p.id ?? i}`}>
                  <span className="capitalize">
                    {String(p.tipo).replace(/_/g, " ")}
                  </span>
                  {p.descricao ? ` — ${p.descricao}` : ""}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => {
                setDelModal(false);
                setPendencias(null);
                arquivar();
              }}
              disabled={arqLoading}
              className="btn-secondary mt-3 flex items-center gap-1 text-xs"
            >
              🗄️ Arquivar em vez disso
            </button>
          </Alert>
        )}
      </ConfirmModal>

      {/* #R8 — Checklist bloqueante de conversão extrajudicial → judicial */}
      <ConversaoChecklist
        caseId={caso.id}
        open={convModal}
        onClose={() => setConvModal(false)}
        onSuccess={() => {
          setTimeout(() => {
            window.location.assign(`/casos/${caso.id}?tab=processos`);
          }, 700);
        }}
      />
    </div>
  );
}
