import { toast } from "../components/Toast";
import Markdown from "../components/Markdown";
import React, { useEffect, useState } from "react";
import { Link, useParams, useSearchParams, useNavigate } from "react-router";
import {
  Sparkles,
  ChevronDown,
  ChevronLeft,
  RefreshCw,
  ShieldCheck,
  Copy,
  ArchiveRestore,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { areaLabel, useAreas } from "../lib/areas";
import {
  mensagemErroHttp,
  mensagemErroIA,
  ROTULO_IA_NAO_ATIVADA,
} from "../lib/iaErro";
import { useIaStatus } from "../lib/iaStatus";
import ContextualAIAssistant from "../components/ContextualAIAssistant";
import IntakeAnalise from "../components/IntakeAnalise";
import ConversaoChecklist from "../components/ConversaoChecklist";
import ProvasCaso from "../components/ProvasCaso";
import DossieEstrategicoCaso from "../components/DossieEstrategicoCaso";
import OrquestradorPanel from "../components/OrquestradorPanel";
import CaseBreadcrumb from "../components/CaseBreadcrumb";
import { ConsultaProfundaTJMG } from "../components/Infosimples";
import type { Case } from "../types";
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
  Badge,
  Empty,
} from "../components/UI";
import BadgesAlerta from "../components/visual/BadgesAlerta";
import CalculadoraAcordo from "../components/visual/CalculadoraAcordo";
import { useAuth } from "../stores/auth";
import {
  CASE_NAV_SECTIONS,
  LEGACY_CASE_TAB_REDIRECTS,
} from "../config/caseNav";
import { RAMOS } from "./ramos/ramosConfig";
import type { FerramentaConfig } from "./ramos/ramosConfig";
import TabPartes from "./CasoDetalhe/TabPartes";
import TabFerramentas from "./CasoDetalhe/TabFerramentas";
import TabResumo, { AvisoCasoEncerrado } from "./CasoDetalhe/TabResumo";
import TabTeses from "./CasoDetalhe/TabTeses";
import TabIndicadoresJuridicos from "./CasoDetalhe/TabIndicadoresJuridicos";
import IaDefensivaCaso from "./CasoDetalhe/IaDefensivaCaso";
import TabMemoria from "./CasoDetalhe/TabMemoria";
import TabProcessos from "./CasoDetalhe/TabProcessos";
// Tela C (Bloco 3) — abas de trabalho agem em lugar, extraídas em componentes
// próprios (padrão Tab*.tsx): upload embutido, prazo inline, peças e composer.
import TabDocumentos from "./CasoDetalhe/TabDocumentos";
import TabPrazos from "./CasoDetalhe/TabPrazos";
import TabTarefas from "./CasoDetalhe/TabTarefas";
import TabIntimacoes from "./CasoDetalhe/TabIntimacoes";
import TabPecas from "./CasoDetalhe/TabPecas";
import { DataRoomPanel } from "./DataRoom";
import { filtrarTabsW3 } from "../config/w3Tabs";
import TabTimeline from "./CasoDetalhe/TabTimeline";

export const TABS = [
  // Fase 1 (plano de simplificação): a antiga aba "orquestrador" deixou de
  // existir como destino — seu conteúdo foi promovido à Visão (aba resumo).
  // O deep-link ?tab=orquestrador segue resolvendo via LEGACY_CASE_TAB_REDIRECTS.
  { key: "resumo", label: "Resumo" },
  { key: "processos", label: "Processos" },
  { key: "timeline", label: "Timeline" },
  { key: "mensagens", label: "Mensagens" },
  { key: "partes", label: "Partes" },
  { key: "etiquetas", label: "Etiquetas" },
  { key: "checklists", label: "Checklists" },
  { key: "documentos", label: "Documentos" },
  // Onda 3 (§3: Data Room → contexto de Caso/Documento): salas do caso
  // embutidas no workspace — atrás de flag (config/w3Tabs.ts) com rollback
  // por perfil; a página global /data-room segue no menu Administração.
  { key: "dataroom", label: "Data Room" },
  // Tela C (Bloco 3) e Onda 3: a produção de peças tem superfície no caso —
  // a aba reusa o componente canônico `Pecas` (mesmo CRUD, motor e gates);
  // /pecas segue no menu 9 como superfície global/por-cliente (§3, mapa 5).
  { key: "pecas", label: "Peças" },
  { key: "provas", label: "Provas" },
  { key: "contratos", label: "Contratos" },
  { key: "procuracoes", label: "Procurações" },
  { key: "prazos", label: "Prazos" },
  { key: "audiencias", label: "Audiências" },
  // Onda 4 (§10: Agenda/Prazos/Tarefas/Intimações): abas SOMENTE LEITURA do
  // workspace — a escrita continua ÚNICA na Central /atividades (padrão da
  // aba Prazos). Entram atrás de flag (config/w3Tabs.ts) com rollback por
  // perfil; deep-link com flag OFF cai no Resumo via filtrarTabsW3().
  { key: "tarefas", label: "Tarefas" },
  { key: "intimacoes", label: "Intimações" },
  { key: "financeiro", label: "Financeiro" },
  { key: "custos", label: "Centro de Custos" },
  { key: "liquidez", label: "Acordo & Liquidez" },
  // Fase 3 (QA / unificação Estratégia): as sub-abas "teses-sugeridas",
  // "jurisprudencia", "precedentes", "score" e "risco" foram consolidadas em
  // "teses" (com seção "Sugeridas pela IA") e "indicadores". O deep-link antigo
  // continua funcionando via LEGACY_CASE_TAB_REDIRECTS.
  { key: "teses", label: "Teses" },
  { key: "indicadores", label: "Indicadores" },
  { key: "memoria", label: "Memória" },
  // Aba "Jurimetria" por caso removida do menu: era um stub "em implementação".
  // A jurimetria é agregada e vive no menu Jurimetria (/inteligencia).
  { key: "dossie", label: "Dossiê Estratégico" },
  // Fase 3 (QA / unificação Estratégia): "IA Defensiva" foi embutida na aba
  // "⚡ Ferramentas" — mesma natureza de ferramenta de trabalho do caso.
  { key: "ferramentas", label: "⚡ Ferramentas" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

// Fase 1 (plano de simplificação): as ~25 abas do workspace são organizadas
// nas CINCO seções canônicas de config/caseNav.ts — os MESMOS rótulos da
// barra persistente (CaseContextBar) e do dock (CaseCommandDock). Cada aba
// mantém a mesma key e o mesmo conteúdo — só muda o agrupamento; deep-links
// (?tab=...) antigos continuam funcionando porque a seção ativa é derivada da
// aba (GROUPS.find abaixo). O antigo grupo "Histórico e encerramento"
// (memoria) foi absorvido por Atividades.
// `links` são rotas irmãs do caso (páginas próprias) expostas na seção
// pertinente para não parecerem sistemas separados. A rota /casos/:id/jornada
// deixou de ser link porque a jornada agora vive embutida na Visão.
const GROUP_LINKS: Record<
  string,
  { label: string; to: (caseId: string) => string }[]
> = {
  Visão: [
    {
      label: "🎤 Entrevista inteligente",
      to: (id) => `/casos/${id}/entrevista`,
    },
  ],
  Estratégia: [],
};

export const GROUPS: {
  label: string;
  tabs: TabKey[];
  links?: { label: string; to: (caseId: string) => string }[];
}[] = CASE_NAV_SECTIONS.map((secao) => ({
  label: secao.label,
  tabs: secao.tabs.filter((t): t is TabKey => TABS.some((x) => x.key === t)),
  links: GROUP_LINKS[secao.label],
}));

// Pendência retornada pelo DELETE /cases/{id} em 422 (bloqueio condicional R2)
// detail pode vir como string ou como objeto { mensagem, pendencias } — nunca
// renderizar objeto cru no toast.
function RiscoChip({ nivel }: { nivel?: string }) {
  const map: Record<string, string> = {
    baixo: "bg-green-100 text-green-700",
    medio: "bg-yellow-100 text-yellow-700",
    alto: "bg-orange-100 text-orange-700",
    critico: "bg-danger-100 text-danger-700",
  };
  if (!nivel) return null;
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[nivel] ?? "bg-gray-100"}`}
    >
      Risco {nivel}
    </span>
  );
}

// ── Tab: Resumo ──────────────────────────────────────────────────────────────
// ── Tab: Timeline completa — extraída para ./CasoDetalhe/TabTimeline.tsx ─────
// ── Tab: Partes ──────────────────────────────────────────────────────────────
// ── Tab: Checklists (estáticos + por legislação via IA · HITL) ───────────────
function TabChecklists({ caseId }: { caseId: string }) {
  const [cks, setCks] = useState<any[]>([]);
  const [gatilho, setGatilho] = useState("pre_protocolo");
  const [gerando, setGerando] = useState(false);
  const carregar = () =>
    api
      .get(`/checklists/casos/${caseId}`)
      .then((r) => setCks(r.data ?? []))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);

  const gerarIA = async () => {
    setGerando(true);
    try {
      await api.post(`/checklists/caso/${caseId}/gerar-ia`, { gatilho });
      toast.success("Checklist gerado por legislação (rascunho — revise).");
      carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao gerar");
    } finally {
      setGerando(false);
    }
  };

  const marcar = async (ckId: string, itemId: string, concluido: boolean) => {
    try {
      await api.patch(`/checklists/${ckId}/itens/${itemId}/marcar`, {
        concluido,
      });
      carregar();
    } catch {
      /* noop */
    }
  };

  const CAT_COR: Record<string, string> = {
    documentos: "bg-primary-100 text-primary-700",
    diligencias: "bg-warn-100 text-warn-700",
    prazos: "bg-danger-100 text-danger-700",
    audiencia: "bg-ai-100 text-ai-700",
    financeiro: "bg-green-100 text-green-700",
    comunicacao: "bg-cyan-100 text-cyan-700",
    outros: "bg-slate-100 text-slate-600",
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <div>
          <h2 className="font-semibold">Checklists do caso</h2>
          <p className="text-xs text-gray-400">
            Providências por área e legislação pertinente. Rascunho de IA —
            revisão humana obrigatória (OAB); não cria prazos.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={gatilho}
            onChange={(e) => setGatilho(e.target.value)}
            className="input text-sm py-1"
          >
            <option value="pre_processo">Antes de virar processo</option>
            <option value="pre_protocolo">Antes do protocolo</option>
            <option value="geral">Geral</option>
          </select>
          <button
            onClick={gerarIA}
            disabled={gerando}
            className="btn-primary text-sm flex items-center gap-1"
          >
            <Sparkles size={14} />{" "}
            {gerando ? "Gerando…" : "Gerar por legislação (IA)"}
          </button>
        </div>
      </div>

      {cks.length === 0 && (
        <Empty message="Nenhum checklist neste caso. Gere um por legislação acima." />
      )}

      {cks.map((ck) => (
        <div key={ck.id} className="card p-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-medium text-sm">{ck.nome}</h3>
            <span className="text-xs text-gray-400">
              {ck.itens_ok}/{ck.total_itens} · {ck.progresso_pct}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-gray-100 rounded-full mb-3 overflow-hidden">
            <div
              className="h-full bg-green-500"
              style={{ width: `${ck.progresso_pct || 0}%` }}
            />
          </div>
          <ul className="space-y-1.5">
            {(ck.itens || []).map((i: any) => (
              <li key={i.id} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={!!i.concluido}
                  onChange={(e) => marcar(ck.id, i.id, e.target.checked)}
                  className="mt-1"
                />
                <span className="flex-1">
                  <span
                    className={i.concluido ? "line-through text-gray-400" : ""}
                  >
                    {i.texto}
                  </span>
                  {i.obrigatorio && (
                    <span className="text-[10px] text-danger-500 ml-1">*</span>
                  )}
                  <span
                    className={`ml-2 text-[10px] px-1.5 py-0.5 rounded-full ${CAT_COR[i.categoria] || "bg-slate-100 text-slate-600"}`}
                  >
                    {i.categoria}
                  </span>
                  {i.dica && (
                    <span className="block text-xs text-gray-400">
                      {i.dica}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

// ── Tab: Processos (entidade Processo — 1 Caso : N Processos) ─────────────────
// ── Tab: Score Jurídico ──────────────────────────────────────────────────────
// ── Tab: Índice de Risco ─────────────────────────────────────────────────────
// ── Tab: Jurisprudência (RAG) ─────────────────────────────────────────────────
// ── Tab genérico: lista simples ──────────────────────────────────────────────
function TabLista({
  titulo,
  endpoint,
  renderItem,
  empty,
  valorCausa,
}: {
  titulo: string;
  endpoint: string;
  renderItem: (item: any) => React.JSX.Element;
  empty: string;
  /** Valor da causa do caso (opcional) — exibe resumo determinístico. */
  valorCausa?: number | null;
}) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    api
      .get(endpoint)
      .then((r) => setItems(asList(r.data)))
      .catch(() => {});
  }, [endpoint]);
  // Fase 3 (FIX-003 / visibilidade): o valor da causa do caso não aparecia em
  // lugar algum do Financeiro — soma determinística dos lançamentos (sem IA).
  const total = items.reduce((acc, it) => acc + (Number(it.valor) || 0), 0);
  const pago = items
    .filter((it) => it.pago === true || it.status === "pago")
    .reduce((acc, it) => acc + (Number(it.valor) || 0), 0);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 className="font-semibold">
          {titulo} ({items.length})
        </h2>
        <span className="text-xs text-gray-400">
          Total {fmtMoney(total)} · {fmtMoney(pago)} recebido(s) ·{" "}
          {fmtMoney(total - pago)} pendente(s)
        </span>
      </div>
      {valorCausa ? (
        <div className="card p-3 bg-navy-50 border border-navy-100 text-sm">
          <span className="text-slate-500">Valor da causa do caso: </span>
          <strong className="font-medium text-slate-800">
            {fmtMoney(valorCausa)}
          </strong>
        </div>
      ) : null}
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={item.id || i}>{renderItem(item)}</div>
        ))}
        {items.length === 0 && (
          <p className="text-center py-8 text-gray-400 text-sm">{empty}</p>
        )}
      </div>
    </div>
  );
}

// ── Tab: Mensagens (chat cliente↔escritório) ─────────────────────────────────
function TabMensagens({ caseId }: { caseId: string }) {
  const [msgs, setMsgs] = useState<any[]>([]);
  const [txt, setTxt] = useState("");
  const [sending, setSending] = useState(false);
  const carregar = () =>
    api
      .get(`/cases/${caseId}/mensagens`)
      .then((r) => setMsgs(asList(r.data)))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);
  const enviar = async () => {
    if (!txt.trim()) return;
    setSending(true);
    try {
      await api.post(`/cases/${caseId}/mensagens`, { mensagem: txt });
      setTxt("");
      carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao enviar");
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-semibold">Mensagens com o cliente</h2>
        <p className="text-xs text-gray-400">
          Conversa visível ao cliente no Portal — evite expor dados sensíveis
          desnecessários.
        </p>
      </div>
      <div className="card p-4 max-h-[28rem] overflow-auto space-y-2 bg-gray-50">
        {msgs.map((m) => (
          <div
            key={m.id}
            className={`flex ${m.autor_tipo === "escritorio" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${m.autor_tipo === "escritorio" ? "bg-primary-600 text-white" : "bg-slate-900/[0.05] text-slate-800 dark:bg-white/[0.08] dark:text-slate-200"}`}
            >
              <Markdown source={m.mensagem} />
              <p
                className={`text-[10px] mt-1 ${m.autor_tipo === "escritorio" ? "text-primary-100" : "text-gray-400"}`}
              >
                {m.autor_nome ||
                  (m.autor_tipo === "cliente" ? "Cliente" : "Escritório")}{" "}
                · {fmtDate(m.created_at)}
              </p>
            </div>
          </div>
        ))}
        {msgs.length === 0 && <Empty message="Nenhuma mensagem ainda" />}
      </div>
      <div className="flex gap-2">
        <input
          value={txt}
          onChange={(e) => setTxt(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && enviar()}
          placeholder="Escreva uma mensagem ao cliente…"
          className="input flex-1"
        />
        <button
          onClick={enviar}
          disabled={sending || !txt.trim()}
          className="btn-primary"
        >
          Enviar
        </button>
      </div>
    </div>
  );
}

// ── Tab: Etiquetas ───────────────────────────────────────────────────────────
function TabEtiquetas({ caseId }: { caseId: string }) {
  const [todas, setTodas] = useState<any[]>([]);
  const [doCaso, setDoCaso] = useState<any[]>([]);
  const [nome, setNome] = useState("");
  const [cor, setCor] = useState("#CFA961");
  const CORES = [
    "#CFA961",
    "#0A4132",
    "#17985A",
    "#E89A1B",
    "#DF3F49",
    "#14503F",
    "#EACA7F",
    "#8F7117",
  ];

  const carregar = () => {
    api
      .get("/etiquetas")
      .then((r) => setTodas(r.data))
      .catch(() => {});
    api
      .get(`/cases/${caseId}/etiquetas`)
      .then((r) => setDoCaso(asList(r.data)))
      .catch(() => {});
  };
  useEffect(() => {
    carregar();
  }, [caseId]);

  const atribuir = async (id: string) => {
    try {
      await api.post(`/cases/${caseId}/etiquetas`, { etiqueta_id: id });
      carregar();
    } catch (e) {
      toast.error(mensagemErroHttp(e, "Erro ao atribuir etiqueta"));
    }
  };
  const remover = async (id: string) => {
    if (!confirm("Remover esta etiqueta do caso?")) return;
    try {
      await api.delete(`/cases/${caseId}/etiquetas/${id}`);
      setDoCaso((p) => p.filter((x) => x.id !== id));
    } catch (e) {
      toast.error(mensagemErroHttp(e, "Erro ao remover etiqueta"));
    }
  };
  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nome.trim()) return;
    try {
      const { data } = await api.post("/etiquetas", { nome, cor });
      setNome("");
      await api.post(`/cases/${caseId}/etiquetas`, { etiqueta_id: data.id });
      carregar();
    } catch (e) {
      toast.error(mensagemErroHttp(e, "Erro ao criar etiqueta"));
    }
  };
  const disponiveis = todas.filter((t) => !doCaso.some((d) => d.id === t.id));
  const Chip = ({ e, onX }: { e: any; onX?: () => void }) => (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full text-white"
      style={{ background: e.cor || "#CFA961" }}
    >
      {e.nome}
      {onX && (
        <button onClick={onX} className="ml-0.5 opacity-80 hover:opacity-100">
          ×
        </button>
      )}
    </span>
  );

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h2 className="font-semibold mb-2">Etiquetas do caso</h2>
        <div className="flex flex-wrap gap-2">
          {doCaso.map((e) => (
            <Chip key={e.id} e={e} onX={() => remover(e.id)} />
          ))}
          {doCaso.length === 0 && (
            <p className="text-sm text-gray-400">
              Nenhuma etiqueta neste caso.
            </p>
          )}
        </div>
      </div>

      {disponiveis.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-500 mb-2">
            Adicionar existente
          </h3>
          <div className="flex flex-wrap gap-2">
            {disponiveis.map((e) => (
              <button
                key={e.id}
                onClick={() => atribuir(e.id)}
                className="opacity-80 hover:opacity-100"
              >
                <Chip e={e} />
              </button>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={criar} className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Criar nova etiqueta
        </h3>
        <div className="flex gap-2 items-center">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome da etiqueta"
            className="input flex-1"
          />
          <button type="submit" className="btn-primary text-sm">
            Criar + aplicar
          </button>
        </div>
        <div className="flex gap-1.5">
          {CORES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCor(c)}
              className={`w-6 h-6 rounded-full ${cor === c ? "ring-2 ring-offset-1 ring-navy" : ""}`}
              style={{ background: c }}
              aria-label={c}
            />
          ))}
        </div>
      </form>
    </div>
  );
}

// ── Tab: Memória Institucional ───────────────────────────────────────────────
// ── Tab placeholder (módulo ainda não disponível) ────────────────────────────
// ── Componente principal ──────────────────────────────────────────────────────

// ── Mapa área do caso → slugs de ramo ────────────────────────────────────────
// ── Mini Ferramenta (reutiliza lógica do RamoBase, independente) ──────────────
// ── Análise de Contrato com IA ────────────────────────────────────────────────
// -- IA Defensiva / Contestacao ------------------------------------------------
// ── Tab Ferramentas — contextual ao caso ──────────────────────────────────────
// ── Tab: Teses sugeridas (Banco de Teses ranqueado ao caso) ──────────────────
interface TeseSugerida {
  id: string;
  titulo: string;
  tema: string | null;
  ramo: string | null;
  resumo: string;
  score: number;
  distancia: number;
  taxa_sucesso: number | null;
  vezes_venceu: number | null;
  vezes_usada: number | null;
  tribunal: string | null;
}

// Fase 1 — "Dados do caso" numa linha recolhível: o conteúdo clássico do
// Resumo (TabResumo, com todas as ações) permanece integral, mas recolhido
// para que a próxima ação do orquestrador domine a Visão sem clique adicional.
function DadosDoCasoRecolhivel({
  caso,
  abertoInicial = false,
}: {
  caso: Case;
  abertoInicial?: boolean;
}) {
  const [aberto, setAberto] = useState(abertoInicial);
  const numeroProcesso =
    caso.processo_principal?.numero_cnj ?? (caso as any).numero_processo;
  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left"
      >
        <span className="text-sm font-semibold text-slate-700">
          Dados do caso
        </span>
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          {numeroProcesso && <span>Processo {numeroProcesso}</span>}
          {caso.area && <span className="capitalize">Área: {caso.area}</span>}
          {caso.valor_causa != null && (
            <span>Valor: {fmtMoney(caso.valor_causa)}</span>
          )}
          {caso.created_at && <span>Abertura: {fmtDate(caso.created_at)}</span>}
        </span>
        <ChevronDown
          size={16}
          className={`ml-auto shrink-0 text-slate-400 transition-transform ${aberto ? "rotate-180" : ""}`}
        />
      </button>
      {aberto && (
        <div className="border-t border-slate-100 p-4">
          {/* O aviso de encerramento já aparece no topo da Visão. */}
          <TabResumo caso={caso} ocultarAvisoEncerramento />
        </div>
      )}
    </div>
  );
}

export default function CasoDetalhe() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [caso, setCaso] = useState<Case | null>(null);

  // Abas legadas (?tab=orquestrador) são normalizadas de forma síncrona para a
  // aba nova — nenhum deep-link antigo quebra nem mostra tela vazia. Abas
  // desconhecidas (?tab=qualquer-coisa) caem honestamente no Resumo, com a
  // URL normalizada, em vez de exibir uma tela vazia de "em desenvolvimento".
  const rawTab = searchParams.get("tab");
  const tabRedirecionada = rawTab
    ? LEGACY_CASE_TAB_REDIRECTS[rawTab]
    : undefined;
  const tabCandidata = tabRedirecionada ?? rawTab;
  // Aba conhecida = existe no TABS E está visível (flags da Onda 3). Deep-link
  // para aba com flag OFF cai honestamente no Resumo — sem tela vazia.
  const tabConhecida =
    !!tabCandidata &&
    TABS.some((t) => t.key === tabCandidata) &&
    filtrarTabsW3([tabCandidata]).length > 0;
  const activeTab: TabKey = tabConhecida ? (tabCandidata as TabKey) : "resumo";

  useEffect(() => {
    if (rawTab && rawTab !== activeTab) {
      setSearchParams({ tab: activeTab }, { replace: true });
    }
  }, [rawTab, activeTab, setSearchParams]);

  useEffect(() => {
    if (!id) return;
    api
      .get(`/cases/${id}`)
      .then((r) => setCaso(r.data))
      .catch(() => navigate("/casos"));
  }, [id]);

  if (!caso) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner />
      </div>
    );
  }

  const renderTab = () => {
    if (!id) return null;
    switch (activeTab) {
      case "resumo": {
        // Fase 1 — o caso abre com a próxima ação: o painel do orquestrador
        // (próximo passo, ações disponíveis, pendências e jornada embutida)
        // vem primeiro; os dados do caso ficam numa linha recolhível abaixo.
        // Caso encerrado/arquivado: aviso + controle de reabertura em destaque
        // no topo, painel em modo leitura e "Dados do caso" já aberto.
        const casoBloqueado =
          caso.status === "encerrado" || caso.status === "arquivado";
        return (
          <div className="space-y-5">
            {casoBloqueado && <AvisoCasoEncerrado caso={caso} />}
            <OrquestradorPanel caseId={id} casoStatus={caso.status} />
            <DadosDoCasoRecolhivel caso={caso} abertoInicial={casoBloqueado} />
          </div>
        );
      }
      case "processos":
        return <TabProcessos caseId={id} />;
      case "timeline":
        return <TabTimeline caseId={id} />;
      case "mensagens":
        return <TabMensagens caseId={id} />;
      case "partes":
        return <TabPartes caseId={id} />;
      case "etiquetas":
        return <TabEtiquetas caseId={id} />;
      case "checklists":
        return <TabChecklists caseId={id} />;

      case "documentos":
        // Tela C: upload embutido na aba — a ação acontece dentro do caso.
        return <TabDocumentos caseId={id} />;
      case "dataroom":
        // Onda 3: Data Room do caso — mesma superfície canônica (sem segundo
        // CRUD), escopada ao caso; criação já vincula case_id.
        return <DataRoomPanel caseId={id} />;
      case "pecas":
        // Tela C: peças do caso — criação, PDF de minuta e conferir-e-assinar.
        return <TabPecas caseId={id} />;
      case "provas":
        return <ProvasCaso caseId={id} />;
      case "contratos":
        return (
          <TabLista
            titulo="Contratos"
            endpoint={`/contratos?case_id=${id}`}
            empty="Nenhum contrato vinculado"
            renderItem={(c) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">
                  {c.titulo || c.tipo_contrato}
                </span>
                <span className="text-gray-500">{fmtMoney(c.valor_total)}</span>
              </div>
            )}
          />
        );
      case "procuracoes":
        return (
          <TabLista
            titulo="Procurações"
            endpoint={`/procuracoes/?client_id=${(caso as any).client_id ?? ""}`}
            empty="Nenhuma procuração do cliente"
            renderItem={(p) => (
              <div className="card p-3 text-sm flex justify-between items-center">
                <span className="text-gray-800">
                  {p.tipo_poderes || "Procuração"}
                </span>
                {p.data_validade && (
                  <span className="text-gray-400 text-xs">
                    Vence: {fmtDate(p.data_validade)}
                  </span>
                )}
              </div>
            )}
          />
        );
      case "prazos":
        // Tela C: formulário inline de 3 campos — sem navegar para /atividades.
        return <TabPrazos caseId={id} />;
      case "audiencias":
        return (
          <TabLista
            titulo="Audiências"
            endpoint={`/deadlines/?case_id=${id}&tipo=audiencia&status=`}
            empty="Nenhuma audiência cadastrada"
            renderItem={(a) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{a.titulo}</span>
                <span className="text-gray-500 text-xs">
                  {fmtDate(a.data_prazo)}
                </span>
              </div>
            )}
          />
        );
      case "tarefas":
        // Onda 4: tarefas do caso — somente leitura; escrita única na Central.
        return <TabTarefas caseId={id} />;
      case "intimacoes":
        // Onda 4: intimações DJEN do caso — somente leitura; tratamento único
        // na Central (processar, aceitar/recusar prazo).
        return <TabIntimacoes caseId={id} />;
      case "financeiro":
        return (
          <TabLista
            titulo="Honorários e Pagamentos"
            endpoint={`/fees/?case_id=${id}`}
            valorCausa={
              caso.valor_causa ?? caso.processo_principal?.valor_causa ?? null
            }
            empty="Nenhum lançamento financeiro"
            renderItem={(f) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{f.descricao}</span>
                <span
                  className={
                    f.status === "pago"
                      ? "text-green-600 font-medium"
                      : "text-orange-600"
                  }
                >
                  {fmtMoney(f.valor)}
                </span>
              </div>
            )}
          />
        );
      case "custos":
        return (
          <TabLista
            titulo="Centro de Custos"
            endpoint={`/centro-custos?case_id=${id}`}
            valorCausa={
              caso.valor_causa ?? caso.processo_principal?.valor_causa ?? null
            }
            empty="Nenhum lançamento de custo"
            renderItem={(c) => (
              <div className="card p-3 flex justify-between items-center text-sm">
                <span className="text-gray-800">{c.descricao}</span>
                <span
                  className={
                    c.pago ? "text-green-600 font-medium" : "text-orange-600"
                  }
                >
                  {fmtMoney(c.valor)}
                </span>
              </div>
            )}
          />
        );
      case "liquidez":
        return (
          <CalculadoraAcordo
            caseId={id}
            valorCausaInicial={
              caso.valor_causa ?? caso.processo_principal?.valor_causa ?? null
            }
            tribunalInicial={
              caso.tribunal ?? caso.processo_principal?.tribunal ?? null
            }
          />
        );
      case "teses":
        return <TabTeses caso={caso} />;
      case "indicadores":
        return <TabIndicadoresJuridicos caseId={id} caso={caso} />;
      case "memoria":
        return <TabMemoria caseId={id} />;
      case "dossie":
        return <DossieEstrategicoCaso caseId={id} />;

      case "ferramentas":
        return <TabFerramentas caso={caso} />;
      default:
        // Inalcançável: activeTab é normalizado para "resumo" quando a aba
        // não existe (ver derivação acima). Mantido apenas como guarda.
        return null;
    }
  };

  const grupoAtivo =
    GROUPS.find((g) => g.tabs.includes(activeTab)) ?? GROUPS[0];
  const activeTabLabel =
    TABS.find((t) => t.key === activeTab)?.label ?? "Resumo";
  const numeroProcesso =
    (caso as any).processo_principal?.numero_cnj ||
    (caso as any).numero_processo;

  return (
    <div className="space-y-5">
      <CaseBreadcrumb
        caseId={caso.id}
        titulo={caso.titulo}
        tela={activeTabLabel}
      />
      {/* Sticky header + tabs */}
      <div className="sticky top-[4.25rem] z-20 card bg-white">
        <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
          <button
            onClick={() => navigate("/casos")}
            className="icon-btn mt-1 h-9 w-9 shrink-0"
          >
            <ChevronLeft size={18} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {caso.numero_interno && (
                <span className="text-xs font-semibold uppercase tracking-wide text-primary-700">
                  {caso.numero_interno}
                </span>
              )}
              <StatusBadge value={caso.status} />
              <RiscoChip nivel={(caso as any).risco_nivel ?? caso.risco} />
            </div>
            <h1 className="mt-2 truncate text-xl font-semibold text-slate-950 md:text-2xl">
              {caso.titulo}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
              <span className="capitalize">
                Area:{" "}
                <strong className="font-medium text-slate-700">
                  {caso.area || "nao informada"}
                </strong>
              </span>
              {numeroProcesso && (
                <span>
                  Processo:{" "}
                  <strong className="font-medium text-slate-700">
                    {numeroProcesso}
                  </strong>
                </span>
              )}
              {caso.valor_causa != null && (
                <span>
                  Valor:{" "}
                  <strong className="font-medium text-slate-700">
                    {fmtMoney(caso.valor_causa)}
                  </strong>
                </span>
              )}
              {caso.created_at && (
                <span>
                  Abertura:{" "}
                  <strong className="font-medium text-slate-700">
                    {fmtDate(caso.created_at)}
                  </strong>
                </span>
              )}
            </div>
            {/* Visual Law — badges de alerta do caso (falha silenciosa) */}
            <BadgesAlerta caseId={caso.id} className="mt-2" />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:shrink-0">
            {/* Fase 3 (QA): "IA do caso" leva à aba Teses — o assistente
                contextual (ContextualAIAssistant) segue disponível em todas
                as abas do caso, inclusive nesta. */}
            <button
              onClick={() => setSearchParams({ tab: "teses" })}
              className="btn-secondary h-9 text-xs"
            >
              <Sparkles size={14} /> IA do caso
            </button>
            <button
              onClick={() => setSearchParams({ tab: "processos" })}
              className="btn-secondary h-9 text-xs"
            >
              Processos
            </button>
          </div>
        </div>
        {/* Tab bar — grupos */}
        <div className="border-t border-slate-100 px-3 py-2">
          <div className="flex gap-1 overflow-x-auto scrollbar-thin">
            {GROUPS.map((g) => {
              const ativo = g.tabs.includes(activeTab);
              return (
                <button
                  key={g.label}
                  onClick={() => setSearchParams({ tab: g.tabs[0] })}
                  className={`h-9 flex-shrink-0 rounded-lg px-3 text-sm font-medium transition-all ${
                    ativo
                      ? "bg-primary-600 text-white shadow-sm shadow-primary-600/20"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                  }`}
                >
                  {g.label}
                </button>
              );
            })}
          </div>
        </div>
        {/* Sub-abas do grupo ativo */}
        {(() => {
          const grp = grupoAtivo;
          if (grp.tabs.length <= 1 && !grp.links?.length) return null;
          return (
            <div className="flex gap-2 overflow-x-auto border-t border-slate-100 bg-slate-50/70 px-3 py-2 scrollbar-thin">
              <span className="hidden text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400 sm:inline-flex sm:items-center">
                {grp.label}
              </span>
              {grp.tabs.length > 1 &&
                filtrarTabsW3(grp.tabs).map((k) => {
                  const t = TABS.find((x) => x.key === k)!;
                  return (
                    <button
                      key={k}
                      onClick={() => setSearchParams({ tab: k })}
                      className={`h-8 flex-shrink-0 rounded-full px-3 text-xs font-medium transition-colors ${
                        activeTab === k
                          ? "bg-slate-950 text-white"
                          : "text-slate-600 hover:bg-white hover:text-slate-950"
                      }`}
                    >
                      {t.label}
                    </button>
                  );
                })}
              {/* Rotas irmãs do caso vinculadas a esta seção (Sala de Guerra,
                  Jornada, Entrevista) — páginas próprias, não abas. */}
              {grp.links?.map((l) => (
                <Link
                  key={l.label}
                  to={l.to(caso.id)}
                  className="flex h-8 flex-shrink-0 items-center rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-primary-700 transition-colors hover:border-primary-300 hover:bg-primary-50"
                >
                  {l.label}
                </Link>
              ))}
            </div>
          );
        })()}
      </div>

      <div className="flex items-center justify-between">
        <div>
          <div className="eyebrow">Caso</div>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">
            {activeTabLabel}
          </h2>
        </div>
      </div>

      <ContextualAIAssistant caso={caso} surface={activeTab} />

      <div>{renderTab()}</div>
    </div>
  );
}
