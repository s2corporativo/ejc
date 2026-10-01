import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import {
  AlertTriangle,
  BookOpen,
  Briefcase,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderKanban,
  Gavel,
  Library,
  Lightbulb,
  ListTodo,
  Paperclip,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "../components/Toast";
import { officeBranding } from "../config/officeBranding";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import { getUltimoCasoId } from "../stores/caseContext";
import { EntradaInteligente } from "./EntradaUnica";
import { IdentidadeAssistente } from "./EntradaUnica/IdentidadeAssistente";

/**
 * Início canônico do EJC — cockpit jurídico.
 *
 * Prioriza entrada, decisões acionáveis, casos e o fluxo de trabalho. Agenda
 * mensal e próximos compromissos vivem somente na sidebar; detalhes históricos
 * e módulos avançados ficam um nível abaixo para reduzir redundância visual.
 */

type Atividade = {
  id?: string;
  tipo?: string;
  titulo?: string;
  date?: string | null;
  status?: string;
  case_id?: string | null;
  caso_titulo?: string | null;
  urgencia?: string;
  dias_restantes?: number | null;
};

type CasoResumo = {
  id?: string;
  titulo?: string;
  status?: string;
  area?: string;
  prioridade?: string;
  risco?: string | null;
  proxima_acao?: string | null;
  proxima_acao_prazo?: string | null;
  numero_processo?: string | null;
  numero_interno?: string | null;
  created_at?: string | null;
};

type Tarefa = {
  id: string;
  titulo?: string;
  status?: string;
  prioridade?: string;
  data_limite?: string | null;
  concluida_em?: string | null;
};

type Kpis = {
  casos?: { ativos?: number };
  clientes_ativos?: number;
};

type IntegridadeResumo = {
  total_casos_pendentes?: number;
  contagens?: Record<string, number | null>;
};

type LegalDocResumo = {
  id: string;
  titulo?: string;
  status?: string;
  case_id?: string | null;
  tipo_peca?: string;
  human_reviewed?: boolean;
};

type DecisaoHoje = {
  id: string;
  prioridade: number;
  titulo: string;
  detalhe: string;
  acao: string;
  to: string;
  tom: "danger" | "warning" | "info" | "success";
};

type HojeBackend = {
  data_operacional?: string;
  contadores?: {
    casos_ativos?: number;
    casos_total?: number;
    prazos_vencidos?: number;
    prazos_hoje?: number;
    prazos_proximos_3d?: number;
    tarefas_hoje_minhas?: number;
    pecas_aguardando_revisao?: number;
    documentos_7d?: number;
  };
  decisoes?: Array<{
    id: string;
    prioridade?: number;
    titulo: string;
    detalhe: string;
    acao: string;
    to: string;
    tom: "danger" | "warning" | "info" | "success";
  }>;
  degradado?: string[];
};

const PAPEIS_INTEGRIDADE = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
]);

// Tarefa 4 (plano de performance, baseline §10): decisões e badges do Hoje
// vêm do backend (GET /dashboard/hoje) sobre a carteira INTEIRA — não mais
// de amostras do navegador (casos p1=20, peças=30). ROLLBACK SEGUNDA ONDA:
// mudar para `false` restaura o cálculo client-side sem deploy do backend.
const USAR_DASHBOARD_HOJE = true;

function chipDeCaso(status?: string): { rotulo: string; classe: string } {
  if (status === "encerrado") return { rotulo: "Concluso", classe: "is-gold" };
  if (status === "arquivado") return { rotulo: "Arquivado", classe: "is-gray" };
  return { rotulo: "Em andamento", classe: "is-green" };
}

function saudacaoPorHora(): string {
  const hora = new Date().getHours();
  if (hora < 12) return "Bom dia";
  if (hora < 18) return "Boa tarde";
  return "Boa noite";
}

function scoreCaso(caso: CasoResumo, atividades: Atividade[] | null): number {
  let score = 0;
  const status = (caso.status ?? "").toLowerCase();
  const prioridade = (caso.prioridade ?? "").toLowerCase();
  const risco = (caso.risco ?? "").toLowerCase();

  if (status === "encerrado" || status === "arquivado") score -= 100;
  else score += 40;

  if (prioridade === "urgente") score += 30;
  else if (prioridade === "alta") score += 20;

  if (risco === "critico" || risco === "crítico") score += 35;
  else if (risco === "alto") score += 25;

  if (caso.proxima_acao_prazo) {
    const prazo = Date.parse(caso.proxima_acao_prazo);
    if (!Number.isNaN(prazo)) {
      const dias = Math.ceil((prazo - Date.now()) / 86_400_000);
      if (dias < 0) score += 100;
      else if (dias === 0) score += 90;
      else if (dias <= 3) score += 70;
      else if (dias <= 7) score += 45;
      else if (dias <= 30) score += 15;
    }
  }

  for (const atividade of atividades ?? []) {
    if (!caso.id || atividade.case_id !== caso.id) continue;
    const dias = atividade.dias_restantes;
    if (atividade.urgencia === "vencido") score += 120;
    else if (atividade.urgencia === "critico") score += 95;
    else if (atividade.urgencia === "atencao") score += 55;
    if (dias !== null && dias !== undefined) {
      if (dias < 0) score += 120;
      else if (dias === 0) score += 85;
      else if (dias <= 3) score += 60;
      else if (dias <= 7) score += 35;
    }
  }

  return score;
}

function scoreTarefaHoje(tarefa: Tarefa, hoje: string): number {
  let score = 0;
  const prioridade = (tarefa.prioridade ?? "").toLowerCase();
  if (prioridade === "urgente") score += 50;
  else if (prioridade === "alta") score += 30;

  const limite = tarefa.data_limite?.slice(0, 10);
  if (!limite) score += 10;
  else if (limite < hoje) score += 80;
  else if (limite === hoje) score += 60;

  if (tarefa.status === "concluida") score -= 5;
  return score;
}

export default function DashboardUltra() {
  const user = useAuth((state) => state.user);
  const navigate = useNavigate();
  const canUseIntegridade = PAPEIS_INTEGRIDADE.has(user?.role || "");

  const [carregado, setCarregado] = useState(false);
  const [ultimoCaso, setUltimoCaso] = useState<CasoResumo | null>(null);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [integridade, setIntegridade] = useState<IntegridadeResumo | null>(
    null,
  );
  const [atividades, setAtividades] = useState<Atividade[] | null>(null);
  const [casos, setCasos] = useState<CasoResumo[] | null>(null);
  const [documentosRecentes, setDocumentosRecentes] = useState<number | null>(
    null,
  );
  const [tarefas, setTarefas] = useState<Tarefa[] | null>(null);
  const [pecasRecentes, setPecasRecentes] = useState<LegalDocResumo[] | null>(
    null,
  );
  // Resposta autorizada do cockpit (Tarefa 4) — null = backend indisponível
  // ou flag desligada; nesse caso a página calcula tudo client-side (hoje).
  const [hojeBackend, setHojeBackend] = useState<HojeBackend | null>(null);

  const carregar = useCallback(async () => {
    const inicioDocs = format(
      new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
      "yyyy-MM-dd",
    );
    const [rKpis, rAtiv, rCasos, rDocs, rTarefas, rIntegridade, rPecas, rHoje] =
      await Promise.allSettled([
        api.get("/dashboard/"),
        api.get("/atividades", { params: { apenas_pendentes: true } }),
        api.get("/cases/", { params: { page: 1, page_size: 20 } }),
        api.get("/documents/", {
          params: { page: 1, page_size: 1, data_inicio: inicioDocs },
        }),
        api.get("/tasks/", { params: { minhas: true } }),
        canUseIntegridade
          ? api.get("/saneamento/integridade")
          : Promise.resolve({ data: null }),
        api.get("/legal-docs/", { params: { page: 1, page_size: 30 } }),
        USAR_DASHBOARD_HOJE
          ? api.get("/dashboard/hoje")
          : Promise.resolve({ data: null }),
      ]);
    setKpis(rKpis.status === "fulfilled" ? (rKpis.value.data as Kpis) : null);
    setAtividades(
      rAtiv.status === "fulfilled" ? asList<Atividade>(rAtiv.value.data) : null,
    );
    setCasos(
      rCasos.status === "fulfilled"
        ? asList<CasoResumo>(rCasos.value.data)
        : null,
    );
    setDocumentosRecentes(
      rDocs.status === "fulfilled"
        ? ((rDocs.value.data as { total?: number })?.total ?? null)
        : null,
    );
    setTarefas(
      rTarefas.status === "fulfilled"
        ? asList<Tarefa>(rTarefas.value.data)
        : null,
    );
    setIntegridade(
      rIntegridade.status === "fulfilled" && rIntegridade.value.data
        ? (rIntegridade.value.data as IntegridadeResumo)
        : null,
    );
    setPecasRecentes(
      rPecas.status === "fulfilled"
        ? asList<LegalDocResumo>(rPecas.value.data)
        : null,
    );
    setHojeBackend(
      rHoje.status === "fulfilled" && rHoje.value.data
        ? (rHoje.value.data as HojeBackend)
        : null,
    );
    setCarregado(true);
  }, [canUseIntegridade]);

  useEffect(() => {
    if (carregado) return;
    void carregar();
  }, [carregar, carregado]);

  useEffect(() => {
    const id = getUltimoCasoId();
    if (!id) return;
    let ativo = true;
    api
      .get(`/cases/${id}`)
      .then((response) => {
        if (ativo) setUltimoCaso(response.data as CasoResumo);
      })
      .catch(() => {
        if (ativo) setUltimoCaso(null);
      });
    return () => {
      ativo = false;
    };
  }, []);

  const primeiroNome = user?.full_name?.trim().split(/\s+/)[0] || "usuário";

  const prazosHoje = useMemo(() => {
    // Fonte autorizada (Tarefa 4): contagem sobre a carteira inteira.
    if (hojeBackend?.contadores && typeof hojeBackend.contadores.prazos_hoje === "number") {
      return hojeBackend.contadores.prazos_hoje;
    }
    if (!atividades) return null;
    return atividades.filter(
      (a) => a.tipo === "prazo" && a.dias_restantes === 0,
    ).length;
  }, [hojeBackend, atividades]);

  const integridadeTotal = useMemo(() => {
    if (!integridade) return null;
    const chaves = [
      "sem_responsavel",
      "pre_processual_com_cnj",
      "protocolado_sem_processo",
      "processo_sem_principal",
      "judicial_sem_valor_causa",
      "sem_atualizacao_60d",
      "recebimentos_sem_rateio",
      "recebimentos_sem_caso",
      "divergencias_datajud",
      "duplicatas_cnj",
      "numeros_invalidos",
    ];
    return chaves.reduce((total, chave) => {
      const valor = integridade.contagens?.[chave];
      return total + (typeof valor === "number" ? valor : 0);
    }, 0);
  }, [integridade]);

  const casosEmDestaque = useMemo(() => {
    if (!casos) return null;
    return casos
      .map((caso, index) => ({
        caso,
        index,
        score: scoreCaso(caso, atividades),
      }))
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        const aCriado = Date.parse(a.caso.created_at ?? "") || 0;
        const bCriado = Date.parse(b.caso.created_at ?? "") || 0;
        if (bCriado !== aCriado) return bCriado - aCriado;
        return a.index - b.index;
      })
      .slice(0, 4)
      .map(({ caso }) => caso);
  }, [casos, atividades]);

  const hoje = format(new Date(), "yyyy-MM-dd");
  const rotinaHoje = useMemo(() => {
    if (!tarefas) return [];
    return tarefas
      .filter((tarefa) => {
        if (tarefa.status === "concluida") {
          return tarefa.concluida_em?.slice(0, 10) === hoje;
        }
        const limite = tarefa.data_limite?.slice(0, 10);
        return !limite || limite <= hoje;
      })
      .sort((a, b) => scoreTarefaHoje(b, hoje) - scoreTarefaHoje(a, hoje))
      .slice(0, 5);
  }, [tarefas, hoje]);

  const rotinaPendentes = rotinaHoje.filter((t) => t.status !== "concluida");

  const canUseLegal = useMemo(() => {
    const roles = new Set(["superadmin", "admin", "socio", "advogado"]);
    return roles.has(user?.role || "");
  }, [user?.role]);
  const canUseEntry = useMemo(() => {
    const roles = new Set([
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "secretaria",
    ]);
    return roles.has(user?.role || "");
  }, [user?.role]);

  const temCarteira =
    carregado &&
    ((kpis?.casos?.ativos ?? 0) > 0 ||
      (casos?.length ?? 0) > 0 ||
      Boolean(ultimoCaso?.id));

  const decisoesHoje = useMemo<DecisaoHoje[]>(() => {
    // Fonte autorizada (Tarefa 4): decisões calculadas no servidor sobre o
    // conjunto completo permitido pela visibilidade — sem amostra do navegador.
    if (hojeBackend?.decisoes && hojeBackend.decisoes.length > 0) {
      return hojeBackend.decisoes.map((d, index) => ({
        id: d.id,
        prioridade: d.prioridade ?? 1000 - index,
        titulo: d.titulo,
        detalhe: d.detalhe,
        acao: d.acao,
        to: d.to,
        tom: d.tom,
      }));
    }
    const decisoes: DecisaoHoje[] = [];
    const casosPorId = new Map(
      (casos ?? []).filter((caso) => caso.id).map((caso) => [caso.id!, caso]),
    );

    for (const peca of pecasRecentes ?? []) {
      if (!["em_revisao", "corrigida"].includes(peca.status ?? "")) continue;
      const caso = peca.case_id ? casosPorId.get(peca.case_id) : undefined;
      decisoes.push({
        id: `peca-${peca.id}`,
        prioridade: peca.status === "em_revisao" ? 120 : 112,
        titulo:
          peca.status === "em_revisao"
            ? "Peça aguardando sua revisão"
            : "Peça corrigida aguardando aprovação",
        detalhe: [peca.titulo || "Peça jurídica", caso?.titulo]
          .filter(Boolean)
          .join(" · "),
        acao:
          peca.status === "em_revisao" ? "Revisar peça" : "Conferir e aprovar",
        to: peca.case_id
          ? `/casos/${peca.case_id}?tab=pecas#revisao`
          : "/pecas",
        tom: "danger",
      });
    }

    for (const atividade of atividades ?? []) {
      if (atividade.tipo !== "prazo") continue;
      const dias = atividade.dias_restantes;
      if (
        dias === null ||
        dias === undefined ||
        (dias > 3 && atividade.urgencia !== "critico")
      ) {
        continue;
      }
      const caso = atividade.case_id
        ? casosPorId.get(atividade.case_id)
        : undefined;
      decisoes.push({
        id: `prazo-${atividade.id ?? atividade.titulo}`,
        prioridade: dias < 0 ? 118 : dias === 0 ? 110 : 94 - dias,
        titulo:
          dias < 0
            ? "Prazo vencido exige decisão"
            : dias === 0
              ? "Prazo vence hoje"
              : `Prazo em ${dias} dia(s)`,
        detalhe: [
          atividade.titulo || "Prazo",
          caso?.titulo || atividade.caso_titulo,
        ]
          .filter(Boolean)
          .join(" · "),
        acao: atividade.case_id ? "Abrir caso e resolver" : "Resolver prazo",
        to: atividade.case_id
          ? `/casos/${atividade.case_id}`
          : "/atividades?tipo=prazo",
        tom: dias <= 0 ? "danger" : "warning",
      });
    }

    for (const tarefa of rotinaPendentes) {
      decisoes.push({
        id: `tarefa-${tarefa.id}`,
        prioridade: scoreTarefaHoje(tarefa, hoje),
        titulo: "Tarefa requer ação hoje",
        detalhe: tarefa.titulo || "Tarefa pendente",
        acao: "Abrir tarefa",
        to: "/atividades?tipo=tarefa",
        tom: "info",
      });
    }

    for (const caso of casosEmDestaque ?? []) {
      const risco = (caso.risco ?? "").toLowerCase();
      if (!["alto", "critico", "crítico"].includes(risco)) continue;
      decisoes.push({
        id: `risco-${caso.id ?? caso.titulo}`,
        prioridade: risco.startsWith("crit") ? 88 : 76,
        titulo: risco.startsWith("crit")
          ? "Caso com risco crítico"
          : "Caso com risco alto",
        detalhe: [caso.titulo || "Caso", caso.proxima_acao]
          .filter(Boolean)
          .join(" · "),
        acao: "Revisar estratégia",
        to: caso.id ? `/casos/${caso.id}?tab=dossie` : "/radar",
        tom: "warning",
      });
    }

    const unicas = new Map<string, DecisaoHoje>();
    for (const decisao of decisoes.sort(
      (a, b) => b.prioridade - a.prioridade,
    )) {
      const chave = decisao.to + "|" + decisao.titulo;
      if (!unicas.has(chave)) unicas.set(chave, decisao);
    }
    return [...unicas.values()].slice(0, 3);
  }, [
    atividades,
    casos,
    casosEmDestaque,
    hoje,
    pecasRecentes,
    rotinaPendentes,
  ]);

  const valorOuTraco = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : String(v);

  const metrica = (v: number | null | undefined) =>
    carregado ? (
      valorOuTraco(v)
    ) : (
      <span className="ejc-skeleton ejc-skeleton--metric" aria-hidden="true" />
    );

  return (
    <div className="ejc-dash">
      <section
        className={`ejc-dash__ai-home ${temCarteira ? "is-compact" : ""}`}
        aria-label="Entrada de casos"
      >
        {temCarteira ? (
          <div className="ejc-dash__entry-compact">
            <div>
              <span className="ejc-dash__entry-kicker">
                EJC · Entrada Jurídica
              </span>
              <strong>Começar novo trabalho</strong>
              <small>
                Sua carteira já está ativa. Entre direto por IA ou cadastro
                manual sem ocupar o painel de decisões.
              </small>
            </div>
            <div className="ejc-dash__entry-compact-actions">
              {canUseLegal && (
                <Link to="/entrada" className="is-primary">
                  <Sparkles aria-hidden="true" />
                  Analisar novo caso
                </Link>
              )}
              {canUseEntry && (
                <Link to="/cadastro-manual?aba=caso">
                  <Briefcase aria-hidden="true" />
                  Cadastro manual
                </Link>
              )}
            </div>
          </div>
        ) : (
          <>
            <div
              className="ejc-dash__entry-options"
              aria-label="Escolha como iniciar"
            >
              {canUseEntry && (
                <Link
                  to="/cadastro-manual?aba=caso"
                  className="ejc-dash__entry-option is-manual"
                >
                  <span
                    className="ejc-dash__entry-option-icon"
                    aria-hidden="true"
                  >
                    <Briefcase />
                  </span>
                  <span>
                    <strong>Cadastrar caso manualmente</strong>
                    <small>
                      Cliente, título, área, processo e valor. Direto, sem IA.
                    </small>
                  </span>
                  <ChevronRight aria-hidden="true" />
                </Link>
              )}
              {canUseLegal && (
                <a
                  href="#ejc-ai-intake"
                  className="ejc-dash__entry-option is-ai"
                >
                  <span
                    className="ejc-dash__entry-option-icon"
                    aria-hidden="true"
                  >
                    <Sparkles />
                  </span>
                  <span>
                    <strong>Ler e analisar caso com IA</strong>
                    <small>
                      Relate a situação ou envie documentos para a análise
                      jurídica.
                    </small>
                  </span>
                  <ChevronRight aria-hidden="true" />
                </a>
              )}
            </div>

            <section
              id="ejc-ai-intake"
              className="ejc-dash__entry ejc-dash__entry--ai-home"
              aria-label="Leitura e análise do caso com IA"
            >
              <div className="ejc-dash__entry-head ejc-dash__entry-head--ai-home">
                <span className="ejc-dash__entry-icon">
                  <IdentidadeAssistente />
                </span>
                <div className="ejc-dash__entry-copy">
                  <span className="ejc-dash__entry-kicker">
                    EJC · Inteligência Jurídica
                  </span>
                  <h1>Leitura e análise do caso com IA</h1>
                  <p>
                    Relate a situação ou anexe os documentos. A IA organiza o
                    contexto jurídico e propõe o fluxo para sua confirmação.
                  </p>
                </div>
              </div>

              {canUseLegal ? (
                <div className="ejc-dash__entry-body">
                  <EntradaInteligente embedded />
                </div>
              ) : canUseEntry ? (
                <div className="ejc-dash__entry-body ejc-dash__entry-body--plain">
                  <p>
                    Seu perfil pode cadastrar clientes e casos manualmente, sem
                    IA.
                  </p>
                  <Link
                    to="/cadastro-manual?aba=caso"
                    className="ejc-dash__entry-cta"
                  >
                    Cadastrar caso manualmente
                  </Link>
                </div>
              ) : (
                <div className="ejc-dash__entry-body ejc-dash__entry-body--plain">
                  <p>
                    A Entrada Única está disponível apenas aos perfis
                    autorizados.
                  </p>
                </div>
              )}
            </section>
          </>
        )}
      </section>
      <div className="ejc-dash__workspace" aria-label="Painel do escritório">
        <header className="ejc-dash__greeting" aria-label="Saudação do dia">
          <div>
            <h1>
              {saudacaoPorHora()}, {primeiroNome}!
            </h1>
            <p>O que vamos resolver hoje?</p>
          </div>
          {ultimoCaso?.id ? (
            <Link
              to={`/casos/${ultimoCaso.id}`}
              className="ejc-dash__resume"
              aria-label={`Continuar de onde parei: ${ultimoCaso.titulo || "Caso"}`}
            >
              <span>
                <small>Continuar de onde parei</small>
                <strong>{ultimoCaso.titulo || "Caso"}</strong>
                <em>
                  {ultimoCaso.proxima_acao || "Retomar o trabalho neste caso"}
                </em>
              </span>
              <ChevronRight aria-hidden="true" />
            </Link>
          ) : (
            <div className="ejc-dash__greeting-tag" aria-hidden="true">
              <span>Conhecimento</span>
              <span>Estratégia</span>
              <span>Resultados reais</span>
            </div>
          )}
        </header>

        <section className="ejc-dash__stats" aria-label="Sinais do escritório">
          <Link
            to="/atividades?tipo=prazo"
            className="ejc-dash__stat is-dark"
            aria-label={`Prazos hoje: ${valorOuTraco(prazosHoje)}`}
          >
            <span className="ejc-dash__stat-icon" aria-hidden="true">
              <CalendarClock />
            </span>
            <strong>{metrica(prazosHoje)}</strong>
            <small>Prazos hoje</small>
            <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
          </Link>
          <Link
            to="/clientes"
            className="ejc-dash__stat"
            aria-label={`Clientes ativos: ${valorOuTraco(kpis?.clientes_ativos)}`}
          >
            <span className="ejc-dash__stat-icon" aria-hidden="true">
              <Users />
            </span>
            <strong>{metrica(kpis?.clientes_ativos)}</strong>
            <small>Clientes ativos</small>
            <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
          </Link>
          <Link
            to="/casos"
            className="ejc-dash__stat"
            aria-label={`Casos em andamento: ${valorOuTraco(kpis?.casos?.ativos)}`}
          >
            <span className="ejc-dash__stat-icon" aria-hidden="true">
              <FolderKanban />
            </span>
            <strong>{metrica(kpis?.casos?.ativos)}</strong>
            <small>Casos em andamento</small>
            <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
          </Link>
          {canUseIntegridade ? (
            <Link
              to="/radar?modo=integridade"
              className="ejc-dash__stat"
              aria-label={`Pendências de integridade: ${valorOuTraco(integridadeTotal)}`}
            >
              <span className="ejc-dash__stat-icon" aria-hidden="true">
                <ShieldCheck />
              </span>
              <strong>{metrica(integridadeTotal)}</strong>
              <small>Integridade da carteira</small>
              <ChevronRight
                className="ejc-dash__stat-chev"
                aria-hidden="true"
              />
            </Link>
          ) : (
            <Link
              to="/documentos"
              className="ejc-dash__stat"
              aria-label={`Documentos recentes: ${valorOuTraco(documentosRecentes)}`}
            >
              <span className="ejc-dash__stat-icon" aria-hidden="true">
                <FileText />
              </span>
              <strong>{metrica(documentosRecentes)}</strong>
              <small>Documentos recentes</small>
              <ChevronRight
                className="ejc-dash__stat-chev"
                aria-hidden="true"
              />
            </Link>
          )}
        </section>

        <div className="ejc-dash__panels">
          <section className="ejc-dash__panel" aria-label="Casos em destaque">
            <div className="ejc-dash__panel-head">
              <div className="ejc-dash__panel-title">
                <span className="ejc-dash__panel-ico" aria-hidden="true">
                  <Briefcase />
                </span>
                <h3>Casos em destaque</h3>
              </div>
              <Link to="/casos" className="ejc-dash__panel-more">
                Ver todos <ChevronRight aria-hidden="true" />
              </Link>
            </div>
            <ul className="ejc-dash__cases">
              {casosEmDestaque === null ? (
                <li className="ejc-dash__empty">Casos indisponíveis agora.</li>
              ) : casosEmDestaque.length === 0 ? (
                <li className="ejc-dash__empty ejc-dash__empty--action">
                  <span>Nenhum caso cadastrado ainda.</span>
                  <Link to="/cadastro-manual?aba=caso">
                    Cadastrar primeiro caso
                  </Link>
                </li>
              ) : (
                casosEmDestaque.map((c) => {
                  const chip = chipDeCaso(c.status);
                  const meta = c.numero_processo
                    ? `Proc. nº ${c.numero_processo}`
                    : c.numero_interno
                      ? `Caso ${c.numero_interno}`
                      : "";
                  return (
                    <li key={c.id ?? c.titulo}>
                      <button
                        type="button"
                        onClick={() => c.id && navigate(`/casos/${c.id}`)}
                      >
                        <span className={`ejc-dash__case-chip ${chip.classe}`}>
                          {chip.rotulo}
                        </span>
                        <strong>{c.titulo || "Caso sem título"}</strong>
                        <small>
                          {[
                            meta,
                            c.area
                              ? c.area.charAt(0).toUpperCase() + c.area.slice(1)
                              : "",
                            c.proxima_acao ? `Próxima: ${c.proxima_acao}` : "",
                          ]
                            .filter(Boolean)
                            .join("  ·  ")}
                        </small>
                        <ChevronRight aria-hidden="true" />
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </section>

          <section
            className="ejc-dash__panel ejc-dash__radar"
            aria-label="Radar Estratégico do Escritório"
          >
            <div className="ejc-dash__panel-head">
              <div className="ejc-dash__panel-title">
                <span className="ejc-dash__panel-ico" aria-hidden="true">
                  <Sparkles />
                </span>
                <h3>Radar Estratégico do Escritório</h3>
              </div>
              <Link to="/radar" className="ejc-dash__panel-more">
                Análise completa <ChevronRight aria-hidden="true" />
              </Link>
            </div>

            <div className="ejc-dash__decision-head">
              <div>
                <strong>Decisões que exigem sua atenção hoje</strong>
                <small>
                  Revisões, prazos, tarefas e riscos ordenados por urgência.
                </small>
              </div>
              <span>{carregado ? decisoesHoje.length : "—"}</span>
            </div>

            <ol className="ejc-dash__decision-list">
              {!carregado ? (
                [0, 1, 2].map((item) => (
                  <li key={item} className="is-loading" aria-hidden="true">
                    <span className="ejc-skeleton ejc-skeleton--decision" />
                  </li>
                ))
              ) : decisoesHoje.length === 0 ? (
                <li className="is-clear">
                  <span className="is-success">
                    <ShieldCheck aria-hidden="true" />
                  </span>
                  <div>
                    <strong>Nenhuma decisão crítica pendente agora</strong>
                    <small>
                      Continue pela agenda, casos em destaque ou pela busca
                      universal.
                    </small>
                  </div>
                  <Link to="/atividades">Ver agenda</Link>
                </li>
              ) : (
                decisoesHoje.map((decisao, index) => (
                  <li key={decisao.id}>
                    <Link to={decisao.to}>
                      <span className={`is-${decisao.tom}`}>
                        <strong>{String(index + 1).padStart(2, "0")}</strong>
                        <AlertTriangle aria-hidden="true" />
                      </span>
                      <div>
                        <strong>{decisao.titulo}</strong>
                        <small>{decisao.detalhe}</small>
                      </div>
                      <em>{decisao.acao}</em>
                      <ChevronRight aria-hidden="true" />
                    </Link>
                  </li>
                ))
              )}
            </ol>
          </section>
        </div>

        <section className="ejc-dash__quick" aria-label="Fluxo jurídico">
          <div className="ejc-dash__quick-head">
            <Zap aria-hidden="true" />
            <strong>Fluxo jurídico</strong>
            <small>Do caso à próxima ação</small>
          </div>
          <div className="ejc-dash__quick-items">
            <Link to="/entrada" aria-label="Analisar caso">
              <span aria-hidden="true">
                <Sparkles />
              </span>
              <small aria-hidden="true">01</small>
              Analisar caso
            </Link>
            <Link to="/documentos" aria-label="Provas">
              <span aria-hidden="true">
                <Paperclip />
              </span>
              <small aria-hidden="true">02</small>
              Provas
            </Link>
            <Link to="/teses" aria-label="Teses">
              <span aria-hidden="true">
                <Scale />
              </span>
              <small aria-hidden="true">03</small>
              Teses
            </Link>
            <Link to="/inteligencia?tab=assistente" aria-label="Estratégia">
              <span aria-hidden="true">
                <ShieldCheck />
              </span>
              <small aria-hidden="true">04</small>
              Estratégia
            </Link>
            <Link to="/pecas" aria-label="Peça">
              <span aria-hidden="true">
                <FileText />
              </span>
              <small aria-hidden="true">05</small>
              Peça
            </Link>
            <Link to="/pecas" aria-label="Revisão">
              <span aria-hidden="true">
                <Gavel />
              </span>
              <small aria-hidden="true">06</small>
              Revisão
            </Link>
            <Link to="/ajuizamento" aria-label="Ajuizamento">
              <span aria-hidden="true">
                <ChevronRight />
              </span>
              <small aria-hidden="true">07</small>
              Ajuizamento
            </Link>
          </div>
        </section>

        <section
          className="ejc-dash__extras"
          aria-label="Inteligência e conhecimento"
        >
          <article className="ejc-dash__extra-card">
            <div className="ejc-dash__extra-head">
              <span>
                <Sparkles aria-hidden="true" />
              </span>
              <strong>Inteligência estratégica</strong>
              <Link to="/inteligencia">
                Acessar <ChevronRight aria-hidden="true" />
              </Link>
            </div>
            <div className="ejc-dash__extra-links">
              <Link to="/entrada">
                <Sparkles aria-hidden="true" />
                <span>
                  <strong>Análise estratégica</strong>
                  <small>Entrada Única com IA</small>
                </span>
              </Link>
              <Link to="/documentos">
                <FileText aria-hidden="true" />
                <span>
                  <strong>Mapa da prova</strong>
                  <small>Documentos, fatos e lacunas</small>
                </span>
              </Link>
              <Link to="/inteligencia?tab=pesquisa">
                <Search aria-hidden="true" />
                <span>
                  <strong>Pesquisa jurisprudencial</strong>
                  <small>Precedentes e fundamentos</small>
                </span>
              </Link>
              <Link to="/pecas">
                <Gavel aria-hidden="true" />
                <span>
                  <strong>Revisão de peça</strong>
                  <small>Estrutura e consistência</small>
                </span>
              </Link>
            </div>
          </article>

          <article className="ejc-dash__extra-card">
            <div className="ejc-dash__extra-head">
              <span>
                <Lightbulb aria-hidden="true" />
              </span>
              <strong>Teses e oportunidades</strong>
              <Link to="/teses">
                Ver banco <ChevronRight aria-hidden="true" />
              </Link>
            </div>
            <div className="ejc-dash__extra-links">
              <Link to="/teses">
                <Scale aria-hidden="true" />
                <span>
                  <strong>Banco de teses</strong>
                  <small>Teses consolidadas do escritório</small>
                </span>
              </Link>
              <Link to="/radar">
                <AlertTriangle aria-hidden="true" />
                <span>
                  <strong>Riscos e nulidades</strong>
                  <small>Pontos que exigem ação</small>
                </span>
              </Link>
              <Link to="/inteligencia?tab=assistente">
                <Gavel aria-hidden="true" />
                <span>
                  <strong>Advogado do Diabo</strong>
                  <small>Ataque, defesa e fragilidades</small>
                </span>
              </Link>
              <Link to="/atividades">
                <CalendarClock aria-hidden="true" />
                <span>
                  <strong>Próximas ações</strong>
                  <small>Prazos, tarefas e agenda</small>
                </span>
              </Link>
            </div>
          </article>

          <article className="ejc-dash__extra-card">
            <div className="ejc-dash__extra-head">
              <span>
                <Library aria-hidden="true" />
              </span>
              <strong>Base de conhecimento</strong>
              <Link to="/inteligencia?tab=conhecimento">
                Acessar <ChevronRight aria-hidden="true" />
              </Link>
            </div>
            <div className="ejc-dash__knowledge-grid">
              <Link to="/inteligencia?tab=pesquisa">
                <Scale aria-hidden="true" />
                <strong>STF</strong>
                <small>Repercussão geral</small>
              </Link>
              <Link to="/inteligencia?tab=pesquisa">
                <Gavel aria-hidden="true" />
                <strong>STJ</strong>
                <small>Repetitivos</small>
              </Link>
              <Link to="/datajud">
                <FolderKanban aria-hidden="true" />
                <strong>CNJ</strong>
                <small>DataJud</small>
              </Link>
              <Link to="/inteligencia?tab=conhecimento">
                <BookOpen aria-hidden="true" />
                <strong>Legislação</strong>
                <small>Códigos e normas</small>
              </Link>
              <Link to="/inteligencia?tab=pesquisa">
                <Search aria-hidden="true" />
                <strong>Jurisprudência</strong>
                <small>Busca avançada</small>
              </Link>
              <Link to="/teses">
                <Lightbulb aria-hidden="true" />
                <strong>Memória</strong>
                <small>Teses e resultados</small>
              </Link>
            </div>
          </article>
        </section>

        <footer className="ejc-dash__footer">
          <span>
            {officeBranding.officeName} <i aria-hidden="true">|</i> São Paulo -
            SP
          </span>
          <span className="ejc-dash__footer-tag">
            <i aria-hidden="true" /> Mais que soluções. Parcerias duradouras.
          </span>
        </footer>
      </div>
    </div>
  );
}
