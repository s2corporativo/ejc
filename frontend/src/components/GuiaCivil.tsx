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
    <div className="border border-slate-200 rounded-lg overflow-hidden">
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
                className="border border-slate-300 px-3 py-2 text-left font-semibold"
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
                <td key={j} className="border border-slate-300 px-3 py-2">
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

const CHK_KEY = "guia_civil_chk";
const ITEMS = [
  "Verificar prescrição antes de propor a ação",
  "Identificar rito processual (comum / JEC / sumário)",
  "Calcular valor da causa corretamente (CPC art. 292)",
  "Verificar necessidade de tutela de urgência antecedente",
  "Conferir competência territorial e funcional",
  "Juntar documentos indispensáveis na inicial (CPC art. 320)",
  "Verificar legitimidade ativa e passiva",
  "Analisar possibilidade de mediação/conciliação prévia",
  "Checar prazo de contestação após citação",
  "Verificar possibilidade de reconvenção",
];

export default function GuiaCivil() {
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
      <h2 className="text-xl font-bold text-blue-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito Civil
      </h2>

      <Sec title="Base Legal + Prescrição" icon={<Scale size={16} />} open>
        <Tab
          headers={["Pretensão", "Prazo", "Base"]}
          rows={[
            [
              "Reparação civil (responsabilidade extracontratual)",
              "3 anos",
              "CC art. 206 §3º V",
            ],
            ["Cobrança de aluguéis", "3 anos", "CC art. 206 §3º I"],
            ["Enriquecimento sem causa", "3 anos", "CC art. 206 §3º IV"],
            ["Seguro de vida / acidente", "1 ano", "CC art. 206 §1º II"],
            ["Pretensão pessoal (regra geral)", "10 anos", "CC art. 205"],
            ["Pretensão real (regra geral)", "10 anos", "CC art. 205"],
            [
              "Vício do produto — durável",
              "90 dias decadência",
              "CDC art. 26 II",
            ],
            [
              "Vício do produto — não durável",
              "30 dias decadência",
              "CDC art. 26 I",
            ],
            [
              "Fato do produto/serviço (acidente)",
              "5 anos prescrição",
              "CDC art. 27",
            ],
            ["Petição de herança", "10 anos", "CC art. 205"],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Causas suspensivas:</strong> CC arts. 197-201 — entre
          cônjuges, ascendentes/descendentes, absolutamente incapazes.{" "}
          <strong>Causas interruptivas:</strong> CC art. 202 — despacho que
          ordena citação, protesto judicial, reconhecimento do devedor.
        </p>
      </Sec>

      <Sec title="Prazos CPC" icon={<Clock size={16} />}>
        <Tab
          headers={["Ato", "Prazo", "Base"]}
          rows={[
            ["Contestação (rito comum)", "15 dias úteis", "CPC art. 335"],
            [
              "Contestação (Fazenda Pública / MP / Defensoria)",
              "30 dias úteis",
              "CPC art. 183",
            ],
            ["Reconvenção", "Junto com a contestação", "CPC art. 343"],
            ["Embargos de declaração", "5 dias úteis", "CPC art. 1.023"],
            ["Apelação", "15 dias úteis", "CPC art. 1.003 §5º"],
            ["Agravo de instrumento", "15 dias úteis", "CPC art. 1.003 §5º"],
            [
              "Recurso especial / extraordinário",
              "15 dias úteis",
              "CPC art. 1.003 §5º",
            ],
            [
              "Cumprimento de sentença (pagamento voluntário)",
              "15 dias",
              "CPC art. 523",
            ],
            ["Embargos à execução", "15 dias", "CPC art. 915"],
            ["Impugnação ao cumprimento", "15 dias", "CPC art. 525"],
          ]}
        />
      </Sec>

      <Sec title="Responsabilidade Civil" icon={<Scale size={16} />}>
        <Flow>{`ELEMENTOS DA RESPONSABILIDADE SUBJETIVA (CC art. 186):
  1. Conduta (ação ou omissão)
  2. Culpa (negligência, imprudência, imperícia) ou Dolo
  3. Dano (material, moral, estético, existencial)
  4. Nexo causal

RESPONSABILIDADE OBJETIVA (CC art. 927 parágrafo único):
  • Atividade de risco por natureza
  • Fatos: basta conduta + dano + nexo (sem prova de culpa)
  • Ex: empresas de transporte, hospitais, fornecedores (CDC art. 12)

EXCLUDENTES DE RESPONSABILIDADE:
  • Caso fortuito / força maior (CC art. 393)
  • Culpa exclusiva da vítima
  • Fato de terceiro (verificar se não é causa concorrente)
  • Fato inevitável imprevisível

DANO MORAL — PARÂMETROS STJ:
  • Negativação indevida: 5 a 15 SMs
  • Extravio de bagagem: 3 a 10 SMs
  • Acidente de consumo: 10 a 50 SMs
  • Morte de familiar: 100 a 500 SMs
  • Dupla função: compensatória + pedagógica (Súm. 385 STJ)`}</Flow>
      </Sec>

      <Sec
        title="Contratos — Resolução e Revisão"
        icon={<FileText size={16} />}
      >
        <Tab
          headers={["Instituto", "Requisito", "Base"]}
          rows={[
            [
              "Resolução por inadimplemento",
              "Mora ou inadimplemento absoluto",
              "CC art. 475",
            ],
            [
              "Exceção de contrato não cumprido",
              "Bilateralidade + não cumprimento",
              "CC art. 476",
            ],
            [
              "Revisão por onerosidade excessiva",
              "Fato imprevisível + desequilíbrio grave",
              "CC art. 478",
            ],
            [
              "Lesão",
              "Necessidade/inexperiência + desproporção",
              "CC art. 157",
            ],
            [
              "Estado de perigo",
              "Necessidade de salvar pessoa + usura",
              "CC art. 156",
            ],
            [
              "Vício de consentimento — erro",
              "Erro essencial e escusável",
              "CC art. 138",
            ],
            [
              "Vício de consentimento — dolo",
              "Induzimento malicioso + decisivo",
              "CC art. 145",
            ],
            [
              "Simulação (nulidade)",
              "Negócio aparente ≠ negócio real",
              "CC art. 167",
            ],
            [
              "Fraude contra credores",
              "Consilium fraudis + eventus damni",
              "CC art. 158",
            ],
          ]}
        />
      </Sec>

      <Sec title="Tutelas de Urgência" icon={<AlertTriangle size={16} />}>
        <Flow>{`TUTELA CAUTELAR ANTECEDENTE (CPC art. 305):
  → Petição descreve o perigo e a pretensão principal
  → Efetivada: autor tem 30 dias para propor ação principal
  → Requisitos: fumus boni iuris + periculum in mora

TUTELA ANTECIPADA ANTECEDENTE (CPC art. 303):
  → Formulada antes da ação principal
  → Após concessão: autor adita pedido principal em 15 dias
  → Possível estabilização se réu não recorrer (CPC art. 304)

TUTELA CAUTELAR INCIDENTAL (CPC art. 300):
  → Formulada no curso do processo
  → Requisitos: fumus + periculum + reversibilidade
  → Audiência prévia: regra (exceto urgência — art. 300 §2º)

BUSCA E APREENSÃO CÍVEL:
  → CC art. 1.228 — reintegração de posse / reivindicatória
  → CPC arts. 561-566 — reintegração e manutenção de posse
  → Prazo para manutenção: dentro de 1 ano e dia → rito especial
  → Após 1 ano e dia → rito comum

ASTREINTES (multa diária):
  → CPC art. 537 — fixadas de ofício ou a requerimento
  → Podem ser modificadas a qualquer tempo pelo juiz`}</Flow>
      </Sec>

      <Sec title="Execução Civil" icon={<FileText size={16} />}>
        <Flow>{`CUMPRIMENTO DE SENTENÇA — OBRIGAÇÃO DE PAGAR (CPC art. 523):
  1. Intimação do devedor → 15 dias para pagar
  2. Não pago: multa de 10% + honorários de 10%
  3. Penhora online (SISBAJUD) ou sobre bens
  4. Impugnação ao cumprimento: 15 dias após penhora

EXECUÇÃO DE TÍTULO EXTRAJUDICIAL (CPC art. 824):
  → Citação para pagar em 3 dias
  → Penhora imediata se não pagar
  → Embargos à execução: 15 dias da intimação da penhora

PENHORA — ORDEM PREFERENCIAL (CPC art. 835):
  1. Dinheiro e aplicações financeiras
  2. Títulos da dívida pública
  3. Títulos e valores mobiliários
  4. Veículos terrestres
  5. Bens imóveis
  6. Bens móveis em geral

IMPENHORÁVEIS (CPC art. 833):
  • Salário e proventos (até 50 SMs — STJ: flexibilização para dívidas alimentares)
  • Bem de família (Lei 8.009/90)
  • Equipamentos de trabalho profissional liberal
  • FGTS (salvo exceções legais)`}</Flow>
      </Sec>

      <Sec title="Checklist Cível" icon={<ListChecks size={16} />}>
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
