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

const CHK_KEY = "guia_familia_chk";
const ITEMS = [
  "Identificar regime de bens e data do casamento",
  "Verificar bens comunicáveis e incomunicáveis (doações/heranças com cláusula)",
  "Calcular alimentos pelo binômio necessidade/possibilidade",
  "Verificar se há guarda compartilhada ou unilateral a definir",
  "Averiguar se há violência doméstica — pedir medidas protetivas urgentes",
  "Calcular quota-parte na herança (meação + herança)",
  "Verificar testamento no cartório (CENSEC)",
  "Definir via: judicial ou extrajudicial (cartório) para divórcio/inventário",
  "Verificar prazo: inventário deve ser aberto em 60 dias do óbito",
  "Verificar alienação parental — atos configuradores (Lei 12.318/10)",
];

export default function GuiaFamilia() {
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
      <h2 className="text-xl font-bold text-rose-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito de Família
      </h2>

      <Sec title="Base Legal + Prazos" icon={<Scale size={16} />} open>
        <Tab
          headers={["Norma", "Tema"]}
          rows={[
            [
              "CC arts. 1.511-1.783-A",
              "Família, casamento, união estável, filiação, alimentos, tutela, curatela",
            ],
            ["Lei 11.340/06 (LMP)", "Lei Maria da Penha — violência doméstica"],
            ["Lei 12.318/10", "Alienação parental"],
            [
              "Lei 8.069/90 (ECA)",
              "Criança e adolescente — guarda, adoção, proteção",
            ],
            ["Lei 11.441/07", "Divórcio e inventário extrajudicial (cartório)"],
            ["Res. CNJ 35/2007", "Procedimento cartório — divórcio/inventário"],
            ["CPC arts. 693-699", "Ações de família — mediação obrigatória"],
            ["CPC art. 528", "Prisão civil por alimentos — 1 a 3 meses"],
          ]}
        />
        <Tab
          headers={["Prazo", "Ato", "Base"]}
          rows={[
            [
              "Imediato",
              "Medidas protetivas LMP (audiência 48h)",
              "LMP art. 18",
            ],
            [
              "2 anos de casados (qualquer regime)",
              "Divórcio direto — sem prazo de separação",
              "CF art. 226 §6º (EC 66/10)",
            ],
            ["60 dias do óbito", "Abertura do inventário", "CPC art. 611"],
            [
              "12 meses da cessação de convivência",
              "União estável convertida em casamento",
              "CC art. 1.726",
            ],
            [
              "2 anos",
              "Prescrição para anular casamento (vício)",
              "CC art. 1.560",
            ],
            [
              "Imprescritível",
              "Investigação de paternidade",
              "CF art. 227 §6º + STF",
            ],
          ]}
        />
      </Sec>

      <Sec title="Regimes de Bens" icon={<FileText size={16} />}>
        <Tab
          headers={[
            "Regime",
            "O que se comunica",
            "O que não se comunica",
            "Base",
          ]}
          rows={[
            [
              "Comunhão parcial (padrão)",
              "Bens adquiridos na constância do casamento",
              "Bens anteriores, heranças/doações sem comunicação, bens pessoais (CC art. 1.659)",
              "CC arts. 1.658-1.666",
            ],
            [
              "Comunhão universal",
              "Todos os bens presentes e futuros",
              "Bens pessoalíssimos, doações com cláusula de incomunicabilidade",
              "CC arts. 1.667-1.671",
            ],
            [
              "Separação obrigatória",
              "Nada se comunica por lei",
              "Tudo (mas Súm. 377 STF: aquestos com esforço comum)",
              "CC art. 1.641",
            ],
            [
              "Separação voluntária",
              "Nada se comunica (pacto)",
              "Tudo (sem exceção por STF/STJ — pós-EC 66)",
              "CC arts. 1.687-1.688",
            ],
            [
              "Participação final nos aquestos",
              "Apenas os aquestos na dissolução",
              "Bens anteriores e pessoais",
              "CC arts. 1.672-1.686",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Súmula 377 STF:</strong> no regime de separação obrigatória,
          comunicam-se os bens adquiridos na constância do casamento com esforço
          comum dos cônjuges.
        </p>
      </Sec>

      <Sec title="Divórcio" icon={<Scale size={16} />}>
        <Flow>{`VIA EXTRAJUDICIAL (cartório — Lei 11.441/07):
  Requisitos: consensual + sem filhos menores/incapazes + advogado (pode ser um para ambos)
  Documentos: RG, CPF, certidão de casamento, comprovante endereço, matrícula imóveis
  Prazo: escritura lavrada em 1 a 5 dias úteis
  Custo: tabela cartorária estadual

VIA JUDICIAL (Vara de Família):
  Consensual com filhos: petição conjunta + MP (menores) → sentença homologatória
  Litigioso: citação → contestação → mediação obrigatória (CPC art. 694) → instrução → sentença
  Prazos: CPC arts. 335 e 694 (audiência de mediação preferencial)

PARTILHA DE BENS:
  → Regra da comunicação por regime (ver tabela acima)
  → Bens ocultados pelo cônjuge: sobrepartilha + litigância de má-fé
  → Doações feitas durante casamento: anuláveis se prejudicarem partilha

NOME:
  → Cônjuge pode optar por manter o nome de casado (Lei 6.015/73 art. 102)
  → Decisão registrada na escritura / sentença`}</Flow>
      </Sec>

      <Sec title="Alimentos" icon={<Clock size={16} />}>
        <Tab
          headers={["Aspecto", "Regra", "Base"]}
          rows={[
            [
              "Binômio legal",
              "Necessidade do credor + possibilidade do devedor",
              "CC art. 1.694 §1º",
            ],
            [
              "Alimentos provisórios (tutela urgente)",
              "Fixados na inicial da ação de alimentos",
              "Lei 5.478/68 art. 4º",
            ],
            [
              "Alimentos provisionais",
              "Fixados em ação cautelar antecedente",
              "CPC art. 301",
            ],
            [
              "Revisão de alimentos",
              "Mudança de fortuna do credor ou devedor",
              "CC art. 1.699",
            ],
            [
              "Exoneração — filho",
              "Maioridade civil (18 anos) não é automática — cessa com emancipação profissional",
              "STJ Súm. 358",
            ],
            [
              "Alimentos para ex-cônjuge",
              "Transitório ou permanente conforme necessidade/histórico",
              "CC art. 1.694",
            ],
            [
              "Prescrição da execução de alimentos",
              "2 anos (prestações vencidas)",
              "CC art. 206 §2º",
            ],
            [
              "Índice de reajuste",
              "INPC ou índice fixado na sentença (sem ser inferior ao INPC)",
              "Lei 6.899/81 art. 1º §1º",
            ],
          ]}
        />
      </Sec>

      <Sec title="Execução de Alimentos" icon={<AlertTriangle size={16} />}>
        <Flow>{`RITO DA PRISÃO CIVIL (CPC art. 528):
  → Intimação do devedor para pagar em 3 dias
  → Não pago: decreto de prisão de 1 a 3 meses
  → Apenas últimas 3 parcelas + custas (prestações mais antigas → rito patrimonial)
  → Prisão em regime fechado (vedado regime aberto)
  ⚠ STF: inconstitucional prender por dívida; mas ALIMENTOS é exceção constitucional (CF art. 5º LXVII)

RITO PATRIMONIAL (CPC art. 528 §8º):
  → Penhora SISBAJUD, RENAJUD, CNIB
  → Desconto direto em folha (CPC art. 529)
  → Conta corrente, aplicações financeiras
  → Imóvel (não é bem de família se há alimentos — Lei 8.009/90 art. 3º III)

DESCONTO EM FOLHA (CPC art. 529):
  → Empregador notificado para descontar
  → Empregador responde pela falta de desconto
  → Inclui pensionista do INSS (via INSS)

DEFESA DO EXECUTADO:
  → Pagamento (comprovante bancário)
  → Novação (novo acordo judicial)
  → Compensação vedada (Súm. 309 STJ: apenas 3 últimas prestações para prisão)`}</Flow>
      </Sec>

      <Sec title="Guarda e Violência Doméstica" icon={<Scale size={16} />}>
        <Tab
          headers={["Instituto", "Regra", "Base"]}
          rows={[
            [
              "Guarda compartilhada",
              "Regra geral — mesmo sem acordo entre os pais",
              "CC art. 1.584 §2º",
            ],
            [
              "Guarda unilateral",
              "Exceção: violência / incapacidade de um dos genitores",
              "CC art. 1.584 §2º",
            ],
            [
              "Alienação parental",
              "Inversão da guarda + acompanhamento psicológico",
              "Lei 12.318/10 art. 6º",
            ],
            [
              "Medidas protetivas LMP (prazo)",
              "Audiência em 48h; vigência indeterminada enquanto necessário",
              "LMP arts. 18-22",
            ],
            [
              "Distância mínima LMP",
              "Geralmente 300 a 500m — fixada pelo juiz",
              "LMP art. 22 III",
            ],
            [
              "Suspensão de visita com violência",
              "Possível durante medida protetiva",
              "LMP art. 22 IV",
            ],
            [
              "Afastamento do lar pelo agressor",
              "Determinado de ofício ou a requerimento",
              "LMP art. 22 II",
            ],
          ]}
        />
      </Sec>

      <Sec title="Inventário + Checklist" icon={<ListChecks size={16} />}>
        <Flow>{`INVENTÁRIO JUDICIAL (CPC arts. 610-673):
  → Administrador provisório: cônjuge sobrevivente ou herdeiro (CPC art. 613)
  → Prazo de abertura: 60 dias do óbito
  → Prazo para primeiras declarações: 20 dias da nomeação do inventariante
  → Habilitação de herdeiros → avaliação de bens → imposto ITCMD → partilha

INVENTÁRIO EXTRAJUDICIAL (Lei 11.441/07 + Res. CNJ 35/07):
  Requisitos: consensual + sem incapazes + sem testamento (salvo homologado)
  → Escritura pública no cartório de notas
  → Advogado obrigatório (pode ser um para todos)
  → ITCMD deve ser pago antes da escritura

ITCMD EM MG (Lei Estadual 14.941/03):
  → Alíquota: 5% sobre o valor dos bens (mercado)
  → Imunidade: herança até 10.800 UFEMG (verificar tabela anual)
  → Prazo de pagamento: antes do registro da partilha

SOBREPARTILHA (CC art. 2.021):
  → Bens descobertos após a partilha
  → Herdeiro que ocultou bens: perde o direito à quota do bem + pena de sonegação`}</Flow>
        <div className="mt-3 space-y-2">
          <p className="font-semibold text-sm text-slate-700">
            Checklist de Família
          </p>
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
