// ── OrquestradorPanel — Orquestrador Jurídico do Caso (§16) ──────────────────
// Consome GET /cases/{id}/orquestrador (estado derivado dos artefatos reais,
// próximo passo, pendências, jornada de 16 etapas e linha do tempo) e executa
// transições via POST /cases/{id}/orquestrador/avancar.
//
// Regras espelhadas do backend (legal_case_orchestrator.py):
//   • Atos jurídicos (aprovações, confirmação de termo) NUNCA são executados
//     por aqui — o botão aponta para o fluxo próprio de aprovação humana.
//   • Ações executáveis passam por ConfirmModal mostrando o que será chamado.
//   • Tudo que a IA produz é RASCUNHO sujeito à revisão do advogado.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { toast } from "./Toast";
import {
  avancarOrquestrador,
  visaoOrquestrador,
  type OrquestradorAcao,
  type OrquestradorEtapaStatus,
  type OrquestradorPendencia,
  type OrquestradorVisao,
} from "../lib/api";
import {
  Alert,
  Badge,
  Button,
  cn,
  ConfirmModal,
  Empty,
  ErrorState,
  fmtDate,
  IANotice,
  SectionCard,
  Spinner,
} from "./UI";
import { useAuth } from "../stores/auth";

// Mesmo limiar do backend (routers/orquestrador.py::_pode_avancar — advogado+).
// Abaixo disso o painel fica em MODO LEITURA: próximo passo e jornada visíveis,
// execução desabilitada (o /avancar devolveria 403 de qualquer forma).
const ROLES_EXECUCAO = ["superadmin", "admin", "socio", "advogado"];

// Rótulos pt-BR das ações da whitelist do backend (ACOES_VALIDAS).
const ROTULO_ACAO: Record<string, string> = {
  analisar_caso: "Analisar o caso (intake)",
  analisar_peca: "Analisar peças e prazos (Motor de Peça)",
  montar_matriz: "Montar matriz de teses",
  sugerir_proposta: "Sugerir proposta de honorários",
  criar_proposta: "Criar proposta de honorários",
  gerar_kit: "Gerar kit documental (procuração + contrato)",
  gerar_peca: "Gerar peça (Motor de Peça)",
  aprovar_snapshot: "Aprovar snapshot de inteligência",
  aprovar_tese: "Aprovar tese da matriz",
  aprovar_estrategia: "Aprovar estratégia",
  aprovar_proposta: "Aprovar proposta de honorários",
  aprovar_peca: "Aprovar peça",
  confirmar_termo_inicial: "Confirmar termo inicial do prazo",
  registrar_protocolo: "Registrar protocolo da peça",
};

// Ações que o painel executa DIRETO via /avancar com params vazios (todos os
// campos são opcionais no fluxo original). "gerar_peca" e "criar_proposta"
// ficam de fora de propósito: exigem dados definidos pelo advogado
// (termo_inicial_confirmado / faixas) e por isso abrem o fluxo próprio.
const ACOES_EXECUCAO_DIRETA = new Set([
  "analisar_caso",
  "analisar_peca",
  "montar_matriz",
  "sugerir_proposta",
  "gerar_kit",
]);

/** Rota existente do fluxo humano correspondente à ação (quando houver). */
function rotaFluxoHumano(
  acao: string,
  caseId: string,
): { to: string; label: string } | null {
  switch (acao) {
    case "aprovar_snapshot":
      return { to: `/casos/${caseId}/jornada`, label: "Abrir jornada do caso" };
    case "aprovar_tese":
    case "aprovar_estrategia":
      return {
        to: `/casos/${caseId}?tab=teses-sugeridas`,
        label: "Abrir matriz de teses",
      };
    case "aprovar_proposta":
    case "criar_proposta":
      return {
        to: `/casos/${caseId}?tab=financeiro`,
        label: "Abrir honorários do caso",
      };
    case "aprovar_peca":
    case "confirmar_termo_inicial":
    case "registrar_protocolo":
    case "gerar_peca":
      return { to: "/pecas", label: "Abrir módulo de Peças" };
    default:
      return null;
  }
}

const ESTILO_ETAPA: Record<
  OrquestradorEtapaStatus,
  { icone: ReactNode; texto: string; rotulo: string }
> = {
  concluida: {
    icone: <CheckCircle2 className="h-5 w-5 text-success-600" />,
    texto: "text-slate-700",
    rotulo: "Concluída",
  },
  em_andamento: {
    icone: <Loader2 className="h-5 w-5 animate-spin text-primary-600" />,
    texto: "text-slate-900 font-medium",
    rotulo: "Em andamento",
  },
  bloqueada: {
    icone: <ShieldCheck className="h-5 w-5 text-warn-600" />,
    texto: "text-slate-900 font-medium",
    rotulo: "Aguarda o advogado",
  },
  pendente: {
    icone: <Clock className="h-5 w-5 text-slate-300" />,
    texto: "text-slate-400",
    rotulo: "Pendente",
  },
};

const TONE_ETAPA: Record<
  OrquestradorEtapaStatus,
  "green" | "blue" | "amber" | "slate"
> = {
  concluida: "green",
  em_andamento: "blue",
  bloqueada: "amber",
  pendente: "slate",
};

// Extrai mensagem + detalhes estruturados dos erros 422/429/403 do /avancar.
function extrairErroAvancar(e: unknown): {
  titulo: string;
  detalhes: string[];
} {
  const resp = (
    e as { response?: { status?: number; data?: { detail?: unknown } } }
  )?.response;
  const detail = resp?.data?.detail;
  if (resp?.status === 429) {
    return {
      titulo:
        typeof detail === "string"
          ? detail
          : "Limite de execuções atingido — aguarde um instante e tente de novo.",
      detalhes: [],
    };
  }
  if (typeof detail === "string") return { titulo: detail, detalhes: [] };
  if (detail && typeof detail === "object") {
    const d = detail as {
      mensagem?: string;
      erros?: Array<{ campo?: string; erro?: string }>;
      acoes_validas?: string[];
    };
    const detalhes: string[] = [];
    for (const err of d.erros ?? []) {
      detalhes.push([err.campo, err.erro].filter(Boolean).join(": "));
    }
    if (d.acoes_validas?.length) {
      detalhes.push(`Ações válidas: ${d.acoes_validas.join(", ")}`);
    }
    return {
      titulo: d.mensagem ?? "Não foi possível executar a ação.",
      detalhes,
    };
  }
  return { titulo: "Não foi possível executar a ação.", detalhes: [] };
}

function PendenciaItem({ p }: { p: OrquestradorPendencia }) {
  const itens = (p.itens ?? [])
    .map((i) => String(i.descricao ?? i.titulo ?? i.item ?? ""))
    .filter(Boolean);
  return (
    <Alert
      variant="warning"
      title={
        p.tipo === "aprovacao_humana" ? "Aprovação do advogado" : undefined
      }
    >
      <p>{p.detalhe}</p>
      {itens.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs">
          {itens.map((i, idx) => (
            <li key={idx}>{i}</li>
          ))}
        </ul>
      )}
    </Alert>
  );
}

export default function OrquestradorPanel({
  caseId,
  casoStatus,
}: {
  caseId: string;
  /** Status do caso — encerrado/arquivado bloqueia a execução de ações
   *  (espelha a guarda 409 do backend em /orquestrador/avancar). */
  casoStatus?: string;
}) {
  const { user } = useAuth();
  const [visao, setVisao] = useState<OrquestradorVisao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState(false);
  const [confirmando, setConfirmando] = useState<OrquestradorAcao | null>(null);
  const [executando, setExecutando] = useState(false);
  const [erroAcao, setErroAcao] = useState<{
    titulo: string;
    detalhes: string[];
  } | null>(null);
  const [ultimaTransicao, setUltimaTransicao] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErroCarga(false);
    try {
      setVisao(await visaoOrquestrador(caseId));
    } catch {
      setErroCarga(true);
    } finally {
      setCarregando(false);
    }
  }, [caseId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function executar(acao: OrquestradorAcao) {
    setExecutando(true);
    setErroAcao(null);
    try {
      const r = await avancarOrquestrador(caseId, acao.acao, {});
      setConfirmando(null);
      if (r.requer_aprovacao_humana) {
        // Defensivo: o painel não envia atos jurídicos, mas se o backend
        // recusar, mostra a instrução do endpoint humano sem executar nada.
        toast.info(r.instrucao ?? "Esta ação exige aprovação do advogado.");
      } else {
        const de = r.estado_anterior ?? "?";
        const para = r.estado ?? de;
        setUltimaTransicao(
          `Ação "${ROTULO_ACAO[r.acao] ?? r.acao}" executada (${de} → ${para}). ` +
            "O resultado é rascunho e depende da revisão do advogado.",
        );
        toast.success("Ação executada pelo orquestrador.");
      }
      await carregar();
    } catch (e) {
      const info = extrairErroAvancar(e);
      setErroAcao(info);
      toast.error(info.titulo);
    } finally {
      setExecutando(false);
    }
  }

  if (carregando && !visao) {
    return (
      <div className="flex justify-center">
        <Spinner />
      </div>
    );
  }
  if (erroCarga && !visao) {
    return (
      <ErrorState
        title="Orquestrador indisponível"
        message="Não foi possível carregar a visão do orquestrador deste caso."
        onRetry={() => void carregar()}
      />
    );
  }
  if (!visao) {
    return (
      <Empty
        titulo="Sem dados do orquestrador"
        descricao="Este caso ainda não possui informações da jornada orquestrada."
      />
    );
  }

  const prox = visao.proximo_passo;
  const pendencias = prox.pendencias_bloqueantes ?? [];
  const acoes = prox.acoes_disponiveis ?? [];
  const posicao = Math.max(0, visao.estados.indexOf(visao.estado)) + 1;

  // Modo leitura (review PR #483): informação sempre visível, execução não.
  const casoBloqueado =
    casoStatus === "encerrado" || casoStatus === "arquivado";
  const podeExecutar = ROLES_EXECUCAO.includes(user?.role || "");
  const motivoBloqueio = casoBloqueado
    ? "Reabra o caso para executar ações"
    : !podeExecutar
      ? "Ação disponível para advogados"
      : null;

  return (
    <div className="space-y-4">
      <IANotice>
        O orquestrador apenas conduz os fluxos oficiais do EJC. Todo conteúdo
        gerado é rascunho sujeito à revisão obrigatória do advogado — nenhuma
        aprovação jurídica acontece automaticamente.
      </IANotice>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          {/* Estado atual + próximo passo */}
          <SectionCard
            title="Estado atual do caso"
            subtitle={`Fase ${posicao} de ${visao.estados.length} da máquina de estados`}
            actions={
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void carregar()}
                disabled={carregando}
                icon={
                  <RefreshCw
                    className={cn("h-4 w-4", carregando && "animate-spin")}
                  />
                }
              >
                Atualizar
              </Button>
            }
          >
            <div className="space-y-3">
              <Badge tone="ouro" className="text-xs">
                {visao.estado_rotulo}
              </Badge>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Próximo passo recomendado
                </p>
                <p className="mt-1 text-sm text-slate-700">
                  {prox.passo_recomendado}
                </p>
              </div>
              {ultimaTransicao && (
                <Alert variant="success">{ultimaTransicao}</Alert>
              )}
            </div>
          </SectionCard>

          {/* Pendências bloqueantes */}
          <SectionCard
            title="Pendências bloqueantes"
            subtitle="O que impede o caso de avançar agora"
          >
            {pendencias.length === 0 ? (
              <p className="text-sm text-slate-500">
                Nenhuma pendência bloqueante neste estado.
              </p>
            ) : (
              <div className="space-y-2">
                {pendencias.map((p, i) => (
                  <PendenciaItem key={`${p.tipo}-${i}`} p={p} />
                ))}
              </div>
            )}
          </SectionCard>

          {/* Ações disponíveis */}
          <SectionCard
            title="Ações disponíveis"
            subtitle="Execução via orquestrador ou fluxo próprio de aprovação"
          >
            {erroAcao && (
              <Alert variant="danger" title={erroAcao.titulo} className="mb-3">
                {erroAcao.detalhes.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-xs">
                    {erroAcao.detalhes.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                )}
              </Alert>
            )}
            {acoes.length === 0 ? (
              <p className="text-sm text-slate-500">
                Nenhuma ação disponível neste estado.
              </p>
            ) : (
              <ul className="space-y-3">
                {acoes.map((a) => {
                  const rota = rotaFluxoHumano(a.acao, caseId);
                  const executaDireto =
                    a.executavel_via_orquestrador &&
                    ACOES_EXECUCAO_DIRETA.has(a.acao);
                  return (
                    <li
                      key={a.acao}
                      className="flex flex-col gap-2 rounded-xl border border-slate-100 p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800">
                          {ROTULO_ACAO[a.acao] ?? a.acao}
                        </p>
                        <p className="truncate text-xs text-slate-400">
                          {a.metodo} {a.endpoint}
                        </p>
                        {!executaDireto && (
                          <p className="mt-1 flex items-start gap-1 text-xs text-warn-700">
                            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                            Aprovação do advogado — abre o fluxo próprio.
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {executaDireto ? (
                          <Button
                            size="sm"
                            variant="ai"
                            onClick={() => setConfirmando(a)}
                            disabled={executando || motivoBloqueio !== null}
                            title={motivoBloqueio ?? undefined}
                          >
                            Executar
                          </Button>
                        ) : (
                          <>
                            <Button size="sm" variant="secondary" disabled>
                              Execução direta indisponível
                            </Button>
                            {rota && (
                              <Link
                                to={rota.to}
                                className="text-xs font-medium text-ouro-profundo underline underline-offset-2"
                              >
                                {rota.label}
                              </Link>
                            )}
                          </>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </SectionCard>
        </div>

        {/* Jornada visual das 16 etapas */}
        <SectionCard
          title="Jornada do caso"
          subtitle="Etapas derivadas dos artefatos reais — nada é marcado à mão"
        >
          <ol className="space-y-0">
            {visao.jornada.map((etapa, i) => {
              const estilo =
                ESTILO_ETAPA[etapa.status] ?? ESTILO_ETAPA.pendente;
              const ultima = i === visao.jornada.length - 1;
              return (
                <li key={etapa.etapa} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    {estilo.icone}
                    {!ultima && (
                      <span
                        aria-hidden="true"
                        className={cn(
                          "w-px flex-1 min-h-4",
                          etapa.status === "concluida"
                            ? "bg-success-200"
                            : "bg-slate-200",
                        )}
                      />
                    )}
                  </div>
                  <div className="flex min-w-0 flex-1 items-start justify-between gap-2 pb-4">
                    <span className={cn("text-sm", estilo.texto)}>
                      {etapa.rotulo}
                    </span>
                    <Badge tone={TONE_ETAPA[etapa.status] ?? "slate"}>
                      {estilo.rotulo}
                    </Badge>
                  </div>
                </li>
              );
            })}
          </ol>
        </SectionCard>
      </div>

      {/* Linha do tempo de transições */}
      <SectionCard
        title="Linha do tempo"
        subtitle="Histórico de análises e transições registradas no caso"
      >
        {visao.linha_do_tempo.length === 0 ? (
          <p className="text-sm text-slate-500">
            Nenhum evento registrado ainda.
          </p>
        ) : (
          <ul className="space-y-2">
            {[...visao.linha_do_tempo].reverse().map((ev) => (
              <li
                key={ev.versao}
                className="flex flex-col gap-1 rounded-xl border border-slate-100 p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-slate-700">
                    {ev.resumo || `Snapshot v${ev.versao}`}
                  </p>
                  <p className="text-xs text-slate-400">
                    v{ev.versao} · origem: {ev.origem}
                    {ev.congelado ? " · congelado" : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {ev.estado && <Badge tone="slate">{ev.estado}</Badge>}
                  {ev.criado_em && (
                    <span className="text-xs text-slate-400">
                      {fmtDate(ev.criado_em)}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {/* Confirmação de execução */}
      <ConfirmModal
        open={confirmando !== null}
        onClose={() => setConfirmando(null)}
        onConfirm={() => confirmando && void executar(confirmando)}
        variant="primary"
        loading={executando}
        title="Executar ação do orquestrador"
        confirmLabel="Executar agora"
        message={
          confirmando
            ? `Será executada a ação "${
                ROTULO_ACAO[confirmando.acao] ?? confirmando.acao
              }" pelo fluxo oficial ${confirmando.metodo} ${confirmando.endpoint}.`
            : undefined
        }
      >
        {confirmando && (
          <div className="mt-3 space-y-2 text-xs text-slate-500">
            {Object.keys(confirmando.payload_esperado ?? {}).length > 0 && (
              <div>
                <p className="font-medium text-slate-600">Campos do fluxo:</p>
                <ul className="mt-1 list-disc pl-5">
                  {Object.entries(confirmando.payload_esperado).map(
                    ([campo, desc]) => (
                      <li key={campo}>
                        <span className="font-mono">{campo}</span>:{" "}
                        {String(desc)}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}
            <p>
              O resultado será um rascunho sujeito à revisão do advogado — o
              orquestrador não aprova nada sozinho.
            </p>
          </div>
        )}
      </ConfirmModal>
    </div>
  );
}
