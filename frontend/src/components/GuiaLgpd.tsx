// ── src/components/GuiaLgpd.tsx ──────────────────────────────────────────────
// Guia operacional de adequação à LGPD (Lei 13.709/18), padrão dos demais
// Guia*.tsx: seções colapsáveis, tabelas de prazos/bases legais, fluxos e
// checklist com persistência local. Cita apenas artigos corretos da LGPD e
// aponta para o ROPA (âncora #lgpd-registros) no bloco "No sistema".
import React, { useState, useEffect } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  AlertTriangle,
  ShieldCheck,
  ArrowRight,
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

const CHK_KEY = "guia_lgpd_chk";
const ITEMS = [
  "Mapear todas as operações de tratamento e registrá-las no ROPA (art. 37)",
  "Definir a base legal de cada tratamento (art. 7º / art. 11 para sensíveis)",
  "Nomear o encarregado (DPO) e publicar o canal de contato (art. 41)",
  "Elaborar RIPD para tratamentos de alto risco (art. 38)",
  "Publicar política de privacidade clara e acessível (art. 9º)",
  "Estruturar o atendimento aos direitos do titular em até 15 dias (art. 18/19)",
  "Definir plano de resposta a incidentes com comunicação à ANPD (art. 48)",
  "Mapear e formalizar operadores e suboperadores por contrato (art. 39)",
  "Verificar salvaguardas para transferência internacional (art. 33)",
  "Definir prazos de retenção e eliminação após o fim do tratamento (art. 15/16)",
];

export default function GuiaLgpd() {
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
        <BookOpen size={20} /> Guia Operacional — Adequação LGPD
      </h2>

      <Sec title="Bases Legais do Tratamento" icon={<Scale size={16} />} open>
        <Tab
          headers={["Base legal", "Quando se aplica", "Fundamento"]}
          rows={[
            ["Consentimento", "Manifestação livre, informada e inequívoca", "art. 7º I"],
            ["Obrigação legal/regulatória", "Cumprimento de dever legal do controlador", "art. 7º II"],
            ["Execução de contrato", "Necessário para contrato com o titular", "art. 7º V"],
            ["Exercício de direitos", "Processo judicial, administrativo ou arbitral", "art. 7º VI"],
            ["Legítimo interesse", "Interesse do controlador + teste de proporcionalidade", "art. 7º IX / art. 10"],
            ["Proteção do crédito", "Análise e proteção ao crédito", "art. 7º X"],
            ["Dados sensíveis", "Hipóteses próprias e mais restritas", "art. 11"],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Dados sensíveis</strong> (origem racial/étnica, convicção
          religiosa, opinião política, saúde, vida sexual, genético ou
          biométrico) só podem ser tratados nas hipóteses do <strong>art. 11</strong>,
          mais estritas que as do art. 7º.
        </p>
      </Sec>

      <Sec title="Prazos-Chave" icon={<Clock size={16} />}>
        <Tab
          headers={["Obrigação", "Prazo", "Fundamento"]}
          rows={[
            ["Resposta ao titular (confirmação/acesso — forma simplificada)", "Imediata", "art. 19 I"],
            ["Resposta ao titular (declaração completa)", "15 dias", "art. 19 II"],
            ["Comunicação de incidente à ANPD e ao titular", "Prazo razoável — 3 dias úteis (Reg. ANPD)", "art. 48 §1º"],
            ["Eliminação após término do tratamento", "Ao fim da finalidade, salvo guarda legal", "art. 15 / art. 16"],
            ["Revogação do consentimento", "A qualquer tempo, mediante pedido", "art. 8º §5º"],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          A comunicação de incidente deve descrever os dados afetados, os
          titulares envolvidos, as medidas adotadas e os riscos — art. 48 §1º.
        </p>
      </Sec>

      <Sec title="Direitos do Titular" icon={<ShieldCheck size={16} />}>
        <Flow>{`DIREITOS DO TITULAR (art. 18):
  I    Confirmação da existência de tratamento
  II   Acesso aos dados
  III  Correção de dados incompletos/inexatos
  IV   Anonimização, bloqueio ou eliminação de dados desnecessários
  V    Portabilidade a outro fornecedor
  VI   Eliminação dos dados tratados com consentimento
  VII  Informação sobre compartilhamento
  VIII Informação sobre a possibilidade de não consentir
  IX   Revogação do consentimento

ATENDIMENTO (art. 19):
  → Confirmação/acesso: em forma simplificada, imediatamente
  → Declaração clara e completa: em até 15 dias
  → Gratuito ao titular (art. 18 §5º)

REVISÃO DE DECISÕES AUTOMATIZADAS (art. 20):
  → Titular pode solicitar revisão de decisões tomadas só por tratamento
    automatizado que afetem seus interesses`}</Flow>
      </Sec>

      <Sec title="Governança: ROPA, RIPD e DPO" icon={<Scale size={16} />}>
        <Tab
          headers={["Instrumento", "O que é", "Fundamento"]}
          rows={[
            ["ROPA", "Registro das operações de tratamento de dados", "art. 37"],
            ["RIPD", "Relatório de impacto à proteção de dados pessoais", "art. 5º XVII / art. 38"],
            ["Encarregado (DPO)", "Canal entre controlador, titulares e ANPD", "art. 41"],
            ["Operador", "Trata dados em nome do controlador (por contrato)", "art. 39"],
            ["Segurança", "Medidas técnicas e administrativas de proteção", "art. 46"],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          A ANPD pode <strong>determinar</strong> a elaboração do RIPD (art. 38),
          mas ele é boa prática sempre que o tratamento for de <strong>alto
          risco</strong> — dados sensíveis em escala, transferência internacional
          ou decisões automatizadas relevantes.
        </p>
      </Sec>

      <Sec title="Gestão de Incidentes" icon={<AlertTriangle size={16} />}>
        <Flow>{`RESPOSTA A INCIDENTE DE SEGURANÇA (art. 48):
  1. Detectar e conter o incidente
  2. Avaliar risco/dano relevante aos titulares
  3. Comunicar à ANPD e aos titulares em prazo razoável
     → Regulamento ANPD: 3 dias úteis da ciência
  4. Registrar: dados e titulares afetados, medidas técnicas,
     riscos e medidas de mitigação (art. 48 §1º)
  5. ANPD pode determinar ampla divulgação e medidas
     para reverter/mitigar os efeitos (art. 48 §2º)

MEDIDAS PREVENTIVAS (art. 46-49):
  • Segurança desde a concepção (privacy by design)
  • Controle de acesso (RBAC), criptografia, logs
  • Contratos com operadores e suboperadores (art. 39)`}</Flow>
      </Sec>

      <Sec title="No sistema" icon={<ArrowRight size={16} />}>
        <p className="text-sm text-slate-700">
          Use o{" "}
          <a
            href="#lgpd-registros"
            className="text-primary-700 font-semibold underline underline-offset-2"
          >
            Registro de Operações de Tratamento (ROPA)
          </a>{" "}
          acima para mapear cada tratamento por cliente, definir a base legal e
          registrar as categorias de dados e de titulares (art. 37). A partir do
          registro, o botão <strong>Gerar RIPD (Visual Law)</strong> produz o
          relatório de impacto em PDF (art. 38).
        </p>
        <ul className="list-disc list-inside text-sm text-slate-600 space-y-1 mt-2">
          <li>Um registro por operação — mapeamento → ROPA.</li>
          <li>
            O risco (baixo/médio/alto) é calculado pelo sistema a partir dos
            metadados (sensíveis, transferência internacional, base legal).
          </li>
          <li>
            O registro guarda apenas <strong>metadados</strong> (categorias),
            nunca dados pessoais de titulares reais.
          </li>
        </ul>
      </Sec>

      <Sec title="Checklist de Adequação" icon={<ListChecks size={16} />}>
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
