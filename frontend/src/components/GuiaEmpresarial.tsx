// ── src/components/GuiaEmpresarial.tsx ───────────────────────────────────────
// Guia Operacional do ramo Empresarial (padrão GuiaCivil/GuiaTributario):
// os três pilares de atuação do escritório — consultivo estrutural, operacional
// recorrente e contencioso especializado — com referência às ferramentas reais
// do sistema (Sociedades do Cliente, análise IA de contrato, contratos com
// alerta de vencimento) e checklist de Due Diligence persistido localmente.
import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  BookOpen,
  Building2,
  Landmark,
  FileText,
  Briefcase,
  Scale,
  ShieldCheck,
  ListChecks,
  Gavel,
  Users,
  Lock,
  Lightbulb,
} from "lucide-react";

// ── Seção colapsável (mesmo padrão dos demais guias, com badge de valor) ─────
function Sec({
  title,
  icon,
  badge,
  children,
  open = false,
}: {
  title: string;
  icon: React.ReactNode;
  badge?: React.ReactNode;
  children: React.ReactNode;
  open?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(open);
  return (
    <div className="border border-bronze-pale rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between gap-2 p-4 bg-white hover:bg-slate-50 text-left"
      >
        <span className="flex flex-wrap items-center gap-2 font-semibold text-slate-800">
          {icon}
          {title}
          {badge}
        </span>
        <span className="text-slate-400">{isOpen ? "▲" : "▼"}</span>
      </button>
      {isOpen && (
        <div className="p-4 border-t border-slate-100 bg-slate-50 space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Badge de proposta de valor do pilar ──────────────────────────────────────
function Badge({
  cor,
  children,
}: {
  cor: "gold" | "green" | "red";
  children: React.ReactNode;
}) {
  const cores = {
    gold: "bg-gold-100 text-gold-700 border-gold-200",
    green: "bg-green-50 text-green-700 border-green-200",
    red: "bg-danger-50 text-danger-700 border-danger-200",
  } as const;
  return (
    <span
      className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${cores[cor]}`}
    >
      {children}
    </span>
  );
}

// ── Card de linha de serviço dentro de um pilar ──────────────────────────────
function Servico({
  icon,
  titulo,
  desc,
  ferramentas,
}: {
  icon: React.ReactNode;
  titulo: string;
  desc: React.ReactNode;
  ferramentas?: React.ReactNode;
}) {
  return (
    <div className="card p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-gold-600">{icon}</span>
        <span className="font-semibold text-navy text-sm">{titulo}</span>
      </div>
      <p className="text-sm text-slate-600">{desc}</p>
      {ferramentas && (
        <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span className="text-[10px] font-semibold uppercase text-slate-400">
            No sistema
          </span>
          {ferramentas}
        </div>
      )}
    </div>
  );
}

const linkCls =
  "text-gold-700 hover:text-gold-600 underline decoration-gold-200 underline-offset-2";

// ── Checklist de Due Diligence (persistido em localStorage) ──────────────────
const CHK_KEY = "guia_empresarial_chk";
const ITEMS = [
  "Definir escopo e cronograma da Due Diligence (societário, fiscal, trabalhista, contratos, PI, LGPD)",
  "Solicitar data room: atos societários, livros, certidões e demonstrações financeiras",
  "Conferir cadeia societária e cap table (quotas, acordos de sócios, opções outorgadas)",
  "Levantar certidões fiscais federais, estaduais e municipais (CND / CPEN)",
  "Mapear contencioso: processos judiciais, administrativos e arbitragens em curso",
  "Auditar contratos relevantes (cláusulas de change of control, exclusividade, vencimentos)",
  "Revisar passivo trabalhista e planos de incentivo (Stock Options, bônus, comissões)",
  "Verificar titularidade de marcas, patentes e software perante o INPI",
  "Avaliar conformidade LGPD: bases legais, mapeamento de dados, histórico de incidentes",
  "Consolidar relatório de riscos com contingências valoradas (red flags e condições de fechamento)",
];

export default function GuiaEmpresarial() {
  const [checks, setChecks] = useState<boolean[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(CHK_KEY) || "[]");
    } catch {
      return [];
    }
  });
  useEffect(() => {
    localStorage.setItem(CHK_KEY, JSON.stringify(checks));
  }, [checks]);
  const toggle = (i: number) =>
    setChecks((prev) => {
      const n = [...prev];
      n[i] = !n[i];
      return n;
    });

  return (
    <div className="space-y-3 p-4">
      <h2 className="text-xl font-bold text-primary-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito Empresarial
      </h2>
      <p className="text-sm text-slate-500">
        A atuação empresarial do escritório se organiza em três pilares: o
        consultivo estrutural (alto valor agregado), o operacional rotineiro
        (receita recorrente de mensalistas) e o contencioso especializado
        (defesa de interesses).
      </p>

      {/* ── PILAR 1 ─────────────────────────────────────────────────────── */}
      <Sec
        title="Pilar 1 — Consultivo Estrutural e Societário"
        icon={<Landmark size={16} />}
        badge={<Badge cor="gold">Alto valor agregado</Badge>}
        open
      >
        <Servico
          icon={<Building2 size={15} />}
          titulo="Planejamento Sucessório e Patrimonial"
          desc="Constituição de Holdings familiares e patrimoniais para proteger os bens dos sócios e organizar a sucessão em vida, evitando o desgaste e o custo do inventário."
          ferramentas={
            <a href="#sociedades-cliente" className={linkCls}>
              Sociedades do Cliente (cadastro e cap table) ↓
            </a>
          }
        />
        <Servico
          icon={<Users size={15} />}
          titulo="Constituição e Reestruturação Societária"
          desc="Elaboração de contratos sociais complexos, estatutos e atas de assembleia, e desenho de Acordos de Sócios/Acionistas com mecanismos de proteção — Tag Along, Drag Along e cláusulas Shotgun."
          ferramentas={
            <a href="#sociedades-cliente" className={linkCls}>
              Quadro societário e eventos (atas, alterações) ↓
            </a>
          }
        />
        <Servico
          icon={<Briefcase size={15} />}
          titulo="Assessoria em Fusões e Aquisições (M&A)"
          desc="Condução de Due Diligence — auditoria de riscos jurídica e fiscal do negócio-alvo — e estruturação dos contratos de compra e venda de participações societárias."
          ferramentas={
            <span className="text-slate-500">
              Checklist de Due Diligence — seção ao final deste guia
            </span>
          }
        />
        <Servico
          icon={<ShieldCheck size={15} />}
          titulo="Proteção Patrimonial (Blindagem)"
          desc="Estruturação jurídica legal para mitigar riscos de desconsideração da personalidade jurídica sobre os bens pessoais dos sócios — segregação de atividades, governança e uso correto dos tipos societários."
        />
      </Sec>

      {/* ── PILAR 2 ─────────────────────────────────────────────────────── */}
      <Sec
        title="Pilar 2 — Operacional Rotineiro"
        icon={<Briefcase size={16} />}
        badge={<Badge cor="green">Receita recorrente · mensalistas</Badge>}
      >
        <Servico
          icon={<FileText size={15} />}
          titulo="Engenharia Contratual"
          desc="Elaboração, revisão e negociação dos contratos comerciais do dia a dia: prestação de serviços, fornecimento, locação comercial, distribuição e representação."
          ferramentas={
            <>
              <a href="#analise-documento" className={linkCls}>
                Análise IA de contrato empresarial ↑
              </a>
              <Link to="/financeiro?tab=contratos" className={linkCls}>
                Contratos com alertas de vencimento →
              </Link>
            </>
          }
        />
        <Servico
          icon={<Users size={15} />}
          titulo="Assessoria Trabalhista Preventiva"
          desc="Contratos de trabalho, regulamentos internos, políticas de benefícios (incluindo Stock Options) e orientação estratégica para demissões de cargos de confiança."
        />
        <Servico
          icon={<Lock size={15} />}
          titulo="Adequação à LGPD"
          desc="Projetos de conformidade com a Lei Geral de Proteção de Dados: mapeamento de dados corporativos, bases legais de tratamento e termos de privacidade."
        />
        <Servico
          icon={<Lightbulb size={15} />}
          titulo="Registro de Marcas e Patentes"
          desc="Gestão do portfólio de propriedade intelectual da empresa perante o INPI — depósito, acompanhamento, oposições e renovações."
        />
      </Sec>

      {/* ── PILAR 3 ─────────────────────────────────────────────────────── */}
      <Sec
        title="Pilar 3 — Contencioso Especializado"
        icon={<Gavel size={16} />}
        badge={<Badge cor="red">Defesa de interesses</Badge>}
      >
        <Servico
          icon={<Scale size={15} />}
          titulo="Defesa em Execuções e Cobranças"
          desc="Atuação em execuções de títulos extrajudiciais, ações de cobrança e recuperação de crédito — tanto na defesa do devedor quanto na cobrança pelo credor."
        />
        <Servico
          icon={<Landmark size={15} />}
          titulo="Contencioso Tributário"
          desc="Impugnações administrativas e ações judiciais para suspender a exigibilidade de créditos tributários ou recuperar créditos fiscais pagos indevidamente."
        />
        <Servico
          icon={<Users size={15} />}
          titulo="Dissolução de Sociedade e Exclusão de Sócio"
          desc="Condução de conflitos entre sócios, pela via judicial ou extrajudicial, com apuração justa de haveres do sócio retirante ou excluído."
          ferramentas={
            <a href="#sociedades-cliente" className={linkCls}>
              Eventos societários e apuração do cap table ↓
            </a>
          }
        />
      </Sec>

      {/* ── CHECKLIST DD ────────────────────────────────────────────────── */}
      <Sec
        title="Checklist de Due Diligence (M&A)"
        icon={<ListChecks size={16} />}
      >
        <div className="space-y-2">
          {ITEMS.map((item, i) => (
            <label
              key={i}
              className="flex items-start gap-2 cursor-pointer text-sm"
            >
              <input
                type="checkbox"
                checked={!!checks[i]}
                onChange={() => toggle(i)}
                className="mt-0.5"
              />
              <span
                className={
                  checks[i] ? "line-through text-slate-400" : "text-slate-700"
                }
              >
                {item}
              </span>
            </label>
          ))}
          <p className="text-xs text-slate-400">
            {checks.filter(Boolean).length}/{ITEMS.length} itens concluídos
          </p>
        </div>
      </Sec>
    </div>
  );
}
