// ── src/components/GuiaBancario.tsx ──────────────────────────────────────────
// Guia Operacional de Direito Bancário (De Paula Teixeira). Referência interna
// em accordions + checklist interativo. O mesmo conteúdo está no RAG, então o
// Assistente/Motor de Teses também o usa. Tudo exige revisão do advogado.
import { useEffect, useState } from "react";
import {
  BookOpen,
  Scale,
  Calculator,
  MessageSquareWarning,
  Gavel,
  ListChecks,
  AlertTriangle,
} from "lucide-react";

function Sec({ icon: Icon, titulo, children, aberto = false }: any) {
  return (
    <details
      open={aberto}
      className="group border border-bronze-pale rounded-lg overflow-hidden"
    >
      <summary className="flex items-center gap-2 px-4 py-2.5 cursor-pointer bg-bronze-50/40 hover:bg-bronze-50 text-sm font-medium text-navy-900 select-none">
        <Icon size={15} className="text-bronze" /> {titulo}
        <span className="ml-auto text-slate-400 group-open:rotate-180 transition-transform">
          ▾
        </span>
      </summary>
      <div className="px-4 py-3 text-xs text-slate-700 space-y-2 leading-relaxed">
        {children}
      </div>
    </details>
  );
}

function Tab({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-ink-light">
            {head.map((h) => (
              <th key={h} className="py-1 pr-3 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-bronze-50">
              {r.map((c, j) => (
                <td key={j} className="py-1 pr-3 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CHECKLIST = [
  "Identificar o produto (cartão / cheque especial / consignado / CDC / financiamento)",
  "Identificar o instrumento (contrato, CCB, nota promissória, cheque)",
  "Verificar ação em curso (execução, busca e apreensão, cumprimento)",
  "Verificar prescrição (e se já prescreveu)",
  "Verificar prazo processual (embargos / contestação — 15 dias)",
  "Obter contrato, todos os extratos e comprovantes de pagamento",
  "Calcular a taxa de juros efetivamente cobrada",
  "Comparar com a taxa média BACEN para a modalidade e período",
  "Verificar se o CET está no contrato e corresponde ao CET real",
  "Verificar cumulação de encargos vedada (Súmula 472/STJ)",
  "Verificar tarifas proibidas (Tema 958/STJ — TAC/TEC pós 30/04/2008)",
  "WhatsApp abusivo: documentar imediatamente (ata notarial)",
  "Calcular o valor do excesso cobrado (pedido de indébito)",
  "Definir foro (JEC até 40 SM; Vara Cível acima)",
  "Definir pedido de tutela urgente (suspensão de negativação / cobrança)",
];

export default function GuiaBancario() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(JSON.parse(localStorage.getItem("guia_banc_chk") || "{}"));
    } catch {}
  }, []);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem("guia_banc_chk", JSON.stringify(novo));
  };
  const feitos = Object.values(marcados).filter(Boolean).length;

  return (
    <div className="card p-4 mb-4 border-l-4 border-yellow-500">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy text-sm">
          Guia Operacional de Direito Bancário
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Referência interna (súmulas, teses, cálculos, defesas, checklist). O
        mesmo acervo alimenta o Assistente IA e o Motor de Teses. Toda aplicação
        ao caso concreto exige revisão do advogado — verificar a data e eventual
        superação da jurisprudência.
      </p>

      <div className="space-y-2">
        <Sec icon={Scale} titulo="Súmulas e fundamentos-chave" aberto>
          <p>
            IFs não se sujeitam à Lei de Usura (Lei 4.595/64 art. 4º IX).
            Abusividade = comparação com a média BACEN, não com 12% a.a.
          </p>
          <Tab
            head={["Súmula/Norma", "Conteúdo"]}
            rows={[
              [
                "382/STJ",
                "Taxa > 12% a.a. por si só não é abusiva (parâmetro = média BACEN)",
              ],
              [
                "296/STJ",
                "Juros na inadimplência = média BACEN, limitada ao contratado",
              ],
              [
                "530/STJ",
                "Taxa não identificável no contrato → aplica-se média BACEN",
              ],
              [
                "541/STJ",
                "Taxa anual > duodécuplo da mensal: válida a anual efetiva (capitalização c/ previsão)",
              ],
              [
                "472/STJ",
                "Comissão de permanência não cumula com juros moratórios, multa ou IGPM/IPCA",
              ],
              [
                "294/STJ",
                "Comissão de permanência não é potestativa, mas não cumula com correção",
              ],
              [
                "381/STJ",
                "Abusividade não pode ser reconhecida de ofício (exige provocação)",
              ],
              ["297/STJ", "CDC aplica-se às instituições financeiras"],
              [
                "CDC art. 52",
                "Obrigatoriedade do CET — ausência = vício formal grave",
              ],
              [
                "Res. 4.765/19",
                "Cheque especial: cap de 8% ao mês (desde 06.01.2020)",
              ],
            ]}
          />
        </Sec>

        <Sec icon={Scale} titulo="Teses por produto bancário">
          <p>
            <b>Cartão de crédito:</b> taxa acima da média BACEN; CET não
            informado (CDC 52); cobranças indevidas; capitalização sem previsão.
            Res. 4.549/17: após 1 ciclo no rotativo, deve oferecer parcelamento.
            Prescrição indébito 3 anos.
          </p>
          <p>
            <b>Cheque especial:</b> acima de 8%/mês após jan/2020 = ilegal →
            repetição de indébito. Antes: média BACEN.
          </p>
          <p>
            <b>Consignado:</b> desconto além da margem (30% + 5% cartão = 35%);
            tarifas/seguros não autorizados; taxa acima do teto da portaria à
            época.
          </p>
          <p>
            <b>CDC/veículos:</b> CET divergente (CDC 52); seguro prestamista sem
            livre escolha (venda casada CDC 39 I); capitalização sem previsão;
            comissão de permanência cumulada (Súmula 472). Tabela Price por si
            só ≠ anatocismo (tese controversa — usar com cautela).
          </p>
          <p>
            <b>Imobiliário:</b> SFH teto 12% a.a. (Lei 4.380/64); SFI sem teto
            (Lei 9.514/97); TR constitucional no SFH (ADPF 165 — tese de
            invalidade é alto risco); tarifas acessórias proibidas (Tema 958).
          </p>
        </Sec>

        <Sec icon={Calculator} titulo="Cálculos: CET, Price, SAC, Spread">
          <p>
            <b>CET</b> = juros + IOF + tarifas + seguros + encargos. Ex.:
            receber R$9.750 líquido (após IOF 150 + cadastro 100), pagar
            12×1.050 = 12.600 → CET ≈ 2,43% a.m. (33% a.a.) vs nominal 2,0% → se
            oculto/divergente = vício.
          </p>
          <p>
            <b>Conversão:</b> a.a. = (1+a.m.)^12 − 1 (3% a.m. → 42,58% a.a.).
            NÃO multiplicar mensal × 12 (subestima).
          </p>
          <p>
            <b>Price (SAF):</b> parcelas iguais, juros maiores. PMT = PV ×
            [i(1+i)^n]/[(1+i)^n−1]. Ex. PV 20.000, 24m, 2% → PMT ≈ R$1.057,43.
          </p>
          <p>
            <b>SAC:</b> amortização constante (PV/n), parcelas decrescentes,
            juros menores. Beneficia o devedor no longo prazo.
          </p>
          <p>
            <b>Spread:</b> taxa cobrada − CDI/SELIC. &gt; 20 p.p. acima do CDI
            sinaliza possível abusividade.
          </p>
          <p>
            <b>Indébito:</b> dobro se má-fé (CDC 42), simples sem (CC 876).
            Prescrição 3 anos de cada pagamento.
          </p>
        </Sec>

        <Sec
          icon={MessageSquareWarning}
          titulo="WhatsApp como prova / cobrança abusiva"
        >
          <p>
            <b>Autenticação (do mais fraco ao mais forte):</b> (1) print com
            nome/data/hora/conteúdo (CPC 411 I); (2) exportação .txt nativa (CPC
            422); (3) <b>ata notarial</b> (CPC 384 — fé pública, recomendada em
            casos críticos); (4) perícia digital se contestada.
          </p>
          <p>
            <b>Condutas vedadas (CDC 42 e 71):</b> mensagens fora do horário; a
            familiares/empregador; linguagem ameaçadora; em grupos; volume
            excessivo; afirmações falsas; após proibição de contato (CC 187).
            CDC 71 é tipo penal (detenção 3 meses-1 ano).
          </p>
          <p>
            <b>Danos morais TJMG (orientativos):</b> fora de horário R$3-8 mil;
            exposição a terceiros R$8-20 mil; ameaças/humilhação R$10-30 mil.
            Súmula 385 limita dano por negativação preexistente, mas não por
            assédio.
          </p>
        </Sec>

        <Sec icon={Gavel} titulo="Defesa em execução e busca e apreensão">
          <p>
            <b>Busca e apreensão (DL 911/69):</b> notificação → 5 dias p/ purgar
            mora ANTES da apreensão → liminar → apreensão → 5 dias p/ pagar o
            SALDO INTEGRAL (não só as vencidas, após Lei 10.931/04) → 15 dias p/
            contestação.
          </p>
          <p>
            <b>Defesas (contestação 15 dias):</b> notificação inválida; mora não
            comprovada; excesso de execução (juros &gt; BACEN, cumulação Súmula
            472, CET ausente, capitalização irregular); nulidade do contrato;
            quitação. Pedir suspensão da liminar (CPC 300) + recálculo pericial.
          </p>
          <p>
            <b>Exceção de pré-executividade:</b> matérias de ordem pública sem
            prova (prescrição, nulidade, pagamento — Súmula 393/STJ).
          </p>
          <p>
            <b>Embargos (CPC 914-920):</b> 15 dias da penhora; efeito suspensivo
            não automático (CPC 919); excesso de execução exige indicar o valor
            devido (art. 917 §2º).
          </p>
          <p>
            <b>Tarifas proibidas (Tema 958/STJ):</b> permitidas cadastro (1x) e
            avaliação; proibidas TAC e TEC após 30/04/2008.
          </p>
          <p>
            <b>Imóvel (Lei 9.514/97):</b> 15 dias p/ purgar; consolidação; 2
            leilões; 2º negativo → dívida extinta (art. 27 §5º). Litigar ANTES
            do leilão.
          </p>
        </Sec>

        <Sec icon={Scale} titulo="Prescrição — títulos bancários">
          <Tab
            head={["Título", "Prazo", "Base / início"]}
            rows={[
              ["CCB", "5 anos", "CC 206 §5º I — do vencimento"],
              [
                "Cheque (execução)",
                "6 meses",
                "Lei 7.357/85 art. 59 — da apresentação",
              ],
              [
                "Nota promissória",
                "3 anos",
                "Dec 57.663/66 art. 70 — do vencimento",
              ],
              ["Contrato bancário", "5 anos", "CC 206 §5º I"],
              [
                "Repetição de indébito",
                "3 anos",
                "CC 206 §3º IV — de cada pagamento",
              ],
              ["Revisão contratual", "10 anos", "CC 205"],
            ]}
          />
          <p className="text-warn-700">
            ⚠ Verificar suspensão/interrupção (CC 197-204): renegociação,
            reconhecimento de dívida, parcelamento.
          </p>
        </Sec>

        <Sec
          icon={ListChecks}
          titulo={`Checklist do caso bancário (${feitos}/${CHECKLIST.length})`}
        >
          <div className="space-y-1.5">
            {CHECKLIST.map((item, i) => (
              <label key={i} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!marcados[i]}
                  onChange={() => toggle(i)}
                  className="mt-0.5"
                />
                <span
                  className={
                    marcados[i]
                      ? "line-through text-slate-400"
                      : "text-slate-700"
                  }
                >
                  {item}
                </span>
              </label>
            ))}
          </div>
        </Sec>
      </div>

      <p className="text-[10px] text-warn-700 mt-3 flex items-start gap-1">
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        Instrumento de trabalho interno. Jurisprudência sujeita a atualização —
        confirmar a data e eventual superação antes de aplicar.
      </p>
    </div>
  );
}
