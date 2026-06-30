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

const CHK_KEY = "guia_consumidor_chk";
const ITEMS = [
  "Identificar se é vício (produto/serviço) ou fato (acidente de consumo)",
  "Calcular prazo decadencial ou prescricional correto",
  "Verificar responsabilidade solidária: fabricante, importador, vendedor",
  "Reunir documentos: nota fiscal, contrato, registros de atendimento",
  "Protocolar reclamação no Consumidor.gov.br (gera prova de tentativa)",
  "Verificar negativação indevida: checar cadastros SPC/Serasa/SCR",
  "Analisar cláusulas abusivas no contrato (CDC art. 51)",
  "Verificar direito de arrependimento (compra fora do estabelecimento — 7 dias)",
  "Verificar superendividamento: comprometimento acima de 30% da renda",
  "Calcular dano moral com base em parâmetros STJ por tipo de caso",
];

export default function GuiaConsumidor() {
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
      <h2 className="text-xl font-bold text-teal-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito do Consumidor
      </h2>

      <Sec title="Base Legal" icon={<Scale size={16} />} open>
        <Tab
          headers={["Norma", "Tema"]}
          rows={[
            [
              "CF/88 art. 5º XXXII e art. 170 V",
              "Proteção do consumidor como direito fundamental e princípio da ordem econômica",
            ],
            [
              "Lei 8.078/90 (CDC)",
              "Código de Defesa do Consumidor — norma principal",
            ],
            [
              "Lei 14.181/2021",
              "Superendividamento — inclusão dos arts. 54-A a 54-G no CDC",
            ],
            ["Lei 12.965/14 (Marco Civil)", "Proteção do consumidor digital"],
            ["Lei 13.709/18 (LGPD)", "Dados pessoais do consumidor"],
            [
              "Decreto 2.181/97",
              "PROCON — organização do Sistema Nacional de Defesa do Consumidor",
            ],
            ["Lei 9.099/95", "JECrim / JEC — causas até 40 SMs sem advogado"],
            ["Resolução ANAC 400/16", "Direitos do passageiro aéreo"],
            ["RDC ANVISA 222/18", "Direitos do paciente em serviços de saúde"],
          ]}
        />
      </Sec>

      <Sec title="Prazos — Decadência e Prescrição" icon={<Clock size={16} />}>
        <Tab
          headers={["Situação", "Prazo", "Tipo", "Base"]}
          rows={[
            [
              "Vício de produto/serviço não durável",
              "30 dias",
              "Decadência",
              "CDC art. 26 I",
            ],
            [
              "Vício de produto/serviço durável",
              "90 dias",
              "Decadência",
              "CDC art. 26 II",
            ],
            [
              "Fato do produto/serviço (acidente de consumo)",
              "5 anos",
              "Prescrição",
              "CDC art. 27",
            ],
            [
              "Cobrança indevida — devolução em dobro",
              "3 anos",
              "Prescrição",
              "CC art. 206 §3º IV c/c CDC",
            ],
            [
              "Dano moral por negativação indevida",
              "3 anos",
              "Prescrição",
              "CC art. 206 §3º V",
            ],
            [
              "Arrependimento (compra fora do estabelecimento)",
              "7 dias",
              "Direito potestativo",
              "CDC art. 49",
            ],
            [
              "Garantia legal produto durável",
              "90 dias após recebimento",
              "Garantia",
              "CDC art. 26 II",
            ],
            [
              "Garantia contratual adicional (varia por contrato)",
              "Conforme contrato",
              "Contratual",
              "CDC art. 50",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Obstáculo à reclamação:</strong> o prazo decadencial é
          suspenso quando há reclamação comprovada ao fornecedor (CDC art. 26
          §2º I) até a resposta. <strong>Contagem:</strong> a partir da entrega
          do produto ou do término da execução do serviço.
        </p>
      </Sec>

      <Sec
        title="Vício vs. Fato do Produto/Serviço"
        icon={<AlertTriangle size={16} />}
      >
        <Flow>{`VÍCIO (CDC arts. 18-25):
  → Produto/serviço impróprio para uso ou com diminuição de valor
  → Prazo: 30/90 dias (decadência)
  → Legitimados: fabricante, importador, distribuidor, comerciante (solidariedade)
  → Opções do consumidor (CDC art. 18 §1º):
     a) Substituição do produto
     b) Restituição imediata do valor pago + perdas e danos
     c) Abatimento proporcional do preço
  → Prazo do fornecedor para sanar: 30 dias (art. 18 caput)

FATO DO PRODUTO/SERVIÇO — ACIDENTE DE CONSUMO (CDC arts. 12-17):
  → Dano à saúde, segurança ou patrimônio do consumidor
  → Prazo: 5 anos (prescrição)
  → Responsabilidade OBJETIVA: sem necessidade de prova de culpa
  → Excludentes (CDC art. 12 §3º):
     a) Não colocou o produto no mercado
     b) Ausência do defeito (produto conforme)
     c) Culpa exclusiva do consumidor ou terceiro

SERVIÇO DEFEITUOSO (CDC art. 20):
  → Reexecução dos serviços sem custo adicional
  → Restituição de quantias pagas + perdas e danos
  → Abatimento proporcional do preço`}</Flow>
      </Sec>

      <Sec title="Teses e Direitos Principais" icon={<Scale size={16} />}>
        <Tab
          headers={["Situação", "Tese / Direito", "Base"]}
          rows={[
            [
              "Negativação indevida",
              "Dano moral presumido (in re ipsa) — Súm. 388 STJ",
              "STJ Súm. 388",
            ],
            [
              "Cobrança por dívida paga",
              "Devolução em dobro + dano moral",
              "CDC art. 42 parágrafo único",
            ],
            [
              "Serviço não prestado cobrado",
              "Devolução em dobro + juros + dano moral",
              "CDC art. 42 parágrafo único",
            ],
            [
              "Plano de saúde — negativa de cobertura",
              "Cobertura compulsória + dano moral",
              "ANS rol + CDC art. 51 IV",
            ],
            [
              "Produto com vício oculto",
              "Prazo conta da descoberta do vício",
              "CDC art. 26 §3º",
            ],
            [
              "Publicidade enganosa / abusiva",
              "Responsabilidade civil objetiva",
              "CDC arts. 36-38",
            ],
            [
              "Cláusula abusiva em contrato",
              "Nulidade de pleno direito",
              "CDC art. 51",
            ],
            [
              "Recusa de atendimento pelo plano",
              "Tutela de urgência + obrigação de fazer",
              "CDC art. 84 + CPC art. 300",
            ],
          ]}
        />
      </Sec>

      <Sec
        title="Práticas Abusivas (CDC art. 39)"
        icon={<AlertTriangle size={16} />}
      >
        <Flow>{`PRÁTICAS ABUSIVAS MAIS COMUNS:
  • Condicionar venda de produto à aquisição de outro (venda casada) — art. 39 I
  • Recusar atender demanda dentro do estoque disponível — art. 39 II
  • Enviar produto não solicitado — art. 39 III (considera-se amostra grátis)
  • Prevalecer-se da fraqueza/ignorância do consumidor — art. 39 IV
  • Exigir vantagem manifestamente excessiva — art. 39 V
  • Executar serviços sem orçamento prévio aprovado — art. 39 VI
  • Repassar informação depreciativa sobre consumidor — art. 39 VII
  • Colocar no mercado produto com riscos imprevisíveis — art. 39 VIII

CLÁUSULAS ABUSIVAS (CDC art. 51):
  • Limitar responsabilidade por dano à vida ou saúde — inciso I
  • Proibir devolução de quantia paga — inciso II
  • Transferir responsabilidade a terceiro — inciso III
  • Estabelecer obrigações iníquas que causem desvantagem excessiva — inciso IV
  • Cláusula surpresa (contratos de adesão) — art. 54 §4º`}</Flow>
      </Sec>

      <Sec title="Direitos Digitais e E-commerce" icon={<FileText size={16} />}>
        <Tab
          headers={["Direito", "Prazo / Regra", "Base"]}
          rows={[
            [
              "Arrependimento em compra online",
              "7 dias do recebimento do produto",
              "CDC art. 49",
            ],
            [
              "Devolução integral incluindo frete",
              "Junto com o arrependimento",
              "CDC art. 49 parágrafo único",
            ],
            [
              "Produto entregue com atraso",
              "Indenização por danos + opção de cancelamento",
              "CDC art. 35",
            ],
            [
              "Golpe do PIX via marketplace",
              "Responsabilidade solidária da plataforma",
              "CDC art. 14 + Súm. 479 STJ",
            ],
            [
              "Vazamento de dados pessoais",
              "Indenização + notificação ANPD",
              "LGPD art. 48 + CDC art. 14",
            ],
            [
              "Cancelamento de serviço digital",
              "Multa ≤ 2% do valor total",
              "CDC art. 52 §1º",
            ],
            [
              "Voo cancelado / overbooking",
              "Reacomodação, reembolso ou embarque próximo voo",
              "ANAC Res. 400/16 art. 21",
            ],
            [
              "Extravio de bagagem (voo doméstico)",
              "Indenização até R$ 1.350 ou dano provado",
              "ANAC Res. 400/16 art. 28",
            ],
          ]}
        />
      </Sec>

      <Sec
        title="Superendividamento — Lei 14.181/2021"
        icon={<Scale size={16} />}
      >
        <Flow>{`DEFINIÇÃO (CDC art. 54-A):
  → Comprometimento total da renda para pagar dívidas de consumo
  → Sem possibilidade de pagar o mínimo existencial (salário mínimo)
  → Exclui: dívidas de luxo, fraude, pessoa jurídica

DIREITOS DO SUPERENDIVIDADO:
  1. Conciliação coletiva com todos os credores (CDC art. 104-A)
     → Audiência com todos os credores convocados pelo juiz
     → Plano de pagamento em até 5 anos
  2. Manutenção do mínimo existencial irredutível (1 SM/mês)
  3. Suspensão de ações de cobrança durante a conciliação
  4. Renegociação extrajudicial voluntária (CDC art. 54-D)

PROIBIÇÕES AOS FORNECEDORES (CDC art. 54-C):
  → Assédio ou pressão para contratação de crédito
  → Publicidade enganosa sobre crédito consignado
  → Dificultar exercício do direito de arrependimento

PROCESSO JUDICIAL (CDC art. 104-A):
  → Distribuído ao JEC ou Vara Cível
  → Credores citados para audiência de conciliação
  → Sem acordo: juiz estabelece plano compulsório`}</Flow>
      </Sec>

      <Sec title="Checklist Consumidor" icon={<ListChecks size={16} />}>
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
