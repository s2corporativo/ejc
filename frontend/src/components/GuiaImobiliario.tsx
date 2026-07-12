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

const CHK_KEY = "guia_imobiliario_chk";
const ITEMS = [
  "Verificar matrícula do imóvel atualizada (CRI — últimos 30 dias)",
  "Checar ônus reais: hipoteca, alienação fiduciária, penhora, usufruto",
  "Verificar IPTU em dia e certidões municipais negativas",
  "Conferir habite-se e regularidade perante a prefeitura",
  "Verificar se imóvel está em área de preservação permanente (APP/ZPA)",
  "Em locação: checar vínculo de fiança / garantia / seguro-fiança",
  "Em despejo: verificar prazo de desocupação e modalidade de garantia",
  "Em usucapião: reunir provas de posse mansa e pacífica ininterrupta",
  "Verificar regularidade do condomínio (inadimplência de cotas)",
  "Em financiamento bancário: verificar taxa efetiva total (CET)",
];

export default function GuiaImobiliario() {
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
      <h2 className="text-xl font-bold text-warn-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito Imobiliário
      </h2>

      <Sec title="Base Legal + Prazos" icon={<Scale size={16} />} open>
        <Tab
          headers={["Norma", "Tema"]}
          rows={[
            [
              "CC arts. 1.196-1.510",
              "Posse, propriedade, direitos reais, usucapião",
            ],
            [
              "CC arts. 538-619",
              "Contratos de compra e venda, doação, permuta",
            ],
            ["Lei 8.245/91", "Locações urbanas residenciais e comerciais"],
            ["Lei 9.514/97", "Alienação fiduciária de bem imóvel"],
            [
              "Lei 4.591/64 + Lei 10.931/04",
              "Incorporação imobiliária, patrimônio de afetação",
            ],
            ["Lei 13.465/17", "Regularização fundiária urbana (REURB)"],
            ["Lei 6.015/73", "Registros públicos — matrícula, averbação"],
            ["CF art. 183", "Usucapião especial urbana — 250m², 5 anos"],
            [
              "CC art. 1.238",
              "Usucapião extraordinária — 15 anos (10 anos com moradia)",
            ],
            [
              "CC art. 1.242",
              "Usucapião ordinária — 10 anos (5 anos com justo título)",
            ],
            ["CC art. 1.239", "Usucapião especial rural — 50 ha, 5 anos"],
            [
              "CC art. 1.240-A",
              "Usucapião familiar — 2 anos, ex-cônjuge abandonou",
            ],
          ]}
        />
      </Sec>

      <Sec title="Locação Urbana — Lei 8.245/91" icon={<FileText size={16} />}>
        <Tab
          headers={["Situação", "Regra", "Base"]}
          rows={[
            [
              "Prazo mínimo locação residencial com garantia",
              "30 meses (evita revisional)",
              "Lei 8.245/91 art. 46",
            ],
            [
              "Rescisão pelo locatário com multa",
              "Proporcional ao tempo restante (Súm. STJ 259)",
              "Lei 8.245/91 art. 4º",
            ],
            [
              "Denúncia vazia (residencial ≥ 30 meses)",
              "Notificação com 30 dias de aviso",
              "Lei 8.245/91 art. 46 §2º",
            ],
            [
              "Reajuste anual do aluguel",
              "Índice contratual (IGPM/IPCA/INCC)",
              "Lei 8.245/91 art. 18",
            ],
            [
              "Revisional do aluguel (mercado)",
              "A cada 3 anos — judicial ou amigável",
              "Lei 8.245/91 art. 19",
            ],
            [
              "Preferência do locatário na venda",
              "30 dias para exercer, notificação escrita",
              "Lei 8.245/91 art. 27",
            ],
            [
              "Garantias admitidas",
              "Caução, fiança, seguro-fiança, cessão fiduciária",
              "Lei 8.245/91 art. 37",
            ],
            [
              "Locação comercial — ação renovatória",
              "Contrato ≥ 5 anos + ramo ≥ 3 anos",
              "Lei 8.245/91 arts. 51-52",
            ],
          ]}
        />
      </Sec>

      <Sec title="Ação de Despejo" icon={<AlertTriangle size={16} />}>
        <Flow>{`MODALIDADES DE DESPEJO (Lei 8.245/91):

1. FALTA DE PAGAMENTO (art. 9º III)
   → Locatário pode purgar a mora na 1ª vez (art. 62 parágrafo único)
   → Liminar possível: depósito da dívida confessada
   → Prazo de desocupação: 15 dias após ordem judicial (art. 63 §1º)

2. TÉRMINO DO PRAZO CONTRATUAL (art. 46 — denúncia vazia)
   → Contrato ≥ 30 meses: notificação 30 dias antes do término
   → Prazo desocupação voluntária: 30 dias
   → Liminar sem caução: possível (art. 59 §1º VIII)

3. INFRAÇÃO LEGAL/CONTRATUAL (art. 9º II)
   → Uso inadequado do imóvel, sublocação não autorizada
   → Necessidade de notificação prévia

4. DEMOLIÇÃO / REFORMA URGENTE (art. 9º IV)
   → Laudo técnico comprovando necessidade
   → Indenização ao locatário pelos prejuízos (art. 35)

LIMINAR EM DESPEJO — CASOS PERMITIDOS (art. 59 §1º):
   → Falta de pagamento + ausência de garantia
   → Término do prazo + acordo escrito para desocupação
   → Morte do locatário sem sucessores no imóvel
   Garantia: caução equivalente a 3 meses de aluguel`}</Flow>
      </Sec>

      <Sec
        title="Incorporação Imobiliária e Distrato"
        icon={<FileText size={16} />}
      >
        <Tab
          headers={["Situação", "Regra", "Base"]}
          rows={[
            [
              "Atraso na entrega — tolerância máxima",
              "180 dias além do prazo contratual",
              "Lei 13.786/18 art. 43-A",
            ],
            [
              "Multa ao incorporador por atraso",
              "0,5% sobre valor contrato por mês",
              "Lei 13.786/18 art. 43-A §1º",
            ],
            [
              "Distrato pelo comprador (culpa sua)",
              "Incorporador retém 25% das parcelas pagas",
              "Lei 13.786/18 art. 67-A",
            ],
            [
              "Distrato com patrimônio de afetação",
              "Incorporador retém até 50% das parcelas pagas",
              "Lei 13.786/18 art. 67-A §5º",
            ],
            [
              "FGTS — retenção na poupança vinculada",
              "Devolução em até 30 dias do distrato",
              "Lei 13.786/18 art. 67-A §8º",
            ],
            [
              "Patrimônio de afetação — garantia",
              "Obra não entra na falência do incorporador",
              "Lei 10.931/04 art. 31-A",
            ],
            [
              "VGV — valor geral de vendas mínimo",
              "Venda mínima de 2/3 para viabilizar obra",
              "Lei 4.591/64 art. 33",
            ],
          ]}
        />
      </Sec>

      <Sec
        title="Alienação Fiduciária — Lei 9.514/97"
        icon={<Scale size={16} />}
      >
        <Flow>{`CONSOLIDAÇÃO DA PROPRIEDADE (Lei 9.514/97 art. 26):
  → Devedor inadimplente por mais de 90 dias
  → Credor notifica cartório de registro de imóveis
  → Devedor tem 15 dias para purgar a mora (pagar total vencido + encargos)
  → Sem pagamento: consolidação da propriedade em favor do credor
  → Prazo após consolidação: credor realiza leilão extrajudicial

LEILÃO EXTRAJUDICIAL:
  → 1º leilão: no mínimo o valor do imóvel (avaliação contratual)
  → 2º leilão: mínimo o valor da dívida
  → Resultado:
     Positivo: credor retém valor da dívida, entrega saldo ao devedor
     Negativo (2º leilão): dívida extinta, imóvel fica com credor

DEFESA DO DEVEDOR:
  • Questionar notificação inválida (endereço, ausência pessoal)
  • Contestar valor da avaliação do imóvel
  • Ação revisional de juros + consignação em pagamento
  • Arguir quitação parcial / pagamentos não lançados
  ⚠ ADIMPLEMENTO SUBSTANCIAL: STJ admite em casos extremos (pago > 90%)`}</Flow>
      </Sec>

      <Sec title="Usucapião" icon={<FileText size={16} />}>
        <Tab
          headers={["Modalidade", "Prazo de posse", "Requisitos", "Base"]}
          rows={[
            [
              "Extraordinária",
              "15 anos (10 com moradia/produção)",
              "Posse mansa, pacífica, ininterrupta, sem oposição",
              "CC art. 1.238",
            ],
            [
              "Ordinária",
              "10 anos (5 com moradia/produção)",
              "Justo título + boa-fé",
              "CC art. 1.242",
            ],
            [
              "Especial urbana",
              "5 anos",
              "Imóvel até 250m², moradia, sem outro imóvel",
              "CF art. 183 / CC art. 1.240",
            ],
            [
              "Especial rural",
              "5 anos",
              "Imóvel rural até 50 ha, trabalho próprio",
              "CF art. 191 / CC art. 1.239",
            ],
            [
              "Familiar (pró-família)",
              "2 anos",
              "Ex-cônjuge abandonou o lar, imóvel único",
              "CC art. 1.240-A",
            ],
            [
              "Coletiva (habitação popular)",
              "5 anos",
              "Área urbana + comunidade carente",
              "Estatuto Cidade art. 10",
            ],
            [
              "Extrajudicial (cartório)",
              "Qualquer modalidade",
              "Ata notarial + vizinhos anuentes",
              "CPC art. 1.071",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Prova:</strong> depoimento de testemunhas, contas de consumo,
          IPTU, fotos datadas, declaração de vizinhos.{" "}
          <strong>Ação judicial:</strong> vara cível; réu é o proprietário
          registral + Fazenda Pública.
        </p>
      </Sec>

      <Sec title="Checklist Imobiliário" icon={<ListChecks size={16} />}>
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
