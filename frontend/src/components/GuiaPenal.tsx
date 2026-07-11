import React, { useState, useEffect } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  AlertTriangle,
  FileText,
} from "lucide-react";

function Sec({
  title,
  icon,
  children,
  open = false,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  open?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(open);
  return (
    <div className="border border-bronze-pale rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-white hover:bg-slate-50 text-left"
      >
        <span className="flex items-center gap-2 font-semibold text-slate-800">
          {icon}
          {title}
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

function Tab({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-slate-200">
            {headers.map((h, i) => (
              <th
                key={i}
                className="border border-bronze-pale px-3 py-2 text-left font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
              {row.map((cell, j) => (
                <td key={j} className="border border-bronze-pale px-3 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Flow({ children }: { children: string }) {
  return (
    <pre className="text-[10px] bg-slate-50 border border-slate-100 rounded p-3 overflow-x-auto leading-relaxed whitespace-pre-wrap text-slate-700">
      {children}
    </pre>
  );
}

const CHK_KEY = "guia_penal_chk";
const ITEMS = [
  "Verificar prescrição em abstrato (CP art. 109) e prescrição retroativa",
  "Analisar viabilidade de ANPP (pena mín. < 4 anos, sem violência, primário)",
  "Verificar cabimento de transação penal (JECrim — pena máx. ≤ 2 anos)",
  "Verificar suspensão condicional do processo (pena mín. ≤ 1 ano)",
  "Analisar nulidades processuais absolutas e relativas",
  "Requerer acesso imediato ao IP ou procedimento investigativo",
  "Verificar se cliente está preso — prazo de HC imediato",
  "Avaliar aplicação de atenuantes e causas de diminuição de pena",
  "Verificar progressão de regime / livramento condicional",
  "Analisar Lei Maria da Penha: medidas protetivas e competência",
];

export default function GuiaPenal() {
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
      <h2 className="text-xl font-bold text-danger-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito Penal
      </h2>

      <Sec title="Base Legal + Prescrição" icon={<Scale size={16} />} open>
        <Tab
          headers={["Pena máxima do tipo", "Prescrição em abstrato", "Base"]}
          rows={[
            ["Até 1 ano", "3 anos", "CP art. 109 VI"],
            ["Mais de 1 até 2 anos", "4 anos", "CP art. 109 V"],
            ["Mais de 2 até 4 anos", "8 anos", "CP art. 109 IV"],
            ["Mais de 4 até 8 anos", "12 anos", "CP art. 109 III"],
            ["Mais de 8 até 12 anos", "16 anos", "CP art. 109 II"],
            ["Mais de 12 anos", "20 anos", "CP art. 109 I"],
            [
              "Racismo / ação de grupos armados",
              "Imprescritível",
              "CF art. 5º XLII e XLIV",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Prescrição retroativa:</strong> após sentença condenatória,
          recalcula-se pela pena aplicada entre marcos interruptivos (CP art.
          110 §1º). <strong>Redução pela metade:</strong> agente menor de 21 na
          data do fato ou maior de 70 na sentença (CP art. 115).
        </p>
      </Sec>

      <Sec title="Prazos CPP" icon={<Clock size={16} />}>
        <Tab
          headers={["Ato", "Prazo", "Base"]}
          rows={[
            ["Resposta à acusação", "10 dias da citação", "CPP art. 396-A"],
            [
              "Embargos de declaração (juizado)",
              "5 dias",
              "Lei 9.099/95 art. 83 §1º",
            ],
            ["RESE (recurso em sentido estrito)", "5 dias", "CPP art. 586"],
            [
              "Apelação",
              "5 dias (interposição) + 8 dias (razões)",
              "CPP art. 593",
            ],
            ["Agravo em execução", "5 dias", "LEP art. 197"],
            [
              "Habeas corpus",
              "Sem prazo — imprescritível",
              "CF art. 5º LXVIII",
            ],
            [
              "Prisão em flagrante → audiência de custódia",
              "24 horas",
              "CPP art. 310",
            ],
            ["Denúncia (réu preso)", "5 dias", "CPP art. 46"],
            ["Denúncia (réu solto)", "15 dias", "CPP art. 46"],
            [
              "Inquérito (réu preso — PF)",
              "10 dias + 15 dias prorrogação",
              "CPP art. 10",
            ],
          ]}
        />
      </Sec>

      <Sec title="Extinção da Punibilidade" icon={<Scale size={16} />}>
        <Tab
          headers={["Instituto", "Requisito principal", "Base"]}
          rows={[
            [
              "ANPP — Acordo de Não Persecução Penal",
              "Pena mín. < 4 anos, sem violência, confissão, primário",
              "CPP art. 28-A",
            ],
            [
              "Transação penal",
              "Pena máx. ≤ 2 anos, infração de menor potencial ofensivo",
              "Lei 9.099/95 art. 76",
            ],
            [
              "Sursis processual (suspensão condicional)",
              "Pena mín. ≤ 1 ano, não reincidente",
              "CPP art. 89 (Lei 9.099/95)",
            ],
            [
              "Reparação do dano (crimes ambientais)",
              "Antes do recebimento da denúncia",
              "Lei 9.605/98 art. 28 I",
            ],
            ["Morte do agente", "Certidão de óbito", "CP art. 107 I"],
            [
              "Anistia / graça / indulto",
              "Decreto presidencial",
              "CP art. 107 II",
            ],
            [
              "Retratação (crimes contra a honra)",
              "Antes da sentença",
              "CP art. 107 VI",
            ],
            ["Perempção", "Abandono da queixa-crime", "CPP art. 60"],
          ]}
        />
      </Sec>

      <Sec
        title="Tipos Penais Comuns e Qualificadoras"
        icon={<FileText size={16} />}
      >
        <Tab
          headers={["Crime", "Pena base", "Qualificadora relevante"]}
          rows={[
            [
              "Furto (CP art. 155)",
              "1 a 4 anos + multa",
              "Noturno, destruição obstáculo, fraude, destreza, veículo",
            ],
            [
              "Roubo (CP art. 157)",
              "4 a 10 anos + multa",
              "Arma de fogo, concurso, restrição liberdade",
            ],
            [
              "Estelionato (CP art. 171)",
              "1 a 5 anos + multa",
              "Internet (art. 171 §2º-A), prejuízo > 100K",
            ],
            [
              "Lesão corporal leve (CP art. 129)",
              "3 meses a 1 ano",
              "Violência doméstica (§9º): 3 meses a 3 anos",
            ],
            [
              "Lesão corporal grave (CP art. 129 §1º)",
              "1 a 5 anos",
              "Incapacidade > 30 dias, deformidade permanente",
            ],
            [
              "Homicídio simples (CP art. 121)",
              "6 a 20 anos",
              "Qualificado: motivo torpe, meio cruel, recurso",
            ],
            [
              "Ameaça (CP art. 147)",
              "1 a 6 meses + multa",
              "Violência doméstica (Lei 11.340): majoração",
            ],
            [
              "Tráfico (Lei 11.343/06 art. 33)",
              "5 a 15 anos + multa",
              "Redutor: primário, bons antecedentes, não integra org.",
            ],
          ]}
        />
      </Sec>

      <Sec title="Habeas Corpus" icon={<AlertTriangle size={16} />}>
        <Flow>{`CABIMENTO (CF art. 5º LXVIII + CPP art. 647):
  • Prisão ilegal (flagrante inválido, falta de mandado, excesso de prazo)
  • Constrangimento ilegal na liberdade de locomoção
  • Ameaça de prisão ilegal (HC preventivo)
  • Excesso de prazo na instrução criminal

COMPETÊNCIA:
  • TJMG: contra atos de juízes de 1º grau estaduais
  • STJ: contra atos de Tribunais Estaduais / TRFs (STJ art. 105 I c)
  • STF: contra atos do STJ e Tribunais Superiores

PEDIDOS TÍPICOS:
  1. Liberdade imediata (revogação de prisão preventiva)
  2. Relaxamento de flagrante ilegal
  3. Substituição de preventiva por cautelares alternativas (CPP art. 319)
  4. Trancamento da ação penal (falta de justa causa — CPP art. 648 I)
  5. Reconhecimento de prescrição / extinção da punibilidade

PRISÃO PREVENTIVA — REQUISITOS (CPP art. 312):
  • Garantia da ordem pública / econômica
  • Conveniência da instrução criminal
  • Assegurar aplicação da lei penal
  ⚠ VEDAÇÃO: não decretada apenas pela gravidade em abstrato do crime (Súm. 718 STF)`}</Flow>
      </Sec>

      <Sec title="Sursis e Penas Alternativas" icon={<Scale size={16} />}>
        <Tab
          headers={["Instituto", "Requisito", "Base"]}
          rows={[
            [
              "Sursis (suspensão da pena)",
              "Pena ≤ 2 anos, não reincidente, culpabilidade favorável",
              "CP art. 77",
            ],
            [
              "Sursis etário/humanitário",
              "Pena ≤ 4 anos, maior de 70 ou doença grave",
              "CP art. 77 §2º",
            ],
            [
              "PRD — penas restritivas de direito",
              "Pena ≤ 4 anos, sem violência, não reincidente específico",
              "CP art. 44",
            ],
            [
              "Prestação de serviços à comunidade",
              "Pena > 6 meses",
              "CP art. 46",
            ],
            ["Multa substitutiva", "Pena ≤ 1 ano", "CP art. 44 §2º"],
            [
              "Livramento condicional",
              "Cumprido 1/3 (primário) ou 1/2 (reincidente)",
              "CP art. 83",
            ],
            [
              "Progressão de regime",
              "Primário: 16%; reincidente não hediondo: 20%; hediondo: 40/60%",
              "LEP art. 112 (Lei 13.964/19)",
            ],
          ]}
        />
      </Sec>

      <Sec title="Crimes Especiais" icon={<FileText size={16} />}>
        <Tab
          headers={["Lei", "Crime / Instituto", "Destaque"]}
          rows={[
            [
              "Lei 11.340/06 (LMP)",
              "Violência doméstica",
              "Ação penal pública incondicionada; medidas protetivas imediatas",
            ],
            [
              "Lei 8.069/90 (ECA)",
              "Crimes contra criança/adolescente",
              "Prescrição não corre enquanto menor de 18",
            ],
            [
              "Lei 9.099/95",
              "Infrações de menor potencial ofensivo",
              "Pena máx. ≤ 2 anos; JECrim; transação penal",
            ],
            [
              "Lei 8.072/90",
              "Crimes hediondos",
              "Progressão com 40% (primário) ou 60% (reincidente)",
            ],
            [
              "Lei 12.850/13",
              "Organização criminosa",
              "Colaboração premiada; interceptação",
            ],
            [
              "Lei 13.869/19",
              "Abuso de autoridade",
              "Doloso específico; pena de 1 a 4 anos",
            ],
            [
              "Dec.-Lei 3.689/41 art. 28-A",
              "ANPP",
              "Pena mín. < 4 anos; confissão; sem violência",
            ],
          ]}
        />
      </Sec>

      <Sec title="Checklist Penal" icon={<ListChecks size={16} />}>
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
