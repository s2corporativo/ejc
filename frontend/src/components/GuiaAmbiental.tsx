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

const CHK_KEY = "guia_ambiental_chk";
const ITEMS = [
  "Verificar competência do órgão autuador (federal/estadual/municipal)",
  "Checar prazo de defesa (20 dias da ciência do AI)",
  "Requerer conversão junto com a defesa para 40% de desconto (IN IBAMA 4/2026)",
  "Analisar nulidades formais do auto de infração",
  "Verificar georreferenciamento e identificação da espécie/bioma",
  "Levantar documentação INPE/PRODES para contestar dano preexistente",
  "Verificar TCFA: CNAE e porte corretos, vencimentos 2026",
  "CAR regularizado e RL averbada (35% Cerrado)",
  "Outorga de uso de água IGAM para poços/açudes",
  "Verificar embargo: PRAD com ART/RRT protocolado",
];

export default function GuiaAmbiental() {
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
      <h2 className="text-xl font-bold text-green-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito Ambiental
      </h2>

      {/* No sistema — simulador de estratégia do auto de infração */}
      <div className="rounded-lg border border-gold-light bg-gold-50/60 p-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="text-[10px] font-semibold uppercase text-slate-400">
          No sistema
        </span>
        <span className="text-slate-600 flex-1 min-w-[200px]">
          <b className="text-navy">
            Simulador de Estratégia do Auto de Infração
          </b>{" "}
          — compare o custo de pagar à vista, converter a multa em serviços
          (−40%), defender ou prescrição, e gere o requerimento de conversão.
        </span>
        <a
          href="#ambiental-estrategia"
          onClick={(e) => {
            e.preventDefault();
            document
              .getElementById("ambiental-estrategia")
              ?.scrollIntoView({ behavior: "smooth" });
          }}
          className="text-gold-700 hover:text-gold-600 underline decoration-gold-200 underline-offset-2 font-medium"
        >
          Abrir ferramenta ↑
        </a>
      </div>

      <Sec title="Base Legal" icon={<Scale size={16} />} open>
        <Tab
          headers={["Norma", "Tema"]}
          rows={[
            [
              "CF/88 art. 225",
              "Direito ao meio ambiente ecologicamente equilibrado",
            ],
            ["Lei 6.938/81", "Política Nacional do Meio Ambiente — PNMA"],
            ["Lei 9.605/98", "Lei de Crimes Ambientais"],
            ["Dec. 6.514/2008", "Infrações administrativas ambientais"],
            ["IN IBAMA 21/2023", "Processo Administrativo Sancionador federal"],
            ["IN IBAMA 4/2026", "Conversão de multa — desconto 40%"],
            ["Lei 12.651/2012", "Código Florestal — APP, RL, CAR, PRA"],
            ["Lei 15.190/2025", "Regularização ambiental rural"],
            ["Lei 15.042/2024", "Compensação de Reserva Legal"],
            [
              "Lei 10.165/2000",
              "TCFA — Taxa de Controle e Fiscalização Ambiental",
            ],
            ["LC 140/2011", "Competência federativa ambiental"],
            ["Lei 9.873/99", "Prescrição administrativa federal"],
          ]}
        />
        <p className="text-sm text-slate-600 font-semibold mt-2">
          Órgãos MG: SEMAD · SUPRAM · IEF · FEAM · COPAM · IGAM
        </p>
      </Sec>

      <Sec
        title="Fluxo do PAS — Processo Administrativo Sancionador"
        icon={<FileText size={16} />}
      >
        <Flow>{`1. AUTUAÇÃO → Auto de Infração (AI) lavrado pelo IBAMA / IEF / FEAM
   ↓
2. DEFESA / IMPUGNAÇÃO → 20 dias da ciência (IN IBAMA 21/2023, art. 11)
   ⚠️ Requerer CONVERSÃO JUNTO COM A DEFESA → 40% de desconto (IN IBAMA 4/2026)
   ↓
3. JULGAMENTO 1ª INSTÂNCIA → DIQUA / DIBIO / IEF (sem prazo fixo legal)
   ↓
4. RECURSO HIERÁRQUICO → 20 dias da decisão de 1ª instância
   Para: Presidente do IBAMA / SEMAD-MG
   ↓
5. DECISÃO FINAL → inscrição em DAU (Dívida Ativa da União) se não pago / convertido
   ↓
6. MANDADO DE SEGURANÇA → 120 dias da decisão final (Lei 12.016/09, art. 23)`}</Flow>
      </Sec>

      <Sec title="Prazos Críticos" icon={<Clock size={16} />}>
        <Tab
          headers={["Marco", "Prazo", "Base"]}
          rows={[
            [
              "Defesa após ciência do AI",
              "20 dias",
              "IN IBAMA 21/2023, art. 11",
            ],
            [
              "Recurso após decisão 1ª instância",
              "20 dias",
              "Dec. 6.514/2008, art. 126",
            ],
            [
              "Mandado de Segurança após decisão final",
              "120 dias",
              "Lei 12.016/09, art. 23",
            ],
            [
              "Cessação de atividade após embargo",
              "Imediato",
              "Dec. 6.514/2008, art. 101",
            ],
            [
              "Prescrição intercorrente (PAS paralisado)",
              "3 anos",
              "Lei 9.873/99, art. 1°-A",
            ],
            [
              "Prescrição geral da infração administrativa",
              "5 anos",
              "Lei 9.873/99, art. 1°",
            ],
            [
              "Prescrição crime ambiental",
              "Calculado pela pena máxima",
              "CP art. 109",
            ],
          ]}
        />
      </Sec>

      <Sec title="Teses de Defesa Administrativa" icon={<Scale size={16} />}>
        <Flow>{`A) NULIDADE FORMAL
   • Incompetência territorial do agente autuador
   • Falta de descrição clara e precisa da conduta no AI
   • Ausência de fundamentação legal no AI
   • Auto lavrado mais de 60 dias após a constatação da infração
   • Notificação inválida (endereço errado, publicação sem tentativa pessoal)
   • Agente autuador sem habilitação técnica para a matéria

B) MÉRITO TÉCNICO
   • Contestar área georreferenciada (laudo técnico próprio / INCRA)
   • Identificação equivocada de espécie protegida (parecer biólogo)
   • Ausência de nexo causal entre a conduta e o dano apontado
   • Dano preexistente comprovado por imagens INPE/PRODES anteriores ao AI
   • Bioma incorreto (Cerrado / Mata Atlântica / transição)
   • Contestar laudo técnico do órgão (contralaudo com ART/RRT)
   • Embargo maior que a área efetivamente alterada

C) ATENUANTES + CONVERSÃO DE MULTA
   • IN IBAMA 4/2026: requer conversão junto com defesa → 40% de desconto
   • Atenuantes Dec. 6.514/2008 art. 14: baixo grau de instrução, reparação voluntária,
     comunicação espontânea, antecedentes favoráveis, colaboração com fiscais`}</Flow>
      </Sec>

      <Sec title="Embargo Ambiental" icon={<AlertTriangle size={16} />}>
        <Flow>{`1. CESSAR ATIVIDADE → imediato após ciência do embargo
2. PRAD — Projeto de Recuperação de Área Degradada
   → elaborar com engenheiro ambiental (ART/RRT obrigatório)
   → protocolar no órgão autuador junto com pedido de vistoria
3. RELATÓRIOS FOTOGRÁFICOS PERIÓDICOS
   → documentar evolução da recuperação (mensal)
4. TVR — Termo de Verificação de Recuperação
   → prazo típico: 30 a 90 dias para vistoria do órgão
5. LEVANTAMENTO FORMAL DO EMBARGO
   → só com TVR favorável do fiscal
   → sem TVR: crime de desobediência + novo AI`}</Flow>
      </Sec>

      <Sec title="Crimes Ambientais — Lei 9.605/98" icon={<Scale size={16} />}>
        <Tab
          headers={["Artigo", "Crime", "Pena"]}
          rows={[
            [
              "Art. 29",
              "Caçar / capturar espécie da fauna silvestre",
              "6 meses a 1 ano + multa",
            ],
            ["Art. 38", "Destruir APP — doloso", "1 a 3 anos + multa"],
            [
              "Art. 50-A",
              "Desmatamento > 1 ha em área pública",
              "2 a 4 anos + multa",
            ],
            [
              "Art. 54",
              "Poluição dolosa com dano à saúde",
              "1 a 4 anos + multa",
            ],
            [
              "Art. 60",
              "Construir / funcionar sem licença ambiental",
              "1 a 6 meses + multa",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Extinção da punibilidade:</strong> Art. 28 — suspensão
          condicional do processo disponível (pena mín. ≤ 1 ano). Reparação do
          dano pode extinguir punibilidade antes do recebimento da denúncia
          (art. 28, I).
        </p>
      </Sec>

      <Sec title="TCFA — Compliance Industrial" icon={<FileText size={16} />}>
        <Flow>{`BASE LEGAL: Lei 10.165/2000 — Taxa de Controle e Fiscalização Ambiental

VENCIMENTOS 2026:
  • 1º trimestre: 31/03/2026
  • 2º trimestre: 30/06/2026
  • 3º trimestre: 30/09/2026
  • 4º trimestre: 31/12/2026

TESES DE ISENÇÃO / REDUÇÃO:
  • CNAE incorreto → atividade não enquadrada no Anexo VIII Lei 10.165/00
  • Porte incorreto → micro/pequena empresa com base em faturamento real
  • Atividade encerrada → baixa do CNPJ ou mudança de objeto antes do fato gerador
  • Isenção não reconhecida → órgão público, entidade filantrópica, produtor rural
    pessoa física (verificar caso a caso)

NOTA: multa por inadimplência da TCFA pode ser impugnada no PAS com as mesmas teses
do auto de infração ambiental + prescrição 5 anos`}</Flow>
      </Sec>

      <Sec
        title="Regularização Ambiental Rural + Checklist"
        icon={<ListChecks size={16} />}
      >
        <Flow>{`FLUXO REGULARIZAÇÃO:
  1. CAR — Cadastro Ambiental Rural (SICAR)
     → prazo aberto pela Lei 15.190/2025 (prorrogação)
  2. RL — Reserva Legal
     → Cerrado: mínimo 35% (CF 12.651/12 art. 12, II)
     → averbação na matrícula do imóvel
  3. APP — Área de Preservação Permanente
     → açude rural: faixa mínima 15m (CF 12.651/12 art. 4°, III)
  4. Outorga IGAM
     → uso de água (poço, captação superficial, irrigação)
  5. PRA — Programa de Regularização Ambiental
     → para quem tinha passivo anterior a 22/07/2008 (marco lei)
  6. Avicultura / Suinocultura
     → DN COPAM 74/2004 (MG): licenciamento por porte
  7. SBCE — Sistema Brasileiro de Comércio de Emissões
     → implementação gradual a partir de 2027`}</Flow>
        <div className="mt-3 space-y-2">
          <p className="font-semibold text-sm text-slate-700">
            Checklist de Regularização
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
