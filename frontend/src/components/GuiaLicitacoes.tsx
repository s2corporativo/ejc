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

const CHK_KEY = "guia_licitacoes_chk";
const ITEMS = [
  "Ler o edital completo na publicação do PNCP / Compras.gov",
  "Verificar modalidade e regime de execução",
  "Conferir prazos: impugnação (3 dias antes), recurso (3 dias após resultado)",
  "Preparar documentação de habilitação: CND Federal, CND Estadual, CND Municipal, FGTS, CNDT",
  "Verificar qualificação técnica: atestados com quantitativos compatíveis",
  "Verificar qualificação econômica: balanço patrimonial e índices contábeis",
  "Elaborar proposta com BDI correto e impostos embutidos",
  "Verificar benefícios ME/EPP: empate ficto e regularidade fiscal",
  "Guardar comprovante de entrega e número do protocolo",
  "Monitorar publicação da ata de julgamento para prazo recursal",
  "Verificar se há subcritério de desempate (local, ME/EPP)",
  "Em execução: monitorar reajustes e solicitações de equilíbrio econômico",
];

export default function GuiaLicitacoes() {
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
      <h2 className="text-xl font-bold text-slate-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Licitações e Contratos
        Públicos
      </h2>

      <Sec title="Base Legal" icon={<Scale size={16} />} open>
        <Tab
          headers={["Norma", "Tema"]}
          rows={[
            [
              "Lei 14.133/2021 (NLLC)",
              "Nova Lei de Licitações e Contratos — vigência plena desde 30/12/2023",
            ],
            [
              "Lei 8.666/93",
              "Lei anterior — contratos assinados antes de 30/12/2023 ainda regidos por ela",
            ],
            [
              "Lei 10.520/02",
              "Pregão — modalidade mantida expressamente pela NLLC art. 194",
            ],
            [
              "LC 123/06 arts. 42-49",
              "Benefícios ME/EPP — empate ficto, regularidade fiscal, subcontratação",
            ],
            [
              "Lei 12.846/13 (LAC)",
              "Anticorrupção — sanções a empresas em licitações e contratos",
            ],
            [
              "Lei 13.303/16",
              "Licitações em estatais (empresas públicas e sociedades de economia mista)",
            ],
            ["Dec. 11.462/23", "Regulamenta a NLLC — catálogo, SICAF, PNCP"],
            ["Dec. 7.174/10", "TI — prioridade a bens e serviços nacionais"],
            ["CF art. 37 XXI", "Princípio constitucional da licitação"],
          ]}
        />
      </Sec>

      <Sec title="Modalidades — NLLC" icon={<FileText size={16} />}>
        <Tab
          headers={["Modalidade", "Critério de uso", "Prazo mínimo publicação"]}
          rows={[
            [
              "Pregão",
              "Bens e serviços comuns (padronizáveis)",
              "8 dias úteis",
            ],
            [
              "Concorrência",
              "Obras, serviços especiais, concessões",
              "25 dias úteis (técnica e preço: 35)",
            ],
            [
              "Concurso",
              "Trabalho técnico, científico ou artístico",
              "25 dias úteis",
            ],
            [
              "Leilão",
              "Alienação de bens móveis/imóveis inservíveis",
              "15 dias úteis",
            ],
            [
              "Diálogo competitivo",
              "Objeto inovador / tecnicamente complexo",
              "25 dias úteis",
            ],
            [
              "Dispensa eletrônica",
              "Até R$ 57.507 (obras) / R$ 115.014 (outros) — 2024",
              "3 dias úteis",
            ],
            [
              "Inexigibilidade",
              "Inviabilidade de competição (exclusividade, notória especialização)",
              "Sem prazo mínimo",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Pregão eletrônico obrigatório</strong> para bens e serviços
          comuns (NLLC art. 17 §2º). Presencial: exceção justificada no
          processo.
        </p>
      </Sec>

      <Sec title="Prazos Críticos" icon={<Clock size={16} />}>
        <Tab
          headers={["Ato", "Prazo", "Base"]}
          rows={[
            [
              "Impugnação ao edital",
              "Até 3 dias úteis antes da abertura",
              "NLLC art. 164",
            ],
            [
              "Resposta à impugnação pelo órgão",
              "3 dias úteis",
              "NLLC art. 164 §1º",
            ],
            [
              "Pedido de esclarecimento",
              "Até 3 dias úteis antes da abertura",
              "NLLC art. 164",
            ],
            [
              "Recurso após julgamento (pregão)",
              "3 dias úteis da sessão de julgamento",
              "NLLC art. 165 §1º I",
            ],
            [
              "Recurso após habilitação (concorrência)",
              "3 dias úteis da publicação do resultado",
              "NLLC art. 165 §1º I",
            ],
            [
              "Contrarrazões ao recurso",
              "3 dias úteis após a interposição",
              "NLLC art. 165 §1º II",
            ],
            [
              "Assinatura do contrato após homologação",
              "Até 60 dias (prorrogável)",
              "NLLC art. 90",
            ],
            [
              "Prazo máximo do contrato de serviços",
              "5 anos (prorrogável até 10 anos especiais)",
              "NLLC art. 106",
            ],
            [
              "Reajuste anual de contrato",
              "12 meses do orçamento ou da data do índice",
              "NLLC art. 92 §3º",
            ],
          ]}
        />
      </Sec>

      <Sec title="Habilitação" icon={<FileText size={16} />}>
        <Flow>{`DOCUMENTOS DE HABILITAÇÃO (NLLC arts. 62-70):

1. JURÍDICA:
   → Ato constitutivo (contrato social / estatuto atualizado)
   → Ata de eleição dos administradores
   → CNPJ ativo

2. REGULARIDADE FISCAL E TRABALHISTA:
   → CND Federal (Receita Federal + PGFN) — certidoesnegativas.receita.fazenda.gov.br
   → CND Estadual (SEFAZ do estado sede)
   → CND Municipal (prefeitura da sede)
   → Certidão de Regularidade FGTS (CEF) — consulta-crf.caixa.gov.br
   → CNDT — Certidão Negativa de Débitos Trabalhistas (TST) — cndt.tst.jus.br

3. QUALIFICAÇÃO TÉCNICA:
   → Atestado de capacidade técnica emitido por contratante público ou privado
   → Registro no CREA/CAU/CFT conforme atividade
   → Acervo técnico (obras: CAT no CREA)

4. QUALIFICAÇÃO ECONÔMICO-FINANCEIRA:
   → Balanço patrimonial (último exercício assinado por contador com CRC)
   → Índices mínimos: LC ≥ 1,00 / LG ≥ 1,00 / SG ≥ 1,00
   → Capital social ou patrimônio líquido mínimo (geralmente 10% do valor estimado)

BENEFÍCIOS ME/EPP (LC 123/06):
   → Regularidade fiscal: prazo de 5 dias para regularizar após declaração de vencedor
   → Empate ficto: proposta até 10% acima do menor preço
   → Subcontratação obrigatória de ME/EPP em até 30% do contrato`}</Flow>
      </Sec>

      <Sec title="Impugnação ao Edital" icon={<AlertTriangle size={16} />}>
        <Flow>{`FUNDAMENTOS DE IMPUGNAÇÃO MAIS COMUNS:

A) CLÁUSULAS RESTRITIVAS DE COMPETIÇÃO (CF art. 37 XXI):
   • Exigência de marca específica sem justificativa técnica
   • Atestado de capacidade com quantitativos acima do necessário
   • Prazo de experiência mínima sem correlação com o objeto
   • Local de execução que favorece empresa específica
   • Exigência de visita técnica com data e horário únicos

B) AUSÊNCIA DE CRITÉRIOS OBJETIVOS:
   • Ausência de planilha de custos com composição de BDI
   • Critério de julgamento sem pontuação objetiva (técnica)
   • Ausência de Estudo Técnico Preliminar (NLLC art. 18)
   • Ausência de Termo de Referência / Projeto Básico adequado

C) VÍCIOS FORMAIS:
   • Divergência entre edital e anexos
   • Prazo de publicação inferior ao mínimo legal
   • Ausência de publicação no PNCP

PETIÇÃO DE IMPUGNAÇÃO:
  → Endereçada ao pregoeiro / comissão de licitação
  → Protocolo: eletronicamente no sistema (Compras.gov / PNCP)
  → Guardar número de protocolo e confirmação de recebimento`}</Flow>
      </Sec>

      <Sec title="Recursos e Representações" icon={<Scale size={16} />}>
        <Flow>{`RECURSOS ADMINISTRATIVOS (NLLC art. 165):
  → Interposição: 3 dias úteis após a sessão de julgamento
  → Manifestação de intenção no próprio ato (pregão eletrônico)
  → Sem manifestação de intenção: preclusão do recurso
  → Contrarrazões: 3 dias úteis após a intimação dos demais licitantes
  → Decisão: antes da adjudicação (pregoeiro) ou da homologação (autoridade)

EFEITO SUSPENSIVO:
  → Recurso em pregão: automático (NLLC art. 165 §4º)
  → Recurso em concorrência: não automático (requer pedido fundamentado)

REPRESENTAÇÃO AO TCU / TCE:
  → Qualquer licitante ou interessado pode representar
  → TCU: contratos federais (acima de R$ 1,5M em obras)
  → TCE: contratos estaduais
  → Portal TCU: portal.tcu.gov.br/licitacoes

MANDADO DE SEGURANÇA:
  → Contra ato da autoridade homologadora
  → Prazo: 120 dias do ato coator
  → Liminar: fumus + periculum — suspende a assinatura do contrato`}</Flow>
      </Sec>

      <Sec title="Sanções — NLLC art. 156" icon={<AlertTriangle size={16} />}>
        <Tab
          headers={["Sanção", "Causa", "Prazo"]}
          rows={[
            [
              "Advertência",
              "Infração formal leve + cumprimento posterior",
              "Sem prazo específico",
            ],
            [
              "Multa",
              "Inadimplemento contratual (percentual do contrato)",
              "Imediata; recurso em 15 dias",
            ],
            [
              "Impedimento de licitar (SICAF)",
              "Não assinar contrato, recusar entrega, má execução grave",
              "Até 3 anos",
            ],
            [
              "Declaração de inidoneidade",
              "Fraude, dolo, improbidade, crimes contra a Adm.",
              "Mínimo 3 anos + prazo da pena",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Recurso contra sanção:</strong> 15 dias úteis após a intimação
          (NLLC art. 157). <strong>Proporcionalidade obrigatória</strong> — a
          sanção deve ser proporcional à gravidade da conduta (NLLC art. 156
          §1º).
        </p>
      </Sec>

      <Sec title="Gestão Contratual" icon={<FileText size={16} />}>
        <Flow>{`EQUILÍBRIO ECONÔMICO-FINANCEIRO (NLLC art. 92):
  → Direito do contratado quando houver fato superveniente imprevisível
  → Modalidades: reajuste (índice contratual anual) ou revisão/reequilíbrio (fato imprevisto)
  → Reajuste anual: automático após 12 meses (cláusula contratual obrigatória)
  → Revisão: requer demonstração do desequilíbrio com planilha de custos

ADITIVOS CONTRATUAIS (NLLC art. 125):
  → Quantitativos: até 25% (obras/serviços) ou 50% (reforma de edifício)
  → Objeto: supressão pode ser acima de 25% com acordo mútuo
  → Prazo: renovação por interesse público + manutenção do equilíbrio

RECEBIMENTO DO OBJETO (NLLC arts. 140-146):
  → Provisório: no ato da entrega / execução
  → Definitivo: após verificação de conformidade (prazo de vistoria: 30 dias regra)
  → Recusa: prazo para o contratado sanar vícios (mínimo 3 dias)

NOTA DE EMPENHO E LIQUIDAÇÃO:
  → Empenho: reserva da dotação orçamentária (antes da contratação)
  → Liquidação: conferência e atesto da NF (fiscal do contrato)
  → Pagamento: até 30 dias da liquidação (NLLC art. 141)`}</Flow>
      </Sec>

      <Sec title="Checklist Licitações" icon={<ListChecks size={16} />}>
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
