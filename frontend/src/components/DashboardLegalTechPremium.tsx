/**
 * DashboardLegalTechPremium — Componente de demonstração
 *
 * Implementa o estilo Legal Tech Premium conforme especificação:
 * - Fundo branco com profundidade discreta
 * - Menu lateral branco com logo centralizada
 * - Azul-marinho institucional, azul elétrico para ações, violeta para IA
 * - Cards funcionais com ícones, quantidades e indicações de urgência
 * - Dashboard focado em pendências e próximas ações
 */

import { Link } from "react-router";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Bot,
  Briefcase,
  Calendar,
  CheckCircle,
  Clock,
  FileText,
  Gavel,
  Inbox,
  LayoutDashboard,
  Plus,
  Scale,
  Search,
  Sparkles,
  Users,
} from "lucide-react";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  subtitle?: string;
  trend?: "up" | "down" | "neutral";
  tone?: "blue" | "green" | "amber" | "red" | "violet";
  urgent?: boolean;
}

function StatCard({
  icon,
  label,
  value,
  subtitle,
  trend,
  tone = "blue",
  urgent = false,
}: StatCardProps) {
  const toneClasses = {
    blue: "bg-[#EFF6FF] text-[#2563EB]",
    green: "bg-[#ECFDF5] text-[#0F9D8A]",
    amber: "bg-[#FFFBEB] text-[#D97706]",
    red: "bg-[#FEF2F2] text-[#DC2626]",
    violet: "bg-[#F5F3FF] text-[#7C3AED]",
  };

  return (
    <div className="lt-stat-card">
      <div className="lt-flex-between lt-mb-12">
        <div className={`lt-stat-icon ${tone}`}>{icon}</div>
        {urgent && (
          <span className="lt-badge lt-badge-red">
            <AlertTriangle className="h-3 w-3" />
            Crítico
          </span>
        )}
        {trend && (
          <span className={`lt-stat-trend ${trend === "up" ? "up" : "down"}`}>
            {trend === "up" ? "↑" : "↓"} 12%
          </span>
        )}
      </div>
      <div className="lt-stat-value">{value}</div>
      <div className="lt-stat-label">{label}</div>
      {subtitle && (
        <div className="lt-text-xs lt-text-secondary lt-mt-8">{subtitle}</div>
      )}
    </div>
  );
}

interface ActionCardProps {
  icon: React.ReactNode;
  title: string;
  count: number;
  summary: string;
  urgent?: boolean;
  actionLabel: string;
  actionHref: string;
}

function ActionCard({
  icon,
  title,
  count,
  summary,
  urgent = false,
  actionLabel,
  actionHref,
}: ActionCardProps) {
  return (
    <div className="lt-card">
      <div className="lt-card-header lt-mb-16">
        <div className="lt-flex-center lt-flex-gap-12">
          <div className="h-10 w-10 lt-flex-center lt-rounded lt-bg-action-light lt-text-action">
            {icon}
          </div>
          <div>
            <h3 className="lt-card-title">{title}</h3>
            <p className="lt-text-2xl lt-font-semibold lt-text-primary">
              {count}
            </p>
          </div>
        </div>
        {urgent && (
          <span className="lt-badge lt-badge-amber">
            <Clock className="h-3 w-3" />
            Pendente
          </span>
        )}
      </div>
      <p className="lt-text-sm lt-text-secondary lt-mb-16">{summary}</p>
      <Link
        to={actionHref}
        className="lt-text-sm lt-font-medium lt-text-action lt-flex-center lt-flex-gap-8 hover:underline"
      >
        {actionLabel} <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

export default function DashboardLegalTechPremium() {
  const greeting = "Bom dia, Dr. Silva";
  const date = new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="lt-shell">
      {/* Header Superior Fixo */}
      <header className="lt-header">
        {/* Pesquisa Global */}
        <div className="flex flex-1 items-center gap-3">
          <div className="relative max-w-xl flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--lt-text-tertiary)]" />
            <input
              type="text"
              placeholder="Buscar processos, clientes, documentos..."
              className="lt-input pl-10"
            />
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 rounded border border-[var(--lt-card-border)] bg-white px-2 py-0.5 text-[10px] font-medium text-[var(--lt-text-tertiary)]">
              Ctrl K
            </kbd>
          </div>
        </div>

        {/* Ações Rápidas */}
        <div className="lt-flex-center lt-flex-gap-12">
          <Link to="/casos/novo">
            <button className="lt-btn lt-btn-primary">
              <Plus className="h-4 w-4" />
              Novo atendimento
            </button>
          </Link>

          <button className="lt-btn lt-btn-secondary" title="Raio-X">
            <Scale className="h-4 w-4" />
          </button>

          <button className="lt-btn lt-btn-secondary" title="Assistente IA">
            <Sparkles className="h-4 w-4 lt-text-ai" />
          </button>

          <button
            className="relative lt-btn lt-btn-secondary"
            title="Notificações"
          >
            <Bell className="h-4 w-4" />
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-[#DC2626] px-1 text-[10px] font-semibold text-white">
              3
            </span>
          </button>

          {/* Avatar do Usuário */}
          <div className="lt-flex-center lt-flex-gap-8">
            <div className="h-9 w-9 lt-flex-center lt-rounded-full lt-bg-action-light lt-font-semibold lt-text-action">
              DS
            </div>
          </div>
        </div>
      </header>

      {/* Menu Lateral */}
      <aside className="lt-sidebar">
        {/* Logo Centralizada */}
        <div className="lt-sidebar-logo">
          <img
            src="/brand/de-paula-teixeira-logo.jpg"
            alt="De Paula Teixeira"
          />
        </div>

        {/* Navegação */}
        <nav className="lt-nav lt-scrollbar">
          {/* Grupo: Operação */}
          <div className="lt-nav-group">
            <div className="lt-nav-group-label">Operação</div>
            <a href="/" className="lt-nav-item active">
              <LayoutDashboard className="h-5 w-5" />
              <span>Dashboard</span>
            </a>
            <a href="/raio-x" className="lt-nav-item">
              <Scale className="h-5 w-5" />
              <span>Triagem e Raio-X</span>
            </a>
            <a href="/clientes" className="lt-nav-item">
              <Briefcase className="h-5 w-5" />
              <span>Clientes</span>
            </a>
            <a href="/casos" className="lt-nav-item">
              <Gavel className="h-5 w-5" />
              <span>Casos</span>
            </a>
          </div>

          {/* Grupo: Jurídico */}
          <div className="lt-nav-group">
            <div className="lt-nav-group-label">Jurídico</div>
            <a href="/agenda" className="lt-nav-item">
              <Calendar className="h-5 w-5" />
              <span>Agenda e tarefas</span>
            </a>
            <a href="/documentos" className="lt-nav-item">
              <FileText className="h-5 w-5" />
              <span>Documentos</span>
            </a>
            <a href="/prazos" className="lt-nav-item">
              <Clock className="h-5 w-5" />
              <span>Prazos</span>
            </a>
            <a href="/intimacoes" className="lt-nav-item">
              <Inbox className="h-5 w-5" />
              <span>Intimações</span>
            </a>
          </div>

          {/* Grupo: Inteligência */}
          <div className="lt-nav-group">
            <div className="lt-nav-group-label lt-flex-between">
              <span>Inteligência</span>
              <Sparkles className="h-3.5 w-3.5 lt-text-ai" />
            </div>
            <a href="/ia" className="lt-nav-item">
              <Bot className="h-5 w-5 lt-text-ai" />
              <span>IA Jurídica</span>
            </a>
            <a href="/conhecimento" className="lt-nav-item">
              <Scale className="h-5 w-5" />
              <span>Conhecimento jurídico</span>
            </a>
          </div>

          {/* Grupo: Financeiro */}
          <div className="lt-nav-group">
            <div className="lt-nav-group-label">Financeiro</div>
            <a href="/financeiro" className="lt-nav-item">
              <Users className="h-5 w-5" />
              <span>Financeiro</span>
            </a>
          </div>
        </nav>

        {/* Rodapé do Menu */}
        <div className="lt-border-top lt-p-16">
          <div className="lt-flex-between lt-text-xs">
            <span className="lt-text-secondary">Seguro & Conforme</span>
            <CheckCircle className="h-4 w-4 lt-text-success" />
          </div>
        </div>
      </aside>

      {/* Conteúdo Principal */}
      <main className="lt-main">
        {/* Primeira Faixa: Saudação e Ações Rápidas */}
        <div className="lt-page-header lt-flex-between">
          <div>
            <div className="lt-page-eyebrow">Painel Executivo</div>
            <h1 className="lt-page-title">{greeting}</h1>
            <p className="lt-page-subtitle">{date}</p>
          </div>
          <div className="lt-flex-center lt-flex-gap-12">
            <button className="lt-btn lt-btn-primary">
              <Plus className="h-4 w-4" />
              Novo atendimento
            </button>
            <button className="lt-btn lt-btn-secondary">
              <FileText className="h-4 w-4" />
              Analisar documento
            </button>
            <button className="lt-btn lt-btn-secondary">
              <Briefcase className="h-4 w-4" />
              Cadastrar manualmente
            </button>
          </div>
        </div>

        {/* Segunda Faixa: Atenção Imediata (Stat Cards) */}
        <div className="lt-dashboard-stats">
          <StatCard
            icon={<AlertTriangle className="h-5 w-5" />}
            label="Prazos críticos"
            value="7"
            subtitle="2 sem conferência"
            tone="red"
            urgent
          />
          <StatCard
            icon={<Inbox className="h-5 w-5" />}
            label="Intimações para validar"
            value="12"
            subtitle="Últimas 48h"
            tone="amber"
          />
          <StatCard
            icon={<Clock className="h-5 w-5" />}
            label="Tarefas vencidas"
            value="3"
            subtitle="Requer atenção"
            tone="red"
          />
          <StatCard
            icon={<FileText className="h-5 w-5" />}
            label="Peças aguardando revisão"
            value="5"
            subtitle="Prioridade média"
            tone="amber"
          />
          <StatCard
            icon={<Users className="h-5 w-5" />}
            label="Clientes aguardando retorno"
            value="8"
            subtitle="SLA pendente"
            tone="blue"
          />
        </div>

        {/* Terceira Faixa: Cards de Ação */}
        <div className="lt-dashboard-row lt-dashboard-row-2">
          <ActionCard
            icon={<Clock className="h-5 w-5" />}
            title="Prazos próximos"
            count={7}
            summary="2 prazos ainda não foram conferidos"
            urgent
            actionLabel="Revisar prazos"
            actionHref="/prazos"
          />
          <ActionCard
            icon={<Inbox className="h-5 w-5" />}
            title="Intimações pendentes"
            count={12}
            summary="Validação necessária nas próximas 24h"
            urgent
            actionLabel="Validar intimações"
            actionHref="/intimacoes"
          />
          <ActionCard
            icon={<Calendar className="h-5 w-5" />}
            title="Agenda do dia"
            count={4}
            summary="2 audiências, 2 reuniões"
            actionLabel="Ver agenda completa"
            actionHref="/agenda"
          />
          <ActionCard
            icon={<FileText className="h-5 w-5" />}
            title="Documentos pendentes"
            count={9}
            summary="5 documentos para assinatura"
            actionLabel="Gerenciar documentos"
            actionHref="/documentos"
          />
        </div>

        {/* Quarta Faixa: IA e Informações */}
        <div className="lt-dashboard-row lt-dashboard-row-2">
          {/* Painel da IA */}
          <div className="lt-ai-panel">
            <div className="lt-ai-header">
              <Sparkles className="lt-ai-icon" />
              <span className="lt-ai-title">Assistente IA</span>
            </div>
            <div className="lt-ai-content">
              <div className="lt-ai-section">
                <div className="lt-ai-label">Análise Recente</div>
                <p className="lt-ai-text">
                  Documento processual analisado com 94% de confiança. Prazo
                  crítico identificado: 3 dias úteis.
                </p>
                <div className="lt-ai-actions">
                  <button className="lt-btn lt-btn-primary lt-btn-sm">
                    Aprovar
                  </button>
                  <button className="lt-btn lt-btn-secondary lt-btn-sm">
                    Corrigir
                  </button>
                  <button className="lt-btn lt-btn-ghost lt-btn-sm">
                    Descartar
                  </button>
                </div>
              </div>
              <div className="lt-ai-section">
                <div className="lt-ai-label">Recomendações</div>
                <ul
                  className="lt-text-sm lt-text-secondary lt-flex-center lt-flex-gap-8"
                  style={{
                    flexDirection: "column",
                    alignItems: "flex-start",
                    gap: "8px",
                  }}
                >
                  <li>• Revisar petição inicial do caso #2847</li>
                  <li>• Atualizar status do caso #2901</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Notícias e Atualizações */}
          <div className="lt-card">
            <div className="lt-card-header">
              <h3 className="lt-card-title">Atualizações Legislativas</h3>
              <Link
                to="/noticias"
                className="lt-text-sm lt-font-medium lt-text-action hover:underline"
              >
                Ver todas
              </Link>
            </div>
            <div className="space-y-3">
              <div className="lt-flex-between lt-border-bottom lt-p-12">
                <div className="min-w-0 flex-1">
                  <p className="lt-text-sm lt-font-medium lt-text-primary lt-mb-4">
                    Nova resolução CNJ sobre processo eletrônico
                  </p>
                  <p className="lt-text-xs lt-text-secondary">Hoje, 09:30</p>
                </div>
                <span className="lt-badge lt-badge-blue">CNJ</span>
              </div>
              <div className="lt-flex-between lt-border-bottom lt-p-12">
                <div className="min-w-0 flex-1">
                  <p className="lt-text-sm lt-font-medium lt-text-primary lt-mb-4">
                    Alterações na Lei de Execuciones Fiscais
                  </p>
                  <p className="lt-text-xs lt-text-secondary">Ontem, 14:20</p>
                </div>
                <span className="lt-badge lt-badge-violet">Legislação</span>
              </div>
              <div className="lt-flex-between lt-p-12">
                <div className="min-w-0 flex-1">
                  <p className="lt-text-sm lt-font-medium lt-text-primary lt-mb-4">
                    Jurisprudência STJ: Honorários advocatícios
                  </p>
                  <p className="lt-text-xs lt-text-secondary">2 dias atrás</p>
                </div>
                <span className="lt-badge lt-badge-gray">STJ</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
