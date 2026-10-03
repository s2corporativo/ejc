// ── OrquestradorPanel — Orquestrador Jurídico do Caso (§16) ──────────────────
// Consome GET /cases/{id}/orquestrador (estado derivado dos artefatos reais,
// próximo passo e pendências derivadas dos artefatos reais) e executa
// transições via POST /cases/{id}/orquestrador/avancar. A jornada detalhada
// permanece no contrato por compatibilidade, mas não é navegação primária.
//
// Regras espelhadas do backend (legal_case_orchestrator.py):
//   • Atos jurídicos (aprovações, confirmação de termo) NUNCA são executados
//     por aqui — o botão aponta para o fluxo próprio de aprovação humana.
//   • Ações executáveis passam por ConfirmModal mostrando o que será chamado.
//   • Tudo que a IA produz é RASCUNHO sujeito à revisão do advogado.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { toast } from "./Toast";
import {
  avancarOrquestrador,
  visaoOrquestrador,
  type OrquestradorAcao,
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
  IANotice,
  SectionCard,
  Spinner,
} from "./UI";
import { useAuth } from "../stores/auth";

// Mesmo limiar do backend (routers/orquestrador.py::_pode_avancar — advogado+).
// Abaixo disso o painel fica em MODO LEITURA: próxima ação e pendências ficam
// visíveis, mas a execução é desabilitada (o /avancar devolveria 403).
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
      return {
        to: `/casos/${caseId}?tab=resumo`,
        label: "Revisar inteligência do caso",
      };
    case "aprovar_tese":
    case "aprovar_estrategia":
      return {
        to: `/casos/${caseId}?tab=teses`,
        label: "Abrir matriz de teses",
      };
    case "aprovar_proposta":
    case "criar_proposta":
      return {
        to: `/casos/${caseId}?tab=financeiro`,
        label: "Abrir honorários do caso",
      };
    case "gerar_peca":
      return {
        to: `/casos/${caseId}?tab=pecas&acao=produzir`,
        label: "Produzir peça neste caso",
      };
    case "aprovar_peca":
    case "confirmar_termo_inicial":
    case "registrar_protocolo":
      return {
        to: `/casos/${caseId}?tab=pecas`,
        label: "Abrir produção jurídica do caso",
      };
    default:
      return null;
  }
}

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
        A inteligência prepara análises e rascunhos; decisões jurídicas,
        aprovações e prazos continuam sujeitos à revisão humana.
      </IANotice>

      <SectionCard
        title="Próxima ação"
        subtitle={
          casoBloqueado
            ? "Caso em modo leitura"
            : "O que precisa ser feito agora para este caso avançar"
        }
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
        <div className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Recomendação operacional
            </p>
            <p className="mt-1 text-base font-medium text-slate-900">
              {prox.passo_recomendado}
            </p>
          </div>

          {pendencias.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Para avançar
              </p>
              <div className="space-y-2">
                {pendencias.map((p, i) => (
                  <PendenciaItem key={`${p.tipo}-${i}`} p={p} />
                ))}
              </div>
            </div>
          )}

          {pendencias.length === 0 && !casoBloqueado && (
            <Alert variant="success">
              Nenhuma pendência bloqueante identificada neste momento.
            </Alert>
          )}

          {ultimaTransicao && (
            <Alert variant="success">{ultimaTransicao}</Alert>
          )}
        </div>
      </SectionCard>

      {erroAcao && (
        <Alert variant="danger" title={erroAcao.titulo}>
          {erroAcao.detalhes.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs">
              {erroAcao.detalhes.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          )}
        </Alert>
      )}

      <details className="rounded-xl border border-slate-200 bg-white">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800">
          Ver detalhes
          <span className="ml-2 text-xs font-normal text-slate-400">
            jornada completa e ações disponíveis
          </span>
        </summary>
        <div className="space-y-5 border-t border-slate-100 p-4">
          {acoes.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Ações disponíveis
              </h3>
              <div className="space-y-2">
                {acoes.map((a) => {
                  const rota = rotaFluxoHumano(a.acao, caseId);
                  const executaDireto =
                    a.executavel_via_orquestrador &&
                    ACOES_EXECUCAO_DIRETA.has(a.acao);
                  return (
                    <div
                      key={a.acao}
                      className="flex flex-col gap-2 rounded-xl border border-slate-100 p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800">
                          {ROTULO_ACAO[a.acao] ?? a.acao}
                        </p>
                        {!executaDireto && (
                          <p className="mt-1 flex items-start gap-1 text-xs text-warn-700">
                            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                            Exige decisão ou aprovação humana.
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
                          rota && (
                            <Link
                              to={rota.to}
                              className="text-xs font-medium text-primary-700 underline underline-offset-2"
                            >
                              {rota.label}
                            </Link>
                          )
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Jornada completa
            </h3>
            <ol className="space-y-2">
              {(visao.jornada ?? []).map((etapa) => (
                <li
                  key={etapa.etapa}
                  className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 px-3 py-2"
                >
                  <span className="text-sm text-slate-700">{etapa.rotulo}</span>
                  <Badge
                    tone={
                      etapa.status === "concluida"
                        ? "green"
                        : etapa.status === "bloqueada"
                          ? "amber"
                          : etapa.status === "em_andamento"
                            ? "blue"
                            : "slate"
                    }
                  >
                    {etapa.status === "concluida"
                      ? "Concluída"
                      : etapa.status === "bloqueada"
                        ? "Bloqueada"
                        : etapa.status === "em_andamento"
                          ? "Em andamento"
                          : "Pendente"}
                  </Badge>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </details>

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
